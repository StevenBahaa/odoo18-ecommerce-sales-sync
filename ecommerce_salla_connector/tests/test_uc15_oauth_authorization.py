import json
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError, AccessError
from odoo.tests.common import TransactionCase
from odoo.addons.ecommerce_salla_connector.models.ecommerce_store import (
    EcommerceStore as SallaEcommerceStore,
)


class TestUC15OAuthAuthorization(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

        cls.integration_user = cls.env.ref("base.user_admin").copy({
            "name": "Test Integration User UC15",
            "login": "integration_user_uc15",
            "groups_id": [
                (6, 0, [
                    cls.env.ref("base.group_user").id,
                    cls.env.ref("ecommerce_connector_base.group_ecommerce_connector_manager").id,
                    cls.env.ref("base.group_partner_manager").id,
                    cls.env.ref("sales_team.group_sale_manager").id,
                ])
            ],
        })

        cls.integration_manager = cls.env.ref("base.user_admin").copy({
            "name": "Test Integration Manager UC15",
            "login": "integration_manager_uc15",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("ecommerce_connector_base.group_ecommerce_connector_manager").id,
                cls.env.ref("ecommerce_connector_base.group_ecommerce_integration_manager").id,
            ])],
        })

        cls.non_manager_user = cls.env.ref("base.user_admin").copy({
            "name": "Test Non-Manager UC15",
            "login": "non_manager_uc15",
            "groups_id": [
                (6, 0, [
                    cls.env.ref("base.group_user").id,
                ])
            ],
        })

        cls.store = cls.env["ecommerce.store"].create({
            "name": "Test Salla Store UC15",
            "platform": "salla",
            "company_id": cls.company.id,
            "store_identifier": "mock-store-uc15-test-001",
        })
        cls.store.with_user(cls.integration_manager).write({
            "integration_user_id": cls.integration_user.id,
        })

        cls.mapper = cls.env["ecommerce.salla.mapper"]

    def _build_auth_payload(self, overrides=None):
        now = fields.Datetime.now()
        created_at_str = now.strftime("%Y-%m-%d %H:%M:%S")
        now_utc = now.replace(tzinfo=timezone.utc)
        expires_int = int((now_utc + relativedelta(years=1)).timestamp())

        payload = {
            "event": "app.store.authorize",
            "merchant": "mock-store-uc15-test-001",
            "created_at": created_at_str,
            "data": {
                "access_token": "valid_access_token",
                "expires": expires_int,
                "refresh_token": "valid_refresh_token",
                "scope": "orders.read offline_access",
                "token_type": "bearer"
            }
        }
        if overrides:
            payload.update(overrides)
        return payload

    def test_01_mapper_success(self):
        payload = self._build_auth_payload()
        parsed = self.mapper._parse_authorize_payload(payload)

        self.assertEqual(parsed["merchant_identifier"], "mock-store-uc15-test-001")
        self.assertEqual(parsed["access_token"], "valid_access_token")
        self.assertEqual(parsed["refresh_token"], "valid_refresh_token")
        self.assertEqual(parsed["oauth_scope"], "orders.read offline_access")
        self.assertEqual(parsed["oauth_token_type"], "bearer")

        auth_dt = fields.Datetime.from_string(parsed["authorized_at"])
        refresh_expires_dt = fields.Datetime.from_string(parsed["refresh_token_expires_at"])

        self.assertEqual(refresh_expires_dt, auth_dt + relativedelta(months=1))

    def test_02_mapper_rejections(self):
        # Missing offline_access
        with self.assertRaisesRegex(UserError, "must include offline_access"):
            payload = self._build_auth_payload({"data": {
                "access_token": "tok", "expires": 1893578400, "refresh_token": "ref",
                "scope": "orders.read not_offline_access", "token_type": "bearer"
            }})
            self.mapper._parse_authorize_payload(payload)

        # Redacted tokens
        with self.assertRaisesRegex(UserError, "Missing or redacted access_token"):
            payload = self._build_auth_payload({"data": {
                "access_token": "[REDACTED]", "expires": 1893578400, "refresh_token": "ref",
                "scope": "offline_access", "token_type": "bearer"
            }})
            self.mapper._parse_authorize_payload(payload)

        # Expired token
        with self.assertRaisesRegex(UserError, "expires_at must be after authorized_at"):
            payload = self._build_auth_payload({"data": {
                "access_token": "tok", "expires": 946684800, "refresh_token": "ref", # year 2000
                "scope": "offline_access", "token_type": "bearer"
            }})
            self.mapper._parse_authorize_payload(payload)

    def test_03_integration_user_execution(self):
        # A Connector Manager, without Integration Manager access, can process it.
        payload = self._build_auth_payload()
        event = self.env["ecommerce.webhook.event"].sudo().create({
            "store_id": self.store.id,
            "event_type": "app.store.authorize",
            "raw_payload": json.dumps({
                "event": "app.store.authorize",
                "data": {"access_token": "[REDACTED]", "refresh_token": "[REDACTED]"},
            }),
        })

        # Passes payload dictionary explicitly
        event._apply_uc03_processing_gate(processing_payload=payload)
        self.assertEqual(event.processing_status, "processed", event.error_message)
        self.assertNotIn("valid_access_token", event.raw_payload)
        self.assertFalse(self.integration_user.has_group(
            "ecommerce_connector_base.group_ecommerce_integration_manager"
        ))

        # Verify credentials written to store
        store_sudo = self.store.sudo()
        self.assertEqual(store_sudo.access_token, "valid_access_token")
        self.assertEqual(store_sudo.refresh_token, "valid_refresh_token")

    def test_04_cross_store_protection(self):
        """TC-UC15-4: Authorization payload rejected if merchant ID mismatches store."""
        payload = self._build_auth_payload({"merchant": "different-merchant-123"})
        event = self.env["ecommerce.webhook.event"].sudo().create({
            "store_id": self.store.id,
            "event_type": "app.store.authorize",
            "raw_payload": '{"event": "app.store.authorize"}',
        })
        event._apply_uc03_processing_gate(processing_payload=payload)
        self.assertEqual(event.processing_status, "pending_review", event.error_message)
        self.assertIn("does not match", event.error_message)

    def test_05_replay_ordering(self):
        """TC-UC15-5: Replay ordering and deduplication."""
        # Set store's current authorization timestamp
        base_time = fields.Datetime.now()
        self.store.sudo().write({
            "last_oauth_authorized_at": base_time,
            "last_oauth_authorize_event_id": "evt_base",
            "access_token": "tok1",
            "refresh_token": "ref1",
        })

        # 1. Older timestamp -> rejected
        older_time_str = (base_time - relativedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        payload_older = self._build_auth_payload({"created_at": older_time_str})
        event1 = self.env["ecommerce.webhook.event"].sudo().create({
            "store_id": self.store.id,
            "event_type": "app.store.authorize",
            "raw_payload": '{"event": "app.store.authorize"}',
        })
        event1._apply_uc03_processing_gate(processing_payload=payload_older)
        self.assertEqual(event1.processing_status, "pending_review", event1.error_message)
        self.assertIn("older", event1.error_message)

        # Duplicate
        dup_time_str = base_time.strftime("%Y-%m-%d %H:%M:%S")
        payload_dup = self._build_auth_payload({"created_at": dup_time_str})
        # The tokens and time must match EXACTLY to be duplicate
        payload_dup["data"]["access_token"] = self.store.sudo().access_token
        payload_dup["data"]["refresh_token"] = self.store.sudo().refresh_token
        event2 = self.env["ecommerce.webhook.event"].sudo().create({
            "store_id": self.store.id,
            "event_type": "app.store.authorize",
            "raw_payload": '{"event": "app.store.authorize"}',
        })
        event2._apply_uc03_processing_gate(processing_payload=payload_dup)
        self.assertEqual(event2.processing_status, "duplicate", event2.error_message)

        # Ambiguous
        payload_ambig = self._build_auth_payload({"created_at": dup_time_str})
        payload_ambig["data"]["access_token"] = "tok2"
        event3 = self.env["ecommerce.webhook.event"].sudo().create({
            "store_id": self.store.id,
            "event_type": "app.store.authorize",
            "raw_payload": '{"event": "app.store.authorize"}',
        })
        event3._apply_uc03_processing_gate(processing_payload=payload_ambig)
        self.assertEqual(event3.processing_status, "pending_review", event3.error_message)
        self.assertIn("Ambiguous", event3.error_message)

    def test_06_retry_rejection(self):
        event = self.env["ecommerce.webhook.event"].sudo().create({
            "store_id": self.store.id,
            "event_type": "app.store.authorize",
            "processing_status": "pending_review",
        })

        # Test non-manager retry fails with AccessError first
        with self.assertRaises(AccessError):
            event.with_user(self.non_manager_user).action_retry_processing()

        # Test manager retry fails with UserError specific to authorize
        with self.assertRaisesRegex(UserError, "Authorization events cannot be retried"):
            event.with_user(self.integration_manager).action_retry_processing()

    def test_07_order_processing_uses_only_redacted_audit_payload(self):
        """Transient credentials must not leak into raw order-line audit JSON."""
        payload = {
            "event": "order.created",
            "merchant": "mock-store-uc15-test-001",
            "data": {
                "id": "UC15-REDACTED-ORDER",
                "reference_id": "UC15-REDACTED-ORDER",
                "customer": {"first_name": "Redacted", "last_name": "Customer"},
                "amounts": {"total": {"amount": 10}},
                "items": [{
                    "id": "UC15-REDACTED-LINE", "product_id": "P-15",
                    "sku": "UC15-NO-MATCH", "name": "Redacted line",
                    "quantity": 1, "amounts": {"total_with_tax": {"amount": 10}},
                    "access_token": "nested-order-secret",
                }],
            },
        }
        redacted_payload = json.loads(json.dumps(payload))
        redacted_payload["data"]["items"][0]["access_token"] = "[REDACTED]"
        event = self.env["ecommerce.webhook.event"].sudo().create({
            "store_id": self.store.id,
            "event_type": "order.created",
            "raw_payload": json.dumps(redacted_payload),
        })

        event._apply_uc03_processing_gate(processing_payload=payload)

        self.assertEqual(event.processing_status, "pending_review", event.error_message)
        self.assertNotIn("nested-order-secret", event.raw_payload)
        line_payload = event.related_external_order_id.line_ids[0].raw_line_payload
        self.assertIn("[REDACTED]", line_payload)
        self.assertNotIn("nested-order-secret", line_payload)

    def test_08_missing_integration_user_is_pending_review(self):
        store = self.env["ecommerce.store"].create({
            "name": "No Integration User UC15", "platform": "salla",
            "company_id": self.company.id, "store_identifier": "no-user-uc15",
        })
        payload = self._build_auth_payload({"merchant": "no-user-uc15"})
        event = self.env["ecommerce.webhook.event"].sudo().create({
            "store_id": store.id, "event_type": "app.store.authorize",
            "raw_payload": '{"event": "app.store.authorize"}',
        })

        event._apply_uc03_processing_gate(processing_payload=payload)

        self.assertEqual(event.processing_status, "pending_review")
        self.assertFalse(store.sudo().access_token)

    def test_09_newer_authorization_rotates_credentials(self):
        self.store.sudo().write({
            "last_oauth_authorized_at": fields.Datetime.now() - relativedelta(hours=1),
            "last_oauth_authorize_event_id": "older-event",
            "access_token": "older-access", "refresh_token": "older-refresh",
        })
        payload = self._build_auth_payload()
        event = self.env["ecommerce.webhook.event"].sudo().create({
            "store_id": self.store.id, "event_type": "app.store.authorize",
            "raw_payload": '{"event": "app.store.authorize"}',
        })

        event._apply_uc03_processing_gate(processing_payload=payload)

        self.assertEqual(event.processing_status, "processed", event.error_message)
        self.assertEqual(self.store.sudo().access_token, "valid_access_token")
        self.assertEqual(self.store.sudo().refresh_token, "valid_refresh_token")

    def test_10_app_updated_does_not_touch_credentials(self):
        self.store.sudo().write({"access_token": "keep-access", "refresh_token": "keep-refresh"})
        event = self.env["ecommerce.webhook.event"].sudo().create({
            "store_id": self.store.id, "event_type": "app.updated",
            "raw_payload": '{"event": "app.updated", "data": {}}',
        })

        event._apply_uc03_processing_gate()

        self.assertEqual(event.processing_status, "processed", event.error_message)
        self.assertEqual(self.store.sudo().access_token, "keep-access")
        self.assertEqual(self.store.sudo().refresh_token, "keep-refresh")

    def test_11_connector_manager_cannot_write_oauth_credentials_directly(self):
        with self.assertRaises(AccessError):
            self.store.with_user(self.integration_user).write({"access_token": "forbidden"})

    def test_12_redacted_authorization_cannot_be_reprocessed_without_transient_data(self):
        event = self.env["ecommerce.webhook.event"].sudo().create({
            "store_id": self.store.id,
            "event_type": "app.store.authorize",
            "raw_payload": json.dumps({
                "event": "app.store.authorize",
                "data": {"access_token": "[REDACTED]", "refresh_token": "[REDACTED]"},
            }),
        })

        event._apply_uc03_processing_gate()

        self.assertEqual(event.processing_status, "pending_review")
        self.assertIn("not retained", event.error_message)

    def test_13_mock_authorize_sample_is_refreshed_when_loaded(self):
        payload_json = self.env["ecommerce.mock.payload.wizard"]._get_sample_payload_content(
            "salla_app_store_authorize"
        )
        parsed = self.mapper._parse_authorize_payload(json.loads(payload_json))

        self.assertGreater(
            fields.Datetime.from_string(parsed["access_token_expires_at"]),
            fields.Datetime.now(),
        )

    def test_14_cross_company_store_cannot_be_selected_by_payload_merchant(self):
        company_b = self.env["res.company"].create({"name": "UC15 Company B"})
        other_store = self.env["ecommerce.store"].create({
            "name": "UC15 Other Company Store",
            "platform": "salla",
            "company_id": company_b.id,
            "store_identifier": "other-company-merchant",
        })
        payload = self._build_auth_payload({"merchant": "other-company-merchant"})
        event = self.env["ecommerce.webhook.event"].sudo().create({
            "store_id": self.store.id,
            "event_type": "app.store.authorize",
            "raw_payload": '{"event": "app.store.authorize"}',
        })

        event._apply_uc03_processing_gate(processing_payload=payload)

        self.assertEqual(event.processing_status, "pending_review")
        self.assertFalse(self.store.sudo().access_token)
        self.assertFalse(other_store.sudo().access_token)

    def test_15_credential_write_failure_rolls_back_all_oauth_fields(self):
        previous_authorization = fields.Datetime.now() - relativedelta(hours=2)
        baseline = {
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "access_token_expires_at": previous_authorization + relativedelta(days=14),
            "refresh_token_issued_at": previous_authorization,
            "refresh_token_expires_at": previous_authorization + relativedelta(months=1),
            "oauth_scope": "offline_access",
            "oauth_token_type": "bearer",
            "last_oauth_authorized_at": previous_authorization,
            "last_oauth_authorize_event_id": "old-event",
        }
        self.store.sudo().write(baseline)
        payload = self._build_auth_payload()
        event = self.env["ecommerce.webhook.event"].sudo().create({
            "store_id": self.store.id,
            "event_type": "app.store.authorize",
            "raw_payload": '{"event": "app.store.authorize"}',
        })

        with patch.object(
            SallaEcommerceStore,
            "write",
            side_effect=UserError("Forced credential write failure"),
        ):
            event._apply_uc03_processing_gate(processing_payload=payload)

        self.assertEqual(event.processing_status, "failed")
        self.assertNotIn("valid_access_token", event.error_message)
        store_sudo = self.store.sudo()
        for field_name, value in baseline.items():
            self.assertEqual(store_sudo[field_name], value)
