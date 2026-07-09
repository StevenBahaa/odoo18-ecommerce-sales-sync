from odoo import models, fields, api
from ..utils.phone_utils import normalize_phone_digits

class ResPartner(models.Model):
    _inherit = 'res.partner'

    ecommerce_normalized_phone = fields.Char(
        string="E-commerce Normalized Phone",
        compute="_compute_ecommerce_normalized_phones",
        store=True,
        index=True,
    )
    
    ecommerce_normalized_mobile = fields.Char(
        string="E-commerce Normalized Mobile",
        compute="_compute_ecommerce_normalized_phones",
        store=True,
        index=True,
    )

    @api.depends('phone', 'mobile')
    def _compute_ecommerce_normalized_phones(self):
        for partner in self:
            partner.ecommerce_normalized_phone = normalize_phone_digits(partner.phone)
            partner.ecommerce_normalized_mobile = normalize_phone_digits(partner.mobile)
