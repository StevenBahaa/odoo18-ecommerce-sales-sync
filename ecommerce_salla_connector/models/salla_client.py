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

    def _refresh_oauth_token(self, client_id, client_secret, refresh_token):
        import requests

        url = "https://accounts.salla.sa/oauth2/token"
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        try:
            response = requests.post(url, data=data, timeout=(5, 30), allow_redirects=False)
            if response.is_redirect:
                raise UserError(_("Unexpected redirect response from Salla token endpoint."))
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            # Mask the exception because it might contain token strings in URL/params.
            # Only return the HTTP status code or a safe message.
            status_code = getattr(e.response, "status_code", "Unknown")
            raise UserError(_(f"Salla token refresh request failed (Status: {status_code})."))
        except ValueError:
            raise UserError(_("Salla returned an invalid JSON response during token refresh."))
