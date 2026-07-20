import json

from psycopg2 import IntegrityError

from odoo import fields, models, _


class EcommerceWebhookEvent(models.Model):
    _inherit = "ecommerce.webhook.event"

    def _process_business_event(self):
        supported_events = self.filtered(
            lambda event: event.store_id.platform in ("salla", "manual_mock")
        )
        other_events = self - supported_events

        if other_events:
            super(EcommerceWebhookEvent, other_events)._process_business_event()

        for event in supported_events:
            event._process_salla_or_mock_event()

    def _process_salla_or_mock_event(self):
        self.ensure_one()

        payload = self._load_json_payload()
        mapper = self.env["ecommerce.salla.mapper"]
        event_type = mapper._get_event_type(payload)

        if event_type == "order.created":
            self._process_salla_order_created(payload)
            return

        if event_type == "order.updated":
            self._process_salla_order_updated(payload)
            return

        self.write({
            "processing_status": "processed",
            "error_message": False,
            "processed_at": fields.Datetime.now(),
        })

    def _process_salla_order_created(self, payload):
        mapper = self.env["ecommerce.salla.mapper"]
        parsed = mapper._parse_order_payload(payload)

        order_data = parsed["order"]
        external_order_id = order_data["external_order_id"]

        existing_order = self.env["ecommerce.external.order"].search([
            ("store_id", "=", self.store_id.id),
            ("external_order_id", "=", external_order_id),
        ], limit=1)

        if existing_order:
            self.write({
                "related_external_order_id": existing_order.id,
                "related_partner_id": existing_order.partner_id.id if existing_order.partner_id else False,
                "related_sale_order_id": existing_order.sale_order_id.id if existing_order.sale_order_id else False,
                "processing_status": "duplicate",
                "error_message": _(
                    "External order already exists for this store. "
                    "Duplicate webhook payload was ignored."
                ),
                "processed_at": fields.Datetime.now(),
            })
            return

        currency, warning_message = self._resolve_currency(
            order_data.get("currency_code")
        )

        order_vals = {
            "store_id": self.store_id.id,
            "company_id": self.store_id.company_id.id,
            "external_order_id": external_order_id,
            "external_order_reference": order_data.get("external_order_reference"),
            "customer_name": order_data.get("customer_name"),
            "customer_phone": order_data.get("customer_phone"),
            "customer_email": order_data.get("customer_email"),
            "external_customer_id": order_data.get("external_customer_id"),
            "currency_id": currency.id,
            "order_date": order_data.get("order_date"),
            "payment_status": order_data.get("payment_status"),
            "fulfillment_status": order_data.get("fulfillment_status"),
            "external_status": order_data.get("external_status"),
            "total_amount": order_data.get("total_amount") or 0.0,
            "shipping_amount": order_data.get("shipping_amount") or 0.0,
            "discount_amount": order_data.get("discount_amount") or 0.0,
            "tax_amount": order_data.get("tax_amount") or 0.0,
            "raw_payload": self.raw_payload,
            "state": "captured",
            "warning_message": warning_message,
            "last_processed_at": fields.Datetime.now(),
            "line_ids": [],
        }

        for line in parsed["lines"]:
            raw_line_payload = line.pop("raw_line_payload", {})
            order_vals["line_ids"].append((0, 0, {
                "external_line_id": line.get("external_line_id"),
                "external_product_id": line.get("external_product_id"),
                "external_variant_id": line.get("external_variant_id") or "",
                "external_sku": line.get("external_sku"),
                "product_name": line.get("product_name"),
                "quantity": line.get("quantity") or 1.0,
                "unit_price": line.get("unit_price") or 0.0,
                "subtotal": line.get("subtotal") or 0.0,
                "discount_amount": line.get("discount_amount") or 0.0,
                "tax_amount": line.get("tax_amount") or 0.0,
                "match_method": "none",
                "state": "pending_mapping",
                "raw_line_payload": json.dumps(
                    raw_line_payload,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
            }))

        try:
            with self.env.cr.savepoint():
                external_order = self.env["ecommerce.external.order"].create(order_vals)
        except IntegrityError:
            existing_order = self.env["ecommerce.external.order"].search([
                ("store_id", "=", self.store_id.id),
                ("external_order_id", "=", external_order_id),
            ], limit=1)

            self.write({
                "related_external_order_id": existing_order.id if existing_order else False,
                "related_partner_id": existing_order.partner_id.id if existing_order and existing_order.partner_id else False,
                "related_sale_order_id": existing_order.sale_order_id.id if existing_order and existing_order.sale_order_id else False,
                "processing_status": "duplicate",
                "error_message": _(
                    "External order already exists for this store. "
                    "Concurrent duplicate payload was ignored."
                ),
                "processed_at": fields.Datetime.now(),
            })
            return

        partner = external_order._match_or_create_customer()
        external_order._match_products()

        status = "processed"
        error_msg = False

        if external_order.state in ("pending_mapping", "pending_review", "failed"):
            status = "pending_review" if external_order.state != "failed" else "failed"
            error_msg = external_order.error_message or external_order.warning_message

        self.write({
            "related_external_order_id": external_order.id,
            "related_partner_id": partner.id if partner else False,
            "related_sale_order_id": external_order.sale_order_id.id if external_order.sale_order_id else False,
            "processing_status": status,
            "error_message": error_msg,
            "processed_at": fields.Datetime.now(),
        })

    def _process_salla_order_updated(self, payload):
        mapper = self.env["ecommerce.salla.mapper"]
        try:
            parsed = mapper._parse_partial_update_payload(payload)
        except Exception as e:
            self.write({
                "processing_status": "pending_review",
                "error_message": str(e),
                "processed_at": fields.Datetime.now(),
            })
            return

        external_order_id = parsed["external_order_id"]
        external_event_time_str = parsed["external_event_time"]
        currency_code = parsed["currency_code"]
        update_vals = parsed["update_vals"]
        event_id = parsed["event_id"]

        if not external_event_time_str:
            self.write({
                "processing_status": "pending_review",
                "error_message": _("Update event is missing a valid timestamp."),
                "processed_at": fields.Datetime.now(),
            })
            return

        if not update_vals:
            self.write({
                "processing_status": "pending_review",
                "error_message": _("Update event contained no valid supported fields."),
                "processed_at": fields.Datetime.now(),
            })
            return

        has_amounts = any(k in update_vals for k in ("total_amount", "shipping_amount", "discount_amount", "tax_amount"))

        existing_order = self.env["ecommerce.external.order"].search([
            ("store_id", "=", self.store_id.id),
            ("external_order_id", "=", external_order_id),
        ], limit=1)

        if not existing_order:
            self.write({
                "processing_status": "pending_review",
                "error_message": _("Update received for unknown order (received before order.created?)."),
                "processed_at": fields.Datetime.now(),
            })
            return

        self.write({
            "related_external_order_id": existing_order.id,
            "related_partner_id": existing_order.partner_id.id if existing_order.partner_id else False,
            "related_sale_order_id": existing_order.sale_order_id.id if existing_order.sale_order_id else False,
        })

        if has_amounts and (not currency_code or existing_order.currency_id.name != currency_code):
            self.write({
                "processing_status": "pending_review",
                "error_message": _(
                    "Update payload currency '%s' differs from staged order currency '%s'."
                ) % (currency_code, existing_order.currency_id.name),
                "processed_at": fields.Datetime.now(),
            })
            return

        with self.env.cr.savepoint():
            self.env.cr.execute(
                "SELECT id FROM ecommerce_external_order WHERE id = %s FOR UPDATE",
                (existing_order.id,)
            )
            existing_order.invalidate_recordset(["last_external_update_at", "last_external_update_event_id"])

            incoming_time = fields.Datetime.from_string(external_event_time_str)
            watermark_time = existing_order.last_external_update_at

            if watermark_time:
                if incoming_time < watermark_time:
                    self.write({
                        "processing_status": "pending_review",
                        "error_message": _("Update is older than the last applied update."),
                        "processed_at": fields.Datetime.now(),
                    })
                    return
                if incoming_time == watermark_time:
                    if event_id and existing_order.last_external_update_event_id == event_id:
                        self.write({
                            "processing_status": "duplicate",
                            "error_message": _("Exact duplicate of the last applied update."),
                            "processed_at": fields.Datetime.now(),
                        })
                        return
                    else:
                        self.write({
                            "processing_status": "pending_review",
                            "error_message": _("Ambiguous update: same timestamp but different/missing event ID."),
                            "processed_at": fields.Datetime.now(),
                        })
                        return

            write_vals = dict(update_vals)
            write_vals["last_external_update_at"] = external_event_time_str
            write_vals["last_external_update_event_id"] = event_id
            write_vals["last_processed_at"] = fields.Datetime.now()

            existing_order.write(write_vals)

            if existing_order.sale_order_id:
                so_vals = {}
                if "payment_status" in update_vals:
                    so_vals["ecommerce_payment_status"] = update_vals["payment_status"]
                if "fulfillment_status" in update_vals:
                    so_vals["ecommerce_fulfillment_status"] = update_vals["fulfillment_status"]

                if so_vals:
                    existing_order.sale_order_id.write(so_vals)

            self.write({
                "processing_status": "processed",
                "error_message": False,
                "processed_at": fields.Datetime.now(),
            })

    def _load_json_payload(self):
        try:
            payload = json.loads(self.raw_payload or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(_("Webhook raw payload is not valid JSON: %s") % exc) from exc

        if not isinstance(payload, dict):
            raise ValueError(_("Webhook raw payload must be a JSON object."))

        return payload

    def _resolve_currency(self, currency_code):
        company_currency = self.store_id.company_id.currency_id

        if not currency_code:
            return company_currency, _("Currency code was missing. Company currency was used.")

        currency = self.env["res.currency"].with_context(active_test=False).search([
            ("name", "=", currency_code),
        ], limit=1)

        if not currency:
            return company_currency, _(
                "Currency %s was not found in Odoo. Company currency was used."
            ) % currency_code

        return currency, False
