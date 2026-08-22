from datetime import timedelta
from dateutil.relativedelta import relativedelta
from unittest.mock import patch, MagicMock

from odoo import fields
from odoo.exceptions import UserError, AccessError
from odoo.tests.common import TransactionCase, tagged
from odoo.tools import SQL
from odoo.addons.ecommerce_connector_base.models.ecommerce_store import (
    EcommerceStore as BaseEcommerceStore,
)


@tagged("-at_install", "post_install", "ecommerce_salla_connector")
class TestUC16TokenRefresh(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create({
            "name": "Salla Manager",
            "login": "salla_manager",
            "groups_id": [(4, cls.env.ref("ecommerce_connector_base.group_ecommerce_integration_manager").id)],
        })
        cls.user = cls.env["res.users"].create({
            "name": "Salla User",
            "login": "salla_user",
            "groups_id": [(4, cls.env.ref("ecommerce_connector_base.group_ecommerce_connector_user").id)],
        })

    def setUp(self):
        super().setUp()
        self.store = self.env["ecommerce.store"].create({
            "name": f"Live Salla Store",
            "platform": "salla",
            "environment": "production",
            "client_id": "client_abc",
            "client_secret": "secret_123",
            "access_token": "live_access",
            "refresh_token": "live_refresh",
            "oauth_scope": "offline_access read_orders",
            "oauth_token_type": "bearer",
            "access_token_expires_at": fields.Datetime.now() + timedelta(days=10),
            "refresh_token_expires_at": fields.Datetime.now() + relativedelta(months=1),
        })
        self.store_id = self.store.id

        # Patch new cursor creation to use TestCursor synchronously, preventing isolation issues
        def mock_cursor_cm():
            class CursorWrapper:
                def __init__(self, cr):
                    self.cr = cr
                def __enter__(self):
                    return self.cr
                def __exit__(self, exc_type, exc_val, exc_tb):
                    pass
            return CursorWrapper(self.env.cr)

        self.patcher = patch.object(self.env.registry, "cursor", side_effect=mock_cursor_cm)
        self.patcher.start()

        # Patch commit/close/rollback on the actual cursor for the duration
        # of these synchronous unit tests.
        self.patch_commit = patch.object(self.env.cr, 'commit')
        self.patch_close = patch.object(self.env.cr, 'close')
        self.patch_rollback = patch.object(self.env.cr, 'rollback')
        self.patch_commit.start()
        self.patch_close.start()
        self.patch_rollback.start()

        self.addCleanup(self.patcher.stop)
        self.addCleanup(self.patch_commit.stop)
        self.addCleanup(self.patch_close.stop)
        self.addCleanup(self.patch_rollback.stop)

    def test_01_healthy_computed_state(self):
        """Complete future-dated credentials produce 'healthy'."""
        self.assertEqual(self.store.oauth_credential_state, "healthy")
        self.assertIn("valid", self.store.oauth_credential_warning)

    def test_02_state_priority_matrix(self):
        """Test computed state transitions based on field conditions."""
        now = fields.Datetime.now()
        store = self.store

        # Missing access token
        store.access_token = False
        self.assertEqual(store.oauth_credential_state, "access_token_missing")

        # Expired access token
        store.access_token = "expired_access"
        store.access_token_expires_at = now - timedelta(days=1)
        self.assertEqual(store.oauth_credential_state, "access_token_expired")

        # Expiring refresh token
        store.access_token_expires_at = now + timedelta(days=1)
        store.refresh_token_expires_at = now + timedelta(days=4)
        self.assertEqual(store.oauth_credential_state, "refresh_token_expiring")

        # Expired refresh token
        store.refresh_token_expires_at = now - timedelta(days=1)
        self.assertEqual(store.oauth_credential_state, "refresh_token_expired")

        # Missing refresh token
        store.refresh_token = False
        self.assertEqual(store.oauth_credential_state, "refresh_token_missing")

        # In progress
        store.sudo().write({"token_refresh_in_progress_at": now})
        self.assertEqual(store.oauth_credential_state, "refresh_in_progress")
        store.sudo().write({"token_refresh_in_progress_at": False})

        # Reauthorization required
        store.sudo().write({"token_refresh_requires_reauthorization": True})
        self.assertEqual(store.oauth_credential_state, "reauthorization_required")

    def test_03_permission_enforcement(self):
        """Only Integration Manager can invoke the public refresh action."""
        with self.assertRaises(AccessError):
            self.store.with_user(self.user).action_refresh_salla_token()

        # Mocking transport so it doesn't fail on network
        with patch("odoo.addons.ecommerce_salla_connector.models.salla_client.EcommerceSallaClient._refresh_oauth_token") as mock_refresh:
            mock_refresh.return_value = {
                "access_token": "new_access",
                "refresh_token": "new_refresh",
                "expires_in": 1209600,
            }
            # Should not raise AccessError
            self.store.with_user(self.manager).action_refresh_salla_token()

    def test_04_precondition_validation(self):
        """Test that missing/invalid preconditions raise UserError."""
        # Active=False
        self.store.active = False
        with self.assertRaisesRegex(UserError, "Store is archived"):
            self.store._validate_salla_refresh_preconditions()
        self.store.active = True

        # Missing refresh token
        self.store.refresh_token = False
        with self.assertRaisesRegex(UserError, "Missing refresh token"):
            self.store._validate_salla_refresh_preconditions()
        self.store.refresh_token = "live_refresh"

        # Missing offline_access
        self.store.oauth_scope = "read_orders"
        with self.assertRaisesRegex(UserError, "offline_access"):
            self.store._validate_salla_refresh_preconditions()
        self.store.oauth_scope = "offline_access"

        # Missing scope is unsafe because the refresh response may omit it.
        self.store.oauth_scope = False
        with self.assertRaisesRegex(UserError, "offline_access"):
            self.store._validate_salla_refresh_preconditions()
        self.store.oauth_scope = "offline_access"

        # Reauthorization required
        self.store.sudo().write({"token_refresh_requires_reauthorization": True})
        with self.assertRaisesRegex(UserError, "require reauthorization"):
            self.store._validate_salla_refresh_preconditions()
        self.store.sudo().write({"token_refresh_requires_reauthorization": False})

        # Expired refresh token
        self.store.refresh_token_expires_at = fields.Datetime.now() - timedelta(days=1)
        with self.assertRaisesRegex(UserError, "Refresh token is expired"):
            self.store._validate_salla_refresh_preconditions()
        self.store.refresh_token_expires_at = fields.Datetime.now() + relativedelta(months=1)

    def test_05_strict_response_parser(self):
        """Test response parser accepts valid and rejects invalid."""
        now = fields.Datetime.now()

        # Valid
        parsed = self.store._parse_salla_refresh_response({
            "access_token": "new_access",
            "refresh_token": "new_refresh",
            "expires_in": 1209600
        }, now, "old_refresh", "offline_access", "bearer")
        self.assertEqual(parsed["access_token"], "new_access")

        # Unchanged refresh token
        with self.assertRaisesRegex(ValueError, "same refresh token"):
            self.store._parse_salla_refresh_response({
                "access_token": "new_access",
                "refresh_token": "old_refresh",
                "expires_in": 1209600
            }, now, "old_refresh", "offline_access", "bearer")

        # Redacted
        with self.assertRaisesRegex(ValueError, "redacted"):
            self.store._parse_salla_refresh_response({
                "access_token": "[REDACTED]",
                "refresh_token": "new_refresh",
                "expires_in": 1209600
            }, now, "old_refresh", "offline_access", "bearer")

        # Invalid expires_in
        with self.assertRaisesRegex(ValueError, "Invalid expires_in"):
            self.store._parse_salla_refresh_response({
                "access_token": "new_access",
                "refresh_token": "new_refresh",
                "expires_in": "not_an_int"
            }, now, "old_refresh", "offline_access", "bearer")

        for invalid_expiry in ("1209600", 1209600.5, 1209601):
            with self.assertRaisesRegex(ValueError, "Invalid expires_in"):
                self.store._parse_salla_refresh_response({
                    "access_token": "new_access",
                    "refresh_token": "new_refresh",
                    "expires_in": invalid_expiry,
                }, now, "old_refresh", "offline_access", "bearer")

    def test_06_successful_rotation(self):
        """Test full successful rotation via orchestrator."""
        with patch("odoo.addons.ecommerce_salla_connector.models.salla_client.EcommerceSallaClient._refresh_oauth_token") as mock_refresh:
            mock_refresh.return_value = {
                "access_token": "new_access",
                "refresh_token": "new_refresh",
                "expires_in": 1209600,
            }

            self.store.with_user(self.manager).action_refresh_salla_token()

            self.store.invalidate_recordset()
            self.assertEqual(self.store.access_token, "new_access")
            self.assertEqual(self.store.refresh_token, "new_refresh")
            self.assertTrue(self.store.last_token_refresh_at)
            self.assertFalse(self.store.token_refresh_lock)
            self.assertFalse(self.store.token_refresh_requires_reauthorization)

    def test_07_ambiguous_timeout(self):
        """Timeout marks store as requiring reauthorization."""
        with patch("odoo.addons.ecommerce_salla_connector.models.salla_client.EcommerceSallaClient._refresh_oauth_token") as mock_refresh:
            # Simulate a timeout
            mock_refresh.side_effect = UserError("Timeout")

            with self.assertRaisesRegex(UserError, "did not complete safely"):
                self.store.with_user(self.manager).action_refresh_salla_token()

            self.store.invalidate_recordset()
            self.assertEqual(self.store.refresh_token, "live_refresh")
            self.assertTrue(self.store.token_refresh_requires_reauthorization)
            self.assertIn("unexpected error occurred", self.store.last_token_refresh_error)

    def test_08_concurrent_authorization_wins(self):
        """A new authorization payload clears the block."""
        self.store.sudo().write({"token_refresh_requires_reauthorization": True})

        parsed_payload = {
            "authorized_at": fields.Datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "access_token": "newer_access",
            "refresh_token": "newer_refresh",
            "access_token_expires_at": fields.Datetime.now() + timedelta(days=14),
            "refresh_token_issued_at": fields.Datetime.now(),
            "refresh_token_expires_at": fields.Datetime.now() + relativedelta(months=1),
            "oauth_scope": "offline_access",
            "oauth_token_type": "bearer",
            "external_event_id": "evt_123",
        }

        res = self.store._apply_salla_authorization_credentials(parsed_payload)
        self.assertEqual(res["status"], "processed")

        self.assertEqual(self.store.access_token, "newer_access")
        self.assertFalse(self.store.token_refresh_requires_reauthorization)

    def test_08b_superseded_refresh_aborts(self):
        """A refresh that finds new credentials raises a specific superseded message."""
        def mock_refresh_side_effect(client_id, client_secret, refresh_token):
            # Simulate a concurrent UC-15 authorization changing the credentials
            # while the token refresh is waiting for Salla API
            self.store.sudo().write({
                "access_token": "uc15_access",
                "refresh_token": "uc15_refresh",
                "token_refresh_lock": False,
            })
            return {
                "access_token": "new_access",
                "refresh_token": "new_refresh",
                "expires_in": 1209600,
            }

        with patch("odoo.addons.ecommerce_salla_connector.models.salla_client.EcommerceSallaClient._refresh_oauth_token", side_effect=mock_refresh_side_effect):
            with self.assertRaisesRegex(UserError, "superseded by a newer authorization"):
                self.store.with_user(self.manager).action_refresh_salla_token()

    def test_09_cron_warning_creation(self):
        """Cron creates deduplicated activities for expiring tokens."""
        self.store.refresh_token_expires_at = fields.Datetime.now() + timedelta(days=1)

        self.env["ecommerce.store"]._cron_check_salla_token_expiry()

        activities = self.env["mail.activity"].search([
            ("res_model", "=", "ecommerce.store"),
            ("res_id", "=", self.store.id),
        ])

        manager_activities = activities.filtered(lambda a: a.user_id == self.manager)
        self.assertEqual(len(manager_activities), 1)
        self.assertIn("Attention Required", manager_activities.summary)

        self.env["ecommerce.store"]._cron_check_salla_token_expiry()

        manager_activities_after = self.env["mail.activity"].search([
            ("res_model", "=", "ecommerce.store"),
            ("res_id", "=", self.store.id),
            ("user_id", "=", self.manager.id),
        ])
        self.assertEqual(len(manager_activities_after), 1)

    def test_09b_cron_detects_crashed_worker(self):
        """Cron detects a stale refresh lock and requires reauthorization."""
        self.store.sudo().write({
            "token_refresh_lock": True,
            "token_refresh_in_progress_at": fields.Datetime.now() - relativedelta(minutes=35),
        })

        self.env["ecommerce.store"]._cron_check_salla_token_expiry()

        self.assertTrue(self.store.token_refresh_requires_reauthorization)
        self.assertIn("outcome unknown", self.store.last_token_refresh_error)
        self.assertTrue(self.store.token_refresh_lock) # Should remain locked

    def test_09c_salla_client_no_redirects(self):
        """Client disables redirects when refreshing token."""
        client = self.env["ecommerce.salla.client"]
        with patch("requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.is_redirect = False
            mock_response.json.return_value = {"access_token": "test"}
            mock_post.return_value = mock_response

            client._refresh_oauth_token("cid", "sec", "ref")

            mock_post.assert_called_once()
            kwargs = mock_post.call_args.kwargs
            self.assertEqual(kwargs.get("allow_redirects"), False)

            # Test redirect rejection
            mock_response.is_redirect = True
            with self.assertRaisesRegex(UserError, "Unexpected redirect"):
                client._refresh_oauth_token("cid", "sec", "ref")

    def test_10_concurrent_refresh_claim(self):
        """Prove the row lock correctly blocks concurrent refresh attempts."""
        # Disable the mock cursor for this specific concurrency test
        self.patcher.stop()
        self.patch_commit.stop()
        self.patch_close.stop()
        self.patch_rollback.stop()

        # Because we need a committed row for a separate cursor to lock it,
        # we create a temporary store and explicitly commit it in a new cursor.
        with self.env.registry.cursor() as setup_cr:
            setup_env = self.env(cr=setup_cr)
            store = setup_env["ecommerce.store"].create({
                "name": "Lock Test Store",
                "platform": "salla",
                "environment": "production",
            })
            temp_store_id = store.id

        try:
            # Hold the lock in one cursor
            cr1 = self.env.registry.cursor()
            cr1.execute(SQL("SELECT id FROM ecommerce_store WHERE id = %s FOR UPDATE", temp_store_id))

            # Attempt to claim the token in the test cursor
            temp_store = self.env["ecommerce.store"].browse(temp_store_id)
            with self.assertRaisesRegex(UserError, "lock busy"):
                temp_store._claim_salla_refresh_token()

            cr1.rollback()
            cr1.close()
        finally:
            with self.env.registry.cursor() as teardown_cr:
                teardown_env = self.env(cr=teardown_cr)
                teardown_env["ecommerce.store"].browse(temp_store_id).unlink()

    def test_11_refresh_claim_is_durable_after_cursor_closes(self):
        """The committed claim blocks a later request without a row lock."""
        self.patcher.stop()
        self.patch_commit.stop()
        self.patch_close.stop()
        self.patch_rollback.stop()

        with self.env.registry.cursor() as setup_cr:
            setup_env = self.env(cr=setup_cr)
            store = setup_env["ecommerce.store"].create({
                "name": "Durable Claim Test Store",
                "platform": "salla",
                "environment": "production",
                "client_id": "durable-client",
                "client_secret": "durable-secret",
                "access_token": "durable-access",
                "refresh_token": "durable-refresh",
                "oauth_scope": "offline_access",
                "oauth_token_type": "bearer",
                "access_token_expires_at": fields.Datetime.now() + timedelta(days=14),
                "refresh_token_expires_at": fields.Datetime.now() + relativedelta(months=1),
            })
            temp_store_id = store.id

        try:
            temp_store = self.env["ecommerce.store"].browse(temp_store_id)
            temp_store._claim_salla_refresh_token()

            with self.env.registry.cursor() as verify_cr:
                verify_store = self.env(cr=verify_cr)["ecommerce.store"].browse(temp_store_id)
                self.assertTrue(verify_store.token_refresh_lock)

            with self.assertRaisesRegex(UserError, "already in progress"):
                temp_store._claim_salla_refresh_token()
        finally:
            with self.env.registry.cursor() as teardown_cr:
                teardown_env = self.env(cr=teardown_cr)
                teardown_env["ecommerce.store"].browse(temp_store_id).sudo().unlink()

    def test_12_final_write_failure_requires_reauthorization(self):
        """A failed post-dispatch credential write remains fail-closed."""
        original_write = BaseEcommerceStore.write

        def fail_final_token_write(recordset, vals):
            if vals.get("access_token") == "new_access":
                raise UserError("simulated final credential-write failure")
            return original_write(recordset, vals)

        with patch.object(BaseEcommerceStore, "write", new=fail_final_token_write):
            with patch(
                "odoo.addons.ecommerce_salla_connector.models.salla_client."
                "EcommerceSallaClient._refresh_oauth_token",
                return_value={
                    "access_token": "new_access",
                    "refresh_token": "new_refresh",
                    "expires_in": 1209600,
                },
            ):
                with self.assertRaisesRegex(UserError, "Database finalization failed"):
                    self.store.with_user(self.manager).action_refresh_salla_token()

        self.store.invalidate_recordset()
        self.assertEqual(self.store.refresh_token, "live_refresh")
        self.assertTrue(self.store.token_refresh_lock)
        self.assertTrue(self.store.token_refresh_requires_reauthorization)
