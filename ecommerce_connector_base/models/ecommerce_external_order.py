from psycopg2 import IntegrityError
from odoo import models, fields, api, _
from odoo.exceptions import AccessError, UserError
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
    retry_count = fields.Integer(
        string="Retry Count",
        default=0,
        readonly=True,
        copy=False,
    )
    last_retry_at = fields.Datetime(
        string="Last Retry At",
        readonly=True,
        copy=False,
    )
    last_retry_by_id = fields.Many2one(
        'res.users',
        string="Last Retry By",
        readonly=True,
        copy=False,
    )
    error_history = fields.Text(
        string="Error History",
        readonly=True,
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
                unmapped_lines = [l for l in self.line_ids if not l.product_id]
                errs = []
                for l in unmapped_lines:
                    name = l.external_sku or l.product_name or l.external_line_id or str(l.id)
                    errs.append(name)
                error_msg = "Unmapped lines: " + ", ".join(errs)
                self.write({
                    'state': 'pending_mapping',
                    'error_message': error_msg
                })
            else:
                if self.error_message and "Unmapped lines" in self.error_message:
                    self.write({'error_message': False})
                self.action_validate()

    def _snapshot_error(self):
        self.ensure_one()
        if not self.error_message:
            return

        timestamp = fields.Datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        requester = self.env.user.name
        snapshot = f"[{timestamp}] By {requester} (State: {self.state}):\n{self.error_message}\n"

        existing = self.error_history or ""
        self.error_history = f"{existing}\n{snapshot}".strip()

    def _ensure_retry_manager(self):
        if not self.env.user.has_group(
            "ecommerce_connector_base.group_ecommerce_connector_manager"
        ):
            raise AccessError(_("Only an E-commerce Connector Manager can retry imports."))

    def action_retry_import(self):
        self.ensure_one()
        self._ensure_retry_manager()
        if self.state not in ('pending_mapping', 'pending_review', 'failed'):
            raise UserError("Only orders in pending mapping, pending review, or failed state can be retried.")

        self.write({
            'retry_count': self.retry_count + 1,
            'last_retry_at': fields.Datetime.now(),
            'last_retry_by_id': self.env.user.id,
        })

        self._snapshot_error()

        store = self.store_id.sudo()
        integration_user = store.integration_user_id
        if not integration_user:
            self.write({
                'state': 'pending_review',
                'error_message': 'Integration user is not configured for this store.',
                'last_processed_at': fields.Datetime.now(),
            })
            return

        self.write({
            'state': 'captured',
            'error_message': False,
            'warning_message': False,
        })

        try:
            with self.env.cr.savepoint():
                order_as_integration_user = self.with_user(integration_user).with_company(
                    store.company_id
                )
                order_as_integration_user._match_or_create_customer()
                order_as_integration_user._match_products()

                if order_as_integration_user.state == 'ready':
                    order_as_integration_user.action_create_sale_order()
        except Exception as exc:
            self.write({
                'state': 'failed',
                'error_message': str(exc)[:1000],
                'last_processed_at': fields.Datetime.now(),
            })

        # UI Feedback
        if self.state == 'imported':
            return self.action_open_sale_order()
        if self.state in ('pending_mapping', 'pending_review', 'failed'):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Retry Finished',
                    'message': f'Order is still in {self.state} state. Error: {self.error_message}',
                    'type': 'warning',
                    'sticky': False,
                }
            }

    def _find_existing_sale_order(self):
        self.ensure_one()
        return self.env['sale.order'].search([
            ('ecommerce_store_id', '=', self.store_id.id),
            ('ecommerce_external_reference', '=', self.external_order_id),
        ], limit=1)

    def _link_existing_sale_order(self, sale_order, warning_message=False):
        self.ensure_one()

        vals = {
            'sale_order_id': sale_order.id,
            'state': 'imported',
            'error_message': False,
            'last_processed_at': fields.Datetime.now(),
        }
        if warning_message:
            vals['warning_message'] = warning_message

        self.write(vals)

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
        duplicate = self._find_existing_sale_order()
        if duplicate:
            self._link_existing_sale_order(
                duplicate,
                f"Existing sale order {duplicate.name} was linked to this external order.",
            )
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

    def action_create_sale_order(self):
        self.ensure_one()

        if self.sale_order_id:
            return self.action_open_sale_order()

        duplicate = self._find_existing_sale_order()
        if duplicate:
            self._link_existing_sale_order(duplicate)
            return self.action_open_sale_order()

        if self.state != 'ready':
            raise UserError("This external order must be in 'Ready' state before creating a sale order.")

        so_vals = {
            'partner_id':                    self.partner_id.id,
            'company_id':                    self.company_id.id,
            'date_order':                    self.order_date or fields.Datetime.now(),
            'origin':                        f"E-commerce: {self.external_order_reference or self.external_order_id}",
            'ecommerce_store_id':            self.store_id.id,
            'ecommerce_external_reference':  self.external_order_id,
            'ecommerce_external_order_id':   self.id,
            'ecommerce_payment_status':      self.payment_status or '',
            'ecommerce_fulfillment_status':  self.fulfillment_status or '',
        }

        if self.store_id.default_warehouse_id:
            so_vals['warehouse_id'] = self.store_id.default_warehouse_id.id

        if self.store_id.default_sales_team_id:
            so_vals['team_id'] = self.store_id.default_sales_team_id.id

        if self.store_id.default_pricelist_id:
            so_vals['pricelist_id'] = self.store_id.default_pricelist_id.id

        try:
            with self.env.cr.savepoint():
                try:
                    with self.env.cr.savepoint():
                        sale_order = self.env['sale.order'].create(so_vals)
                except IntegrityError:
                    # Concurrent creation happened
                    duplicate = self._find_existing_sale_order()
                    if duplicate:
                        self._link_existing_sale_order(duplicate)
                        return self.action_open_sale_order()
                    raise

                total_product_subtotal = sum(l.quantity * l.unit_price for l in self.line_ids)

                line_warnings = []

                for line in self.line_ids:
                    line_vals, line_warning = self._build_so_line_vals(line, sale_order, total_product_subtotal)
                    if line_warning:
                        line_warnings.append(line_warning)
                    self.env['sale.order.line'].create(line_vals)

                shipping_warning = self._create_shipping_line(sale_order)
                self._create_discount_note_line(sale_order, total_product_subtotal)

                write_vals = {
                    'sale_order_id':      sale_order.id,
                    'state':              'imported',
                    'error_message':      False,
                    'last_processed_at':  fields.Datetime.now(),
                }

                all_new_warnings = line_warnings + ([shipping_warning] if shipping_warning else [])
                if all_new_warnings:
                    existing = self.warning_message or ''
                    combined = f"{existing}\n" + "\n".join(all_new_warnings) if existing else "\n".join(all_new_warnings)
                    write_vals['warning_message'] = combined.strip()

                self.write(write_vals)

        except Exception as e:
            self.write({
                'state':              'failed',
                'error_message':      str(e),
                'last_processed_at':  fields.Datetime.now(),
            })
            return False

        return self.action_open_sale_order()

    def action_open_sale_order(self):
        self.ensure_one()
        if not self.sale_order_id:
            return
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.sale_order_id.id,
            'view_mode': 'form',
        }

    def _build_so_line_vals(self, line, sale_order, total_product_subtotal):
        strategy = self.store_id.discount_strategy
        raw_discount_pct = 0.0

        if strategy == 'line_discount':
            if line.quantity * line.unit_price > 0:
                raw_discount_pct = (line.discount_amount / (line.quantity * line.unit_price)) * 100
        elif strategy == 'proportional':
            if total_product_subtotal > 0:
                raw_discount_pct = (self.discount_amount / total_product_subtotal) * 100

        computed_discount_pct = max(0.0, min(100.0, raw_discount_pct))

        warning = None
        if raw_discount_pct < 0:
            warning = (
                f"Line {line.external_line_id or line.id}: negative discount value detected "
                f"(computed {round(raw_discount_pct, 2)}%) and treated as 0%."
            )

        line_vals = {
            'order_id':          sale_order.id,
            'product_id':        line.product_id.id,
            'name':              line.product_name,
            'product_uom_qty':   line.quantity,
            'product_uom':       line.product_id.uom_id.id,
            'price_unit':        line.unit_price,
            'discount':          computed_discount_pct,
        }
        return line_vals, warning

    def _create_shipping_line(self, sale_order):
        if self.shipping_amount <= 0:
            return None

        shipping_product = self.store_id.shipping_product_id
        if not shipping_product:
            return f"Shipping amount of {self.shipping_amount} {self.currency_id.name} was not added as a line because no shipping product is configured on the store."

        self.env['sale.order.line'].create({
            'order_id':        sale_order.id,
            'product_id':      shipping_product.id,
            'name':            shipping_product.display_name or "Shipping",
            'product_uom_qty': 1.0,
            'product_uom':     shipping_product.uom_id.id,
            'price_unit':      self.shipping_amount,
            'discount':        0.0,
        })
        return None

    def _create_discount_note_line(self, sale_order, total_product_subtotal):
        strategy = self.store_id.discount_strategy

        if strategy != 'note_only' and not (strategy == 'proportional' and total_product_subtotal == 0):
            return

        display_discount = max(0.0, self.discount_amount or 0.0)

        self.env['sale.order.line'].create({
            'order_id':        sale_order.id,
            'display_type':    'line_note',
            'name':            f"Discount of {display_discount} {self.currency_id.name} was applied by the external platform. Not reflected in line pricing.",
            'product_uom_qty': 0,
            'price_unit':      0.0,
            'product_id':      False,
        })
