import json

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase


class TestUC24OrderCancellation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

        cls.integration_user = cls.env.ref("base.user_admin")
        cls.integration_user.sudo().write({
            "groups_id": [
                (4, cls.env.ref("base.group_system").id),
                (4, cls.env.ref("base.group_partner_manager").id),
                (4, cls.env.ref("sales_team.group_sale_manager").id),
                (4, cls.env.ref("ecommerce_connector_base.group_ecommerce_integration_manager").id),
                (4, cls.env.ref("ecommerce_connector_base.group_ecommerce_connector_manager").id),
            ],
        })

        cls.manager = cls.env["res.users"].create({
            "name": "Test Manager UC24",
            "login": "test_manager_uc24",
            "groups_id": [(4, cls.env.ref("ecommerce_connector_base.group_ecommerce_connector_manager").id)],
        })

        cls.store = cls.env["ecommerce.store"].create({
            "name": "Test Salla Store UC24",
            "platform": "salla",
            "company_id": cls.company.id,
            "discount_strategy": "line_discount",
            "stock_sync_policy": "none",
            "cancellation_policy": "stage_only",
        })
        cls.store.with_user(cls.integration_user).write({
            "integration_user_id": cls.integration_user.id,
        })

        cls.partner = cls.env["res.partner"].create({
            "name": "Test Customer UC24",
        })

    def setUp(self):
        super().setUp()
        self.store.with_user(self.integration_user).write({
            "cancellation_policy": "stage_only",
        })
        self.staged_order = self.env["ecommerce.external.order"].create({
            "store_id": self.store.id,
            "company_id": self.company.id,
            "external_order_id": "uc24_ord_1",
            "currency_id": self.company.currency_id.id,
            "payment_status": "pending",
            "fulfillment_status": "unfulfilled",
            "external_status": "created",
            "total_amount": 100.0,
            "partner_id": self.partner.id,
            "raw_payload": '{"original": "payload"}',
            "state": "captured",
        })

    # ---- helpers -------------------------------------------------------

    def _build_cancel_payload(
        self,
        order_id="uc24_ord_1",
        event_id=None,
        canceled_at={"date": "2026-07-19 13:00:00.000000", "timezone": "Asia/Riyadh"},
        created_at="2026-07-19T10:05:00Z",
        data_extra=None,
    ):
        data = {"id": order_id, "status": "canceled"}
        if canceled_at is not None:
            data["canceled_at"] = canceled_at
        data.update(data_extra or {})
        payload = {"event": "order.cancelled", "data": data}
        if created_at is not None:
            payload["created_at"] = created_at
        if event_id:
            payload["id"] = event_id
        return payload

    def _create_and_process_event(self, payload_dict):
        event = self.env["ecommerce.webhook.event"].create({
            "store_id": self.store.id,
            "raw_payload": json.dumps(payload_dict),
        })
        event._apply_uc03_processing_gate()
        return event

    def _seed_watermark(self, dt_str, event_id):
        self.staged_order.write({
            "last_external_update_at": dt_str,
            "last_external_update_event_id": event_id,
        })

    def _create_imported_order(self):
        product = self.env["product.product"].create({
            "name": "UC24 Product",
            "type": "service",
        })
        self.env["ecommerce.external.order.line"].create({
            "external_order_id": self.staged_order.id,
            "store_id": self.store.id,
            "company_id": self.company.id,
            "external_product_id": "P-UC24",
            "product_name": "UC24 Product",
            "quantity": 1.0,
            "unit_price": 100.0,
            "subtotal": 100.0,
            "match_method": "manual",
            "state": "mapped",
            "product_id": product.id,
        })
        self.staged_order.write({"state": "ready"})
        self.staged_order.action_create_sale_order()
        self.staged_order.invalidate_recordset()
        return self.staged_order.sale_order_id

    # ---- tests ---------------------------------------------------------

    def test_01_known_non_imported_order_cancelled(self):
        """Known order transitions to cancelled, sets watermark, preserves raw_payload."""
        payload = self._build_cancel_payload(
            order_id="uc24_ord_1",
            event_id="evt_cancel_01",
            canceled_at={"date": "2026-07-19 13:00:00.000000", "timezone": "Asia/Riyadh"},
        )
        event = self._create_and_process_event(payload)

        self.assertEqual(event.processing_status, "processed")
        self.assertFalse(event.error_message)
        self.assertEqual(event.related_external_order_id, self.staged_order)

        self.staged_order.invalidate_recordset()
        self.assertEqual(self.staged_order.state, "cancelled")
        self.assertEqual(self.staged_order.external_status, "canceled")
        self.assertEqual(self.staged_order.last_external_update_event_id, "evt_cancel_01")
        self.assertEqual(
            fields.Datetime.to_string(self.staged_order.last_external_update_at),
            "2026-07-19 10:00:00",
        )
        self.assertEqual(self.staged_order.raw_payload, '{"original": "payload"}')

    def test_02_unknown_order_parks_pending_review(self):
        """Cancellation for an unknown external order parks as pending_review."""
        payload = self._build_cancel_payload(
            order_id="uc24_ord_missing",
            event_id="evt_cancel_02",
        )
        event = self._create_and_process_event(payload)

        self.assertEqual(event.processing_status, "pending_review")
        self.assertIn("unknown order", event.error_message or "")
        count = self.env["ecommerce.external.order"].search_count([
            ("store_id", "=", self.store.id),
            ("external_order_id", "=", "uc24_ord_missing"),
        ])
        self.assertEqual(count, 0)

    def test_03_stale_cancellation_parked(self):
        """Cancellation older than the current watermark is parked as pending_review without mutating staging."""
        self._seed_watermark("2026-08-01 00:00:00", "evt_prior")
        payload = self._build_cancel_payload(
            order_id="uc24_ord_1",
            event_id="evt_cancel_03",
            canceled_at={"date": "2026-07-19 13:00:00.000000", "timezone": "Asia/Riyadh"},
        )
        event = self._create_and_process_event(payload)

        self.assertEqual(event.processing_status, "pending_review")
        self.assertIn("older than the last applied update", event.error_message or "")

        self.staged_order.invalidate_recordset()
        self.assertEqual(self.staged_order.state, "captured")
        self.assertEqual(self.staged_order.last_external_update_event_id, "evt_prior")

    def test_04_exact_duplicate_cancellation(self):
        """Exact duplicate timestamp and event id is recognized as duplicate without mutating staging."""
        self._seed_watermark("2026-07-19 10:00:00", "evt_cancel_04")
        payload = self._build_cancel_payload(
            order_id="uc24_ord_1",
            event_id="evt_cancel_04",
            canceled_at={"date": "2026-07-19 13:00:00.000000", "timezone": "Asia/Riyadh"},
        )
        event = self._create_and_process_event(payload)

        self.assertEqual(event.processing_status, "duplicate")
        self.staged_order.invalidate_recordset()
        self.assertEqual(self.staged_order.state, "captured")

    def test_05_same_time_different_event_id_ambiguous(self):
        """Same timestamp with a different event id is parked as ambiguous pending_review."""
        self._seed_watermark("2026-07-19 10:00:00", "evt_cancel_05a")
        payload = self._build_cancel_payload(
            order_id="uc24_ord_1",
            event_id="evt_cancel_05b",
            canceled_at={"date": "2026-07-19 13:00:00.000000", "timezone": "Asia/Riyadh"},
        )
        event = self._create_and_process_event(payload)

        self.assertEqual(event.processing_status, "pending_review")
        self.assertIn("Ambiguous cancellation", event.error_message or "")
        self.staged_order.invalidate_recordset()
        self.assertEqual(self.staged_order.state, "captured")

    def test_06_missing_timestamp_parks(self):
        """Cancellation payload missing any valid timestamp is parked as pending_review."""
        payload = self._build_cancel_payload(
            order_id="uc24_ord_1",
            event_id="evt_cancel_06",
            canceled_at=None,
            created_at=None,
        )
        event = self._create_and_process_event(payload)

        self.assertEqual(event.processing_status, "pending_review")
        self.assertIn("missing a valid timestamp", event.error_message or "")
        self.staged_order.invalidate_recordset()
        self.assertEqual(self.staged_order.state, "captured")

    def test_07_malformed_data_object_parks(self):
        """Cancellation with non-dict data object is parked safely."""
        payload = {
            "event": "order.cancelled",
            "data": "not-a-dict",
        }
        event = self._create_and_process_event(payload)

        self.assertEqual(event.processing_status, "pending_review")
        self.staged_order.invalidate_recordset()
        self.assertEqual(self.staged_order.state, "captured")

    def test_08_imported_stage_only_policy_keeps_sale_order(self):
        """Under stage_only policy, cancelling an imported order cancels staging but leaves sale order in draft."""
        sale_order = self._create_imported_order()
        self.assertEqual(self.staged_order.state, "imported")
        self.assertEqual(sale_order.state, "draft")

        payload = self._build_cancel_payload(
            order_id="uc24_ord_1",
            event_id="evt_cancel_08",
            canceled_at={"date": "2026-07-19 13:00:00.000000", "timezone": "Asia/Riyadh"},
        )
        event = self._create_and_process_event(payload)

        self.assertEqual(event.processing_status, "processed")
        self.staged_order.invalidate_recordset()
        self.assertEqual(self.staged_order.state, "cancelled")
        sale_order.invalidate_recordset()
        self.assertEqual(sale_order.state, "draft")
        self.assertEqual(self.staged_order.sale_order_id, sale_order)

    def test_09_imported_cancel_policy_cancels_draft_sale_order(self):
        """Under cancel_linked_sale_order policy, cancelling an imported order cancels draft sale order."""
        sale_order = self._create_imported_order()
        self.store.with_user(self.integration_user).write({
            "cancellation_policy": "cancel_linked_sale_order",
        })

        payload = self._build_cancel_payload(
            order_id="uc24_ord_1",
            event_id="evt_cancel_09",
            canceled_at={"date": "2026-07-19 13:00:00.000000", "timezone": "Asia/Riyadh"},
        )
        event = self._create_and_process_event(payload)

        self.assertEqual(event.processing_status, "processed")
        self.staged_order.invalidate_recordset()
        self.assertEqual(self.staged_order.state, "cancelled")
        sale_order.invalidate_recordset()
        self.assertEqual(sale_order.state, "cancel")

    def test_10_uncancellable_sale_order_parks_atomically(self):
        """If linked sale order cannot be auto-cancelled, event parks and staging is NOT cancelled."""
        sale_order = self._create_imported_order()
        self.store.with_user(self.integration_user).write({
            "cancellation_policy": "cancel_linked_sale_order",
        })
        sale_order.write({"state": "sale"})

        payload = self._build_cancel_payload(
            order_id="uc24_ord_1",
            event_id="evt_cancel_10",
            canceled_at={"date": "2026-07-19 13:00:00.000000", "timezone": "Asia/Riyadh"},
        )
        event = self._create_and_process_event(payload)

        self.assertEqual(event.processing_status, "pending_review")
        self.assertIn("cannot be auto-cancelled", event.error_message or "")
        self.staged_order.invalidate_recordset()
        self.assertEqual(self.staged_order.state, "imported")
        sale_order.invalidate_recordset()
        self.assertEqual(sale_order.state, "sale")

    def test_11_manual_cancel_requires_manager(self):
        """Only Connector Manager can manually cancel external orders."""
        user = self.env["res.users"].create({
            "name": "Standard User UC24",
            "login": "uc24_std_user",
            "groups_id": [(6, 0, [
                self.env.ref("base.group_user").id,
                self.env.ref("ecommerce_connector_base.group_ecommerce_connector_user").id,
            ])],
        })
        with self.assertRaises(AccessError):
            self.staged_order.with_user(user).action_cancel_external_order()

        self.staged_order.invalidate_recordset()
        self.assertEqual(self.staged_order.state, "captured")

    def test_12_manual_cancel_success_and_reblock(self):
        """Manager can cancel staging; re-cancelling or cancelling imported/duplicate order is blocked."""
        self.staged_order.with_user(self.manager).action_cancel_external_order()
        self.staged_order.invalidate_recordset()
        self.assertEqual(self.staged_order.state, "cancelled")

        with self.assertRaises(UserError):
            self.staged_order.with_user(self.manager).action_cancel_external_order()

        # Imported order manual cancel blocked
        imported_staged = self.env["ecommerce.external.order"].create({
            "store_id": self.store.id,
            "company_id": self.company.id,
            "external_order_id": "uc24_ord_imp",
            "currency_id": self.company.currency_id.id,
            "partner_id": self.partner.id,
            "state": "imported",
        })
        with self.assertRaises(UserError):
            imported_staged.with_user(self.manager).action_cancel_external_order()

    def test_13_retry_blocked_after_cancellation(self):
        """Retry import is blocked on a cancelled external order."""
        payload = self._build_cancel_payload(
            order_id="uc24_ord_1",
            event_id="evt_cancel_13",
            canceled_at={"date": "2026-07-19 13:00:00.000000", "timezone": "Asia/Riyadh"},
        )
        self._create_and_process_event(payload)
        self.staged_order.invalidate_recordset()
        self.assertEqual(self.staged_order.state, "cancelled")

        with self.assertRaises(UserError):
            self.staged_order.with_user(self.manager).action_retry_import()

    def test_14_redelivery_after_successful_cancel_is_duplicate(self):
        """Re-delivery of the exact cancellation payload marks the second event as duplicate."""
        payload = self._build_cancel_payload(
            order_id="uc24_ord_1",
            event_id="evt_cancel_14",
            canceled_at={"date": "2026-07-19 13:00:00.000000", "timezone": "Asia/Riyadh"},
        )
        evt1 = self._create_and_process_event(payload)
        self.assertEqual(evt1.processing_status, "processed")

        evt2 = self._create_and_process_event(payload)
        self.assertEqual(evt2.processing_status, "duplicate")

        self.staged_order.invalidate_recordset()
        self.assertEqual(self.staged_order.state, "cancelled")
