from odoo import fields, models , api 


class EcommerceExternalOrderLine(models.Model):
    _name = "ecommerce.external.order.line"
    _description = "E-commerce External Order Line"
    _order = "external_order_id, id"
    _check_company_auto = True

    external_order_id = fields.Many2one(
        "ecommerce.external.order",
        string="External Order",
        required=True,
        index=True,
        ondelete="cascade",
        check_company=True,
    )
    store_id = fields.Many2one(
        "ecommerce.store",
        string="Store",
        related="external_order_id.store_id",
        store=True,
        readonly=True,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="external_order_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="external_order_id.currency_id",
        store=True,
        readonly=True,
    )
    external_line_id = fields.Char(
        string="External Line ID",
        index=True,
    )
    external_product_id = fields.Char(
        string="External Product ID",
        index=True,
    )
    external_variant_id = fields.Char(
        string="External Variant ID",
        index=True,
        default="",
    )
    external_sku = fields.Char(
        string="External SKU",
        index=True,
    )
    product_name = fields.Char(
        string="Product Name",
        required=True,
    )
    quantity = fields.Float(
        string="Quantity",
        required=True,
        default=1.0,
    )
    unit_price = fields.Monetary(
        string="Unit Price",
        currency_field="currency_id",
    )
    subtotal = fields.Monetary(
        string="Subtotal",
        currency_field="currency_id",
        compute="_compute_subtotal",
        store=True,
        readonly=False,
    )
    discount_amount = fields.Monetary(
        string="Discount Amount",
        currency_field="currency_id",
    )
    tax_amount = fields.Monetary(
        string="Tax Amount",
        currency_field="currency_id",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Matched Product",
        index=True,
        check_company=True,
    )
    match_method = fields.Selection(
        selection=[
            ("mapping", "Mapping"),
            ("sku", "SKU"),
            ("ambiguous", "Ambiguous SKU"),
            ("manual", "Manual"),
            ("none", "None"),
        ],
        string="Match Method",
        required=True,
        default="none",
        index=True,
    )
    state = fields.Selection(
        selection=[
            ("pending_mapping", "Pending Mapping"),
            ("mapped", "Mapped"),
            ("failed", "Failed"),
        ],
        string="State",
        required=True,
        default="pending_mapping",
        index=True,
    )
    error_message = fields.Text(
        string="Error Message",
        copy=False,
    )
    raw_line_payload = fields.Text(
        string="Raw Line Payload",
        copy=False,
    )

    @api.depends("quantity", "unit_price")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_price