import json

from odoo.tests.common import TransactionCase


class TestUC14OrderStatusUpdates(TransactionCase):

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

        cls.store = cls.env["ecommerce.store"].create({
            "name": "Test Salla Store UC14",
            "platform": "salla",
            "company_id": cls.company.id,
            "discount_strategy": "line_discount",
            "order_import_policy": "manual_validate",
            "stock_sync_policy": "readiness_only",
        })
        cls.store.with_user(cls.integration_user).write({
            "integration_user_id": cls.integration_user.id,
        })

        cls.partner = cls.env["res.partner"].create({
            "name": "Test Customer UC14",
        })

        cls.staged_order = cls.env["ecommerce.external.order"].create({
            "store_id": cls.store.id,
            "company_id": cls.company.id,
            "external_order_id": "uc14_ord_1",
            "currency_id": cls.company.currency_id.id,
            "payment_status": "pending",
            "fulfillment_status": "unfulfilled",
            "external_status": "created",
            "total_amount": 100.0,
            "shipping_amount": 10.0,
            "discount_amount": 0.0,
            "tax_amount": 15.0,
            "partner_id": cls.partner.id,
            "raw_payload": '{"original": "payload"}',
            "state": "captured",
        })

    def _build_update_payload(self, order_id, event_id=None, created_at="2026-07-19T10:00:00Z", data_extra=None):
        payload = {
            "event": "order.updated",
            "created_at": created_at,
            "data": dict({"id": order_id}, **(data_extra or {})),
        }
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

    def _refresh(self):
        self.staged_order.invalidate_recordset()

    # ------------------------------------------------------------------
    # 01  Accepted update: known order, status + monetary fields
    # ------------------------------------------------------------------
    def test_01_accepted_known_order_update(self):
        """Accepted update writes status and monetary fields; raw_payload preserved; event relations set."""
        payload = self._build_update_payload(
            "uc14_ord_1",
            event_id="evt_01",
            created_at="2026-07-19T10:00:00Z",
            data_extra={
                "payment_status": "paid",
                "fulfillment_status": "processing",
                "status": "in_progress",
                "currency": self.company.currency_id.name,
                "amounts": {
                    "total": {"amount": 120.0},
                    "shipping_cost": {"amount": 15.0},
                    "tax": {"amount": 5.0},
                },
            },
        )
        event = self._create_and_process_event(payload)

        self.assertEqual(event.processing_status, "processed")
        self.assertEqual(event.related_external_order_id.id, self.staged_order.id)
        self.assertEqual(event.related_partner_id.id, self.partner.id)

        self._refresh()
        self.assertEqual(self.staged_order.payment_status, "paid")
        self.assertEqual(self.staged_order.fulfillment_status, "processing")
        self.assertEqual(self.staged_order.external_status, "in_progress")
        self.assertEqual(self.staged_order.total_amount, 120.0)
        self.assertEqual(self.staged_order.shipping_amount, 15.0)
        self.assertEqual(self.staged_order.tax_amount, 5.0)
        self.assertEqual(self.staged_order.last_external_update_event_id, "evt_01")
        # Original creation payload must not be overwritten
        self.assertEqual(self.staged_order.raw_payload, '{"original": "payload"}')

    # ------------------------------------------------------------------
    # 02  Omitted fields preserved; explicit zero accepted
    # ------------------------------------------------------------------
    def test_02_omitted_fields_preserved_explicit_zero_accepted(self):
        """Omitted fields stay unchanged; an explicit 0.0 for tax is accepted."""
        # Reset watermark so test runs independently
        self.staged_order.write({
            "last_external_update_at": False,
            "last_external_update_event_id": False,
            "payment_status": "pending",
            "total_amount": 100.0,
            "tax_amount": 15.0,
        })

        payload = self._build_update_payload(
            "uc14_ord_1",
            event_id="evt_02",
            created_at="2026-07-19T10:10:00Z",
            data_extra={
                "currency": self.company.currency_id.name,
                "amounts": {
                    "tax": {"amount": 0.0},  # explicit zero
                },
                # payment_status, total_amount omitted
            },
        )
        event = self._create_and_process_event(payload)

        self.assertEqual(event.processing_status, "processed")
        self._refresh()
        # Omitted fields preserved
        self.assertEqual(self.staged_order.payment_status, "pending")
        self.assertEqual(self.staged_order.total_amount, 100.0)
        # Explicit zero applied
        self.assertEqual(self.staged_order.tax_amount, 0.0)

    # ------------------------------------------------------------------
    # 03  Orphan update parked (unknown order)
    # ------------------------------------------------------------------
    def test_03_orphan_update_parked(self):
        """Update for an unknown external_order_id parks the event."""
        payload = self._build_update_payload(
            "unknown_ord_999",
            created_at="2026-07-19T10:00:00Z",
            data_extra={"status": "paid"},
        )
        event = self._create_and_process_event(payload)

        self.assertEqual(event.processing_status, "pending_review")
        self.assertIn("unknown order", event.error_message)
        self.assertFalse(event.related_external_order_id)

    # ------------------------------------------------------------------
    # 04  Stale update parked; no mutation
    # ------------------------------------------------------------------
    def test_04_stale_update_parked_without_mutation(self):
        """Update with timestamp older than the watermark is parked; staged order unchanged."""
        self.staged_order.write({
            "last_external_update_at": "2026-07-19 10:00:00",
            "last_external_update_event_id": "evt_prev",
            "external_status": "in_progress",
        })

        payload = self._build_update_payload(
            "uc14_ord_1",
            created_at="2026-07-19T09:00:00Z",  # OLDER than watermark
            data_extra={"status": "stale_status"},
        )
        event = self._create_and_process_event(payload)

        self.assertEqual(event.processing_status, "pending_review")
        self.assertIn("older", event.error_message)
        self._refresh()
        self.assertNotEqual(self.staged_order.external_status, "stale_status")

    # ------------------------------------------------------------------
    # 05  Equal timestamp + same event ID → duplicate
    # ------------------------------------------------------------------
    def test_05_equal_timestamp_same_event_id_duplicate(self):
        """Exact replay of the last applied event is marked duplicate."""
        self.staged_order.write({
            "last_external_update_at": "2026-07-19 10:00:00",
            "last_external_update_event_id": "evt_dup",
        })

        payload = self._build_update_payload(
            "uc14_ord_1",
            event_id="evt_dup",
            created_at="2026-07-19T10:00:00Z",
            data_extra={"status": "dup_status"},
        )
        event = self._create_and_process_event(payload)

        self.assertEqual(event.processing_status, "duplicate")

    # ------------------------------------------------------------------
    # 06  Equal timestamp + different event ID → ambiguous (pending_review)
    # ------------------------------------------------------------------
    def test_06_equal_timestamp_different_event_id_ambiguous(self):
        """Same timestamp but different event ID is parked as ambiguous."""
        self.staged_order.write({
            "last_external_update_at": "2026-07-19 10:00:00",
            "last_external_update_event_id": "evt_dup",
        })

        payload = self._build_update_payload(
            "uc14_ord_1",
            event_id="evt_different",
            created_at="2026-07-19T10:00:00Z",
            data_extra={"status": "ambiguous"},
        )
        event = self._create_and_process_event(payload)

        self.assertEqual(event.processing_status, "pending_review")
        self.assertIn("Ambiguous", event.error_message)

    # ------------------------------------------------------------------
    # 07  Missing/invalid event time parked
    # ------------------------------------------------------------------
    def test_07_missing_event_time_parked(self):
        """Event with no parseable timestamp is parked."""
        payload = {
            "event": "order.updated",
            # no created_at, no data.updated_at, no data.created_at
            "data": {
                "id": "uc14_ord_1",
                "status": "no_time",
            },
        }
        event = self._create_and_process_event(payload)

        self.assertEqual(event.processing_status, "pending_review")
        self.assertIn("missing a valid timestamp", event.error_message)

    # ------------------------------------------------------------------
    # 08  Currency mismatch with monetary fields → parked atomically
    # ------------------------------------------------------------------
    def test_08_currency_mismatch_parked_atomically(self):
        """Amount update with mismatched currency parks event; no fields mutated."""
        # Ensure the company currency is not USD for this test to be meaningful
        order_currency = self.staged_order.currency_id.name
        wrong_currency = "USD" if order_currency != "USD" else "EUR"

        original_total = self.staged_order.total_amount

        payload = self._build_update_payload(
            "uc14_ord_1",
            created_at="2026-07-19T11:00:00Z",
            data_extra={
                "currency": wrong_currency,
                "amounts": {
                    "total": {"amount": 999.0},
                },
            },
        )
        event = self._create_and_process_event(payload)

        self.assertEqual(event.processing_status, "pending_review")
        self.assertIn("differs from staged order currency", event.error_message)

        self._refresh()
        self.assertEqual(self.staged_order.total_amount, original_total)

    # ------------------------------------------------------------------
    # 09  Linked sale order: only status fields mirrored, finances untouched
    # ------------------------------------------------------------------
    def test_09_linked_sale_order_statuses_mirrored(self):
        """payment_status and fulfillment_status are mirrored to linked sale.order; no financial change."""
        # Reset watermark
        self.staged_order.write({
            "last_external_update_at": False,
            "last_external_update_event_id": False,
        })

        sale_order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "ecommerce_store_id": self.store.id,
            "ecommerce_external_reference": "uc14_ord_1",
            "ecommerce_payment_status": "pending",
            "ecommerce_fulfillment_status": "unfulfilled",
        })
        self.staged_order.write({"sale_order_id": sale_order.id})

        payload = self._build_update_payload(
            "uc14_ord_1",
            event_id="evt_09",
            created_at="2026-07-19T12:00:00Z",
            data_extra={"payment_status": "paid"},
        )
        event = self._create_and_process_event(payload)

        self.assertEqual(event.processing_status, "processed")
        self.assertEqual(event.related_sale_order_id.id, sale_order.id)
        self.assertEqual(sale_order.ecommerce_payment_status, "paid")
        # Fulfillment was NOT in payload; must remain unchanged
        self.assertEqual(sale_order.ecommerce_fulfillment_status, "unfulfilled")
        # Sale order state must not have changed
        self.assertEqual(sale_order.state, "draft")

        # Remove sale order link so later tests are clean
        self.staged_order.write({"sale_order_id": False})

    # ------------------------------------------------------------------
    # 10  Original staged raw_payload preserved; event relations populated
    # ------------------------------------------------------------------
    def test_10_raw_payload_preserved_and_event_relations_set(self):
        """The staged order's original raw_payload is never overwritten by an update."""
        self.staged_order.write({
            "last_external_update_at": False,
            "last_external_update_event_id": False,
            "raw_payload": '{"original": "payload"}',
        })

        payload = self._build_update_payload(
            "uc14_ord_1",
            event_id="evt_10",
            created_at="2026-07-19T13:00:00Z",
            data_extra={"status": "updated"},
        )
        event = self._create_and_process_event(payload)

        self.assertEqual(event.processing_status, "processed")
        self._refresh()
        self.assertEqual(self.staged_order.raw_payload, '{"original": "payload"}')
        self.assertTrue(event.related_external_order_id)
        self.assertTrue(event.related_partner_id)

    # ------------------------------------------------------------------
    # 11  Same external_order_id in another store is isolated
    # ------------------------------------------------------------------
    def test_11_same_order_id_different_store_isolated(self):
        """An update for the same external_order_id in a different store is treated as orphan."""
        other_store = self.env["ecommerce.store"].create({
            "name": "Other Store UC14",
            "platform": "salla",
            "company_id": self.company.id,
            "discount_strategy": "line_discount",
            "order_import_policy": "manual_validate",
            "stock_sync_policy": "readiness_only",
        })
        other_store.with_user(self.integration_user).write({
            "integration_user_id": self.integration_user.id,
        })

        payload = self._build_update_payload(
            "uc14_ord_1",  # Same external ID, but different store
            created_at="2026-07-19T10:00:00Z",
            data_extra={"status": "other_store_status"},
        )
        event = self.env["ecommerce.webhook.event"].create({
            "store_id": other_store.id,
            "raw_payload": json.dumps(payload),
        })
        event._apply_uc03_processing_gate()

        self.assertEqual(event.processing_status, "pending_review")
        self.assertIn("unknown order", event.error_message)
        self._refresh()
        self.assertNotEqual(self.staged_order.external_status, "other_store_status")

    # ------------------------------------------------------------------
    # 12  No valid supported fields → parked
    # ------------------------------------------------------------------
    def test_12_empty_update_fields_parked(self):
        """Payload with no valid supported fields (e.g. only items) is parked for review."""
        payload = self._build_update_payload(
            "uc14_ord_1",
            created_at="2026-07-19T10:00:00Z",
            data_extra={
                # Only unsupported field: items — no status, no amounts
                "items": [{"id": "x"}],
            },
        )
        event = self._create_and_process_event(payload)

        self.assertEqual(event.processing_status, "pending_review")
        self.assertIn("no valid supported fields", event.error_message)

    # ------------------------------------------------------------------
    # 13  Blank or non-string status parked
    # ------------------------------------------------------------------
    def test_13_blank_or_non_string_status_parked(self):
        """A blank string or non-string status (like int or bool) is parked as malformed."""
        payload = self._build_update_payload(
            "uc14_ord_1",
            created_at="2026-07-19T10:00:00Z",
            data_extra={
                "status": "   ",  # blank string
                "payment_status": False,  # non-string
            },
        )
        event = self._create_and_process_event(payload)

        self.assertEqual(event.processing_status, "pending_review")
        self.assertIn("must be a non-blank string", event.error_message)

    # ------------------------------------------------------------------
    # 14  Explicit null amount parked
    # ------------------------------------------------------------------
    def test_14_explicit_null_amount_parked(self):
        """An explicit null for an amount is treated as malformed, parking the whole update."""
        payload = self._build_update_payload(
            "uc14_ord_1",
            created_at="2026-07-19T10:00:00Z",
            data_extra={
                "status": "valid_status",  # valid field that shouldn't apply
                "currency": self.company.currency_id.name,
                "amounts": {
                    "total": None,  # explicit null
                },
            },
        )
        event = self._create_and_process_event(payload)

        self.assertEqual(event.processing_status, "pending_review")
        self.assertIn("Malformed explicit null amount", event.error_message)
        self._refresh()
        self.assertNotEqual(self.staged_order.external_status, "valid_status")
