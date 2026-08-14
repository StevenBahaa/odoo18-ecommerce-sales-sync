import psycopg2

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from odoo.tools import SQL

from odoo.addons.ecommerce_connector_base.utils.phone_utils import normalize_phone_digits
from .salla_client import SallaAPIError


class EcommerceExternalOrder(models.Model):
    _inherit = "ecommerce.external.order"

    store_environment = fields.Selection(
        related="store_id.environment",
        string="Store Environment",
        readonly=True,
    )

    salla_enrichment_count = fields.Integer(
        string="Salla Enrichment Count",
        default=0,
        readonly=True,
        copy=False,
    )
    last_salla_enriched_at = fields.Datetime(
        string="Last Salla Enriched At",
        readonly=True,
        copy=False,
        tracking=True,
    )
    last_salla_enriched_by_id = fields.Many2one(
        "res.users",
        string="Last Salla Enriched By",
        readonly=True,
        copy=False,
    )
    last_salla_enrichment_status = fields.Selection(
        [
            ("success", "Success"),
            ("failed", "Failed"),
        ],
        string="Last Salla Enrichment Status",
        readonly=True,
        copy=False,
    )
    last_salla_enrichment_error = fields.Text(
        string="Last Salla Enrichment Error",
        readonly=True,
        copy=False,
        groups="ecommerce_connector_base.group_ecommerce_integration_manager",
    )

    def _ensure_salla_enrichment_manager(self):
        if not (
            self.env.su
            or self.env.user.has_group(
                "ecommerce_connector_base.group_ecommerce_integration_manager"
            )
        ):
            raise AccessError(_("Only Integration Managers may enrich external orders from Salla."))
        return True

    def _validate_salla_enrichment_target(self):
        self.ensure_one()
        self._ensure_salla_enrichment_manager()

        if self.platform != "salla":
            raise UserError(_("Order platform is not Salla."))

        if not self.store_id or not self.store_id.active:
            raise UserError(_("Store is missing or archived."))

        if self.store_id.environment == "mock":
            raise UserError(_("Mock environment orders cannot be enriched via live API."))

        allowed_companies = self.env.companies.ids if hasattr(self.env, "companies") else [self.env.company.id]
        if self.company_id.id not in allowed_companies or self.store_id.company_id.id not in allowed_companies:
            raise AccessError(_("Order or store is not in current company context."))

        allowed_states = {"draft", "captured", "pending_mapping", "pending_review", "failed", "ready"}
        if self.state not in allowed_states:
            raise UserError(_("Order state '%s' is not eligible for Salla enrichment.") % self.state)

        if self.sale_order_id:
            raise UserError(_("Orders with linked Sale Orders cannot be enriched."))

        if not self.external_order_id or not str(self.external_order_id).strip():
            raise UserError(_("Order is missing external order ID."))

        return True

    def action_enrich_from_salla(self):
        self.ensure_one()
        self._validate_salla_enrichment_target()

        store = self.store_id
        client = self.env["ecommerce.salla.client"]
        mapper = self.env["ecommerce.salla.mapper"]

        try:
            raw_data = client._fetch_order_details(store, self.external_order_id)
            parsed = mapper._parse_order_details_payload(raw_data)
        except (SallaAPIError, UserError) as e:
            safe_err = str(e)
            self.sudo().write({
                "salla_enrichment_count": self.salla_enrichment_count + 1,
                "last_salla_enriched_at": fields.Datetime.now(),
                "last_salla_enriched_by_id": self.env.user.id,
                "last_salla_enrichment_status": "failed",
                "last_salla_enrichment_error": safe_err,
            })
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Enrichment Failed"),
                    "message": safe_err,
                    "type": "warning",
                    "sticky": False,
                },
            }

        with self.env.cr.savepoint():
            try:
                self.env.cr.execute(SQL("SELECT id FROM ecommerce_external_order WHERE id = %s FOR UPDATE NOWAIT", self.id))
            except psycopg2.errors.LockNotAvailable:
                raise UserError(_("Order is currently locked by another operation."))

            self.invalidate_recordset([
                "state",
                "sale_order_id",
                "store_id",
                "company_id",
                "external_order_id",
                "currency_id",
                "last_external_update_at",
            ])

            self._validate_salla_enrichment_target()

            if str(parsed.get("external_order_id", "")).strip() != str(self.external_order_id).strip():
                safe_err = _("Returned order ID does not match staged order ID.")
                self.sudo().write({
                    "salla_enrichment_count": self.salla_enrichment_count + 1,
                    "last_salla_enriched_at": fields.Datetime.now(),
                    "last_salla_enriched_by_id": self.env.user.id,
                    "last_salla_enrichment_status": "failed",
                    "last_salla_enrichment_error": safe_err,
                })
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Enrichment Failed"),
                        "message": safe_err,
                        "type": "warning",
                        "sticky": False,
                    },
                }

            api_updated_at = parsed.get("external_updated_at")
            if api_updated_at and self.last_external_update_at:
                watermark_str = fields.Datetime.to_string(self.last_external_update_at)
                if api_updated_at < watermark_str:
                    safe_err = _("Salla API response is older than the last webhook update.")
                    self.sudo().write({
                        "salla_enrichment_count": self.salla_enrichment_count + 1,
                        "last_salla_enriched_at": fields.Datetime.now(),
                        "last_salla_enriched_by_id": self.env.user.id,
                        "last_salla_enrichment_status": "failed",
                        "last_salla_enrichment_error": safe_err,
                    })
                    return {
                        "type": "ir.actions.client",
                        "tag": "display_notification",
                        "params": {
                            "title": _("Enrichment Skipped"),
                            "message": safe_err,
                            "type": "warning",
                            "sticky": False,
                        },
                    }

            currency_code = parsed.get("currency_code")
            if currency_code:
                currency = self.env["res.currency"].sudo().search([
                    ("name", "=ilike", currency_code),
                    ("active", "=", True),
                ], limit=1)
                if not currency or currency.id != self.currency_id.id:
                    safe_err = _("Salla API currency '%s' does not match staged order currency '%s'.") % (
                        currency_code, self.currency_id.name
                    )
                    self.sudo().write({
                        "salla_enrichment_count": self.salla_enrichment_count + 1,
                        "last_salla_enriched_at": fields.Datetime.now(),
                        "last_salla_enriched_by_id": self.env.user.id,
                        "last_salla_enrichment_status": "failed",
                        "last_salla_enrichment_error": safe_err,
                    })
                    return {
                        "type": "ir.actions.client",
                        "tag": "display_notification",
                        "params": {
                            "title": _("Enrichment Failed"),
                            "message": safe_err,
                            "type": "warning",
                            "sticky": False,
                        },
                    }

            update_vals = dict(parsed.get("update_vals", {}))

            if "customer_phone" in update_vals:
                normalized = normalize_phone_digits(update_vals["customer_phone"])
                update_vals["normalized_customer_phone"] = normalized

            update_vals.update({
                "salla_enrichment_count": self.salla_enrichment_count + 1,
                "last_salla_enriched_at": fields.Datetime.now(),
                "last_salla_enriched_by_id": self.env.user.id,
                "last_salla_enrichment_status": "success",
                "last_salla_enrichment_error": False,
            })

            self.sudo().write(update_vals)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Order Enriched"),
                "message": _("Salla order details enriched successfully. Validate or Retry Import to proceed."),
                "type": "success",
                "sticky": False,
            },
        }
