from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestUC20DemoDataBootstrap(TransactionCase):

    def test_01_missing_sku_and_multicurrency_templates_wired(self):
        """01. The two previously-orphaned sample payloads are now selectable and load
        real file content."""
        Wizard = self.env['ecommerce.mock.payload.wizard']

        missing_sku_content = Wizard._get_sample_payload_content('salla_order_missing_sku')
        self.assertNotEqual(missing_sku_content, "{}")
        self.assertIn('SALLA-ORDER-3001', missing_sku_content)

        multicurrency_content = Wizard._get_sample_payload_content('salla_order_multicurrency_sar')
        self.assertNotEqual(multicurrency_content, "{}")
        self.assertIn('SALLA-ORDER-4001', multicurrency_content)

    def test_02_app_installed_template_wired(self):
        """02. The new salla_app_installed template is selectable and loads real content."""
        Wizard = self.env['ecommerce.mock.payload.wizard']
        content = Wizard._get_sample_payload_content('salla_app_installed')
        self.assertNotEqual(content, "{}")
        self.assertIn('app.installed', content)

    def test_03_bootstrap_creates_demo_store_and_expected_records(self):
        """03. The bootstrap creates one demo store, five webhook events, and three
        external orders in the expected states: imported, pending_mapping, ready."""
        Wizard = self.env['ecommerce.mock.payload.wizard']
        store = Wizard.action_bootstrap_demo_scenario()

        self.assertEqual(store.store_identifier, '999000111')

        events = self.env['ecommerce.webhook.event'].search([
            ('store_id', '=', store.id),
        ])
        self.assertEqual(len(events), 5)

        orders = self.env['ecommerce.external.order'].search([
            ('store_id', '=', store.id),
        ])
        self.assertEqual(len(orders), 3)
        self.assertEqual(
            sorted(orders.mapped('state')),
            sorted(['imported', 'pending_mapping', 'ready']),
        )

    def test_04_bootstrap_is_idempotent(self):
        """04. Calling the bootstrap twice does not create a second demo store or
        duplicate any records."""
        Wizard = self.env['ecommerce.mock.payload.wizard']
        store_first = Wizard.action_bootstrap_demo_scenario()
        store_second = Wizard.action_bootstrap_demo_scenario()

        self.assertEqual(store_first.id, store_second.id)

        stores = self.env['ecommerce.store'].search([
            ('store_identifier', '=', '999000111'),
        ])
        self.assertEqual(len(stores), 1)

        events = self.env['ecommerce.webhook.event'].search([
            ('store_id', '=', store_first.id),
        ])
        self.assertEqual(len(events), 5)

    def test_05_demo_store_receives_sanitized_oauth_tokens(self):
        """05. The OAuth authorize step populates the store with the sanitized
        (non-real) token values from the sample payload -- confirms the authorize
        payload's merchant identifier correctly matched the demo store."""
        Wizard = self.env['ecommerce.mock.payload.wizard']
        store = Wizard.action_bootstrap_demo_scenario()

        self.assertEqual(store.access_token, 'sanitized-access-token-not-real')
        self.assertEqual(store.refresh_token, 'sanitized-refresh-token-not-real')
        self.assertTrue(store.access_token_expires_at)

    def test_06_imported_order_has_a_linked_sale_order(self):
        """06. The salla_order_created demo order actually produced a real sale.order,
        not just an external-order state change."""
        Wizard = self.env['ecommerce.mock.payload.wizard']
        store = Wizard.action_bootstrap_demo_scenario()

        imported_order = self.env['ecommerce.external.order'].search([
            ('store_id', '=', store.id),
            ('state', '=', 'imported'),
        ], limit=1)
        self.assertTrue(imported_order)
        self.assertTrue(imported_order.sale_order_id)
