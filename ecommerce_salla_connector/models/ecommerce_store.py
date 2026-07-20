from odoo import api, fields, models,_


class EcommerceStore(models.Model):
    _inherit = "ecommerce.store"

    platform = fields.Selection(
        selection_add=[("salla", "Salla")],
        ondelete={
            "salla": "set default",
        },
        index=True,
        tracking=True,
        help="Technical platform handled by this store. Salla will be added by the Salla connector module."
    )
