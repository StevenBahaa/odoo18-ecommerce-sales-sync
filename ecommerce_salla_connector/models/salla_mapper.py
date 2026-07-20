from datetime import datetime, timezone

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

    def _parse_authorize_payload(self, payload):
        raise UserError(
            _("Salla authorization payload handling will be implemented in UC-15.")
        )

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
