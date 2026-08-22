from odoo.tests.common import TransactionCase, tagged
from odoo.tools import float_compare


@tagged("-at_install", "post_install", "ecommerce_connector_base")
class TestUC18StockReadiness(TransactionCase):
    """UC-18: Stock Readiness and Inventory Reservation Policies.

    Odoo 18 fixture notes:
      - Storable product: type="consu", is_storable=True
      - Non-tracked consumable: type="consu", is_storable=False
      - Service: type="service"
      Warehouse scoping context key: warehouse (NOT warehouse_id).
      Unreserved on-hand quantity field: product.free_qty (NOT qty_available).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.ext_id_counter = 0

        cls.manager = cls.env.ref("base.user_admin")
        cls.manager.sudo().write({
            "groups_id": [
                (4, cls.env.ref("base.group_system").id),
                (4, cls.env.ref("sales_team.group_sale_manager").id),
                (4, cls.env.ref(
                    "ecommerce_connector_base.group_ecommerce_connector_manager"
                ).id),
            ],
        })

        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )

        # Store: readiness_only with warehouse configured
        cls.store = cls.env["ecommerce.store"].create({
            "name": "UC18 Test Store",
            "platform": "manual_mock",
            "company_id": cls.company.id,
            "discount_strategy": "line_discount",
            "order_import_policy": "manual_validate",
            "stock_sync_policy": "readiness_only",
            "default_warehouse_id": cls.warehouse.id,
            "integration_user_id": cls.manager.id,
        })

        # Store: stock check disabled
        cls.store_no_check = cls.env["ecommerce.store"].create({
            "name": "UC18 No Check Store",
            "platform": "manual_mock",
            "company_id": cls.company.id,
            "discount_strategy": "line_discount",
            "order_import_policy": "manual_validate",
            "stock_sync_policy": "none",
            "integration_user_id": cls.manager.id,
        })

        # Store: readiness_only, NO warehouse (fail-closed)
        cls.store_no_wh = cls.env["ecommerce.store"].create({
            "name": "UC18 No Warehouse Store",
            "platform": "manual_mock",
            "company_id": cls.company.id,
            "discount_strategy": "line_discount",
            "order_import_policy": "manual_validate",
            "stock_sync_policy": "readiness_only",
        })

        cls.partner = cls.env["res.partner"].create({"name": "UC18 Test Customer"})

        # Odoo 18 storable product: type="consu", is_storable=True
        cls.storable_product = cls.env["product.product"].create({
            "name": "UC18 Storable Widget",
            "default_code": "UC18-WIDGET",
            "type": "consu",
            "is_storable": True,
        })

        # Odoo 18 non-tracked consumable: type="consu", is_storable=False
        cls.consu_product = cls.env["product.product"].create({
            "name": "UC18 Consumable Item",
            "default_code": "UC18-CONSU",
            "type": "consu",
            "is_storable": False,
        })

        # Service product
        cls.service_product = cls.env["product.product"].create({
            "name": "UC18 Service Item",
            "default_code": "UC18-SERVICE",
            "type": "service",
        })

        # Second storable for multi-product tests
        cls.storable_product_b = cls.env["product.product"].create({
            "name": "UC18 Storable Widget B",
            "default_code": "UC18-WIDGET-B",
            "type": "consu",
            "is_storable": True,
        })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_free_stock(self, product, qty, warehouse=None):
        """Set on-hand qty (no reservations, so free_qty == qty after this call)."""
        wh = warehouse or self.warehouse
        location = wh.lot_stock_id
        quant = self.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": product.id,
            "location_id": location.id,
            "inventory_quantity": qty,
        })
        quant.action_apply_inventory()

    def _reserve_stock(self, product, qty, warehouse=None):
        """Confirm a sale order and assign picking to reserve qty of product."""
        wh = warehouse or self.warehouse
        so = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "warehouse_id": wh.id,
            "company_id": self.company.id,
            "order_line": [(0, 0, {
                "product_id": product.id,
                "product_uom_qty": qty,
                "price_unit": 1.0,
            })],
        })
        so.action_confirm()
        so.picking_ids.action_assign()
        return so

    def _make_ready_order(self, store=None, lines=None):
        """Create an external order in 'ready' state."""
        self.__class__.ext_id_counter += 1
        ext_id = f"UC18-STOCK-{self.__class__.ext_id_counter}"
        
        s = store or self.store
        line_vals = lines or [
            (0, 0, {
                "external_line_id": f"{ext_id}-L1",
                "external_sku": self.storable_product.default_code,
                "product_name": self.storable_product.display_name,
                "product_id": self.storable_product.id,
                "quantity": 2.0,
                "unit_price": 50.0,
                "state": "mapped",
            })
        ]
        return self.env["ecommerce.external.order"].create({
            "store_id": s.id,
            "external_order_id": ext_id,
            "state": "ready",
            "partner_id": self.partner.id,
            "line_ids": line_vals,
        })

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_01_policy_none_skips_stock_check_and_creates_order(self):
        """01. stock_sync_policy='none' creates sale order regardless of stock."""
        self._set_free_stock(self.storable_product, 0.0)
        order = self._make_ready_order(store=self.store_no_check)
        order.with_user(self.manager).action_create_sale_order()
        self.assertEqual(order.state, "imported")
        self.assertTrue(order.sale_order_id)

    def test_02_no_warehouse_fails_closed_parks_order(self):
        """02. readiness_only + no warehouse = fail closed (Option A); order parked in pending_review."""
        order = self._make_ready_order(store=self.store_no_wh)
        result = order.with_user(self.manager).action_create_sale_order()
        self.assertFalse(result)
        self.assertEqual(order.state, "pending_review")
        self.assertFalse(order.sale_order_id)
        self.assertIn("no warehouse is configured", order.warning_message)

    def test_03_sufficient_free_stock_allows_creation(self):
        """03. Sufficient unreserved stock allows sale order creation."""
        self._set_free_stock(self.storable_product, 10.0)
        order = self._make_ready_order()
        order.with_user(self.manager).action_create_sale_order()
        self.assertEqual(order.state, "imported")
        self.assertTrue(order.sale_order_id)
        self.assertNotIn("Stock warning", order.warning_message or "")

    def test_04_insufficient_stock_parks_with_descriptive_warning(self):
        """04. free_qty < ordered: parks order in pending_review with descriptive warning_message."""
        self._set_free_stock(self.storable_product, 1.0)  # ordered 2
        order = self._make_ready_order()
        result = order.with_user(self.manager).action_create_sale_order()
        self.assertFalse(result)
        self.assertEqual(order.state, "pending_review")
        self.assertFalse(order.sale_order_id)
        self.assertIn("Stock warning", order.warning_message)
        self.assertIn("UC18 Storable Widget", order.warning_message)
        self.assertIn("ordered 2.0", order.warning_message)
        self.assertIn("unreserved available 1.0", order.warning_message)
        self.assertIn(self.warehouse.name, order.warning_message)

    def test_05_all_stock_reserved_parks_order(self):
        """05. On-hand stock exists but all reserved by other orders (free_qty=0): parks."""
        self._set_free_stock(self.storable_product, 5.0)
        self._reserve_stock(self.storable_product, 5.0)
        order = self._make_ready_order()
        result = order.with_user(self.manager).action_create_sale_order()
        self.assertEqual(order.state, "pending_review")
        self.assertFalse(order.sale_order_id)
        self.assertIn("unreserved available 0.0", order.warning_message)

    def test_06_partially_reserved_only_free_qty_counts(self):
        """06. 4 on-hand, 3 reserved (1 free), order requests 2: parks."""
        self._set_free_stock(self.storable_product, 4.0)
        self._reserve_stock(self.storable_product, 3.0)  # 1 free remaining
        order = self._make_ready_order()  # orders 2
        result = order.with_user(self.manager).action_create_sale_order()
        self.assertEqual(order.state, "pending_review")
        self.assertFalse(order.sale_order_id)
        self.assertIn("unreserved available 1.0", order.warning_message)

    def test_07_non_storable_consumable_skipped(self):
        """07. Non-storable consumable (is_storable=False) never triggers stock warning."""
        order = self._make_ready_order(lines=[(0, 0, {
            "external_line_id": "L-CONS",
            "product_name": "Consumable Item",
            "product_id": self.consu_product.id,
            "quantity": 5.0,
            "unit_price": 50.0,
            "state": "mapped",
        })])
        order.with_user(self.manager).action_create_sale_order()
        self.assertEqual(order.state, "imported")
        self.assertTrue(order.sale_order_id)
        self.assertNotIn("Stock warning", order.warning_message or "")

    def test_08_service_product_skipped(self):
        """08. Service products are skipped — they never hold physical stock."""
        order = self._make_ready_order(lines=[(0, 0, {
            "external_line_id": "L-SVC",
            "product_name": "Service Item",
            "product_id": self.service_product.id,
            "quantity": 5.0,
            "unit_price": 100.0,
            "state": "mapped",
        })])
        order.with_user(self.manager).action_create_sale_order()
        self.assertEqual(order.state, "imported")
        self.assertTrue(order.sale_order_id)
        self.assertNotIn("Stock warning", order.warning_message or "")

    def test_09_mixed_lines_one_short_parks_whole_order(self):
        """09. One short storable parks the whole order; service line not named in warning."""
        self._set_free_stock(self.storable_product, 1.0)  # ordered 2
        order = self._make_ready_order(lines=[
            (0, 0, {
                "external_line_id": "L1",
                "product_name": self.storable_product.display_name,
                "product_id": self.storable_product.id,
                "quantity": 2.0,
                "unit_price": 50.0,
                "state": "mapped",
            }),
            (0, 0, {
                "external_line_id": "L2",
                "product_name": self.service_product.display_name,
                "product_id": self.service_product.id,
                "quantity": 1.0,
                "unit_price": 20.0,
                "state": "mapped",
            }),
        ])
        result = order.with_user(self.manager).action_create_sale_order()
        self.assertEqual(order.state, "pending_review")
        self.assertFalse(order.sale_order_id)
        self.assertIn("UC18 Storable Widget", order.warning_message)
        self.assertNotIn("UC18 Service Item", order.warning_message)

    def test_10_exact_free_stock_match_allows_creation(self):
        """10. free_qty exactly equals ordered qty: sufficient, order imported."""
        self._set_free_stock(self.storable_product, 2.0)
        order = self._make_ready_order()
        order.with_user(self.manager).action_create_sale_order()
        self.assertEqual(order.state, "imported")
        self.assertTrue(order.sale_order_id)

    def test_11_stock_warning_appended_to_existing_warning_message(self):
        """11. Stock warning is APPENDED to any pre-existing warning_message (not overwriting it)."""
        self._set_free_stock(self.storable_product, 0.0)
        order = self._make_ready_order()
        # Simulate a pre-existing advisory (e.g. currency mismatch written by action_validate)
        order.warning_message = "Currency mismatch: SAR vs USD."
        result = order.with_user(self.manager).action_create_sale_order()
        self.assertEqual(order.state, "pending_review")
        # Both the pre-existing advisory AND the stock warning must be present
        self.assertIn("Currency mismatch", order.warning_message)
        self.assertIn("Stock warning", order.warning_message)
        # Stock warning must not replace the pre-existing text; error_message untouched
        self.assertFalse(order.error_message)

    def test_12_duplicate_product_lines_aggregated(self):
        """12. Two lines for same product are aggregated; combined qty vs free_qty decides."""
        # 3 free, two lines each ordering 2 (total 4) — should park
        self._set_free_stock(self.storable_product, 3.0)
        order = self._make_ready_order(lines=[
            (0, 0, {
                "external_line_id": "L1",
                "product_name": self.storable_product.display_name,
                "product_id": self.storable_product.id,
                "quantity": 2.0,
                "unit_price": 50.0,
                "state": "mapped",
            }),
            (0, 0, {
                "external_line_id": "L2",
                "product_name": self.storable_product.display_name,
                "product_id": self.storable_product.id,
                "quantity": 2.0,
                "unit_price": 50.0,
                "state": "mapped",
            }),
        ])
        result = order.with_user(self.manager).action_create_sale_order()
        self.assertEqual(order.state, "pending_review")
        self.assertFalse(order.sale_order_id)
        self.assertIn("ordered 4.0", order.warning_message)
        self.assertIn("unreserved available 3.0", order.warning_message)

    def test_13_warehouse_context_key_is_warehouse_not_warehouse_id(self):
        """13. Only the configured warehouse's stock counts (context key 'warehouse', not 'warehouse_id').

        Two warehouses in the same company: 0 stock in the store's warehouse, 10 in another.
        Order should be parked because the check is correctly scoped to the store's warehouse.
        If the wrong context key were used, free_qty would aggregate across all warehouses (=10)
        and the order would incorrectly be allowed through.
        """
        second_wh = self.env["stock.warehouse"].create({
            "name": "UC18 Second Warehouse",
            "code": "UC18B",
            "company_id": self.company.id,
        })
        self._set_free_stock(self.storable_product, 0.0, warehouse=self.warehouse)
        self._set_free_stock(self.storable_product, 10.0, warehouse=second_wh)

        order = self._make_ready_order()  # store uses self.warehouse (0 free)
        result = order.with_user(self.manager).action_create_sale_order()
        self.assertEqual(order.state, "pending_review")
        self.assertIn("Stock warning", order.warning_message)
        # Sanity: 10 units ARE available across the company; only wrong if free_qty was unscoped
        self.assertIn("unreserved available 0.0", order.warning_message)

    def test_14_uom_rounding_boundary_passes(self):
        """14. free_qty within half a UOM rounding unit of ordered qty is treated as sufficient."""
        rounding = self.storable_product.uom_id.rounding
        ordered = 2.0
        self._set_free_stock(self.storable_product, ordered - rounding / 2.0)
        order = self._make_ready_order()  # orders 2.0
        order.with_user(self.manager).action_create_sale_order()
        self.assertEqual(order.state, "imported")
        self.assertTrue(order.sale_order_id)

    def test_15_retry_after_stock_resolved(self):
        """15. After stock resolved, action_retry_import correctly processes the order."""
        self._set_free_stock(self.storable_product, 0.0)
        order = self._make_ready_order()
        order.with_user(self.manager).action_create_sale_order()
        self.assertEqual(order.state, "pending_review")

        self._set_free_stock(self.storable_product, 5.0)

        # Retry clears warning_message at start of retry, then transitions to imported
        order.with_user(self.manager).action_retry_import()

        self.assertEqual(order.state, "imported")
        self.assertTrue(order.sale_order_id)
        self.assertFalse(order.warning_message)
        self.assertFalse(order.error_message)

    def test_16_action_retry_import_parks_again_if_still_short(self):
        """16. Retry when stock still short re-parks the order; warning_message updated."""
        self._set_free_stock(self.storable_product, 0.0)
        order = self._make_ready_order()
        order.with_user(self.manager).action_create_sale_order()
        self.assertEqual(order.state, "pending_review")

        # Retry without resolving stock
        order.with_user(self.manager).action_retry_import()

        self.assertEqual(order.state, "pending_review")
        self.assertFalse(order.sale_order_id)
        self.assertIn("Stock warning", order.warning_message)
        self.assertIn("unreserved available 0.0", order.warning_message)

    def test_17_multi_company_stock_scoped_to_order_company(self):
        """17. Cross-company stock not counted; only order company's stock matters."""
        second_company = self.env["res.company"].sudo().create({"name": "UC18 Second Company"})
        second_wh = self.env["stock.warehouse"].sudo().search(
            [("company_id", "=", second_company.id)], limit=1
        )
        if not second_wh:
            second_wh = self.env["stock.warehouse"].sudo().create({
                "name": "UC18 Company2 WH",
                "code": "UC18C2",
                "company_id": second_company.id,
            })

        location2 = second_wh.lot_stock_id
        quant = self.env["stock.quant"].sudo().with_context(inventory_mode=True).create({
            "product_id": self.storable_product.id,
            "location_id": location2.id,
            "inventory_quantity": 10.0,
        })
        quant.action_apply_inventory()

        self._set_free_stock(self.storable_product, 0.0, warehouse=self.warehouse)

        order = self._make_ready_order()
        result = order.with_user(self.manager).action_create_sale_order()
        self.assertEqual(order.state, "pending_review")
        self.assertIn("Stock warning", order.warning_message)

    def test_18_retry_notification_displays_warning(self):
        """18. The dictionary returned by action_retry_import includes the stock warning in its message."""
        self._set_free_stock(self.storable_product, 0.0)
        order = self._make_ready_order()
        order.with_user(self.manager).action_create_sale_order()

        # Retry while still short — notification reads error_message or warning_message
        result_dict = order.with_user(self.manager).action_retry_import()
        self.assertIsInstance(result_dict, dict)
        self.assertEqual(result_dict.get("type"), "ir.actions.client")

        message = result_dict.get("params", {}).get("message", "")
        self.assertIn("Stock warning", message)
        self.assertIn("unreserved available 0.0", message)

    def test_19_stock_recheck_and_resolution_cleans_warning(self):
        """19. Re-checks update shortage numbers without duplicating warnings, and resolution clears stock warning while preserving currency warning."""
        self._set_free_stock(self.storable_product, 0.0)
        order = self._make_ready_order()
        order.warning_message = "Order currency USD differs from company currency SAR. Verify pricing before importing."

        # First check fails due to stock shortage
        order.with_user(self.manager).action_create_sale_order()
        self.assertEqual(order.state, "pending_review")
        self.assertIn("Order currency USD differs", order.warning_message)
        self.assertIn("Stock warning", order.warning_message)
        self.assertIn("unreserved available 0.0", order.warning_message)

        # Case 1: Shortage still present on second check (stock partially updated to 1.0, still short of 2.0)
        self._set_free_stock(self.storable_product, 1.0)
        order.with_user(self.manager).action_validate()
        order.with_user(self.manager).action_create_sale_order()
        self.assertEqual(order.state, "pending_review")
        self.assertIn("unreserved available 1.0", order.warning_message)
        self.assertEqual(order.warning_message.count("Stock warning (warehouse:"), 1)
        self.assertEqual(order.warning_message.count("Order currency USD differs"), 1)

        # Case 2: Shortage resolved (stock updated to 5.0 >= 2.0)
        self._set_free_stock(self.storable_product, 5.0)
        order.with_user(self.manager).action_validate()
        order.with_user(self.manager).action_create_sale_order()
        self.assertEqual(order.state, "imported")
        self.assertTrue(order.sale_order_id)
        self.assertNotIn("Stock warning", order.warning_message or "")
        self.assertIn("Order currency USD differs", order.warning_message)

    def test_20_switch_policy_to_none_clears_stale_stock_warning(self):
        """20. Switching stock_sync_policy to 'none' clears stale stock warning on next check."""
        self._set_free_stock(self.storable_product, 0.0)
        order = self._make_ready_order()
        order.warning_message = "Order currency USD differs from company currency SAR."
        order.with_user(self.manager).action_create_sale_order()
        self.assertEqual(order.state, "pending_review")
        self.assertIn("Stock warning", order.warning_message)

        # Switch store policy to 'none'
        order.store_id.stock_sync_policy = "none"
        order.with_user(self.manager).action_validate()
        order.with_user(self.manager).action_create_sale_order()
        self.assertEqual(order.state, "imported")
        self.assertTrue(order.sale_order_id)
        self.assertNotIn("Stock warning", order.warning_message or "")
        self.assertIn("Order currency USD differs", order.warning_message)

    def test_21_strip_stock_warning_helper(self):
        """21. _strip_stock_warning correctly removes stock and no-warehouse blocks while preserving other advisories."""
        order = self._make_ready_order()
        currency_msg = "Order currency USD differs from company currency SAR."
        stock_msg = "Stock warning (warehouse: WH):\n  - Product \"Widget\" (SKU: W1): ordered 2.0, unreserved available 1.0\nOrder parked for review. Resolve stock shortage or disable stock check to proceed."
        no_wh_msg = "Stock readiness policy is active but no warehouse is configured on this store.\nOrder parked for review. Configure a warehouse on the store to proceed."

        # Case 1: Currency + stock warning
        combined = f"{currency_msg}\n{stock_msg}"
        self.assertEqual(order._strip_stock_warning(combined), currency_msg)

        # Case 2: Only stock warning
        self.assertEqual(order._strip_stock_warning(stock_msg), "")

        # Case 3: Currency + no warehouse warning
        combined_wh = f"{currency_msg}\n{no_wh_msg}"
        self.assertEqual(order._strip_stock_warning(combined_wh), currency_msg)

        # Case 4: Only no warehouse warning
        self.assertEqual(order._strip_stock_warning(no_wh_msg), "")

        # Case 5: False / empty
        self.assertEqual(order._strip_stock_warning(False), "")
        self.assertEqual(order._strip_stock_warning(""), "")
