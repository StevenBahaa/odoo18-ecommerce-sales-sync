from odoo.tests.common import TransactionCase
from odoo.exceptions import AccessError
from unittest.mock import patch

class TestUC13ManualRetry(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

        # We need a manager user
        cls.manager = cls.env['res.users'].create({
            'name': 'Test Manager',
            'login': 'test_manager',
            'groups_id': [(4, cls.env.ref('ecommerce_connector_base.group_ecommerce_connector_manager').id)],
        })

        # We need an integration user
        cls.integration_user = cls.env['res.users'].create({
            'name': 'Integration User',
            'login': 'integration_user',
            'company_id': cls.company.id,
            'company_ids': [(6, 0, [cls.company.id])],
            'groups_id': [
                (4, cls.env.ref('base.group_partner_manager').id),
                (4, cls.env.ref('sales_team.group_sale_manager').id),
                (4, cls.env.ref('ecommerce_connector_base.group_ecommerce_integration_manager').id),
            ],
        })

        cls.store = cls.env['ecommerce.store'].create({
            'name': 'Test Store',
            'platform': 'manual_mock',
            'company_id': cls.company.id,
            'discount_strategy': 'line_discount',
            'order_import_policy': 'manual_validate',
            'stock_sync_policy': 'readiness_only',
        })
        cls.store.with_user(cls.integration_user).write({
            'integration_user_id': cls.integration_user.id,
        })

        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Customer',
        })

    def test_01_retry_missing_sku_recovery(self):
        """Test retrying an order that failed mapping because of a missing SKU."""
        ext_order = self.env['ecommerce.external.order'].create({
            'store_id': self.store.id,
            'external_order_id': 'EXT-RETRY-1',
            'state': 'pending_mapping',
            'partner_id': self.partner.id,
            'error_message': 'Initial error',
            'line_ids': [(0, 0, {
                'external_line_id': 'EXT-RETRY-1_line1',
                'external_sku': 'UNKNOWN-SKU',
                'product_name': 'Unknown Product',
                'quantity': 1.0,
                'unit_price': 100.0,
                'state': 'pending_mapping',
            })],
        })

        ext_order = ext_order.with_user(self.manager)

        # First retry with still no product - should stay pending_mapping and increment retry count
        res = ext_order.action_retry_import()

        self.assertEqual(ext_order.state, 'pending_mapping')
        self.assertEqual(ext_order.retry_count, 1)
        self.assertEqual(ext_order.last_retry_by_id, self.manager)
        self.assertIn('[', ext_order.error_history) # Error snapshot was saved

        # Now "fix" the mapping
        product = self.env['product.product'].create({
            'name': 'Known Product',
            'default_code': 'UNKNOWN-SKU',
            'type': 'consu',
        })

        # Second retry
        res2 = ext_order.action_retry_import()

        # It should now match, validate, and create SO
        self.assertEqual(ext_order.state, 'imported')
        self.assertEqual(ext_order.retry_count, 2)
        self.assertTrue(ext_order.sale_order_id.id)
        self.assertFalse(ext_order.error_message) # Active error cleared

    def test_02_retry_no_integration_user(self):
        """Test retrying an order when the store has no integration user configured."""
        self.store.with_user(self.integration_user).write({
            'integration_user_id': False,
        })

        ext_order = self.env['ecommerce.external.order'].create({
            'store_id': self.store.id,
            'external_order_id': 'EXT-RETRY-2',
            'state': 'pending_mapping',
            'partner_id': self.partner.id,
        })

        ext_order = ext_order.with_user(self.manager)
        ext_order.action_retry_import()

        self.assertEqual(ext_order.state, 'pending_review')
        self.assertEqual(ext_order.retry_count, 1)
        self.assertIn('Integration user is not configured', ext_order.error_message)

    def test_03_retry_requires_connector_manager(self):
        external_order = self.env['ecommerce.external.order'].create({
            'store_id': self.store.id,
            'external_order_id': 'EXT-RETRY-3',
            'state': 'pending_mapping',
        })
        regular_user = self.env['res.users'].create({
            'name': 'Regular Connector User',
            'login': 'regular_connector_user',
            'company_id': self.company.id,
            'company_ids': [(6, 0, [self.company.id])],
            'groups_id': [
                (4, self.env.ref('ecommerce_connector_base.group_ecommerce_connector_user').id),
            ],
        })

        with self.assertRaises(AccessError):
            external_order.with_user(regular_user).action_retry_import()

    def test_04_retry_failure_preserves_audit(self):
        external_order = self.env['ecommerce.external.order'].create({
            'store_id': self.store.id,
            'external_order_id': 'EXT-RETRY-4',
            'state': 'pending_mapping',
            'error_message': 'Initial mapping error',
        })

        with patch.object(
            type(external_order),
            '_match_or_create_customer',
            autospec=True,
            side_effect=RuntimeError('Customer matching failed'),
        ):
            external_order.with_user(self.manager).action_retry_import()

        self.assertEqual(external_order.state, 'failed')
        self.assertEqual(external_order.retry_count, 1)
        self.assertIn('Initial mapping error', external_order.error_history)
        self.assertIn('Customer matching failed', external_order.error_message)
