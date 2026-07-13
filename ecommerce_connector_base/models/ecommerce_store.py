import secrets

from odoo import api, fields, models,_
from odoo.exceptions import AccessError

class EcommerceStore(models.Model):
    _name = "ecommerce.store"
    _description = "E-commerce Store"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True
    _order = 'name'

    _SENSITIVITY_FIELDS = {
        "webhook_token",
        "webhook_secret",
        "client_id",
        "client_secret",
        "access_token",
        "refresh_token",
        "access_token_expires_at",
        "refresh_token_issued_at",
        "refresh_token_expires_at",
        "token_refresh_lock",
        "token_refresh_in_progress_at",
        "last_token_refresh_at",
        "integration_user_id",
    }

    name = fields.Char(string="Store Name", required=True, tracking=True)
    active = fields.Boolean(string="Active", default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, default=lambda self: self.env.company.id, tracking=True , index=True)

    platform = fields.Selection(
        selection=[("manual_mock", "Manual / Mock")],
        required=True,
        default="manual_mock",
        index=True,
        tracking=True,
        help="Technical platform handled by this store. Salla will be added by the Salla connector module."
        )
    
    environment = fields.Selection(
            selection= [
                ("mock", "Mock"),
                ("demo", "Demo"),
                ("production", "Production"),],
            required=True,
            default="mock",
            index=True,
            tracking=True,
            help="Environment in which the store operates."
        )
    
    store_identifier = fields.Char(
        string="Store Identifier", 
        index=True, tracking=True, 
        help="External store identifier. For Mock Mode, this can be an internal demo code."
    )

    webhook_token = fields.Char(
        string="Webhook Token", 
        readonly=True ,
        required=True ,
        copy=False, 
        index=True,
        tracking=True , 
        default=lambda self: self._generate_webhook_token(),
        help="Random URL token used to identify this store webhook endpoint.",)

    webhook_url = fields.Char(
        compute="_compute_webhook_url",
        readonly=True,
    )

    webhook_secret = fields.Char(
        copy=False,
        groups="ecommerce_connector_base.group_ecommerce_integration_manager",
        help="Webhook HMAC secret. Masked in the UI, but not database-encrypted.",
    )

    client_id = fields.Char(
        copy=False,
        groups="ecommerce_connector_base.group_ecommerce_integration_manager",
    )
    
    client_secret = fields.Char(
        copy=False,
        groups="ecommerce_connector_base.group_ecommerce_integration_manager",
        help="API client secret. Masked in the UI, but not database-encrypted.",
    )

    access_token = fields.Char(
        copy=False,
        groups="ecommerce_connector_base.group_ecommerce_integration_manager",
    )

    refresh_token = fields.Char(
        copy=False,
        groups="ecommerce_connector_base.group_ecommerce_integration_manager",
    )
    access_token_expires_at = fields.Datetime(
        groups="ecommerce_connector_base.group_ecommerce_integration_manager",
    )

    refresh_token_issued_at = fields.Datetime(
        groups="ecommerce_connector_base.group_ecommerce_integration_manager",
    )
    refresh_token_expires_at = fields.Datetime(
        groups="ecommerce_connector_base.group_ecommerce_integration_manager",
    )

    token_refresh_lock = fields.Boolean(
        default=False,
        groups="ecommerce_connector_base.group_ecommerce_integration_manager",
    )
    token_refresh_in_progress_at = fields.Datetime(
        groups="ecommerce_connector_base.group_ecommerce_integration_manager",
    )
    last_token_refresh_at = fields.Datetime(
        groups="ecommerce_connector_base.group_ecommerce_integration_manager",
    )
    last_webhook_received_at = fields.Datetime(
        readonly=True,
        copy=False,
    )

    default_warehouse_id = fields.Many2one(
        "stock.warehouse",
        check_company=True,
        tracking=True,
    )

    default_pricelist_id = fields.Many2one(
        "product.pricelist",
        check_company=True,
        tracking=True,
    )
    default_sales_team_id = fields.Many2one(
        "crm.team",
        check_company=True,
        tracking=True,
    )
    default_journal_id = fields.Many2one(
        "account.journal",
        check_company=True,
        tracking=True,
    )
    shipping_product_id = fields.Many2one(
        "product.product",
        check_company=True,
        tracking=True,
        help="Service product used later to represent shipping fees on imported sale orders.",
    )

    discount_strategy = fields.Selection(
        selection=[
            ("line_discount", "Line Discount"),
            ("proportional", "Proportional Allocation"),
            ("note_only", "Note Only"),
        ],
        default="line_discount",
        required=True,
        tracking=True,
    )
    order_import_policy = fields.Selection(
        selection=[
            ("manual_validate", "Manual Validation Before Sale Order"),
            ("auto_when_ready", "Auto Import When Ready"),
        ],
        default="manual_validate",
        required=True,
        tracking=True,
        help="Manual Validation requires a manager to click 'Create Sale Order' when the order is Ready. Auto Import When Ready is reserved for a future UC and is currently inactive — selecting it has no effect.",
    )
    stock_sync_policy = fields.Selection(
        selection=[
            ("none", "No Stock Sync"),
            ("readiness_only", "Stock Readiness Only"),
        ],
        default="readiness_only",
        required=True,
        tracking=True,
    )

    integration_user_id = fields.Many2one(
        "res.users",
        tracking=True,
        groups="ecommerce_connector_base.group_ecommerce_integration_manager",
        help=(
            "Dedicated technical user used later for business processing. "
            "If this user is not configured, webhook processing may only store raw events "
            "and must not create partners, products, or sale orders with broad sudo access."
        ),
    )

    rate_limit_window_seconds = fields.Integer(
        default=60,
        required=True,
        groups="ecommerce_connector_base.group_ecommerce_integration_manager",
    )
    rate_limit_max_events = fields.Integer(
        default=120,
        required=True,
        groups="ecommerce_connector_base.group_ecommerce_integration_manager",
    )

    _sql_constraints = [
        ( "unique_webhook_token", "unique(webhook_token)", "The webhook token must be unique across stores." ),
        ( "unique_platform_identifier_company", "UNIQUE(platform, store_identifier, company_id)", "A store with this platform and identifier already exists for this company." ),
    ]

    @api.model
    def _generate_webhook_token(self):
        return secrets.token_urlsafe(32)

    @api.depends("platform", "webhook_token")
    def _compute_webhook_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        base_url = base_url.rstrip("/")
        for store in self:
            if store.platform and store.webhook_token and base_url:
                 store.webhook_url = "%s/ecommerce/webhook/%s/%s" % (
                    base_url,
                    store.platform,
                    store.webhook_token,
                )
            else:
                store.webhook_url = False
            
    @api.model_create_multi
    def create(self, vals_list):
        self._check_sensitive_field_access(vals_list)
        return super().create(vals_list)

    def write(self, vals):
        self._check_sensitive_field_access([vals])
        return super().write(vals)
    
    def action_regenerate_webhook_token(self):
        self._ensure_integration_manager()
        for store in self:
           store.write({"webhook_token": self._generate_webhook_token()})
        return True

    def _check_sensitive_field_access(self, vals_list):
        sensitive_keys = set()
        for vals in vals_list:
            sensitive_keys.update(set(vals.keys()) & self._SENSITIVITY_FIELDS)

        if sensitive_keys:
            self._ensure_integration_manager()
    
    def _ensure_integration_manager(self):
        if not self.env.user.has_group("ecommerce_connector_base.group_ecommerce_integration_manager"):
           raise AccessError(
                _(
                    "Only an E-commerce Integration Manager can edit connector credentials, "
                    "tokens, webhook secrets, rate limits, or integration user settings."
                )
            )
