from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import email.utils
import math
import re
import zoneinfo
from dateutil.relativedelta import relativedelta

from odoo import fields, models, _
from odoo.exceptions import UserError
from odoo.addons.ecommerce_connector_base.utils.phone_utils import normalize_phone_digits


def _clean_scalar_id(value):
    """Return a non-empty stripped string for external string/integer IDs."""
    if value is None or isinstance(value, (bool, dict, list, tuple, set)):
        return False
    if isinstance(value, (str, int)):
        s = str(value).strip()
        return s if s else False
    return False


def _first_clean_scalar_id(*values):
    """Return the first valid scalar external identifier from ordered candidates."""
    for value in values:
        cleaned = _clean_scalar_id(value)
        if cleaned:
            return cleaned
    return False


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

    def _normalize_status(self, value):
        """Normalize a status representation to a clean scalar string or False.

        - A string returns its stripped value (or False if blank).
        - A mapping returns the first nonblank string: 'slug', then 'name'.
        - Numeric IDs, booleans, lists, nested dicts return False.
        - Never stringifies a container.
        """
        if value is None or isinstance(value, bool):
            return False

        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or False

        if isinstance(value, dict):
            slug = value.get("slug")
            if isinstance(slug, str) and slug.strip():
                return slug.strip()
            name = value.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
            return False

        return False

    def _parse_datetime(self, value):
        """Parse datetime from ISO scalar string, HTTP/GMT date, or Salla datetime object.

        Converts timezone-aware timestamps to UTC-naive datetimes expected by Odoo fields.Datetime.
        """
        if not value or isinstance(value, (bool, list, tuple, set)):
            return False

        if isinstance(value, datetime):
            if value.tzinfo:
                utc_dt = value.astimezone(timezone.utc).replace(tzinfo=None)
                return fields.Datetime.to_string(utc_dt)
            return fields.Datetime.to_string(value)

        # Handle Salla datetime dict: {"date": "...", "timezone": "Asia/Riyadh"}
        if isinstance(value, dict):
            raw_date = value.get("date")
            if not isinstance(raw_date, str) or not raw_date.strip():
                return False
            raw_tz = value.get("timezone")
            try:
                date_str = raw_date.strip()
                normalized = date_str.replace("Z", "+00:00")
                parsed = datetime.fromisoformat(normalized)
                if parsed.tzinfo is not None:
                    utc_dt = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                    return fields.Datetime.to_string(utc_dt)

                if raw_tz is not None:
                    if not isinstance(raw_tz, str) or not raw_tz.strip():
                        return False
                    tz_str = raw_tz.strip()
                    try:
                        tz_obj = zoneinfo.ZoneInfo(tz_str)
                        aware_dt = parsed.replace(tzinfo=tz_obj)
                    except Exception:
                        import pytz
                        tz_obj = pytz.timezone(tz_str)
                        aware_dt = tz_obj.localize(parsed)

                    utc_dt = aware_dt.astimezone(timezone.utc).replace(tzinfo=None)
                    return fields.Datetime.to_string(utc_dt)

                return fields.Datetime.to_string(parsed)
            except Exception:
                return False

        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return False
            try:
                normalized = cleaned.replace("Z", "+00:00")
                parsed = datetime.fromisoformat(normalized)
                if parsed.tzinfo:
                    parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                return fields.Datetime.to_string(parsed)
            except Exception:
                try:
                    # Normalize "GMT+0300" / "GMT+03:00" / "GMT-0500" to "+0300"
                    norm_gmt = re.sub(r'GMT\s*([+-]\d{2}):?(\d{2})', r'\1\2', cleaned)
                    parsed_http = email.utils.parsedate_to_datetime(norm_gmt)
                    if parsed_http.tzinfo:
                        parsed_http = parsed_http.astimezone(timezone.utc).replace(tzinfo=None)
                    return fields.Datetime.to_string(parsed_http)
                except Exception:
                    try:
                        import dateutil.parser
                        parsed_du = dateutil.parser.parse(cleaned)
                        if parsed_du.tzinfo:
                            parsed_du = parsed_du.astimezone(timezone.utc).replace(tzinfo=None)
                        return fields.Datetime.to_string(parsed_du)
                    except Exception:
                        return False

        return False

    def _extract_customer_name(self, customer):
        if not isinstance(customer, dict):
            return False
        full_name = customer.get("full_name")
        if isinstance(full_name, str) and full_name.strip():
            return full_name.strip()
        name = customer.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
        first = customer.get("first_name")
        last = customer.get("last_name")
        first_str = first.strip() if isinstance(first, str) else ""
        last_str = last.strip() if isinstance(last, str) else ""
        joined = f"{first_str} {last_str}".strip()
        return joined or False

    def _extract_customer_phone(self, customer):
        if not isinstance(customer, dict):
            return False
        raw_phone = customer.get("mobile") if customer.get("mobile") is not None else customer.get("phone")
        if raw_phone is None or isinstance(raw_phone, (bool, dict, list, tuple, set)):
            return False
        raw_str = str(raw_phone).strip()
        if not raw_str:
            return False

        digits = normalize_phone_digits(raw_str)
        if not digits:
            return False

        mobile_code = customer.get("mobile_code")
        if mobile_code is not None and not isinstance(mobile_code, (bool, dict, list, tuple, set)):
            code_digits = normalize_phone_digits(str(mobile_code))
            if code_digits:
                clean_local = digits.lstrip("0")
                if not digits.startswith(code_digits):
                    digits = f"{code_digits}{clean_local}"

        return digits or False

    def _extract_amount_decimal(self, value, depth=0, allow_list=False):
        """Extract a finite Decimal from an amount field with bounded unwrapping.

        Returns Decimal if valid (including Decimal('0.0')).
        Returns None if missing, malformed, non-numeric, or boolean.
        """
        if depth > 3 or value is None or isinstance(value, bool):
            return None

        if isinstance(value, (int, float)):
            try:
                if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                    return None
                d_val = Decimal(str(value))
                if not d_val.is_finite():
                    return None
                return d_val
            except (InvalidOperation, TypeError, ValueError, OverflowError):
                return None

        if isinstance(value, Decimal):
            if value.is_finite():
                return value
            return None

        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return None
            try:
                d_val = Decimal(cleaned)
                if not d_val.is_finite():
                    return None
                return d_val
            except (InvalidOperation, TypeError, ValueError):
                return None

        if isinstance(value, dict):
            for k in ("amount", "value", "total"):
                if k in value and value[k] is not None:
                    unwrapped = self._extract_amount_decimal(
                        value[k], depth + 1
                    )
                    if unwrapped is not None:
                        return unwrapped
            return None

        if isinstance(value, list):
            if not allow_list:
                return None
            if not value:
                return Decimal("0.0")
            total_sum = Decimal("0.0")
            for item in value:
                item_val = self._extract_amount_decimal(item, depth + 1)
                if item_val is None:
                    return None
                total_sum += item_val
            return total_sum

        return None

    def _extract_amount_numeric(self, value, depth=0, allow_list=False):
        d_val = self._extract_amount_decimal(
            value, depth=depth, allow_list=allow_list
        )
        return self._decimal_to_finite_float(d_val)

    def _decimal_to_finite_float(self, value):
        """Convert a finite Decimal to a finite Float for Odoo field storage."""
        if value is None:
            return None
        try:
            float_value = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return float_value if math.isfinite(float_value) else None

    def _extract_amount_value(self, value):
        val = self._extract_amount_numeric(value)
        return val if val is not None else 0.0

    def _extract_amount_currency(self, value):
        if isinstance(value, dict):
            if "currency" in value and isinstance(value["currency"], str):
                return value["currency"].strip().upper() or False
            if "amount" in value and isinstance(value["amount"], dict):
                return self._extract_amount_currency(value["amount"])
        return False

    def _extract_order_id(self, data):
        return _first_clean_scalar_id(
            data.get("id"),
            data.get("order_id"),
            data.get("order_reference"),
        )

    def _extract_items(self, data):
        raw_items = data.get("items") or data.get("products") or []
        if not isinstance(raw_items, list):
            return []

        lines = []
        for idx, raw_item in enumerate(raw_items):
            if not isinstance(raw_item, dict):
                raise UserError(_("Malformed line item at position %s.") % (idx + 1))

            product_obj = raw_item.get("product") if isinstance(raw_item.get("product"), dict) else {}
            amounts_obj = raw_item.get("amounts") if isinstance(raw_item.get("amounts"), dict) else {}

            # External Product ID: valid legacy scalar, otherwise valid live nested scalar
            external_prod_id = _clean_scalar_id(raw_item.get("product_id")) or _clean_scalar_id(product_obj.get("id"))

            # External Variant ID: valid legacy scalar, otherwise valid live nested scalar
            external_var_id = _clean_scalar_id(raw_item.get("variant_id")) or _clean_scalar_id(raw_item.get("product_sku_id")) or ""

            # SKU
            sku = _clean_scalar_id(raw_item.get("sku")) or _clean_scalar_id(raw_item.get("product_sku")) or _clean_scalar_id(product_obj.get("sku"))

            # Name
            raw_name = _clean_scalar_id(raw_item.get("name")) or _clean_scalar_id(product_obj.get("name"))
            prod_name = raw_name or _("Unnamed External Product")

            # Sanitized line label for safe error messages (no container leakage)
            line_label = _clean_scalar_id(raw_item.get("id")) or sku or f"#{idx + 1}"

            # Quantity extraction and strict positive finite check
            if "quantity" in raw_item:
                qty_raw = raw_item["quantity"]
            elif "qty" in raw_item:
                qty_raw = raw_item["qty"]
            else:
                qty_raw = None
                quantity_dec = Decimal("1.0")
            if qty_raw is not None and isinstance(
                qty_raw, (bool, dict, list, tuple, set)
            ):
                raise UserError(_("Invalid quantity for line %s: must be a positive number.") % line_label)
            if qty_raw is not None:
                try:
                    cleaned_qty = str(qty_raw).strip()
                    quantity_dec = Decimal(cleaned_qty)
                    if not quantity_dec.is_finite() or quantity_dec <= Decimal("0"):
                        raise ValueError
                except (InvalidOperation, TypeError, ValueError):
                    raise UserError(_("Invalid quantity for line %s: must be a finite positive number.") % line_label)
            elif "quantity" in raw_item or "qty" in raw_item:
                raise UserError(_("Invalid quantity for line %s: must be a finite positive number.") % line_label)
            quantity = self._decimal_to_finite_float(quantity_dec)
            if quantity is None:
                raise UserError(_("Invalid quantity for line %s: must be a finite positive number.") % line_label)

            # Discount
            raw_disc = None
            if "total_discount" in amounts_obj:
                raw_disc = amounts_obj.get("total_discount")
            elif "discount" in raw_item:
                raw_disc = raw_item.get("discount")
            elif "discount_amount" in raw_item:
                raw_disc = raw_item.get("discount_amount")
            elif "discounts" in raw_item:
                raw_disc = raw_item.get("discounts")
            disc_dec = (
                self._extract_amount_decimal(raw_disc, allow_list=True)
                if raw_disc is not None
                else Decimal("0.0")
            )
            if disc_dec is None:
                raise UserError(_("Malformed discount amount for line item %s.") % line_label)

            # Tax
            raw_tax = None
            if "tax" in amounts_obj:
                raw_tax = amounts_obj.get("tax")
            elif "tax_amount" in raw_item:
                raw_tax = raw_item.get("tax_amount")
            elif "tax" in raw_item:
                raw_tax = raw_item.get("tax")
            tax_dec = self._extract_amount_decimal(raw_tax) if raw_tax is not None else Decimal("0.0")
            if tax_dec is None:
                raise UserError(_("Malformed tax amount for line item %s.") % line_label)

            # Unit price precedence:
            # 1. legacy item.price / item.unit_price
            # 2. item.amounts.price_without_tax
            # 3. fallback: total / quantity (ONLY when no discount/tax ambiguity!)
            unit_price_dec = None
            if "price" in raw_item and raw_item["price"] is not None:
                unit_price_dec = self._extract_amount_decimal(raw_item["price"])
                if unit_price_dec is None:
                    raise UserError(_("Malformed unit price for line item %s.") % line_label)
            elif "unit_price" in raw_item and raw_item["unit_price"] is not None:
                unit_price_dec = self._extract_amount_decimal(raw_item["unit_price"])
                if unit_price_dec is None:
                    raise UserError(_("Malformed unit price for line item %s.") % line_label)

            if unit_price_dec is None and "price_without_tax" in amounts_obj and amounts_obj["price_without_tax"] is not None:
                unit_price_dec = self._extract_amount_decimal(amounts_obj["price_without_tax"])
                if unit_price_dec is None:
                    raise UserError(_("Malformed price_without_tax for line item %s.") % line_label)

            # Line total candidate from amounts or line
            raw_tot = (
                amounts_obj.get("total")
                if "total" in amounts_obj
                else (
                    amounts_obj.get("total_with_tax")
                    if "total_with_tax" in amounts_obj
                    else (
                        amounts_obj.get("sub_total")
                        if "sub_total" in amounts_obj
                        else (raw_item.get("total") if "total" in raw_item else raw_item.get("subtotal"))
                    )
                )
            )

            if unit_price_dec is None and raw_tot is not None:
                tot_dec = self._extract_amount_decimal(raw_tot)
                if tot_dec is None:
                    raise UserError(_("Malformed line total for line item %s.") % line_label)
                # Fallback only allowed without discount/tax ambiguity!
                if disc_dec == Decimal("0.0") and tax_dec == Decimal("0.0"):
                    if quantity_dec > Decimal("0"):
                        unit_price_dec = tot_dec / quantity_dec
                else:
                    raise UserError(
                        _("Cannot derive unit price from total for line item %s due to discount or tax ambiguity.")
                        % line_label
                    )

            if unit_price_dec is None:
                raise UserError(_("Missing or malformed unit price for line item %s.") % line_label)

            # Subtotal precedence: authoritative line total or quantity * unit_price
            subtotal_dec = None
            if raw_tot is not None:
                subtotal_dec = self._extract_amount_decimal(raw_tot)
                if subtotal_dec is None:
                    raise UserError(_("Malformed line total for line item %s.") % line_label)
            if subtotal_dec is None:
                subtotal_dec = quantity_dec * unit_price_dec

            unit_price = self._decimal_to_finite_float(unit_price_dec)
            subtotal = self._decimal_to_finite_float(subtotal_dec)
            discount = self._decimal_to_finite_float(disc_dec)
            tax = self._decimal_to_finite_float(tax_dec)
            if None in (unit_price, subtotal, discount, tax):
                raise UserError(_("Line item %s contains an amount outside the supported range.") % line_label)

            lines.append({
                "external_line_id": _clean_scalar_id(raw_item.get("id")),
                "external_product_id": external_prod_id,
                "external_variant_id": external_var_id,
                "external_sku": sku,
                "product_name": prod_name,
                "quantity": quantity,
                "unit_price": unit_price,
                "subtotal": subtotal,
                "discount_amount": discount,
                "tax_amount": tax,
                "raw_line_payload": raw_item,
            })

        return lines

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
            or self._extract_amount_currency(data.get("total"))
            or False
        )
        if isinstance(currency_code, str):
            currency_code = currency_code.strip().upper() or False

        items = self._extract_items(data)

        # Customer fields
        customer_name = self._extract_customer_name(customer)
        customer_phone = self._extract_customer_phone(customer)
        customer_email = customer.get("email") if isinstance(customer.get("email"), str) and customer.get("email").strip() else False
        external_customer_id = _clean_scalar_id(customer.get("id"))

        # Reference
        ref = _first_clean_scalar_id(
            data.get("reference_id"),
            data.get("reference"),
            data.get("order_reference"),
        ) or external_order_id

        # Total amount check
        raw_total = amounts.get("total") if "total" in amounts else data.get("total")
        total_amount = self._extract_amount_numeric(raw_total) if raw_total is not None else 0.0
        if total_amount is None:
            raise UserError(_("Invalid or malformed total amount in Salla order payload."))

        # Shipping check
        raw_ship = amounts.get("shipping_cost") if "shipping_cost" in amounts else (amounts.get("shipping") if "shipping" in amounts else data.get("shipping_cost"))
        shipping_amount = self._extract_amount_numeric(raw_ship) if raw_ship is not None else 0.0
        if shipping_amount is None:
            raise UserError(_("Invalid or malformed shipping amount in Salla order payload."))

        # Discounts check
        raw_disc = amounts.get("discounts") if "discounts" in amounts else (amounts.get("discount") if "discount" in amounts else (amounts.get("discount_amount") if "discount_amount" in amounts else data.get("discounts")))
        discount_amount = (
            self._extract_amount_numeric(raw_disc, allow_list=True)
            if raw_disc is not None
            else 0.0
        )
        if discount_amount is None:
            raise UserError(_("Invalid or malformed discount amount in Salla order payload."))

        # Tax check
        raw_tax = amounts.get("tax") if "tax" in amounts else (amounts.get("tax_amount") if "tax_amount" in amounts else (data.get("tax") or data.get("tax_amount")))
        tax_amount = self._extract_amount_numeric(raw_tax) if raw_tax is not None else 0.0
        if tax_amount is None:
            raise UserError(_("Invalid or malformed tax amount in Salla order payload."))

        return {
            "event_type": event_type,
            "order": {
                "external_order_id": external_order_id,
                "external_order_reference": ref,
                "customer_name": customer_name,
                "customer_phone": customer_phone,
                "customer_email": customer_email,
                "external_customer_id": external_customer_id,
                "currency_code": currency_code,
                "order_date": self._parse_datetime(
                    data.get("created_at")
                    or data.get("date")
                    or payload.get("created_at")
                ),
                "payment_status": self._normalize_status(data.get("payment_status")),
                "fulfillment_status": self._normalize_status(data.get("fulfillment_status")),
                "external_status": self._normalize_status(data.get("status")),
                "total_amount": total_amount,
                "shipping_amount": shipping_amount,
                "discount_amount": discount_amount,
                "tax_amount": tax_amount,
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
        if isinstance(currency_code, str):
            currency_code = currency_code.strip().upper() or False

        update_vals = {}

        def _get_strict_amount(source_dict, key):
            if not isinstance(source_dict, dict) or key not in source_dict:
                return None
            val = source_dict[key]
            if val is None:
                raise UserError(_("Malformed explicit null amount for field %s") % key)
            parsed = self._extract_amount_numeric(
                val, allow_list=key == "discounts"
            )
            if parsed is None:
                raise UserError(_("Malformed amount for field %s") % key)
            return parsed

        def _get_strict_status(data_dict, key):
            if key not in data_dict:
                return None
            val = data_dict[key]
            normalized = self._normalize_status(val)
            if not normalized:
                raise UserError(_("Malformed status for field %s: must be a non-blank string or valid status object") % key)
            return normalized

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
            "external_order_id": external_order_id,
            "external_event_time": external_event_time,
            "currency_code": currency_code,
            "update_vals": update_vals,
            "event_id": _first_clean_scalar_id(
                payload.get("event_id"),
                payload.get("uuid"),
                payload.get("id"),
            ) or "",
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
        ref = _first_clean_scalar_id(
            data.get("reference_id"),
            data.get("reference"),
            data.get("order_reference"),
        )
        if ref:
            update_vals["external_order_reference"] = ref
        elif external_order_id:
            update_vals["external_order_reference"] = external_order_id

        # Customer
        customer = data.get("customer")
        if isinstance(customer, dict):
            cust_name = self._extract_customer_name(customer)
            if cust_name:
                update_vals["customer_name"] = cust_name

            cust_phone = self._extract_customer_phone(customer)
            if cust_phone:
                update_vals["customer_phone"] = cust_phone

            raw_email = customer.get("email")
            if isinstance(raw_email, str) and raw_email.strip():
                update_vals["customer_email"] = raw_email.strip()

            cust_id = _clean_scalar_id(customer.get("id"))
            if cust_id:
                update_vals["external_customer_id"] = cust_id

        # Order Date
        date_str = data.get("date") or data.get("created_at")
        if date_str:
            parsed_date = self._parse_datetime(date_str)
            if parsed_date:
                update_vals["order_date"] = parsed_date

        # External Status (string slug, then string name, or top-level string)
        norm_status = self._normalize_status(data.get("status"))
        if norm_status:
            update_vals["external_status"] = norm_status

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
            val = self._extract_amount_numeric(raw_disc, allow_list=True)
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
            "external_order_id": external_order_id,
            "external_updated_at": external_updated_at,
            "currency_code": currency_code,
            "update_vals": update_vals,
        }

    def _parse_authorize_payload(self, payload):
        if not isinstance(payload, dict):
            raise UserError(_("Authorization payload must be a JSON object."))

        event_type = self._get_event_type(payload)
        if event_type != "app.store.authorize":
            raise UserError(_("Unsupported authorization event type: %s") % (event_type or "unknown"))

        merchant = payload.get("merchant")
        if isinstance(merchant, dict):
            merchant = merchant.get("id")
        merchant_str = _clean_scalar_id(merchant)
        if not merchant_str:
            raise UserError(_("Missing or empty merchant identifier."))

        created_at_raw = payload.get("created_at")
        authorized_at = self._parse_datetime(created_at_raw)
        if not authorized_at:
            raise UserError(_("Missing or invalid authorization timestamp."))
        authorized_at = fields.Datetime.from_string(authorized_at)

        data = payload.get("data")
        if not isinstance(data, dict):
            raise UserError(_("Authorization payload is missing data object."))

        access_token = data.get("access_token")
        if not isinstance(access_token, str) or not access_token.strip() or access_token.strip() == "[REDACTED]":
            raise UserError(_("Missing or redacted access_token in authorization payload."))
        access_token = access_token.strip()

        refresh_token = data.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token.strip() or refresh_token.strip() == "[REDACTED]":
            raise UserError(_("Missing or redacted refresh_token in authorization payload."))
        refresh_token = refresh_token.strip()

        scope = data.get("scope")
        if not isinstance(scope, str) or not scope.strip():
            raise UserError(_("Missing or empty OAuth scope."))
        scope = scope.strip()

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

        external_event_id = _first_clean_scalar_id(
            payload.get("event_id"),
            payload.get("uuid"),
            payload.get("id"),
        )

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
