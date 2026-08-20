from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval


@tagged('post_install', '-at_install')
class TestUC19ReportingManagerViews(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company = cls.env.company

        cls.store = cls.env['ecommerce.store'].create({
            'name': 'UC19 Reporting Store',
            'platform': 'manual_mock',
            'environment': 'mock',
            'company_id': cls.company.id,
        })

        cls.partner = cls.env['res.partner'].create({
            'name': 'UC19 Reporting Customer',
        })

        # Plain, non-ecommerce sale order — must NOT show up in the new reporting view.
        cls.plain_sale_order = cls.env['sale.order'].create({
            'partner_id': cls.partner.id,
        })

        # E-commerce sale order — must show up in the new reporting view.
        cls.ecommerce_sale_order = cls.env['sale.order'].create({
            'partner_id': cls.partner.id,
            'ecommerce_store_id': cls.store.id,
            'ecommerce_external_reference': 'UC19-SO-1',
        })

        # A pure connector user with no Sales-app group at all.
        cls.connector_only_user = cls.env['res.users'].create({
            'name': 'UC19 Connector Only User',
            'login': 'uc19_connector_only_user',
            'email': 'uc19.connector.only@example.com',
            'groups_id': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('ecommerce_connector_base.group_ecommerce_connector_user').id,
            ])],
        })

    def test_01_connector_only_user_can_read_ecommerce_sale_order(self):
        """01. A user with only group_ecommerce_connector_user (no Sales group) can read sale.order."""
        order = self.ecommerce_sale_order.with_user(self.connector_only_user)
        self.assertEqual(order.ecommerce_external_reference, 'UC19-SO-1')

    def test_02_connector_only_user_cannot_write_sale_order(self):
        """02. The new access right is read-only — write must still be denied."""
        order = self.ecommerce_sale_order.with_user(self.connector_only_user)
        with self.assertRaises(AccessError):
            order.write({'ecommerce_payment_status': 'paid'})

    def test_03_connector_only_user_cannot_create_sale_order(self):
        """03. The new access right is read-only — create must still be denied."""
        with self.assertRaises(AccessError):
            self.env['sale.order'].with_user(self.connector_only_user).create({
                'partner_id': self.partner.id,
            })

    def test_04_reporting_action_domain_excludes_non_ecommerce_orders(self):
        """04. action_ecommerce_sale_order's domain must exclude orders with no ecommerce_store_id."""
        action = self.env.ref('ecommerce_connector_base.action_ecommerce_sale_order')
        domain = safe_eval(action.domain or '[]')
        orders = self.env['sale.order'].search(domain)
        self.assertIn(self.ecommerce_sale_order, orders)
        self.assertNotIn(self.plain_sale_order, orders)

    def test_05_external_order_report_action_exposes_pivot_and_graph(self):
        """05. The external-order reporting action must expose pivot and graph view types."""
        action = self.env.ref('ecommerce_connector_base.action_ecommerce_external_order_report')
        view_modes = [m.strip() for m in action.view_mode.split(',')]
        self.assertIn('pivot', view_modes)
        self.assertIn('graph', view_modes)

    def test_06_webhook_event_report_action_exposes_pivot_and_graph(self):
        """06. The webhook-event reporting action must expose pivot and graph view types."""
        action = self.env.ref('ecommerce_connector_base.action_ecommerce_webhook_event_report')
        view_modes = [m.strip() for m in action.view_mode.split(',')]
        self.assertIn('pivot', view_modes)
        self.assertIn('graph', view_modes)

    def test_07_sale_order_report_action_exposes_pivot_and_graph(self):
        """07. The sale-order reporting action must expose pivot and graph view types."""
        action = self.env.ref('ecommerce_connector_base.action_ecommerce_sale_order')
        view_modes = [m.strip() for m in action.view_mode.split(',')]
        self.assertIn('pivot', view_modes)
        self.assertIn('graph', view_modes)

    def test_08_reporting_menu_items_exist_and_point_to_correct_actions(self):
        """08. All three new reporting menu items exist and point at the right actions."""
        menu_report = self.env.ref('ecommerce_connector_base.menu_ecommerce_connector_reporting')
        self.assertTrue(menu_report.exists())

        menu_orders = self.env.ref('ecommerce_connector_base.menu_ecommerce_external_order_report')
        self.assertEqual(
            menu_orders.action.id,
            self.env.ref('ecommerce_connector_base.action_ecommerce_external_order_report').id,
        )

        menu_webhooks = self.env.ref('ecommerce_connector_base.menu_ecommerce_webhook_event_report')
        self.assertEqual(
            menu_webhooks.action.id,
            self.env.ref('ecommerce_connector_base.action_ecommerce_webhook_event_report').id,
        )

        menu_sale_orders = self.env.ref('ecommerce_connector_base.menu_ecommerce_sale_order')
        self.assertEqual(
            menu_sale_orders.action.id,
            self.env.ref('ecommerce_connector_base.action_ecommerce_sale_order').id,
        )
