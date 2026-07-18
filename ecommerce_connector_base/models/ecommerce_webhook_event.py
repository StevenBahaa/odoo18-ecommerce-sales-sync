import json


from odoo import models, fields, api, _
from odoo.exceptions import AccessError, UserError

class EcommerceWebhookEvent(models.Model):
    _name = 'ecommerce.webhook.event'
    _description = 'E-commerce Webhook Event'
    _order = 'create_date desc , id desc'
    _check_company_auto = True

    name = fields.Char(
        string="Event Reference",
        readonly=True,
        copy=False,
        index=True,
        default="New",
    )

    store_id = fields.Many2one(
        "ecommerce.store",
        string="Store",
        required=True,
        readonly=True,
        index=True,
        ondelete="restrict",
        check_company=True
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        readonly=True,
        index=True,
        default=lambda self: self.env.company.id,
    )

    platform =fields.Selection(
        related="store_id.platform",
        string="Platform",
        store=True,
        readonly=True,
        index=True,
    )

    event_type = fields.Char(
        string="Event Type",
        readonly=True,
        index=True,
    )

    external_event_id = fields.Char(
        string="External Event ID",
        readonly=True,
        index=True,
    )

    external_order_id = fields.Char(
        string="External Order ID",
        readonly=True,
        index=True,
    )

    raw_payload = fields.Text(
        string="Raw Payload",
        readonly=True,
    )

    headers_json = fields.Text(
        string="Request Headers (JSON)",
        readonly=True,
    )

    signature_valid = fields.Boolean(
        string="Signature Valid",
        readonly=True,
    )

    processing_status = fields.Selection(
        selection=[
            ("received", "Received"),
            ("processing", "Processing"),
            ("processed", "Processed"),
            ("failed", "Failed"),
            ("ignored", "Ignored"),
            ("duplicate", "Duplicate"),
            ("invalid_signature", "Invalid Signature"),
            ("rate_limited", "Rate Limited"),
            ("pending_review", "Pending Review"),
        ],
        string="Processing Status",
        default="received",
        readonly=True,
        index=True,
        required=True,
    )

    error_message = fields.Text(
        string="Error Message",
        readonly=True,
    )

    processed_at = fields.Datetime(
        string="Processed At",
        readonly=True,
    )

    http_status_returned = fields.Integer(
        string="HTTP Status Returned",
        readonly=True,
    )

    related_sale_order_id = fields.Many2one(
        "sale.order",
        string="Related Sale Order",
        readonly=True,
        index=True,
        check_company=True,
    )

    related_partner_id = fields.Many2one(
        "res.partner",
        string="Related Partner",
        readonly=True,
        index=True,
        check_company=True,
    )

    related_product_id = fields.Many2one(
        "product.product",
        string="Related Product",
        readonly=True,
        index=True,
        check_company=True,
    )

    related_external_order_id = fields.Many2one(
        "ecommerce.external.order",
        string="Related External Order",
        readonly=True,
        index=True,
        check_company=True,
    )

    retry_count = fields.Integer(
        string="Retry Count",
        default=0,
        readonly=True,
    )

    last_retry_at = fields.Datetime(
        string="Last Retry At",
        readonly=True,
    )

    last_retry_by_id = fields.Many2one(
        "res.users",
        string="Last Retry By",
        readonly=True,
    )

    error_history = fields.Text(
        string="Error History",
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault("name", "New")

        records = super().create(vals_list)

        for record in records:
            if record.name in ("New", "/"):
                record.name = "WH-%05d" % record.id

        return records

    def _snapshot_error(self):
        self.ensure_one()
        if not self.error_message:
            return

        timestamp = fields.Datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        requester = self.env.user.name
        snapshot = f"[{timestamp}] By {requester} (Status: {self.processing_status}):\n{self.error_message}\n"

        existing = self.error_history or ""
        self.error_history = f"{existing}\n{snapshot}".strip()

    def _ensure_retry_manager(self):
        if not self.env.user.has_group(
            "ecommerce_connector_base.group_ecommerce_connector_manager"
        ):
            raise AccessError(_("Only an E-commerce Connector Manager can retry webhook processing."))

    def action_retry_processing(self):
        self.ensure_one()
        self._ensure_retry_manager()
        if self.processing_status not in ("failed", "pending_review"):
            raise UserError(_("Only failed or pending_review events can be retried."))

        self.write({
            "retry_count": self.retry_count + 1,
            "last_retry_at": fields.Datetime.now(),
            "last_retry_by_id": self.env.user.id,
        })

        self._snapshot_error()

        store = self.store_id.sudo()
        if not store.integration_user_id:
            self.write({
                "processing_status": "pending_review",
                "error_message": _("Integration user is not configured."),
                "processed_at": fields.Datetime.now(),
            })
            return True

        if self.event_type == 'order.created':
            # Try to find external order and delegate to it
            ext_order = self.related_external_order_id
            if not ext_order:
                ext_order = self.env['ecommerce.external.order'].search([
                    ('store_id', '=', self.store_id.id),
                    ('external_order_id', '=', self.external_order_id)
                ], limit=1)

            if ext_order:
                res = ext_order.action_retry_import()
                # Synchronize status back
                new_status = 'processed' if ext_order.state == 'imported' else ('failed' if ext_order.state == 'failed' else 'pending_review')
                self.write({
                    'processing_status': new_status,
                    'related_external_order_id': ext_order.id,
                    'related_partner_id': ext_order.partner_id.id if ext_order.partner_id else False,
                    'related_sale_order_id': ext_order.sale_order_id.id if ext_order.sale_order_id else False,
                    'error_message': ext_order.error_message or False,
                })
                return res

        # Fallback to normal processing
        self.write({
            "processing_status": "received",
            "error_message": False,
        })
        self._apply_uc03_processing_gate()
        return True

    def _apply_uc03_processing_gate(self):
        now = fields.Datetime.now()

        for event in self:
            store = event.store_id.sudo()
            integration_user = store.integration_user_id

            if not integration_user:
                event.sudo().write({
                    "processing_status": "pending_review",
                    "error_message": _(
                        "Integration user is not configured. Raw webhook event "
                        "was stored, but business processing was skipped."
                    ),
                    "processed_at": now,
                })
                continue

            try:
                event.with_user(integration_user).with_company(
                    store.company_id
                )._process_business_event()
            except Exception as exc:
                event.sudo().write({
                    "processing_status": "failed",
                    "error_message": str(exc)[:1000],
                    "processed_at": fields.Datetime.now(),
                })

    def _process_business_event(self):
        self.write({
            "processing_status": "processed",
            "error_message": False,
            "processed_at": fields.Datetime.now(),
        })
