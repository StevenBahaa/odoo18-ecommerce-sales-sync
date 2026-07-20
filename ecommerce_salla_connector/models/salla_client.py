from odoo import models, _
from odoo.exceptions import UserError


class EcommerceSallaClient(models.AbstractModel):
    _name = "ecommerce.salla.client"
    _description = "Salla API Client"

    def _ensure_salla_store(self, store):
        if not store or store.platform != "salla":
            raise UserError(_("This operation requires a Salla store."))
        return True

    def _request(self, store, method, endpoint, **kwargs):
        """Placeholder for UC-17.

        Live Salla API calls are intentionally out of scope for UC-02.
        Token refresh locking must be implemented before real live API usage.
        """
        self._ensure_salla_store(store)
        raise UserError(
            _("Live Salla API client calls will be implemented in UC-17.")
        )

    def _fetch_order_details(self, store, external_order_id):
        """Placeholder for future order enrichment."""
        self._ensure_salla_store(store)
        raise UserError(
            _("Salla order detail enrichment will be implemented in UC-17.")
        )
