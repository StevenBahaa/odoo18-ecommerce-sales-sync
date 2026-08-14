from datetime import datetime, timezone
import math

from odoo import fields, models, _
from odoo.exceptions import UserError


class EcommerceSallaMapper(models.AbstractModel):
    _name = "ecommerce.salla.mapper"
    _description = "Salla Payload Mapper"

    def _get_event_type(self, payload):
        if not isinstance(payload, dict):
            return False

        return (
            payload.get("event")
            or payload.get("event_type")
            or payload.get("type")
            or False
        )

    def _parse_order_payload(self, payload):
        if not isinstance(payload, dict):
            raise UserError(_("Salla order payload must be a JSON object."))

        event_type = self._get_event_type(payload)
        if event_type not in ("order.created", "order.updated"):
            raise UserError(
                _("Unsupported Salla order event type: %s") % (event_type or "unknown")
            )

        data = payload.get("data")
        if not isinstance(data, dict):
            raise UserError(_("Salla order payload is missing a valid data object."))

        external_order_id = self._extract_order_id(data)
        if not external_order_id:
            raise UserError(_("Salla order payload is missing the external order ID."))

        customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
        amounts = data.get("amounts") if isinstance(data.get("amounts"), dict) else {}

        currency_code = (
            data.get("currency")
            or self._extract_amount_currency(amounts.get("total"))
            or self._extract_amount_currency(amounts.get("shipping_cost"))
            or False
        )

        items = self._extract_items(data)

        return {
            "event_type": event_type,
            "order": {
                "external_order_id": str(external_order_id),
                "external_order_reference": (
                    data.get("reference_id")
                    or data.get("reference")
                    or data.get("order_reference")
                    or str(external_order_id)
                ),
                "customer_name": customer.get("name"),
                "customer_phone": customer.get("mobile") or customer.get("phone"),
                "customer_email": customer.get("email"),
                "external_customer_id": (
                    str(customer.get("id")) if customer.get("id") else False
                ),
                "currency_code": currency_code,
                "order_date": self._parse_datetime(
                    data.get("created_at")
                    or data.get("date")
                    or payload.get("created_at")
                ),
                "payment_status": data.get("payment_status"),
                "fulfillment_status": data.get("fulfillment_status"),
                "external_status": data.get("status"),
                "total_amount": self._extract_amount_value(amounts.get("total")),
                "shipping_amount": self._extract_amount_value(
                    amounts.get("shipping_cost")
                ),
                "discount_amount": self._extract_amount_value(amounts.get("discounts")),
                "tax_amount": self._extract_amount_value(amounts.get("tax")),
            },
            "lines": items,
        }

    def _parse_partial_update_payload(self, payload):
        if not isinstance(payload, dict):
            raise UserError(_("Salla order payload must be a JSON object."))

        event_type = self._get_event_type(payload)
        if event_type != "order.updated":
            raise UserError(
                _("Unsupported Salla order update event type: %s") % (event_type or "unknown")
            )

        data = payload.get("data")
        if not isinstance(data, dict):
            raise UserError(_("Salla order payload is missing a valid data object."))

        external_order_id = self._extract_order_id(data)
        if not external_order_id:
            raise UserError(_("Salla order payload is missing the external order ID."))

        event_time_str = data.get("updated_at") or data.get("created_at") or payload.get("created_at")
        external_event_time = self._parse_datetime(event_time_str)

        amounts = data.get("amounts") if isinstance(data.get("amounts"), dict) else {}

        currency_code = (
            data.get("currency")
            or self._extract_amount_currency(amounts.get("total"))
            or self._extract_amount_currency(amounts.get("shipping_cost"))
            or False
        )

        update_vals = {}

        def _get_strict_amount(source_dict, key):
            if not isinstance(source_dict, dict):
                return None
            if key not in source_dict:
                return None
            val = source_dict[key]
            if isinstance(val, dict):
                # If amount is explicitly null inside the dict, we still fail it below
                val = val.get("amount") if "amount" in val else val.get("value")

            if val is None:
                raise UserError(_("Malformed explicit null amount for field %s") % key)
            try:
                return float(val)
            except (TypeError, ValueError):
                raise UserError(_("Malformed amount for field %s") % key)

        def _get_strict_status(data_dict, key):
            if key not in data_dict:
                return None
            val = data_dict[key]
            if not isinstance(val, str) or not val.strip():
                raise UserError(_("Malformed status for field %s: must be a non-blank string") % key)
            return val.strip()

        payment_status = _get_strict_status(data, "payment_status")
        if payment_status is not None:
            update_vals["payment_status"] = payment_status

        fulfillment_status = _get_strict_status(data, "fulfillment_status")
        if fulfillment_status is not None:
            update_vals["fulfillment_status"] = fulfillment_status

        external_status = _get_strict_status(data, "status")
        if external_status is not None:
            update_vals["external_status"] = external_status

        tot = _get_strict_amount(amounts, "total")
        if tot is not None:
            update_vals["total_amount"] = tot

        ship = _get_strict_amount(amounts, "shipping_cost")
        if ship is not None:
            update_vals["shipping_amount"] = ship

        disc = _get_strict_amount(amounts, "discounts")
        if disc is not None:
            update_vals["discount_amount"] = disc

        tax = _get_strict_amount(amounts, "tax")
        if tax is not None:
            update_vals["tax_amount"] = tax

        return {
            "external_order_id": str(external_order_id),
            "external_event_time": external_event_time,
            "currency_code": currency_code,
            "update_vals": update_vals,
            "event_id": str(payload.get("event_id") or payload.get("uuid") or payload.get("id") or "").strip(),
        }

    def _parse_order_details_payload(self, data):
        """Parse and normalize Salla Merchant API Order Details response data.

        Returns a dictionary containing external_order_id, external_updated_at,
        currency_code, and an allowlisted update_vals dictionary.
        """
        if not isinstance(data, dict):
            raise UserError(_("Salla order details data must be a JSON object."))

        external_order_id = self._extract_order_id(data)
        if not external_order_id:
            raise UserError(_("Salla order details payload is missing the external order ID."))

        external_order_id_str = str(external_order_id).strip()
        if not external_order_id_str:
            raise UserError(_("Salla order details payload has an empty external order ID."))

        updated_at_str = data.get("updated_at") or data.get("date") or data.get("created_at")
        external_updated_at = self._parse_datetime(updated_at_str)

        amounts = data.get("amounts") if isinstance(data.get("amounts"), dict) else {}

        currency_code = (
            data.get("currency")
            or self._extract_amount_currency(amounts.get("total"))
            or self._extract_amount_currency(amounts.get("shipping_cost"))
            or self._extract_amount_currency(data.get("total"))
            or False
        )
        if isinstance(currency_code, str):
            currency_code = currency_code.strip().upper() or False

        update_vals = {}

        # Reference
        ref = data.get("reference_id") or data.get("reference") or data.get("order_reference")
        if ref is not None:
            ref_str = str(ref).strip()
            if ref_str:
                update_vals["external_order_reference"] = ref_str
        elif external_order_id_str:
            update_vals["external_order_reference"] = external_order_id_str

        # Customer
        customer = data.get("customer")
        if isinstance(customer, dict):
            # Name
            cust_name = customer.get("name")
            if isinstance(cust_name, str) and cust_name.strip():
                update_vals["customer_name"] = cust_name.strip()
            else:
                first = customer.get("first_name")
                last = customer.get("last_name")
                first_str = first.strip() if isinstance(first, str) else ""
                last_str = last.strip() if isinstance(last, str) else ""
                full_name = f"{first_str} {last_str}".strip()
                if full_name:
                    update_vals["customer_name"] = full_name

            # Phone
            raw_phone = customer.get("mobile") or customer.get("phone")
            if isinstance(raw_phone, (str, int)) and not isinstance(raw_phone, bool):
                phone_str = str(raw_phone).strip()
                if phone_str:
                    mobile_code = customer.get("mobile_code")
                    if isinstance(mobile_code, (str, int)) and not isinstance(mobile_code, bool):
                        code_str = str(mobile_code).strip().lstrip("+")
                        clean_phone = phone_str.lstrip("+")
                        if code_str and not clean_phone.startswith(code_str):
                            phone_str = f"{code_str}{clean_phone}"
                    update_vals["customer_phone"] = phone_str

            # Email
            raw_email = customer.get("email")
            if isinstance(raw_email, str) and raw_email.strip():
                update_vals["customer_email"] = raw_email.strip()

            # External Customer ID
            cust_id = customer.get("id")
            if isinstance(cust_id, (str, int)) and not isinstance(cust_id, bool):
                cust_id_str = str(cust_id).strip()
                if cust_id_str:
                    update_vals["external_customer_id"] = cust_id_str

        # Order Date
        date_str = data.get("date") or data.get("created_at")
        if date_str:
            parsed_date = self._parse_datetime(date_str)
            if parsed_date:
                update_vals["order_date"] = parsed_date

        # External Status (string slug, then string name, or top-level string)
        status_val = data.get("status")
        if isinstance(status_val, dict):
            status_slug = status_val.get("slug")
            status_name = status_val.get("name")
            if isinstance(status_slug, str) and status_slug.strip():
                update_vals["external_status"] = status_slug.strip()
            elif isinstance(status_name, str) and status_name.strip():
                update_vals["external_status"] = status_name.strip()
        elif isinstance(status_val, str) and status_val.strip():
            update_vals["external_status"] = status_val.strip()

        # Amounts (preserving explicit numeric 0.0, omitting malformed/missing amounts)
        raw_total = None
        if isinstance(amounts, dict) and "total" in amounts:
            raw_total = amounts.get("total")
        elif "total" in data:
            raw_total = data.get("total")

        if raw_total is not None:
            val = self._extract_amount_numeric(raw_total)
            if val is not None:
                update_vals["total_amount"] = val
            else:
                raise UserError(_("Invalid or malformed total amount in Salla order details."))

        raw_ship = None
        if isinstance(amounts, dict):
            if "shipping_cost" in amounts:
                raw_ship = amounts.get("shipping_cost")
            elif "shipping" in amounts:
                raw_ship = amounts.get("shipping")
        if raw_ship is None and "shipping_cost" in data:
            raw_ship = data.get("shipping_cost")

        if raw_ship is not None:
            val = self._extract_amount_numeric(raw_ship)
            if val is not None:
                update_vals["shipping_amount"] = val

        raw_disc = None
        if isinstance(amounts, dict):
            if "discounts" in amounts:
                raw_disc = amounts.get("discounts")
            elif "discount" in amounts:
                raw_disc = amounts.get("discount")
            elif "discount_amount" in amounts:
                raw_disc = amounts.get("discount_amount")
        if raw_disc is None and "discounts" in data:
            raw_disc = data.get("discounts")

        if raw_disc is not None:
            val = self._extract_amount_numeric(raw_disc)
            if val is not None:
                update_vals["discount_amount"] = val

        raw_tax = None
        if isinstance(amounts, dict):
            if "tax" in amounts:
                raw_tax = amounts.get("tax")
            elif "tax_amount" in amounts:
                raw_tax = amounts.get("tax_amount")
        if raw_tax is None and ("tax" in data or "tax_amount" in data):
            raw_tax = data.get("tax") if "tax" in data else data.get("tax_amount")

        if raw_tax is not None:
            val = self._extract_amount_numeric(raw_tax)
            if val is not None:
                update_vals["tax_amount"] = val

        return {
            "external_order_id": external_order_id_str,
            "external_updated_at": external_updated_at,
            "currency_code": currency_code,
            "update_vals": update_vals,
        }

    def _parse_authorize_payload(self, payload):
        from dateutil.relativedelta import relativedelta

        if not isinstance(payload, dict):
            raise UserError(_("Authorization payload must be a JSON object."))

        event_type = self._get_event_type(payload)
        if event_type != "app.store.authorize":
            raise UserError(_("Unsupported authorization event type: %s") % (event_type or "unknown"))

        merchant = payload.get("merchant")
        if isinstance(merchant, dict):
            merchant = merchant.get("id")
        merchant_str = str(merchant or "").strip()
        if not merchant_str:
            raise UserError(_("Missing or empty merchant identifier."))

        created_at_str = payload.get("created_at")
        if not created_at_str:
            raise UserError(_("Missing created_at timestamp."))

        authorized_at_str = self._parse_datetime(created_at_str)
        if not authorized_at_str:
            raise UserError(_("Invalid created_at timestamp format."))

        authorized_at = fields.Datetime.from_string(authorized_at_str)

        data = payload.get("data")
        if not isinstance(data, dict):
            raise UserError(_("Missing or invalid data object in payload."))

        access_token_raw = data.get("access_token")
        if not isinstance(access_token_raw, str):
            raise UserError(_("Missing or invalid access_token."))
        access_token = access_token_raw.strip()

        refresh_token_raw = data.get("refresh_token")
        if not isinstance(refresh_token_raw, str):
            raise UserError(_("Missing or invalid refresh_token."))
        refresh_token = refresh_token_raw.strip()

        if not access_token or access_token == "[REDACTED]":
            raise UserError(_("Missing or redacted access_token."))

        if not refresh_token or refresh_token == "[REDACTED]":
            raise UserError(_("Missing or redacted refresh_token."))

        scope_raw = data.get("scope")
        if not isinstance(scope_raw, str):
            raise UserError(_("Missing or invalid scope."))
        scope = scope_raw.strip()

        if "offline_access" not in scope.split():
            raise UserError(_("OAuth scope must include offline_access."))

        token_type_raw = data.get("token_type")
        if not isinstance(token_type_raw, str):
            raise UserError(_("Missing or invalid token_type."))
        token_type = token_type_raw.strip().lower()

        if token_type != "bearer":
            raise UserError(_("OAuth token_type must be bearer."))

        expires = data.get("expires")
        try:
            expires_int = int(expires)
            if expires_int <= 0:
                raise ValueError
            access_token_expires_at = datetime.fromtimestamp(expires_int, tz=timezone.utc).replace(tzinfo=None)
        except (TypeError, ValueError, OSError, OverflowError):
            raise UserError(_("Invalid expires timestamp."))

        if access_token_expires_at <= authorized_at:
            raise UserError(_("Access token expires_at must be after authorized_at."))

        if access_token_expires_at <= fields.Datetime.now():
            raise UserError(_("Access token is already expired."))

        refresh_token_issued_at = authorized_at
        refresh_token_expires_at = refresh_token_issued_at + relativedelta(months=1)

        external_event_id = str(payload.get("event_id") or payload.get("uuid") or payload.get("id") or "").strip()

        return {
            "event_type": "app.store.authorize",
            "merchant_identifier": merchant_str,
            "authorized_at": fields.Datetime.to_string(authorized_at),
            "access_token": access_token,
            "refresh_token": refresh_token,
            "access_token_expires_at": fields.Datetime.to_string(access_token_expires_at),
            "refresh_token_issued_at": fields.Datetime.to_string(refresh_token_issued_at),
            "refresh_token_expires_at": fields.Datetime.to_string(refresh_token_expires_at),
            "oauth_scope": scope,
            "oauth_token_type": token_type,
            "external_event_id": external_event_id or False,
        }

    def _extract_order_id(self, data):
        return data.get("id") or data.get("order_id") or data.get("order_reference")

    def _extract_items(self, data):
        raw_items = data.get("items") or data.get("products") or []
        if not isinstance(raw_items, list):
            return []

        lines = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue

            quantity = raw_item.get("quantity") or raw_item.get("qty") or 1.0
            unit_price = self._extract_amount_value(raw_item.get("price"))

            try:
                quantity = float(quantity)
            except (TypeError, ValueError):
                quantity = 1.0

            try:
                unit_price = float(unit_price or 0.0)
            except (TypeError, ValueError):
                unit_price = 0.0

            lines.append({
                "external_line_id": (
                    str(raw_item.get("id")) if raw_item.get("id") else False
                ),
                "external_product_id": (
                    str(raw_item.get("product_id"))
                    if raw_item.get("product_id")
                    else False
                ),
                "external_variant_id": (
                    str(raw_item.get("variant_id"))
                    if raw_item.get("variant_id")
                    else ""
                ),
                "external_sku": raw_item.get("sku") or raw_item.get("product_sku"),
                "product_name": raw_item.get("name") or _("Unnamed External Product"),
                "quantity": quantity,
                "unit_price": unit_price,
                "subtotal": quantity * unit_price,
                "discount_amount": self._extract_amount_value(
                    raw_item.get("discount")
                    or raw_item.get("discount_amount")
                    or raw_item.get("discounts")
                ),
                "tax_amount": self._extract_amount_value(
                    raw_item.get("tax") or raw_item.get("tax_amount")
                ),
                "raw_line_payload": raw_item,
            })

        return lines

    def _extract_amount_numeric(self, value):
        """Extract a numeric float from an amount field or dict.

        Returns float if valid (including explicit 0.0).
        Returns None if missing, malformed, non-numeric, or boolean.
        """
        if value is None or isinstance(value, bool):
            return None

        if isinstance(value, dict):
            raw_val = value.get("amount")
            if raw_val is None:
                raw_val = value.get("value")
            if raw_val is None:
                raw_val = value.get("total")
            if raw_val is None or isinstance(raw_val, (dict, list, bool)):
                return None
            value = raw_val

        if isinstance(value, (int, float)):
            try:
                f_val = float(value)
                if math.isnan(f_val) or math.isinf(f_val):
                    return None
                return f_val
            except (TypeError, ValueError, OverflowError):
                return None

        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return None
            try:
                f_val = float(cleaned)
                if math.isnan(f_val) or math.isinf(f_val):
                    return None
                return f_val
            except (TypeError, ValueError, OverflowError):
                return None

        return None

    def _extract_amount_value(self, value):
        if isinstance(value, dict):
            value = value.get("amount") or value.get("value") or 0.0

        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _extract_amount_currency(self, value):
        if isinstance(value, dict):
            return value.get("currency")
        return False

    def _parse_datetime(self, value):
        if not value:
            return False

        if isinstance(value, datetime):
            return fields.Datetime.to_string(value)

        try:
            normalized = str(value).replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)

            if parsed.tzinfo:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)

            return fields.Datetime.to_string(parsed)
        except Exception:
            return False
