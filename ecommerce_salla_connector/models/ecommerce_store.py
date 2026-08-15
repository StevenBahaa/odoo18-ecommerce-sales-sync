import logging
import psycopg2
from datetime import timedelta
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from odoo.tools import SQL

_logger = logging.getLogger(__name__)


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

    token_refresh_requires_reauthorization = fields.Boolean(
        string="Requires Reauthorization",
        default=False,
        copy=False,
        readonly=True,
        groups="ecommerce_connector_base.group_ecommerce_integration_manager",
    )

    last_token_refresh_error = fields.Text(
        string="Last Refresh Error",
        copy=False,
        readonly=True,
        groups="ecommerce_connector_base.group_ecommerce_integration_manager",
    )

    last_salla_api_call_at = fields.Datetime(
        string="Last Salla API Call",
        readonly=True,
        copy=False,
        groups="ecommerce_connector_base.group_ecommerce_integration_manager",
    )

    salla_api_rate_limit_limit = fields.Integer(
        string="Salla API Rate Limit",
        readonly=True,
        copy=False,
        groups="ecommerce_connector_base.group_ecommerce_integration_manager",
    )

    salla_api_rate_limit_remaining = fields.Integer(
        string="Salla API Rate Remaining",
        readonly=True,
        copy=False,
        groups="ecommerce_connector_base.group_ecommerce_integration_manager",
    )

    salla_api_rate_limit_reset_at = fields.Datetime(
        string="Salla API Rate Reset",
        readonly=True,
        copy=False,
        groups="ecommerce_connector_base.group_ecommerce_integration_manager",
    )

    salla_api_retry_after_at = fields.Datetime(
        string="Salla API Retry After",
        readonly=True,
        copy=False,
        groups="ecommerce_connector_base.group_ecommerce_integration_manager",
    )

    oauth_credential_state = fields.Selection([
        ("not_salla", "Not Applicable"),
        ("mock", "Mock"),
        ("reauthorization_required", "Reauthorization Required"),
        ("refresh_in_progress", "Refresh In Progress"),
        ("refresh_token_missing", "Missing Refresh Token"),
        ("refresh_token_missing_expiry", "Refresh Token Missing Expiry"),
        ("refresh_token_expired", "Expired Refresh Token"),
        ("refresh_token_expiring", "Expiring Refresh Token"),
        ("access_token_missing", "Missing Access Token"),
        ("access_token_missing_expiry", "Access Token Missing Expiry"),
        ("access_token_expired", "Expired Access Token"),
        ("healthy", "Healthy"),
    ], string="Credential State", compute="_compute_salla_oauth_credential_status")

    oauth_credential_warning = fields.Char(
        string="Credential Warning",
        compute="_compute_salla_oauth_credential_status"
    )

    def _check_sensitive_field_access(self, vals_list):
        salla_sensitive = {
            "token_refresh_requires_reauthorization",
            "last_token_refresh_error",
            "last_salla_api_call_at",
            "salla_api_rate_limit_limit",
            "salla_api_rate_limit_remaining",
            "salla_api_rate_limit_reset_at",
            "salla_api_retry_after_at",
        }
        for vals in vals_list:
            if salla_sensitive.intersection(vals.keys()):
                self._ensure_integration_manager()
                break
        return super()._check_sensitive_field_access(vals_list)

    @api.depends(
        "platform", "environment", "access_token", "refresh_token",
        "token_refresh_requires_reauthorization", "token_refresh_in_progress_at",
        "refresh_token_expires_at", "access_token_expires_at"
    )
    def _compute_salla_oauth_credential_status(self):
        now = fields.Datetime.now()
        for store in self:
            if store.platform != "salla":
                store.oauth_credential_state = "not_salla"
                store.oauth_credential_warning = _("Not applicable")
                continue
            if store.environment == "mock":
                store.oauth_credential_state = "mock"
                store.oauth_credential_warning = _("Mock environment credentials")
                continue

            if store.token_refresh_requires_reauthorization:
                store.oauth_credential_state = "reauthorization_required"
                store.oauth_credential_warning = _("Token refresh failed ambiguously. Re-authorize the Salla app.")
                continue

            if store.token_refresh_in_progress_at:
                store.oauth_credential_state = "refresh_in_progress"
                store.oauth_credential_warning = _("A token refresh is currently in progress.")
                continue

            if not store.refresh_token:
                store.oauth_credential_state = "refresh_token_missing"
                store.oauth_credential_warning = _("Refresh token is missing. Re-authorize the app.")
                continue

            if not store.refresh_token_expires_at:
                store.oauth_credential_state = "refresh_token_missing_expiry"
                store.oauth_credential_warning = _("Refresh token missing expiry timestamp.")
                continue

            if store.refresh_token_expires_at <= now:
                store.oauth_credential_state = "refresh_token_expired"
                store.oauth_credential_warning = _("Refresh token is expired. Re-authorize the app.")
                continue

            if store.refresh_token_expires_at and store.refresh_token_expires_at <= now + relativedelta(days=5):
                store.oauth_credential_state = "refresh_token_expiring"
                store.oauth_credential_warning = _("Refresh token expires within 5 days. Refresh it now.")
                continue

            if not store.access_token:
                store.oauth_credential_state = "access_token_missing"
                store.oauth_credential_warning = _("Access token is missing.")
                continue

            if not store.access_token_expires_at:
                store.oauth_credential_state = "access_token_missing_expiry"
                store.oauth_credential_warning = _("Access token missing expiry timestamp.")
                continue

            if store.access_token_expires_at <= now:
                store.oauth_credential_state = "access_token_expired"
                store.oauth_credential_warning = _("Access token is expired.")
                continue

            store.oauth_credential_state = "healthy"
            store.oauth_credential_warning = _("Credentials are valid.")

    def _apply_salla_authorization_credentials(self, parsed):
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
                # UC-16: newly accepted authorization clears refresh failure/claim state
                "token_refresh_lock": False,
                "token_refresh_in_progress_at": False,
                "token_refresh_requires_reauthorization": False,
                "last_token_refresh_error": False,
            }

            res = store_sudo.write(write_vals)
            return {"status": "processed", "error_message": False}

    def _validate_salla_refresh_preconditions(self):
        self.ensure_one()
        if self.platform != "salla":
            raise UserError(_("Store platform is not salla."))
        if self.environment == "mock":
            raise UserError(_("Mock environment cannot refresh live tokens."))
        if not self.active:
            raise UserError(_("Store is archived."))
        if not self.client_id or not self.client_secret:
            raise UserError(_("Missing client ID or client secret."))
        if not self.refresh_token:
            raise UserError(_("Missing refresh token."))
        if (
            not isinstance(self.oauth_scope, str)
            or "offline_access" not in self.oauth_scope.split()
        ):
            raise UserError(_("Store was not authorized with offline_access scope."))
        if self.token_refresh_requires_reauthorization:
            raise UserError(_("Credentials require reauthorization. Cannot refresh."))
        if self.refresh_token_expires_at and self.refresh_token_expires_at <= fields.Datetime.now():
            raise UserError(_("Refresh token is expired. Cannot refresh."))
        if self.token_refresh_lock:
            raise UserError(_("A token refresh is already in progress."))

    def _claim_salla_refresh_token(self):
        self.ensure_one()

        with self.env.registry.cursor() as new_cr:
            env = self.env(cr=new_cr)
            store = env["ecommerce.store"].browse(self.id)

            with env.cr.savepoint():
                try:
                    env.cr.execute(SQL("SELECT id FROM ecommerce_store WHERE id = %s FOR UPDATE NOWAIT", store.id))
                except psycopg2.errors.LockNotAvailable:
                    raise UserError(_("A token refresh is already in progress (lock busy)."))

                store.invalidate_recordset([
                    "platform", "environment", "active", "client_id", "client_secret",
                    "refresh_token", "oauth_scope", "token_refresh_requires_reauthorization",
                    "refresh_token_expires_at", "token_refresh_lock"
                ])

                store._validate_salla_refresh_preconditions()

                store.sudo().write({
                    "token_refresh_lock": True,
                    "token_refresh_in_progress_at": fields.Datetime.now(),
                    "last_token_refresh_error": False,
                })

                current_token = store.refresh_token

            return {
                "store_id": store.id,
                "refresh_token": current_token,
                "client_id": store.client_id,
                "client_secret": store.client_secret,
                "effective_scope": store.oauth_scope,
                "effective_token_type": store.oauth_token_type,
            }

    @api.model
    def _parse_salla_refresh_response(self, payload, refreshed_at, previous_refresh_token, effective_scope, effective_token_type):
        if not isinstance(payload, dict):
            raise ValueError("Response payload is not a dictionary.")

        if not isinstance(payload.get("access_token"), str) or not isinstance(payload.get("refresh_token"), str):
            raise ValueError("Tokens must be exactly strings.")

        access_token = payload.get("access_token", "").strip()
        refresh_token = payload.get("refresh_token", "").strip()

        if not access_token or access_token == "[REDACTED]":
            raise ValueError("Missing or redacted access_token.")
        if not refresh_token or refresh_token == "[REDACTED]":
            raise ValueError("Missing or redacted refresh_token.")

        if refresh_token == previous_refresh_token:
            raise ValueError("Salla returned the same refresh token.")

        token_type = payload.get("token_type", effective_token_type)
        if not isinstance(token_type, str) or not token_type.strip():
            raise ValueError("token_type must be a non-empty string.")
        token_type = token_type.strip().lower()

        scope = payload.get("scope", effective_scope)
        if not isinstance(scope, str) or not scope.strip():
            raise ValueError("scope must be a non-empty string.")
        scope = scope.strip()
        if "offline_access" not in scope.split():
            raise ValueError("OAuth scope must include offline_access.")

        expires_in_val = payload.get("expires_in")
        if (
            type(expires_in_val) is not int
            or not 0 < expires_in_val <= 14 * 24 * 60 * 60
        ):
            raise ValueError("Invalid expires_in duration.")
        expires_in = expires_in_val

        access_token_expires_at = refreshed_at + relativedelta(seconds=expires_in)
        refresh_token_issued_at = refreshed_at
        refresh_token_expires_at = refreshed_at + relativedelta(months=1)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "access_token_expires_at": access_token_expires_at,
            "refresh_token_issued_at": refresh_token_issued_at,
            "refresh_token_expires_at": refresh_token_expires_at,
            "oauth_scope": scope,
            "oauth_token_type": token_type,
        }

    def _finalize_salla_token_refresh(self, claim, parsed):
        self.ensure_one()
        with self.env.registry.cursor() as new_cr:
            env = self.env(cr=new_cr)
            store = env["ecommerce.store"].browse(self.id)

            with env.cr.savepoint():
                try:
                    env.cr.execute(SQL("SELECT id FROM ecommerce_store WHERE id = %s FOR UPDATE NOWAIT", store.id))
                except psycopg2.errors.LockNotAvailable:
                    raise UserError(_("Store lock busy during finalization."))

                store.invalidate_recordset([
                    "token_refresh_lock", "token_refresh_requires_reauthorization", "refresh_token"
                ])

                if not store.token_refresh_lock:
                    raise UserError(_("Token refresh lock was already cleared."))
                if store.token_refresh_requires_reauthorization:
                    raise UserError(_("Store already requires reauthorization."))
                if store.refresh_token != claim["refresh_token"]:
                    raise UserError(_("Credentials changed during refresh."))

                write_vals = parsed.copy()
                write_vals.update({
                    "last_token_refresh_at": fields.Datetime.now(),
                    "token_refresh_lock": False,
                    "token_refresh_in_progress_at": False,
                    "token_refresh_requires_reauthorization": False,
                    "last_token_refresh_error": False,
                })
                store.sudo().write(write_vals)

    def _mark_salla_refresh_reauthorization_required(self, claim, reason_code):
        self.ensure_one()
        with self.env.registry.cursor() as new_cr:
            env = self.env(cr=new_cr)
            store = env["ecommerce.store"].browse(self.id)

            with env.cr.savepoint():
                env.cr.execute(SQL("SELECT id FROM ecommerce_store WHERE id = %s FOR UPDATE", store.id))

                store.invalidate_recordset([
                    "token_refresh_lock", "refresh_token"
                ])

                if not store.token_refresh_lock:
                    return "superseded" # Lock was cleared
                if store.refresh_token != claim["refresh_token"]:
                    return "superseded" # Credentials changed, assume newer won

                store.sudo().write({
                    "token_refresh_requires_reauthorization": True,
                    "last_token_refresh_error": reason_code,
                    "token_refresh_in_progress_at": False,
                })
                return "marked"

    def _refresh_salla_token(self):
        self.ensure_one()
        self._ensure_integration_manager()

        claim = self._claim_salla_refresh_token()

        refreshed_at = fields.Datetime.now()
        client = self.env["ecommerce.salla.client"]
        try:
            payload = client._refresh_oauth_token(claim["client_id"], claim["client_secret"], claim["refresh_token"])
        except Exception:
            _logger.warning(
                "Salla token refresh did not complete safely for store %s.",
                self.id,
            )
            if self._mark_salla_refresh_reauthorization_required(claim, "An unexpected error occurred during token refresh. Re-authorize the Salla app before retrying.") == "superseded":
                raise UserError(_("Token refresh superseded by a newer authorization. No further action required."))
            raise UserError(_("Token refresh did not complete safely. Re-authorize the Salla app before retrying."))

        try:
            parsed = self._parse_salla_refresh_response(payload, refreshed_at, claim["refresh_token"], claim["effective_scope"], claim["effective_token_type"])
        except ValueError:
            if self._mark_salla_refresh_reauthorization_required(claim, "Token refresh response was invalid. Re-authorize the Salla app.") == "superseded":
                raise UserError(_("Token refresh superseded by a newer authorization. No further action required."))
            raise UserError(_("Token refresh response was invalid. Re-authorize the Salla app."))

        try:
            self._finalize_salla_token_refresh(claim, parsed)
        except UserError as e:
            if "Credentials changed" in str(e) or "lock was already cleared" in str(e):
                raise UserError(_("Token refresh superseded by a newer authorization. No further action required."))
            _logger.warning("Salla token refresh finalization failed for store %s: %s", self.id, str(e))
            if self._mark_salla_refresh_reauthorization_required(claim, "Database finalization failed. Re-authorize the Salla app.") == "superseded":
                raise UserError(_("Token refresh superseded by a newer authorization. No further action required."))
            raise UserError(_("Database finalization failed. Re-authorize the Salla app before retrying."))
        except Exception:
            _logger.warning(
                "Salla token refresh finalization failed for store %s.",
                self.id,
            )
            if self._mark_salla_refresh_reauthorization_required(claim, "Database finalization failed. Re-authorize the Salla app.") == "superseded":
                raise UserError(_("Token refresh superseded by a newer authorization. No further action required."))
            raise UserError(_("Database finalization failed. Re-authorize the Salla app before retrying."))

    def action_refresh_salla_token(self):
        self.ensure_one()
        self._ensure_integration_manager()
        self._refresh_salla_token()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("Salla token refreshed successfully."),
                "sticky": False,
                "type": "success",
            }
        }

    @api.model
    def _cron_check_salla_token_expiry(self):
        stores = self.search([("active", "=", True), ("platform", "=", "salla"), ("environment", "!=", "mock")])
        now = fields.Datetime.now()

        manager_group = self.env.ref("ecommerce_connector_base.group_ecommerce_integration_manager", raise_if_not_found=False)
        if not manager_group:
            return

        managers = manager_group.users.filtered(lambda u: u.active)

        for store in stores:
            try:
                with self.env.cr.savepoint():
                    needs_attention = False
                    reason_code = ""

                    if store.token_refresh_lock and store.token_refresh_in_progress_at and store.token_refresh_in_progress_at <= now - relativedelta(minutes=30):
                        store.sudo().write({
                            "token_refresh_requires_reauthorization": True,
                            "last_token_refresh_error": "Refresh outcome unknown. Reauthorize.",
                        })
                        needs_attention = True
                        reason_code = "Refresh process crashed"
                    elif store.token_refresh_requires_reauthorization:
                        needs_attention = True
                        reason_code = "Reauthorization required"
                    elif not store.refresh_token:
                        needs_attention = True
                        reason_code = "Missing refresh token"
                    elif store.refresh_token_expires_at and store.refresh_token_expires_at <= now:
                        needs_attention = True
                        reason_code = "Expired refresh token"
                    elif store.refresh_token_expires_at and store.refresh_token_expires_at <= now + relativedelta(days=5):
                        needs_attention = True
                        reason_code = "Expiring refresh token"
                    elif not store.access_token:
                        needs_attention = True
                        reason_code = "Missing access token"
                    elif store.access_token_expires_at and store.access_token_expires_at <= now:
                        needs_attention = True
                        reason_code = "Expired access token"

                    if needs_attention:
                        store_managers = managers.filtered(lambda u: store.company_id in u.company_ids)
                        for user in store_managers:
                            self._schedule_salla_credential_activity(store, user, reason_code)
            except Exception:
                _logger.exception("Failed to process token warning for store %s", store.id)

    @api.model
    def _schedule_salla_credential_activity(self, store, user, reason_code):
        summary = "Salla Credential Attention Required"

        existing = self.env["mail.activity"].search([
            ("res_model", "=", "ecommerce.store"),
            ("res_id", "=", store.id),
            ("activity_type_id", "=", self.env.ref("mail.mail_activity_data_todo").id),
            ("user_id", "=", user.id),
            ("summary", "=", summary),
        ])

        if not existing:
            self.env["mail.activity"].sudo().create({
                "res_model_id": self.env["ir.model"]._get_id("ecommerce.store"),
                "res_id": store.id,
                "activity_type_id": self.env.ref("mail.mail_activity_data_todo").id,
                "user_id": user.id,
                "summary": summary,
                "note": f"Store {store.name} requires attention: {reason_code}.",
                "date_deadline": fields.Date.context_today(store),
            })

    def _ensure_salla_api_caller(self):
        self.ensure_one()
        if not (
            self.env.su
            or self.env.user.has_group(
                "ecommerce_connector_base.group_ecommerce_integration_manager"
            )
        ):
            raise AccessError(_("Only Integration Managers may initiate Salla API calls."))
        return True

    def _update_salla_api_usage_metadata(self, metadata):
        self.ensure_one()
        allowed_keys = {
            "last_salla_api_call_at",
            "salla_api_rate_limit_limit",
            "salla_api_rate_limit_remaining",
            "salla_api_rate_limit_reset_at",
            "salla_api_retry_after_at",
        }
        write_vals = {k: v for k, v in metadata.items() if k in allowed_keys}
        if write_vals:
            self.sudo().write(write_vals)
            self.invalidate_recordset(allowed_keys)

    def _prepare_salla_access_token(self):
        self.ensure_one()
        self._ensure_salla_api_caller()

        if self.platform != "salla":
            raise UserError(_("Store platform is not salla."))
        if self.environment == "mock":
            raise UserError(_("Mock environment cannot make live Salla API calls."))
        if not self.active:
            raise UserError(_("Store is archived."))
        if self.token_refresh_requires_reauthorization:
            raise UserError(_("Credentials require reauthorization. Cannot make API requests."))
        if self.token_refresh_lock:
            raise UserError(_("A token refresh is currently in progress."))

        now = fields.Datetime.now()
        if self.salla_api_retry_after_at and self.salla_api_retry_after_at > now:
            from .salla_client import SallaAPIError
            raise SallaAPIError(
                _("Salla API request cooldown active until %s.") % fields.Datetime.to_string(self.salla_api_retry_after_at),
                code="cooldown",
                retry_after_at=self.salla_api_retry_after_at
            )

        scopes = set((self.oauth_scope or "").split())
        if not ({"orders.read", "orders.read_write"} & scopes):
            raise UserError(_("Store was not authorized with orders.read or orders.read_write scope."))

        near_expiry_threshold = now + timedelta(seconds=60)
        needs_refresh = (
            not self.access_token
            or not self.access_token_expires_at
            or self.access_token_expires_at <= near_expiry_threshold
        )

        if needs_refresh:
            self._refresh_salla_token()
            self.invalidate_recordset([
                "access_token",
                "access_token_expires_at",
                "token_refresh_requires_reauthorization",
            ])

        if not self.access_token or self.access_token == "[REDACTED]":
            raise UserError(_("Missing or invalid access token."))

        if (
            not self.access_token_expires_at
            or self.access_token_expires_at <= fields.Datetime.now() + timedelta(seconds=60)
        ):
            raise UserError(_("Access token is expired or expires too soon."))

        return self.access_token
