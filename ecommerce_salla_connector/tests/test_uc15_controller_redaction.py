import json

from odoo.addons.ecommerce_connector_base.controllers.ecommerce_webhook_controller import (
    EcommerceWebhookController,
)
from odoo.tests.common import TransactionCase


class TestUC15ControllerRedaction(TransactionCase):

    def test_01_authorize_payload_redacted_at_controller(self):
        """The controller storage helper redacts token-bearing JSON."""
        payload = {
            "event": "app.store.authorize",
            "merchant": "mock-store-ctrl",
            "created_at": "2030-01-01 10:00:00",
            "data": {
                "access_token": "super_secret_access",
                "expires": 1893578400,
                "refresh_token": "super_secret_refresh",
                "scope": "orders.read offline_access",
                "token_type": "bearer"
            }
        }

        stored_payload = EcommerceWebhookController()._prepare_stored_payload(
            json.dumps(payload).encode(), payload
        )

        self.assertNotIn("super_secret_access", stored_payload)
        self.assertNotIn("super_secret_refresh", stored_payload)
        self.assertIn("[REDACTED]", stored_payload)

    def test_02_malformed_payload_omitted(self):
        """Test that malformed JSON payloads do not leak sensitive information in raw_payload fallback."""
        malformed_payload = '{"event": "app.store.authorize", "data": {"access_token": "leak_me"'

        stored_payload = EcommerceWebhookController()._prepare_stored_payload(
            malformed_payload.encode(), None
        )

        self.assertNotIn("leak_me", stored_payload)
        self.assertIn("Malformed payload omitted", stored_payload)
