import json
from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


def get_sanitized_live_salla_order_payload():
    """Returns a sanitized representative Salla order.created live webhook payload.
    All merchant, customer, order, product, and variant IDs are invented test fixtures.
    """
    return {
        "event": "order.created",
        "merchant": 999000111,
        "created_at": "Sat Aug 15 2026 03:17:13 GMT+0300",
        "data": {
            "id": 9001001,
            "reference_id": 8002001,
            "date": {
                "date": "2026-08-15 03:17:11.000000",
                "timezone_type": 3,
                "timezone": "Asia/Riyadh"
            },
            "updated_at": {
                "date": "2026-08-15 03:17:11.000000",
                "timezone_type": 3,
                "timezone": "Asia/Riyadh"
            },
            "status": {
                "id": 1001,
                "name": "Under Review",
                "slug": "under_review",
                "customized": {"id": 2001, "name": "Custom Review"}
            },
            "currency": "SAR",
            "amounts": {
                "sub_total": {"amount": 372.0, "currency": "SAR"},
                "shipping_cost": {"amount": 0.0, "currency": "SAR", "original_cost": 0},
                "cash_on_delivery": {"amount": 0.0, "currency": "SAR"},
                "tax": {"percent": "0.00", "amount": {"amount": 0.0, "currency": "SAR"}},
                "discounts": [],
                "total": {"amount": 372.0, "currency": "SAR"}
            },
            "customer": {
                "id": 5001,
                "full_name": "Sanitized Customer",
                "first_name": "Sanitized",
                "last_name": "Customer",
                "mobile": 1234567890,
                "mobile_code": "+20",
                "email": "test.customer@example.com"
            },
            "items": [
                {
                    "id": 101,
                    "name": "Demo Blouse",
                    "sku": "SKU-BLOUSE-01",
                    "product_sku_id": 201,
                    "quantity": 2,
                    "currency": "SAR",
                    "amounts": {
                        "original_price": {"amount": 299.0, "currency": "SAR"},
                        "price_without_tax": {"amount": 149.0, "currency": "SAR"},
                        "total_discount": {"amount": 0.0, "currency": "SAR"},
                        "tax": {"percent": "0.00", "amount": {"amount": 0.0, "currency": "SAR"}},
                        "total": {"amount": 298.0, "currency": "SAR"}
                    },
                    "product": {
                        "id": 301,
                        "sku": "SKU-BLOUSE-01",
                        "name": "Demo Blouse"
                    }
                },
                {
                    "id": 102,
                    "name": "Demo Trousers",
                    "sku": "SKU-TROUSERS-01",
                    "product_sku_id": None,
                    "quantity": 1,
                    "currency": "SAR",
                    "amounts": {
                        "original_price": {"amount": 149.0, "currency": "SAR"},
                        "price_without_tax": {"amount": 74.0, "currency": "SAR"},
                        "total_discount": {"amount": 0.0, "currency": "SAR"},
                        "tax": {"percent": "0.00", "amount": {"amount": 0.0, "currency": "SAR"}},
                        "total": {"amount": 74.0, "currency": "SAR"}
                    },
                    "product": {
                        "id": 302,
                        "sku": "SKU-TROUSERS-01",
                        "name": "Demo Trousers"
                    }
                }
            ]
        }
    }


@tagged("-at_install", "post_install", "ecommerce_salla_connector")
class TestSallaLivePayloadCompatibility(TransactionCase):

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
            ],
        })

        cls.store = cls.env["ecommerce.store"].create({
            "name": "Salla Sanitized Store",
            "platform": "salla",
            "environment": "production",
            "company_id": cls.company.id,
            "integration_user_id": cls.integration_user.id,
            "store_identifier": "999000111",
            "client_id": "client_sanitized",
            "client_secret": "secret_sanitized",
            "access_token": "token_sanitized",
            "refresh_token": "refresh_sanitized",
            "oauth_scope": "offline_access orders.read_write",
            "oauth_token_type": "bearer",
            "stock_sync_policy": "none",
            "access_token_expires_at": fields.Datetime.now() + timedelta(days=10),
            "refresh_token_expires_at": fields.Datetime.now() + relativedelta(months=1),
        })
        cls.mapper = cls.env["ecommerce.salla.mapper"]

    # =========================================================================
    # 1-4: Status Normalization
    # =========================================================================

    def test_01_live_status_object_normalized_to_slug(self):
        """1. A live status object maps to exactly 'under_review' without dictionary stringification."""
        payload = get_sanitized_live_salla_order_payload()
        parsed = self.mapper._parse_order_payload(payload)
        status = parsed["order"]["external_status"]
        self.assertEqual(status, "under_review")
        self.assertNotIn("{", status)
        self.assertNotIn("id", status)

    def test_02_status_fallback_to_name_when_slug_missing(self):
        """2. Status falls back to string name only when slug is absent or blank."""
        data = {"status": {"name": "Under Review"}}
        self.assertEqual(self.mapper._normalize_status(data["status"]), "Under Review")

        data_blank_slug = {"status": {"slug": "   ", "name": "Under Review"}}
        self.assertEqual(self.mapper._normalize_status(data_blank_slug["status"]), "Under Review")

        # Numeric slug should not win over string name
        data_num_slug = {"status": {"slug": 5, "name": "Under Review"}}
        self.assertEqual(self.mapper._normalize_status(data_num_slug["status"]), "Under Review")

    def test_03_legacy_string_status_preserved(self):
        """3. Plain string status values are preserved as-is."""
        self.assertEqual(self.mapper._normalize_status("pending"), "pending")
        self.assertEqual(self.mapper._normalize_status("  shipped  "), "shipped")

    def test_04_invalid_status_types_never_stringified(self):
        """4. Integer, list, boolean, and empty statuses return False."""
        self.assertFalse(self.mapper._normalize_status(None))
        self.assertFalse(self.mapper._normalize_status(True))
        self.assertFalse(self.mapper._normalize_status(False))
        self.assertFalse(self.mapper._normalize_status(123))
        self.assertFalse(self.mapper._normalize_status(["pending"]))
        self.assertFalse(self.mapper._normalize_status({"id": 123}))  # No slug or name
        self.assertFalse(self.mapper._normalize_status({"slug": {"nested": "dict"}}))

    # =========================================================================
    # 5-7: Salla Datetime & GMT Offset Normalization
    # =========================================================================

    def test_05_salla_datetime_object_with_timezone_converted_to_utc(self):
        """5. Salla Asia/Riyadh datetime object is converted to UTC-naive datetime string."""
        # 2026-08-15 03:17:11 in Asia/Riyadh (UTC+3) -> 2026-08-15 00:17:11 UTC
        dt_dict = {
            "date": "2026-08-15 03:17:11.000000",
            "timezone_type": 3,
            "timezone": "Asia/Riyadh"
        }
        res = self.mapper._parse_datetime(dt_dict)
        self.assertEqual(res, "2026-08-15 00:17:11")

        # Legacy scalar string
        self.assertEqual(self.mapper._parse_datetime("2026-08-15T00:17:11Z"), "2026-08-15 00:17:11")

    def test_06_top_level_gmt_offset_parsed_to_utc(self):
        """6. Top-level RFC/GMT timestamp with offset 'Sat Aug 15 2026 03:17:13 GMT+0300' parses to UTC."""
        res = self.mapper._parse_datetime("Sat Aug 15 2026 03:17:13 GMT+0300")
        self.assertEqual(res, "2026-08-15 00:17:13")

    def test_07_invalid_datetime_returns_false(self):
        """7. Malformed date dicts and invalid timezone names return False."""
        self.assertFalse(self.mapper._parse_datetime(None))
        self.assertFalse(self.mapper._parse_datetime(True))
        self.assertFalse(self.mapper._parse_datetime({"date": "invalid_date", "timezone": "Asia/Riyadh"}))
        self.assertFalse(self.mapper._parse_datetime({"date": "2026-08-15 03:17:11", "timezone": "Invalid/Timezone"}))

    # =========================================================================
    # 8: Customer Identity & Consistent Phone Normalization
    # =========================================================================

    def test_08_customer_name_and_phone_normalization(self):
        """8. Customer full_name and numeric mobile with mobile_code produce consistent canonical digits."""
        payload = get_sanitized_live_salla_order_payload()
        parsed = self.mapper._parse_order_payload(payload)
        order = parsed["order"]

        self.assertEqual(order["customer_name"], "Sanitized Customer")
        self.assertEqual(order["customer_phone"], "201234567890")
        self.assertEqual(order["customer_email"], "test.customer@example.com")
        self.assertEqual(order["external_customer_id"], "5001")

        # Phone with existing country code and formatting
        cust_formatted = {"mobile": "+20 1234567890", "mobile_code": "+20"}
        self.assertEqual(self.mapper._extract_customer_phone(cust_formatted), "201234567890")

        # Local phone with leading zero
        cust_local = {"mobile": "01234567890", "mobile_code": "+20"}
        self.assertEqual(self.mapper._extract_customer_phone(cust_local), "201234567890")

    # =========================================================================
    # 9-10: Item Identifiers & Container Protection
    # =========================================================================

    def test_09_nested_product_and_sku_identifiers(self):
        """9. Nested product.id and product_sku_id map correctly to external product/variant IDs."""
        payload = get_sanitized_live_salla_order_payload()
        parsed = self.mapper._parse_order_payload(payload)
        lines = parsed["lines"]
        self.assertEqual(len(lines), 2)

        # Line 1: Blouse
        self.assertEqual(lines[0]["external_line_id"], "101")
        self.assertEqual(lines[0]["external_product_id"], "301")
        self.assertEqual(lines[0]["external_variant_id"], "201")
        self.assertEqual(lines[0]["external_sku"], "SKU-BLOUSE-01")
        self.assertEqual(lines[0]["quantity"], 2.0)
        self.assertEqual(lines[0]["unit_price"], 149.0)
        self.assertEqual(lines[0]["subtotal"], 298.0)
        self.assertEqual(lines[0]["tax_amount"], 0.0)

        # Line 2: Trousers (no variant)
        self.assertEqual(lines[1]["external_line_id"], "102")
        self.assertEqual(lines[1]["external_product_id"], "302")
        self.assertEqual(lines[1]["external_variant_id"], "")
        self.assertEqual(lines[1]["external_sku"], "SKU-TROUSERS-01")
        self.assertEqual(lines[1]["quantity"], 1.0)
        self.assertEqual(lines[1]["unit_price"], 74.0)
        self.assertEqual(lines[1]["subtotal"], 74.0)
        self.assertEqual(lines[1]["tax_amount"], 0.0)

    def test_10_container_identifiers_never_stringified(self):
        """10. Product, variant, and order container IDs are not stringified to '{...}'."""
        data_bad_ids = {
            "id": {"nested": 123},
            "items": [
                {
                    "id": ["line", "list"],
                    "product_id": {"bad": "dict"},
                    "variant_id": ["var", "list"],
                    "sku": {"sku": "dict"},
                    "price": 10.0,
                    "quantity": 1,
                }
            ]
        }
        items = self.mapper._extract_items(data_bad_ids)
        self.assertEqual(len(items), 1)
        self.assertFalse(items[0]["external_line_id"])
        self.assertFalse(items[0]["external_product_id"])
        self.assertEqual(items[0]["external_variant_id"], "")
        self.assertFalse(items[0]["external_sku"])

    # =========================================================================
    # 11-13: Monetary & Pricing Ambiguity Rules
    # =========================================================================

    def test_11_nested_monetary_objects_and_amounts(self):
        """11. Order-level nested monetary objects extract valid totals, taxes, and shipping."""
        payload = get_sanitized_live_salla_order_payload()
        parsed = self.mapper._parse_order_payload(payload)
        order = parsed["order"]

        self.assertEqual(order["total_amount"], 372.0)
        self.assertEqual(order["shipping_amount"], 0.0)
        self.assertEqual(order["discount_amount"], 0.0)
        self.assertEqual(order["tax_amount"], 0.0)

    def test_12_malformed_unit_price_rejected_not_zeroed(self):
        """12. Malformed or unparseable line prices raise UserError and are never converted to 0.0."""
        payload = get_sanitized_live_salla_order_payload()
        # Corrupt unit price
        payload["data"]["items"][0]["amounts"]["price_without_tax"] = "not_a_number"
        payload["data"]["items"][0]["amounts"]["total"] = "also_bad"
        with self.assertRaises(UserError):
            self.mapper._parse_order_payload(payload)

    def test_13_derived_price_fallback_and_discount_ambiguity(self):
        """13. Price is derived from total/qty ONLY when no discount/tax exists; ambiguous lines raise UserError."""
        # Clean derivation without discount or tax
        clean_item = {
            "name": "Fallback Item",
            "quantity": 2,
            "amounts": {"total": 100.0, "total_discount": 0.0, "tax": 0.0}
        }
        lines = self.mapper._extract_items({"items": [clean_item]})
        self.assertEqual(lines[0]["unit_price"], 50.0)
        self.assertEqual(lines[0]["subtotal"], 100.0)

        # Ambiguous derivation with discount
        ambiguous_item = {
            "name": "Ambiguous Item",
            "quantity": 2,
            "amounts": {"total": 100.0, "total_discount": 20.0, "tax": 0.0}
        }
        with self.assertRaises(UserError):
            self.mapper._extract_items({"items": [ambiguous_item]})

    # =========================================================================
    # 14-15: Partial Update Compatibility
    # =========================================================================

    def test_14_partial_update_with_status_object(self):
        """14. Webhook partial update handles official status object."""
        update_payload = {
            "event": "order.updated",
            "merchant": 999000111,
            "data": {
                "id": 9001001,
                "updated_at": {
                    "date": "2026-08-15 04:00:00.000000",
                    "timezone_type": 3,
                    "timezone": "Asia/Riyadh"
                },
                "status": {
                    "id": 1002,
                    "name": "Delivered",
                    "slug": "delivered"
                }
            }
        }
        parsed = self.mapper._parse_partial_update_payload(update_payload)
        self.assertEqual(parsed["external_order_id"], "9001001")
        self.assertEqual(parsed["update_vals"]["external_status"], "delivered")
        self.assertEqual(parsed["external_event_time"], "2026-08-15 01:00:00")

    def test_15_partial_update_invalid_status_rejected(self):
        """15. Partial update with invalid required status raises UserError."""
        bad_payload = {
            "event": "order.updated",
            "merchant": 999000111,
            "data": {
                "id": 9001001,
                "status": {"id": 123}  # No slug or name
            }
        }
        with self.assertRaises(UserError):
            self.mapper._parse_partial_update_payload(bad_payload)

    # =========================================================================
    # 16: Scope Preflight
    # =========================================================================

    def test_16_oauth_scope_allows_orders_read_and_orders_read_write(self):
        """16. Store preflight allows orders.read and orders.read_write, rejecting lookalikes."""
        # orders.read_write is valid
        self.store.oauth_scope = "offline_access orders.read_write"
        token = self.store._prepare_salla_access_token()
        self.assertEqual(token, "token_sanitized")

        # orders.read is valid
        self.store.oauth_scope = "offline_access orders.read"
        token = self.store._prepare_salla_access_token()
        self.assertEqual(token, "token_sanitized")

        # Lookalikes or substrings fail
        for bad_scope in (
            "offline_access orders.read_all",
            "offline_access orders.readonly",
            "offline_access Orders.Read",
            "offline_access customers.read",
        ):
            self.store.oauth_scope = bad_scope
            with self.assertRaises(UserError):
                self.store._prepare_salla_access_token()

    # =========================================================================
    # 17-19: End-to-End Webhook Ingestion & Workflow State Coverage
    # =========================================================================

    def test_17_e2e_live_like_webhook_event_with_mappings_reaches_ready(self):
        """17. Mapped products allow the external order to reach 'ready' and event to become 'processed'."""
        # Create matching products with exact SKUs
        self.env["product.product"].create({
            "name": "Demo Blouse Product",
            "default_code": "SKU-BLOUSE-01",
            "type": "consu",
        })
        self.env["product.product"].create({
            "name": "Demo Trousers Product",
            "default_code": "SKU-TROUSERS-01",
            "type": "consu",
        })

        payload = get_sanitized_live_salla_order_payload()
        event = self.env["ecommerce.webhook.event"].create({
            "store_id": self.store.id,
            "event_type": "order.created",
            "external_event_id": "EVT-LIVE-MAPPED-01",
            "raw_payload": json.dumps(payload),
        })

        event._apply_uc03_processing_gate()
        self.assertTrue(event.related_external_order_id)
        ext_order = event.related_external_order_id

        # Assert full workflow state transitions
        self.assertEqual(event.processing_status, "processed")
        self.assertEqual(ext_order.state, "ready")

        self.assertEqual(ext_order.external_order_id, "9001001")
        self.assertEqual(ext_order.external_status, "under_review")
        self.assertEqual(ext_order.customer_name, "Sanitized Customer")
        self.assertEqual(ext_order.customer_phone, "201234567890")
        self.assertEqual(ext_order.order_date, fields.Datetime.from_string("2026-08-15 00:17:11"))
        self.assertEqual(ext_order.total_amount, 372.0)
        self.assertEqual(len(ext_order.line_ids), 2)

        # Assert persisted product and variant IDs
        self.assertEqual(ext_order.line_ids[0].external_product_id, "301")
        self.assertEqual(ext_order.line_ids[0].external_variant_id, "201")
        self.assertEqual(ext_order.line_ids[0].unit_price, 149.0)
        self.assertEqual(ext_order.line_ids[0].subtotal, 298.0)
        self.assertEqual(ext_order.line_ids[0].state, "mapped")

        self.assertEqual(ext_order.line_ids[1].external_product_id, "302")
        self.assertEqual(ext_order.line_ids[1].external_variant_id, "")
        self.assertEqual(ext_order.line_ids[1].unit_price, 74.0)
        self.assertEqual(ext_order.line_ids[1].subtotal, 74.0)
        self.assertEqual(ext_order.line_ids[1].state, "mapped")

    def test_18_e2e_unmapped_products_remain_pending_mapping(self):
        """18. Unmapped products keep external order in 'pending_mapping' and event in 'pending_review'."""
        payload = get_sanitized_live_salla_order_payload()
        # Use unmapped unique SKUs
        payload["data"]["items"][0]["sku"] = "UNMAPPED-SKU-991"
        payload["data"]["items"][1]["sku"] = "UNMAPPED-SKU-992"

        event = self.env["ecommerce.webhook.event"].create({
            "store_id": self.store.id,
            "event_type": "order.created",
            "external_event_id": "EVT-LIVE-UNMAPPED-01",
            "raw_payload": json.dumps(payload),
        })

        event._apply_uc03_processing_gate()
        ext_order = event.related_external_order_id
        self.assertTrue(ext_order)

        # Assert workflow state and review message
        self.assertEqual(event.processing_status, "pending_review")
        self.assertEqual(ext_order.state, "pending_mapping")
        self.assertIn("Unmapped lines", event.error_message or "")
        self.assertIn("UNMAPPED-SKU-991", event.error_message or "")

        for line in ext_order.line_ids:
            self.assertEqual(line.state, "pending_mapping")

    def test_19_e2e_redelivery_idempotency(self):
        """19. Redelivered live-like webhook does not create duplicate external orders or lines."""
        payload = get_sanitized_live_salla_order_payload()
        event1 = self.env["ecommerce.webhook.event"].create({
            "store_id": self.store.id,
            "event_type": "order.created",
            "external_event_id": "EVT-LIVE-DUP-1",
            "raw_payload": json.dumps(payload),
        })
        event1._apply_uc03_processing_gate()
        order1 = event1.related_external_order_id

        event2 = self.env["ecommerce.webhook.event"].create({
            "store_id": self.store.id,
            "event_type": "order.created",
            "external_event_id": "EVT-LIVE-DUP-2",
            "raw_payload": json.dumps(payload),
        })
        event2._apply_uc03_processing_gate()
        self.assertEqual(event2.related_external_order_id, order1)
        self.assertEqual(len(order1.line_ids), 2)

    # =========================================================================
    # 20-22: Quantity Validation, Error Redaction & Null Legacy Fallback
    # =========================================================================

    def test_20_malformed_quantities_rejected(self):
        """20. Malformed, zero, negative, Boolean, and infinite quantities raise UserError."""
        for bad_qty in (0, -1, -5.5, "invalid", True, False, "Infinity", "-Infinity", "NaN", {"qty": 2}):
            bad_item = {
                "name": "Bad Qty Item",
                "quantity": bad_qty,
                "price": 10.0,
            }
            with self.assertRaises(UserError):
                self.mapper._extract_items({"items": [bad_item]})

        # Genuinely missing quantity defaults to 1.0
        missing_qty_item = {
            "name": "Default Qty Item",
            "price": 10.0,
        }
        lines = self.mapper._extract_items({"items": [missing_qty_item]})
        self.assertEqual(lines[0]["quantity"], 1.0)

    def test_21_container_ids_never_leaked_in_error_message(self):
        """21. Container dictionary IDs are never interpolated into validation exception strings."""
        bad_item = {
            "id": {"secret_token": "sensitive_leak_token_9988"},
            "name": "Leak Probe Item",
            "price": "not_a_valid_price",
        }
        with self.assertRaises(UserError) as cm:
            self.mapper._extract_items({"items": [bad_item]})

        err_text = str(cm.exception)
        self.assertNotIn("sensitive_leak_token_9988", err_text)
        self.assertNotIn("{", err_text)

    def test_22_null_legacy_keys_fallback_to_live_nested_keys(self):
        """22. Null legacy product/variant IDs fall back to valid live nested scalars."""
        item_with_null_legacy = {
            "id": 101,
            "product_id": None,
            "product": {"id": 301, "sku": "SKU-LIVE-01", "name": "Live Product"},
            "variant_id": None,
            "product_sku_id": 201,
            "price": 100.0,
            "quantity": 1,
        }
        lines = self.mapper._extract_items({"items": [item_with_null_legacy]})
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["external_product_id"], "301")
        self.assertEqual(lines[0]["external_variant_id"], "201")
        self.assertEqual(lines[0]["external_sku"], "SKU-LIVE-01")
        self.assertEqual(lines[0]["product_name"], "Live Product")

    # =========================================================================
    # 23-26: Final Review Regression Coverage
    # =========================================================================

    def test_23_non_object_line_item_is_rejected(self):
        """23. A malformed item entry is rejected instead of silently omitted."""
        valid_item = {
            "name": "Valid Item",
            "quantity": 1,
            "price": 10.0,
        }
        with self.assertRaises(UserError):
            self.mapper._extract_items({"items": [valid_item, "malformed-item"]})

    def test_24_explicit_null_quantity_is_rejected(self):
        """24. Explicit null quantities are malformed; only absent keys default to one."""
        for quantity_key in ("quantity", "qty"):
            with self.subTest(quantity_key=quantity_key):
                with self.assertRaises(UserError):
                    self.mapper._extract_items({
                        "items": [{
                            "name": "Null Quantity Item",
                            quantity_key: None,
                            "price": 10.0,
                        }],
                    })

    def test_25_decimal_overflow_is_rejected_at_float_boundary(self):
        """25. Finite Decimal exponents that overflow Float storage are rejected."""
        self.assertIsNone(self.mapper._extract_amount_numeric("1e309"))

        with self.assertRaises(UserError):
            self.mapper._extract_items({
                "items": [{"name": "Overflow Quantity", "quantity": "1e309", "price": 1.0}],
            })
        with self.assertRaises(UserError):
            self.mapper._extract_items({
                "items": [{"name": "Overflow Price", "quantity": 1, "price": "1e309"}],
            })

    def test_26_invalid_identifier_candidates_do_not_block_fallbacks(self):
        """26. Invalid truthy IDs are ignored in favor of later valid scalar candidates."""
        payload = get_sanitized_live_salla_order_payload()
        payload["data"].update({
            "id": {"invalid": "container"},
            "order_id": 9001002,
            "reference_id": {"invalid": "container"},
            "reference": "REF-FALLBACK-01",
        })
        parsed = self.mapper._parse_order_payload(payload)
        self.assertEqual(parsed["order"]["external_order_id"], "9001002")
        self.assertEqual(parsed["order"]["external_order_reference"], "REF-FALLBACK-01")

        update_payload = {
            "event": "order.updated",
            "event_id": {"invalid": "container"},
            "uuid": "EVT-FALLBACK-01",
            "data": {
                "id": float("nan"),
                "order_id": 9001002,
                "updated_at": "2026-08-15T04:00:00+03:00",
                "status": "delivered",
            },
        }
        update_parsed = self.mapper._parse_partial_update_payload(update_payload)
        self.assertEqual(update_parsed["external_order_id"], "9001002")
        self.assertEqual(update_parsed["event_id"], "EVT-FALLBACK-01")

    # =========================================================================
    # 27-30: Final Parser-Contract and End-to-End Regression Coverage
    # =========================================================================

    def test_27_monetary_lists_are_limited_to_discounts(self):
        """27. Lists are valid only for discount collections, never totals or prices."""
        self.assertEqual(
            self.mapper._extract_amount_numeric(
                [{"amount": 1}, {"value": "2"}], allow_list=True
            ),
            3.0,
        )
        self.assertIsNone(self.mapper._extract_amount_numeric([1, 2]))
        self.assertIsNone(
            self.mapper._extract_amount_numeric(
                {"amount": [1, 2]}, allow_list=True
            )
        )
        self.assertIsNone(self.mapper._extract_amount_numeric({"price": 10}))

        payload = get_sanitized_live_salla_order_payload()
        payload["data"]["amounts"]["total"] = [100, 200]
        with self.assertRaises(UserError):
            self.mapper._parse_order_payload(payload)

        update_payload = {
            "event": "order.updated",
            "data": {
                "id": 9001001,
                "updated_at": "2026-08-15T04:00:00+03:00",
                "amounts": {"total": {"total": "372.00"}},
            },
        }
        update_parsed = self.mapper._parse_partial_update_payload(update_payload)
        self.assertEqual(update_parsed["update_vals"]["total_amount"], 372.0)

    def test_28_invalid_naive_datetime_timezone_is_rejected(self):
        """28. A naive Salla datetime needs either no timezone or a valid IANA string."""
        self.assertFalse(self.mapper._parse_datetime({
            "date": "2026-08-15 03:17:11",
            "timezone": 3,
        }))
        self.assertFalse(self.mapper._parse_datetime({
            "date": "2026-08-15 03:17:11",
            "timezone": " ",
        }))
        self.assertEqual(
            self.mapper._parse_datetime({"date": "2026-08-15 03:17:11"}),
            "2026-08-15 03:17:11",
        )

    def test_29_malformed_webhook_line_fails_before_order_creation(self):
        """29. A malformed line fails safely without persisting a partial external order."""
        payload = get_sanitized_live_salla_order_payload()
        payload["data"]["items"].append("malformed-item")
        external_order_model = self.env["ecommerce.external.order"]
        before_count = external_order_model.search_count([
            ("store_id", "=", self.store.id),
            ("external_order_id", "=", "9001001"),
        ])
        event = self.env["ecommerce.webhook.event"].create({
            "store_id": self.store.id,
            "event_type": "order.created",
            "external_event_id": "EVT-LIVE-MALFORMED-LINE-01",
            "raw_payload": json.dumps(payload),
        })

        event._apply_uc03_processing_gate()

        self.assertEqual(event.processing_status, "failed")
        self.assertFalse(event.related_external_order_id)
        self.assertIn("Malformed line item at position 3", event.error_message or "")
        self.assertEqual(
            external_order_model.search_count([
                ("store_id", "=", self.store.id),
                ("external_order_id", "=", "9001001"),
            ]),
            before_count,
        )

    def test_30_redelivery_does_not_duplicate_partner_or_sale_order(self):
        """30. A duplicate webhook reuses the same order, partner, and sale order."""
        self.env["product.product"].create({
            "name": "Duplicate Blouse Product",
            "default_code": "SKU-BLOUSE-01",
            "type": "consu",
        })
        self.env["product.product"].create({
            "name": "Duplicate Trousers Product",
            "default_code": "SKU-TROUSERS-01",
            "type": "consu",
        })
        payload = get_sanitized_live_salla_order_payload()
        event1 = self.env["ecommerce.webhook.event"].create({
            "store_id": self.store.id,
            "event_type": "order.created",
            "external_event_id": "EVT-LIVE-SALE-DUP-1",
            "raw_payload": json.dumps(payload),
        })
        event1._apply_uc03_processing_gate()
        order1 = event1.related_external_order_id
        self.assertEqual(order1.state, "ready")

        order1.with_user(self.integration_user).action_create_sale_order()
        self.assertTrue(order1.sale_order_id)
        partner_id = order1.partner_id
        sale_order_id = order1.sale_order_id
        external_count = self.env["ecommerce.external.order"].search_count([
            ("store_id", "=", self.store.id),
            ("external_order_id", "=", order1.external_order_id),
        ])
        sale_order_count = self.env["sale.order"].search_count([
            ("ecommerce_store_id", "=", self.store.id),
            ("ecommerce_external_reference", "=", order1.external_order_id),
        ])

        event2 = self.env["ecommerce.webhook.event"].create({
            "store_id": self.store.id,
            "event_type": "order.created",
            "external_event_id": "EVT-LIVE-SALE-DUP-2",
            "raw_payload": json.dumps(payload),
        })
        event2._apply_uc03_processing_gate()

        self.assertEqual(event2.processing_status, "duplicate")
        self.assertEqual(event2.related_external_order_id, order1)
        self.assertEqual(event2.related_partner_id, partner_id)
        self.assertEqual(event2.related_sale_order_id, sale_order_id)
        self.assertEqual(
            self.env["ecommerce.external.order"].search_count([
                ("store_id", "=", self.store.id),
                ("external_order_id", "=", order1.external_order_id),
            ]),
            external_count,
        )
        self.assertEqual(
            self.env["sale.order"].search_count([
                ("ecommerce_store_id", "=", self.store.id),
                ("ecommerce_external_reference", "=", order1.external_order_id),
            ]),
            sale_order_count,
        )
