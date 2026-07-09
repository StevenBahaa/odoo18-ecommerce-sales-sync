from odoo import models, fields

class EcommerceProductMapping(models.Model):
    _name = 'ecommerce.product.mapping'
    _description = 'E-commerce Product Mapping'
    _check_company_auto = True

    store_id = fields.Many2one(
        'ecommerce.store',
        string="Store",
        required=True,
        index=True,
        ondelete='cascade',
        check_company=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    external_product_id = fields.Char(
        string="External Product ID",
        required=True,
        index=True,
    )
    external_variant_id = fields.Char(
        string="External Variant ID",
        default='',
        required=True,
        index=True,
    )
    external_sku = fields.Char(
        string="External SKU",
        index=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string="Product",
        required=True,
        index=True,
        ondelete='restrict',
        check_company=True,
    )
    active = fields.Boolean(
        string="Active",
        default=True,
    )
    last_seen_at = fields.Datetime(
        string="Last Seen At",
    )

    _sql_constraints = [
        (
            'unique_store_product_variant',
            'UNIQUE(store_id, external_product_id, external_variant_id)',
            'Product mapping already exists for this store/product/variant.',
        ),
    ]
