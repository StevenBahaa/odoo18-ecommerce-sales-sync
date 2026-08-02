{
    "name": "E-commerce Salla Connector",
    "version": "18.0.1.0.0",
    "category": "Sales",
    "summary": "Salla integration layer for E-commerce Connector Base",
    "depends": [
        "ecommerce_connector_base",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/salla_store_views.xml",
        "views/ecommerce_webhook_event_views.xml",
        "views/ecommerce_mock_payload_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
