import json
from odoo.tests.common import TransactionCase

class TestUC12WebhookIdempotency(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

        cls.integration_user = cls.env.ref('base.user_admin')
        cls.integration_user.sudo().write({
            'groups_id': [
                (4, cls.env.ref('base.group_system').id),
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

        cls.product = cls.env['product.product'].create({
            'name': 'Test Item',
            'default_code': 'TEST-SKU',
            'type': 'consu',
        })

        cls.sample_payload = json.dumps({
            "event": "order.created",
            "merchant": "12345",
            "data": {
                "id": "SALLA-101",
                "reference_id": "ORD-101",
                "customer": {
                    "first_name": "Test",
                    "last_name": "User",
                    "mobile": "+966500000000",
                },
                "amounts": {
                    "total": {"amount": 100},
                    "tax": {"amount": 15},
                },
                "items": [
                    {
                        "id": "ITEM-1",
                        "product_id": "PROD-1",
                        "sku": "TEST-SKU",
                        "name": "Test Item",
                        "quantity": 1,
                        "amounts": {
                            "total_with_tax": {"amount": 100},
                        }
                    }
                ]
            }
        })

    def test_01_duplicate_webhook_payload(self):
        """Test sending the same webhook payload twice results in duplicate marking and linked records."""
        # First webhook
        event1 = self.env['ecommerce.webhook.event'].create({
            'store_id': self.store.id,
            'raw_payload': self.sample_payload,
        })
        event1._apply_uc03_processing_gate()
        self.assertEqual(event1.processing_status, 'processed')
        self.assertTrue(event1.related_external_order_id.id)

        ext_order = event1.related_external_order_id
        self.assertEqual(ext_order.state, 'ready')
        ext_order.action_create_sale_order()
        self.assertTrue(ext_order.sale_order_id)

        # Second webhook (duplicate)
        event2 = self.env['ecommerce.webhook.event'].create({
            'store_id': self.store.id,
            'raw_payload': self.sample_payload,
        })
        event2._apply_uc03_processing_gate()

        self.assertEqual(event2.processing_status, 'duplicate')
        self.assertEqual(event2.related_external_order_id.id, ext_order.id)
        self.assertEqual(event2.related_partner_id.id, ext_order.partner_id.id)
        self.assertEqual(event2.related_sale_order_id.id, ext_order.sale_order_id.id)

    def test_02_duplicate_webhook_links_existing_sale_order(self):
        """A duplicate delivery links the already imported sale order."""
        event1 = self.env['ecommerce.webhook.event'].create({
            'store_id': self.store.id,
            'raw_payload': self.sample_payload,
        })
        event1._apply_uc03_processing_gate()
        ext_order = event1.related_external_order_id
        ext_order.action_create_sale_order()

        event2 = self.env['ecommerce.webhook.event'].create({
            'store_id': self.store.id,
            'raw_payload': self.sample_payload,
        })
        event2._apply_uc03_processing_gate()

        self.assertEqual(event2.processing_status, 'duplicate')
        self.assertEqual(event2.related_external_order_id.id, ext_order.id)
        self.assertEqual(event2.related_sale_order_id.id, ext_order.sale_order_id.id)
