from psycopg2 import IntegrityError
from odoo import models, fields ,api,_
from ..utils.phone_utils import normalize_phone_digits


class EcommerceExternalOrder(models.Model):
    _name = 'ecommerce.external.order'
    _description = 'E-commerce External Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc , id desc'
    _check_company_auto = True


    name = fields.Char(
        string="Order Reference",
        required=True,
        readonly=True,
        copy=False,
        index=True,
        default="New",
    )

    store_id = fields.Many2one(
        "ecommerce.store",
        string="Store",
        required=True,
        index=True,
        ondelete="restrict",
        check_company=True,
        tracking=True,
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company', 
        required=True, 
        index=True,
        default=lambda self: self.env.company.id, 
        tracking=True,
    )

    platform =fields.Selection(
        related="store_id.platform",
        string="Platform",
        store=True,
        readonly=True,
        index=True,
    )

    external_order_id = fields.Char(
        string="External Order ID",
        required=True,
        index=True,
        tracking=True,
    )


    external_order_reference = fields.Char(
        string="External Order Reference",
        index=True,
        tracking=True,
    )


    customer_name = fields.Char(
        string="Customer Name",
        tracking=True,
    )
    customer_phone = fields.Char(
        string="Customer Phone",
        tracking=True,
    )
    customer_email = fields.Char(
        string="Customer Email",
        tracking=True,
    )
    normalized_customer_phone = fields.Char(
        string="Normalized Customer Phone",
        index=True,
        tracking=True,
    )
    external_customer_id = fields.Char(
        string="External Customer ID",
        index=True,
        tracking=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Matched Customer",
        index=True,
        check_company=True,
        tracking=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
        tracking=True,
    )
    order_date = fields.Datetime(
        string="External Order Date",
        tracking=True,
    )
    payment_status = fields.Char(
        string="Payment Status",
        tracking=True,
    )
    fulfillment_status = fields.Char(
        string="Fulfillment Status",
        tracking=True,
    )
    external_status = fields.Char(
        string="External Status",
        tracking=True,
    )
    total_amount = fields.Monetary(
        string="Total Amount",
        currency_field="currency_id",
        tracking=True,
    )
    shipping_amount = fields.Monetary(
        string="Shipping Amount",
        currency_field="currency_id",
        tracking=True,
    )
    discount_amount = fields.Monetary(
        string="Discount Amount",
        currency_field="currency_id",
        tracking=True,
    )
    tax_amount = fields.Monetary(
        string="Tax Amount",
        currency_field="currency_id",
        tracking=True,
    )
    raw_payload = fields.Text(
        string="Raw Payload",
        readonly=True,
        copy=False,
    )
    sale_order_id = fields.Many2one(
        "sale.order",
        string="Created Sale Order",
        readonly=True,
        copy=False,
        index=True,
        check_company=True,
        tracking=True,
    )
    line_ids = fields.One2many(
        "ecommerce.external.order.line",
        "external_order_id",
        string="External Order Lines",
        copy=True,
    )
    line_count = fields.Integer(
        string="Line Count",
        compute="_compute_line_count",
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("captured", "Captured"),
            ("pending_mapping", "Pending Mapping"),
            ("ready", "Ready"),
            ("imported", "Imported"),
            ("failed", "Failed"),
            ("cancelled", "Cancelled"),
            ("duplicate", "Duplicate"),
            ("pending_review", "Pending Review"),
        ],
        string="State",
        required=True,
        default="draft",
        index=True,
        tracking=True,
    )
    error_message = fields.Text(
        string="Error Message",
        copy=False,
    )
    warning_message = fields.Text(
        string="Warning Message",
        copy=False,
    )
    last_processed_at = fields.Datetime(
        string="Last Processed At",
        copy=False,
    )

    _sql_constraints = [
        (
            "unique_store_external_order",
            "UNIQUE(store_id, external_order_id)",
            "An external order with this ID already exists for this store.",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"].sudo()
        for vals in vals_list:
            vals.setdefault("name", "New")
            if vals["name"] in ("New", "/"):
                vals["name"] = sequence.next_by_code("ecommerce.external.order") or "New"

        return super().create(vals_list)

    @api.depends("line_ids")
    def _compute_line_count(self):
        for order in self:
            order.line_count = len(order.line_ids)

    def action_set_captured(self):
        self.write({
            "state": "captured",
            "last_processed_at": fields.Datetime.now(),
        })
        return True

    def action_set_pending_review(self):
        self.write({
            "state": "pending_review",
            "last_processed_at": fields.Datetime.now(),
        })
        return True

    def action_reset_to_draft(self):
        allowed = self.filtered(
            lambda order: order.state in ("failed", "pending_review", "pending_mapping")
        )
        allowed.write({
            "state": "draft",
            "error_message": False,
            "warning_message": False,
            "last_processed_at": fields.Datetime.now(),
        })
        return True

    def _match_or_create_customer(self):
        self.ensure_one()

        ext_cust_id = (self.external_customer_id or "").strip() or False
        email = (self.customer_email or "").strip().lower() or False
        normalized_phone = normalize_phone_digits(self.customer_phone)

        Mapping = self.env['ecommerce.customer.mapping']
        Partner = self.env['res.partner']

        mapping = Mapping
        partner_id = False
        warning = False
        
        # A. Mapping lookup
        if ext_cust_id:
            mapping = Mapping.search([
                ('store_id', '=', self.store_id.id),
                ('external_customer_id', '=', ext_cust_id)
            ], limit=1)
            if mapping:
                partner_id = mapping.partner_id
        
        # B. Email lookup
        if not partner_id and email:
            if 'email_normalized' in Partner._fields:
                partners_by_email = Partner.search([('email_normalized', '=', email)])
            else:
                partners_by_email = Partner.search([('email', '=ilike', email)])
                
            if len(partners_by_email) == 1:
                partner_id = partners_by_email[0]
            elif len(partners_by_email) > 1:
                warning = f"Ambiguous email match: {len(partners_by_email)} partners found for {email}."

        # C. Phone lookup
        if not partner_id and not warning and normalized_phone:
            domain = [
                '|',
                ('ecommerce_normalized_mobile', '=', normalized_phone),
                ('ecommerce_normalized_phone', '=', normalized_phone),
            ]
            partners_by_phone = Partner.search(domain)
            if len(partners_by_phone) == 1:
                partner_id = partners_by_phone[0]
            elif len(partners_by_phone) > 1:
                warning = f"Ambiguous phone match: {len(partners_by_phone)} partners found for {normalized_phone}."

        # Handle Ambiguity
        if warning:
            self.write({
                'warning_message': warning,
                'state': 'pending_review',
                'last_processed_at': fields.Datetime.now(),
                'normalized_customer_phone': normalized_phone,
            })
            return False

        # E. Create Partner
        if not partner_id:
            partner_name = (self.customer_name or "").strip() or "Unknown Customer"
            partner_vals = {
                'name': partner_name,
                'email': self.customer_email or False,
                'mobile': self.customer_phone or False,
                # Scope connector-created customers to the external order company; this is not the partner parent/company-contact relation.
                'company_id': self.company_id.id,
            }

            if ext_cust_id:
                try:
                    with self.env.cr.savepoint():
                        partner_id = Partner.create(partner_vals)
                        mapping = Mapping.create({
                            'store_id': self.store_id.id,
                            'company_id': self.company_id.id,
                            'external_customer_id': ext_cust_id,
                            'partner_id': partner_id.id,
                            'external_email': self.customer_email or False,
                            'external_phone': self.customer_phone or False,
                            'normalized_phone': normalized_phone,
                            'last_order_at': self.order_date or fields.Datetime.now(),
                        })
                except IntegrityError:
                    mapping = Mapping.search([
                        ('store_id', '=', self.store_id.id),
                        ('external_customer_id', '=', ext_cust_id)
                    ], limit=1)
                    if mapping:
                        partner_id = mapping.partner_id
                    else:
                        raise
            else:
                partner_id = Partner.create(partner_vals)
        else:
            # F. Mapping upsert for existing partner
            if ext_cust_id:
                order_date = self.order_date or fields.Datetime.now()
                
                if mapping:
                    if not mapping.last_order_at or mapping.last_order_at < order_date:
                        mapping.write({
                            'external_email': self.customer_email or mapping.external_email,
                            'external_phone': self.customer_phone or mapping.external_phone,
                            'normalized_phone': normalized_phone or mapping.normalized_phone,
                            'last_order_at': order_date,
                        })
                else:
                    try:
                        with self.env.cr.savepoint():
                            mapping = Mapping.create({
                                'store_id': self.store_id.id,
                                'company_id': self.company_id.id,
                                'external_customer_id': ext_cust_id,
                                'partner_id': partner_id.id,
                                'external_email': self.customer_email or False,
                                'external_phone': self.customer_phone or False,
                                'normalized_phone': normalized_phone,
                                'last_order_at': order_date,
                            })
                    except IntegrityError:
                        mapping = Mapping.search([
                            ('store_id', '=', self.store_id.id),
                            ('external_customer_id', '=', ext_cust_id),
                        ], limit=1)

                        if mapping:
                            partner_id = mapping.partner_id
                        else:
                            raise
            
        # Defensive partner guard
        if not partner_id or not partner_id.exists():
            self.write({
                'warning_message': "Matched/created partner record is missing or invalid.",
                'state': 'captured',
                'last_processed_at': fields.Datetime.now(),
                'normalized_customer_phone': normalized_phone,
            })
            return False

        # G. Link records
        self.write({
            'partner_id': partner_id.id,
            'normalized_customer_phone': normalized_phone,
        })
        return partner_id
