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
    currency_mismatch = fields.Boolean(
        string="Currency Mismatch",
        compute="_compute_currency_mismatch",
        store=False,
    )
    discount_strategy = fields.Selection(
        related="store_id.discount_strategy",
        selection=[
            ("line_discount", "Line Discount"),
            ("proportional", "Proportional Allocation"),
            ("note_only", "Note Only"),
        ],
        string="Discount Strategy",
        readonly=True,
    )
    shipping_product_id = fields.Many2one(
        comodel_name="product.product",
        related="store_id.shipping_product_id",
        string="Shipping Product",
        readonly=True,
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

    @api.depends("currency_id", "company_id")
    def _compute_currency_mismatch(self):
        for order in self:
            order.currency_mismatch = (
                order.currency_id and order.company_id and 
                order.currency_id != order.company_id.currency_id
            )

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
            lambda order: order.state in ("failed", "pending_review", "pending_mapping", "ready")
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

    def _match_products(self):
        self.ensure_one()

        Mapping = self.env['ecommerce.product.mapping']
        Product = self.env['product.product']

        all_mapped = True
        
        for line in self.line_ids:
            ext_prod_id = (line.external_product_id or "").strip()
            ext_var_id = (line.external_variant_id or "").strip()
            ext_sku = (line.external_sku or "").strip()

            matched_product = False
            match_method = 'none'
            state = 'pending_mapping'
            error_message = False

            mapping = False

            # 1. Check existing mapping
            if ext_prod_id:
                mapping = Mapping.search([
                    ('store_id', '=', self.store_id.id),
                    ('external_product_id', '=', ext_prod_id),
                    ('external_variant_id', '=', ext_var_id),
                ], limit=1)

                if mapping:
                    matched_product = mapping.product_id
                    match_method = 'mapping'
                    state = 'mapped'
                    # Only update last_seen_at if our date is newer
                    event_date = self.order_date or fields.Datetime.now()
                    if not mapping.last_seen_at or mapping.last_seen_at < event_date:
                        mapping.write({'last_seen_at': event_date})

            # 2. Check SKU if no mapping
            if not matched_product and ext_sku:
                # '&' is implicit first operator; we need:
                # default_code = ext_sku AND (company_id = False OR company_id = our_company)
                domain = [
                    '&',
                    ('default_code', '=', ext_sku),
                    '|', ('company_id', '=', False), ('company_id', '=', self.company_id.id)
                ]
                products = Product.search(domain)
                
                if len(products) == 1:
                    matched_product = products[0]
                    match_method = 'sku'
                    state = 'mapped'

                    # Create mapping if external_product_id exists
                    if ext_prod_id:
                        try:
                            with self.env.cr.savepoint():
                                Mapping.create({
                                    'store_id': self.store_id.id,
                                    'company_id': self.company_id.id,
                                    'external_product_id': ext_prod_id,
                                    'external_variant_id': ext_var_id,
                                    'external_sku': ext_sku,
                                    'product_id': matched_product.id,
                                    'last_seen_at': self.order_date or fields.Datetime.now(),
                                })
                        except IntegrityError:
                            # Concurrent creation happened
                            mapping = Mapping.search([
                                ('store_id', '=', self.store_id.id),
                                ('external_product_id', '=', ext_prod_id),
                                ('external_variant_id', '=', ext_var_id),
                            ], limit=1)
                            if mapping:
                                matched_product = mapping.product_id
                                match_method = 'mapping'
                                event_date = self.order_date or fields.Datetime.now()
                                if not mapping.last_seen_at or mapping.last_seen_at < event_date:
                                    mapping.write({'last_seen_at': event_date})
                            else:
                                raise

                elif len(products) > 1:
                    match_method = 'ambiguous'
                    state = 'pending_mapping'
                    error_message = f"Ambiguous SKU match: {len(products)} Odoo products found for SKU '{ext_sku}'."
                else:
                    match_method = 'none'
                    state = 'pending_mapping'
                    error_message = f"Product SKU '{ext_sku}' not found in Odoo."

            if not matched_product and not error_message:
                error_message = "No SKU and no mapping found for this product."
            
            if not matched_product:
                all_mapped = False

            line.write({
                'product_id': matched_product.id if matched_product else False,
                'match_method': match_method,
                'state': state,
                'error_message': error_message,
            })

        # Update order state
        if not self.line_ids:
            if self.state != 'pending_review':
                self.write({
                    'state': 'pending_mapping',
                    'warning_message': 'Order has no lines. Cannot be processed into a sale order.'
                })
            return

        if self.state != 'pending_review':
            if not all_mapped:
                self.write({'state': 'pending_mapping'})
            else:
                self.action_validate()

    def action_validate(self):
        self.ensure_one()

        # Step 1 — Explicit sale_order_id link check
        if self.sale_order_id:
            self.write({
                'state': 'imported',
                'warning_message': f"This order is already linked to sale order {self.sale_order_id.name}. Re-import blocked.",
                'last_processed_at': fields.Datetime.now()
            })
            return

        # Step 2 — Database duplicate check on sale.order
        # Note: Fields ecommerce_store_id and ecommerce_external_reference are added
        # to sale.order in UC-11. We guard with a field existence check to avoid
        # crashing before UC-11 is installed.
        SaleOrder = self.env['sale.order']
        so_fields = SaleOrder._fields
        if 'ecommerce_store_id' in so_fields and 'ecommerce_external_reference' in so_fields:
            duplicate = SaleOrder.search([
                ('ecommerce_store_id', '=', self.store_id.id),
                ('ecommerce_external_reference', '=', self.external_order_id),
            ], limit=1)
            if duplicate:
                self.write({
                    'state': 'duplicate',
                    'warning_message': f"Duplicate sale order found: {duplicate.name}.",
                    'last_processed_at': fields.Datetime.now(),
                })
                return

        # Step 3 — Partner check
        if not self.partner_id:
            self.write({
                'state': 'failed',
                'error_message': "No matched customer (partner_id). Run customer matching before validating.",
                'last_processed_at': fields.Datetime.now()
            })
            return

        # Step 4 — Line mapping check
        if not self.line_ids:
            self.write({
                'state': 'pending_mapping',
                'error_message': "Order has no lines and cannot be imported.",
                'last_processed_at': fields.Datetime.now()
            })
            return

        unmapped_lines = []
        for line in self.line_ids:
            if line.state != 'mapped' or not line.product_id:
                unmapped_lines.append(line.external_line_id or str(line.id))
        
        if unmapped_lines:
            self.write({
                'state': 'pending_mapping',
                'error_message': f"Unmapped lines detected: {', '.join(unmapped_lines)}",
                'last_processed_at': fields.Datetime.now()
            })
            return

        # Step 5 — Currency warning check (non-blocking)
        warning_message = self.warning_message or ""
        if self.currency_id != self.company_id.currency_id:
            msg = f"Order currency {self.currency_id.name} differs from company currency {self.company_id.currency_id.name}. Verify pricing before importing."
            if msg not in warning_message:
                warning_message = f"{warning_message}\n{msg}".strip()

        # Step 6 — All checks passed → Ready state
        self.write({
            'state': 'ready',
            'error_message': False,
            'warning_message': warning_message if warning_message else False,
            'last_processed_at': fields.Datetime.now()
        })
