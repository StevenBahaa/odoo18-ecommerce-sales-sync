import json
from odoo.tests.common import TransactionCase

class TestUC13WebhookRetry(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

        cls.manager = cls.env['res.users'].create({
            'name': 'Test Manager',
            'login': 'test_manager_salla',
            'groups_id': [(4, cls.env.ref('ecommerce_connector_base.group_ecommerce_connector_manager').id)],
        })

        cls.integration_user = cls.env.ref('base.user_admin')
        cls.integration_user.sudo().write({
            'groups_id': [
                (4, cls.env.ref('base.group_partner_manager').id),
                (4, cls.env.ref('sales_team.group_sale_manager').id),
                (4, cls.env.ref('ecommerce_connector_base.group_ecommerce_integration_manager').id),
            ],
        })

        cls.store = cls.env['ecommerce.store'].create({
            'name': 'Test Salla Store',
            'platform': 'salla',
            'company_id': cls.company.id,
            'discount_strategy': 'line_discount',
            'order_import_policy': 'manual_validate',
            'stock_sync_policy': 'none',
        })
        cls.store.with_user(cls.integration_user).write({
            'integration_user_id': cls.integration_user.id,
        })

        cls.sample_payload = json.dumps({
            "event": "order.created",
            "merchant": "12345",
            "data": {
                "id": "SALLA-102",
                "reference_id": "ORD-102",
                "customer": {
                    "first_name": "Test",
                    "last_name": "User",
                    "mobile": "+966500000001",
                },
                "amounts": {
                    "total": {"amount": 100},
                    "tax": {"amount": 15},
                },
                "items": [
                    {
                        "id": "ITEM-1",
                        "product": {"id": "PROD-1"},
                        "sku": "SALLA-UNKNOWN-SKU",
                        "name": "Test Item",
                        "quantity": 1,
                        "amounts": {
                            "total_with_tax": {"amount": 100},
                        }
                    }
                ]
            }
        })

    def test_01_webhook_retry_links_to_external_order(self):
        """Test retrying a webhook event properly links and retries its external order."""
        event = self.env['ecommerce.webhook.event'].create({
            'store_id': self.store.id,
            'event_type': 'order.created',
            'external_order_id': 'SALLA-102',
            'raw_payload': self.sample_payload,
        })

        # Initial processing will leave the external order in pending_mapping due to missing SKU
        event._apply_uc03_processing_gate()

        self.assertEqual(event.processing_status, 'pending_review')
        self.assertTrue(event.related_external_order_id)

        ext_order = event.related_external_order_id
        self.assertEqual(ext_order.state, 'pending_mapping')

        event = event.with_user(self.manager)

        # Retry webhook - should retry external order
        event.action_retry_processing()

        self.assertEqual(event.retry_count, 1)
        self.assertEqual(event.last_retry_by_id, self.manager)
        self.assertEqual(ext_order.retry_count, 1)

        # Now fix mapping and retry webhook again
        product = self.env['product.product'].create({
            'name': 'Known Product',
            'default_code': 'SALLA-UNKNOWN-SKU',
            'type': 'consu',
        })

        event.action_retry_processing()

        self.assertEqual(ext_order.state, 'imported')
        self.assertEqual(event.processing_status, 'processed')
        self.assertEqual(event.related_sale_order_id.id, ext_order.sale_order_id.id)
