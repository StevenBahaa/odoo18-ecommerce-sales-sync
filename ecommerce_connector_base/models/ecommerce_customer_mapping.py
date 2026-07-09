from odoo import models, fields

class EcommerceCustomerMapping(models.Model):
    _name = 'ecommerce.customer.mapping'
    _description = 'E-commerce Customer Mapping'
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
    external_customer_id = fields.Char(
        string="External Customer ID",
        required=True,
        index=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string="Partner",
        required=True,
        index=True,
        ondelete='restrict',
        check_company=True,
    )
    external_email = fields.Char(string="External Email")
    external_phone = fields.Char(string="External Phone")
    normalized_phone = fields.Char(string="Normalized Phone")
    last_order_at = fields.Datetime(string="Last Order Date")
    active = fields.Boolean(string="Active", default=True)

    _sql_constraints = [
        (
            'unique_store_external_customer',
            'UNIQUE(store_id, external_customer_id)',
            'Customer mapping already exists for this store.',
        ),
    ]
