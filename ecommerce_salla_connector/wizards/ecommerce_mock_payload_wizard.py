import json

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.modules.module import get_module_resource


class EcommerceMockPayloadWizard(models.TransientModel):
    _name = "ecommerce.mock.payload.wizard"
    _description = "E-commerce Mock Payload Lab"

    store_id = fields.Many2one(
        "ecommerce.store",
        string="Store",
        required=True,
        domain=[("active", "=", True), ("environment", "=", "mock")],
        help="Mock Payload Lab only runs against stores in Mock environment.",
    )
    payload_template = fields.Selection(
        selection=[
            ("salla_order_created", "Salla - order.created"),
            ("salla_order_created_same_customer_new_order", "Salla - order.created (TC-6)"),
            ("salla_order_updated", "Salla - order.updated"),
            ("salla_app_store_authorize", "Salla - app.store.authorize"),
            ("custom_json", "Custom JSON"),
        ],
        string="Payload Template",
        required=True,
        default="salla_order_created",
    )
    payload_json = fields.Text(
        string="Payload JSON",
        required=True,
    )
    created_event_id = fields.Many2one(
        "ecommerce.webhook.event",
        string="Created Webhook Event",
        readonly=True,
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if "payload_json" in fields_list and not values.get("payload_json"):
            values["payload_json"] = self._get_sample_payload_content(
                "salla_order_created"
            )
        return values

    @api.onchange("payload_template")
    def _onchange_payload_template(self):
        if self.payload_template and self.payload_template != "custom_json":
            self.payload_json = self._get_sample_payload_content(
                self.payload_template
            )

    def action_load_sample_payload(self):
        self.ensure_one()
        if self.payload_template == "custom_json":
            raise UserError(_("Custom JSON has no sample file to load."))

        self.payload_json = self._get_sample_payload_content(
            self.payload_template
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Mock Payload Lab"),
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }

    def action_create_webhook_event(self):
        self.ensure_one()

        if self.store_id.environment != "mock":
            raise UserError(
                _("Mock Payload Lab can only run against stores in Mock environment.")
            )

        payload = self._parse_payload_json(self.payload_json)
        redacted_payload = self._redact_payload(payload)

        event = self.env["ecommerce.webhook.event"].sudo().create({
            "store_id": self.store_id.id,
            "company_id": self.store_id.company_id.id,
            "event_type": self.env["ecommerce.salla.mapper"]._get_event_type(payload) or "unknown",
            "external_event_id": self._extract_external_event_id(payload),
            "external_order_id": self._extract_external_order_id(payload),
            "raw_payload": json.dumps(
                redacted_payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            "headers_json": self._prepare_mock_headers(),
            "signature_valid": True,
            "processing_status": "received",
            "http_status_returned": 200,
        })

        event._apply_uc03_processing_gate()

        self.created_event_id = event.id

        return {
            "type": "ir.actions.act_window",
            "name": _("Webhook Event"),
            "res_model": "ecommerce.webhook.event",
            "view_mode": "form",
            "res_id": event.id,
            "target": "current",
        }

    def _parse_payload_json(self, payload_json):
        try:
            payload = json.loads(payload_json or "{}")
        except json.JSONDecodeError as exc:
            raise UserError(
                _("Invalid JSON payload. Error: %s") % str(exc)
            ) from exc

        if not isinstance(payload, dict):
            raise UserError(_("The mock payload must be a JSON object."))

        return payload

    def _get_sample_payload_content(self, template):
        filename_by_template = {
            "salla_order_created": "salla_order_created.json",
            "salla_order_created_same_customer_new_order": "salla_order_created_same_customer_new_order.json",
            "salla_order_updated": "salla_order_updated.json",

            "salla_app_store_authorize": "salla_app_store_authorize.json",
        }

        filename = filename_by_template.get(template)
        if not filename:
            return "{}"

        file_path = get_module_resource(
            "ecommerce_salla_connector",
            "sample_payloads",
            filename,
        )

        if not file_path:
            raise UserError(_("Sample payload file was not found: %s") % filename)

        with open(file_path, "r", encoding="utf-8") as payload_file:
            return payload_file.read()

    def _prepare_mock_headers(self):
        headers = {
            "X-Mock-Payload-Lab": "true",
            "Mock-Payload-Template": self.payload_template,
            "Content-Type": "application/json",
        }
        return json.dumps(
            headers,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )

    def _extract_external_event_id(self, payload):
        external_event_id = (
            payload.get("id")
            or payload.get("event_id")
            or payload.get("uuid")
        )
        return str(external_event_id) if external_event_id else False

    def _extract_external_order_id(self, payload):
        data = payload.get("data")
        if not isinstance(data, dict):
            return False

        order = data.get("order")
        if isinstance(order, dict):
            order_id = order.get("id") or order.get("order_id")
            if order_id:
                return str(order_id)

        order_id = (
            data.get("id")
            or data.get("order_id")
            or data.get("order_reference")
        )
        return str(order_id) if order_id else False

    def _redact_payload(self, value):
        sensitive_keys = {
            "access_token",
            "refresh_token",
            "client_secret",
            "webhook_secret",
            "authorization_code",
            "auth_code",
            "oauth_code",
            "token",
            "secret",
        }

        if isinstance(value, dict):
            redacted = {}
            for key, item_value in value.items():
                key_text = str(key)
                if key_text.lower() in sensitive_keys:
                    redacted[key] = "[REDACTED]"
                else:
                    redacted[key] = self._redact_payload(item_value)
            return redacted

        if isinstance(value, list):
            return [self._redact_payload(item) for item in value]

        return value