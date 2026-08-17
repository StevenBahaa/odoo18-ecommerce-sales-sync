from psycopg2 import IntegrityError
from odoo.tests.common import TransactionCase
import odoo.tools
from unittest.mock import patch

class TestUC12SaleOrderIdempotency(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

        cls.store = cls.env['ecommerce.store'].create({
            'name': 'Test Store',
            'platform': 'manual_mock',
            'company_id': cls.company.id,
            'discount_strategy': 'line_discount',
            'order_import_policy': 'manual_validate',
            'stock_sync_policy': 'readiness_only',
        })

        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Customer',
        })

        cls.product = cls.env['product.product'].create({
            'name': 'Test Product',
            'type': 'consu',
        })

    def _create_ready_external_order(self, external_id):
        order = self.env['ecommerce.external.order'].create({
            'store_id': self.store.id,
            'external_order_id': external_id,
            'state': 'ready',
            'partner_id': self.partner.id,
            'line_ids': [(0, 0, {
                'external_line_id': f"{external_id}_line1",
                'product_name': 'Test Product',
                'product_id': self.product.id,
                'quantity': 1.0,
                'unit_price': 100.0,
                'state': 'mapped',
            })],
        })
        return order

    def test_01_sql_uniqueness(self):
        """Test the sale-order uniqueness constraint."""
        so_vals = {
            'partner_id': self.partner.id,
            'ecommerce_store_id': self.store.id,
            'ecommerce_external_reference': 'TEST-SO-1',
        }
        so1 = self.env['sale.order'].create(so_vals)

        with odoo.tools.mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                self.env['sale.order'].create(so_vals)

        # Normal SO with no ecommerce link should not conflict
        so_normal_1 = self.env['sale.order'].create({'partner_id': self.partner.id})
        so_normal_2 = self.env['sale.order'].create({'partner_id': self.partner.id})
        self.assertTrue(so_normal_1.id)
        self.assertTrue(so_normal_2.id)

    def test_02_idempotent_creation(self):
        """Test action_create_sale_order called twice returns the same SO."""
        ext_order = self._create_ready_external_order('EXT-100')

        # First call creates the SO
        res1 = ext_order.action_create_sale_order()
        self.assertEqual(ext_order.state, 'imported')
        so_id = ext_order.sale_order_id.id
        self.assertTrue(so_id)

        # Second call returns the action to open it
        res2 = ext_order.action_create_sale_order()
        self.assertEqual(res2['res_id'], so_id)

    def test_03_concurrent_race_recovery(self):
        """Test that IntegrityError triggers a search and link, preventing crash."""
        ext_order = self._create_ready_external_order('EXT-101')

        # Simulate race condition: another transaction created the SO first
        so_vals = {
            'partner_id': self.partner.id,
            'ecommerce_store_id': self.store.id,
            'ecommerce_external_reference': ext_order.external_order_id,
        }
        existing_so = self.env['sale.order'].create(so_vals)

        # Bypass the initial lookup once to simulate another transaction winning
        # after our pre-check but before sale.order.create().
        with patch.object(
            type(ext_order),
            '_find_existing_sale_order',
            autospec=True,
            side_effect=[self.env['sale.order'].browse(), existing_so],
        ):
            with odoo.tools.mute_logger('odoo.sql_db'):
                res = ext_order.action_create_sale_order()

        self.assertEqual(ext_order.state, 'imported')
        self.assertEqual(ext_order.sale_order_id.id, existing_so.id)
        self.assertEqual(res['res_id'], existing_so.id)

    def test_04_validation_links_existing_sale_order(self):
        """Validation reconciles an existing sale order instead of leaving a duplicate state."""
        ext_order = self._create_ready_external_order('EXT-102')
        existing_so = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'ecommerce_store_id': self.store.id,
            'ecommerce_external_reference': ext_order.external_order_id,
        })

        ext_order.action_validate()

        self.assertEqual(ext_order.state, 'imported')
        self.assertEqual(ext_order.sale_order_id.id, existing_so.id)

    def test_05_same_reference_allowed_for_different_stores(self):
        """The uniqueness key is scoped to the store."""
        store_two = self.env['ecommerce.store'].create({
            'name': 'Second Test Store',
            'platform': 'manual_mock',
            'company_id': self.company.id,
            'discount_strategy': 'line_discount',
            'order_import_policy': 'manual_validate',
            'stock_sync_policy': 'readiness_only',
        })
        reference = 'CROSS-STORE-1'

        sale_order_one = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'ecommerce_store_id': self.store.id,
            'ecommerce_external_reference': reference,
        })
        sale_order_two = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'ecommerce_store_id': store_two.id,
            'ecommerce_external_reference': reference,
        })

        self.assertNotEqual(sale_order_one.id, sale_order_two.id)
