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

    def _apply_salla_authorization_credentials(self, parsed):
        from odoo.tools import SQL

        self.ensure_one()
        if self.platform != "salla":
            return {"status": "pending_review", "error_message": _("Store platform is not salla.")}

        with self.env.cr.savepoint():
            self.env.cr.execute(SQL("SELECT id FROM ecommerce_store WHERE id = %s FOR UPDATE", self.id))

            store_sudo = self.sudo()
            store_sudo.invalidate_recordset([
                "last_oauth_authorized_at",
                "last_oauth_authorize_event_id",
                "access_token",
                "refresh_token",
            ])

            incoming_time = fields.Datetime.from_string(parsed["authorized_at"])
            watermark_time = store_sudo.last_oauth_authorized_at

            if watermark_time:
                if incoming_time < watermark_time:
                    return {"status": "pending_review", "error_message": _("Authorization is older than the last accepted authorization.")}
                if incoming_time == watermark_time:
                    if store_sudo.access_token == parsed["access_token"] and store_sudo.refresh_token == parsed["refresh_token"]:
                        return {"status": "duplicate", "error_message": _("Exact duplicate of the current authorization tokens at the same timestamp.")}
                    else:
                        return {"status": "pending_review", "error_message": _("Ambiguous authorization: same timestamp but different tokens.")}

            write_vals = {
                "access_token": parsed["access_token"],
                "refresh_token": parsed["refresh_token"],
                "access_token_expires_at": parsed["access_token_expires_at"],
                "refresh_token_issued_at": parsed["refresh_token_issued_at"],
                "refresh_token_expires_at": parsed["refresh_token_expires_at"],
                "oauth_scope": parsed["oauth_scope"],
                "oauth_token_type": parsed["oauth_token_type"],
                "last_oauth_authorized_at": parsed["authorized_at"],
                "last_oauth_authorize_event_id": parsed["external_event_id"],
            }

            res = store_sudo.write(write_vals)
            return {"status": "processed", "error_message": False}
