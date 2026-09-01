import json
from datetime import timedelta, timezone

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.misc import file_path


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
            ("salla_order_cancelled", "Salla - order.cancelled"),
            ("salla_order_missing_sku", "Salla - order.created (Missing SKU)"),
            ("salla_order_multicurrency_sar", "Salla - order.created (Multi-currency SAR)"),
            ("salla_app_installed", "Salla - app.installed"),
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

        event._apply_uc03_processing_gate(processing_payload=payload)

        self.created_event_id = event.id

        return {
            "type": "ir.actions.act_window",
            "name": _("Webhook Event"),
            "res_model": "ecommerce.webhook.event",
            "view_mode": "form",
            "res_id": event.id,
            "target": "current",
        }

    @api.model
    def action_bootstrap_demo_scenario(self):
        """Idempotent UC-20 demo bootstrap. Creates one demo Salla store and walks it
        through a realistic onboarding + order-sync sequence (app install -> OAuth
        authorize -> three order.created payloads covering success, a pending-mapping
        failure, and a currency-mismatch warning), producing screenshot-ready records.
        Safe to call multiple times -- returns the existing demo store unchanged if it
        was already bootstrapped.
        """
        store = self.env['ecommerce.store'].sudo().search([
            ('store_identifier', '=', '999000111'),
        ], limit=1)
        if store:
            return store

        company = self.env.company

        warehouse = self.env['stock.warehouse'].sudo().search([
            ('company_id', '=', company.id),
        ], limit=1)

        Product = self.env['product.product'].sudo()

        shipping_product = Product.search([
            ('name', '=', 'Demo Shipping Fee'),
            ('type', '=', 'service'),
        ], limit=1)
        if not shipping_product:
            shipping_product = Product.create({
                'name': 'Demo Shipping Fee',
                'type': 'service',
                'sale_ok': False,
                'purchase_ok': False,
            })

        store = self.env['ecommerce.store'].sudo().create({
            'name': 'UC-20 Demo Salla Store',
            'platform': 'salla',
            'environment': 'mock',
            'store_identifier': '999000111',
            'company_id': company.id,
            'integration_user_id': self.env.user.id,
            'stock_sync_policy': 'none',
            'default_warehouse_id': warehouse.id if warehouse else False,
            'shipping_product_id': shipping_product.id,
        })

        demo_products = {
            'MOCK-SKU-001': 'Demo Product One',
            'MOCK-SKU-002': 'Demo Product Two',
            'MULTI-RED': 'Demo T-Shirt Red',
            'MULTI-BLUE': 'Demo T-Shirt Blue',
        }
        for sku, name in demo_products.items():
            # Get-or-create keeps the SKU lookup unambiguous when the database
            # already contains products with these codes.
            product = Product.search([('default_code', '=', sku)], limit=1)
            if not product:
                product = Product.create({
                    'name': name,
                    'default_code': sku,
                    'type': 'consu',
                    'is_storable': True,
                })

        Wizard = self.env['ecommerce.mock.payload.wizard'].sudo()

        def _run(template):
            wiz = Wizard.create({
                'store_id': store.id,
                'payload_template': template,
            })
            wiz.payload_json = wiz._get_sample_payload_content(template)
            wiz.action_create_webhook_event()
            return wiz

        # 1. App installation notice -- no business effect, demonstrates graceful
        #    handling of a recognized-but-unrouted event type.
        _run('salla_app_installed')

        # 2. OAuth authorization -- populates the store's token metadata.
        _run('salla_app_store_authorize')

        # 3. Clean success path -> fully imported sale order.
        wiz_created = _run('salla_order_created')
        created_order = wiz_created.created_event_id.related_external_order_id
        if created_order and created_order.state == 'ready':
            created_order.action_create_sale_order()

        # 4. Missing-SKU path -> parked in pending_mapping, visible in the error queue.
        _run('salla_order_missing_sku')

        # 5. Multi-currency path -> validated to 'ready' with a currency-mismatch
        #    warning automatically (via _match_products -> action_validate), deliberately
        #    left un-imported so the warning banner is visible on screenshot.
        _run('salla_order_multicurrency_sar')

        return store

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
            "salla_order_cancelled": "salla_order_cancelled.json",
            "salla_order_missing_sku": "salla_order_missing_sku.json",
            "salla_order_multicurrency_sar": "salla_order_multicurrency_sar.json",
            "salla_app_installed": "salla_app_installed.json",
            "salla_app_store_authorize": "salla_app_store_authorize.json",
        }

        filename = filename_by_template.get(template)
        if not filename:
            return "{}"

        try:
            sample_file_path = file_path(
                "ecommerce_salla_connector/sample_payloads/%s" % filename
            )
        except FileNotFoundError:
            raise UserError(_("Sample payload file was not found: %s") % filename)

        with open(sample_file_path, "r", encoding="utf-8") as payload_file:
            payload_content = payload_file.read()

        if template == "salla_app_store_authorize":
            return self._refresh_authorize_sample_timestamps(payload_content)

        return payload_content

    def _refresh_authorize_sample_timestamps(self, payload_content):
        """Keep the bundled mock authorization payload valid when it is loaded."""
        try:
            payload = json.loads(payload_content)
        except json.JSONDecodeError:
            return payload_content

        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            return payload_content

        now = fields.Datetime.now()
        payload["created_at"] = fields.Datetime.to_string(now)
        payload["data"]["expires"] = int(
            (now.replace(tzinfo=timezone.utc) + timedelta(days=14)).timestamp()
        )
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

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
