from odoo import models, fields

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    ecommerce_store_id = fields.Many2one(
        'ecommerce.store',
        string="E-commerce Store",
        index=True,
        check_company=True,
        ondelete='restrict',
        copy=False,
    )
    ecommerce_external_reference = fields.Char(
        string="External Reference",
        index=True,
        copy=False,
    )
    ecommerce_external_order_id = fields.Many2one(
        'ecommerce.external.order',
        string="External Order",
        index=True,
        check_company=True,
        ondelete='restrict',
        copy=False,
    )
    ecommerce_platform = fields.Selection(
        related='ecommerce_store_id.platform',
        string="Platform",
        store=True,
        readonly=True,
    )
    ecommerce_payment_status = fields.Char(
        string="E-commerce Payment Status",
        copy=False,
    )
    ecommerce_fulfillment_status = fields.Char(
        string="E-commerce Fulfillment Status",
        copy=False,
    )
