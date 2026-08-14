from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta
from unittest.mock import patch, MagicMock
import json

from odoo import fields
from odoo.exceptions import UserError, AccessError
from odoo.tests.common import TransactionCase, tagged
from odoo.addons.ecommerce_salla_connector.models.salla_client import (
    SallaAPIError,
    SALLA_API_BASE_URL,
    SALLA_MAX_RESPONSE_BYTES,
    EcommerceSallaClient,
)
from odoo.addons.ecommerce_salla_connector.models.ecommerce_store import (
    EcommerceStore,
)


class MockResponse:
    def __init__(self, status_code=200, json_data=None, headers=None, content=None, is_redirect=False):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.headers = headers or {"Content-Type": "application/json"}
        self._content = content
        self.is_redirect = is_redirect

    @property
    def content(self):
        if self._content is not None:
            return self._content
        return json.dumps(self._json_data).encode("utf-8")

    def json(self):
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            err = requests.exceptions.HTTPError(f"HTTP {self.status_code}")
            err.response = self
            raise err


@tagged("-at_install", "post_install", "ecommerce_salla_connector")
class TestUC17SallaAPIEnrichment(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user_id = cls.env.ref("base.group_user").id
        cls.manager = cls.env["res.users"].create({
            "name": "Salla API Manager",
            "login": "salla_api_manager",
            "groups_id": [
                (4, group_user_id),
                (4, cls.env.ref("ecommerce_connector_base.group_ecommerce_integration_manager").id),
            ],
        })
        cls.user = cls.env["res.users"].create({
            "name": "Salla API User",
            "login": "salla_api_user",
            "groups_id": [
                (4, group_user_id),
                (4, cls.env.ref("ecommerce_connector_base.group_ecommerce_connector_user").id),
            ],
        })
        cls.connector_manager = cls.env["res.users"].create({
            "name": "Salla Connector Manager",
            "login": "salla_connector_manager",
            "groups_id": [
                (4, group_user_id),
                (4, cls.env.ref("ecommerce_connector_base.group_ecommerce_connector_manager").id),
            ],
        })
        cls.company_other = cls.env["res.company"].create({
            "name": "Other Test Company",
        })

    def setUp(self):
        super().setUp()
        self.store = self.env["ecommerce.store"].create({
            "name": "Live Salla Store UC17",
            "platform": "salla",
            "environment": "production",
            "client_id": "client_uc17",
            "client_secret": "secret_uc17",
            "access_token": "valid_token_uc17",
            "refresh_token": "valid_refresh_uc17",
            "oauth_scope": "offline_access orders.read",
            "oauth_token_type": "bearer",
            "access_token_expires_at": fields.Datetime.now() + timedelta(days=10),
            "refresh_token_expires_at": fields.Datetime.now() + relativedelta(months=1),
        })

        self.external_order = self.env["ecommerce.external.order"].create({
            "name": "EXT/SALLA/1001",
            "store_id": self.store.id,
            "external_order_id": "1001",
            "external_order_reference": "REF-1001",
            "customer_name": "Original Customer",
            "customer_phone": "+966500000001",
            "normalized_customer_phone": "966500000001",
            "customer_email": "orig@example.com",
            "currency_id": self.env.company.currency_id.id,
            "total_amount": 150.0,
            "shipping_amount": 20.0,
            "discount_amount": 0.0,
            "tax_amount": 15.0,
            "state": "draft",
            "raw_payload": '{"original": "payload"}',
        })

        # Base mock order details response
        self.valid_order_details = {
            "status": 200,
            "success": True,
            "data": {
                "id": 1001,
                "reference_id": "REF-1001-ENRICHED",
                "date": "2026-08-13 15:30:00",
                "updated_at": "2026-08-13 16:00:00",
                "currency": self.env.company.currency_id.name,
                "status": {
                    "id": 2,
                    "name": "Under Review",
                    "slug": "under_review",
                },
                "customer": {
                    "id": 555,
                    "first_name": "Ahmed",
                    "last_name": "Ali",
                    "mobile": "512345678",
                    "mobile_code": "+966",
                    "email": "ahmed.ali@example.com",
                },
                "amounts": {
                    "total": {"amount": 250.0, "currency": self.env.company.currency_id.name},
                    "shipping_cost": {"amount": 35.0, "currency": self.env.company.currency_id.name},
                    "discounts": {"amount": 15.0, "currency": self.env.company.currency_id.name},
                    "tax": {"amount": 25.0, "currency": self.env.company.currency_id.name},
                },
            },
        }

    # =========================================================================
    # A. Permissions and target eligibility (1-5)
    # =========================================================================

    def test_01_permissions_integration_manager_only(self):
        """Only integration managers may invoke action_enrich_from_salla."""
        with self.assertRaises(AccessError):
            self.external_order.with_user(self.user).action_enrich_from_salla()

        with self.assertRaises(AccessError):
            self.external_order.with_user(self.connector_manager).action_enrich_from_salla()

        with patch.object(EcommerceSallaClient, "_fetch_order_details", return_value=self.valid_order_details["data"]):
            res = self.external_order.with_user(self.manager).action_enrich_from_salla()
            self.assertEqual(res.get("params", {}).get("type"), "success")

    def test_02_mock_mode_rejected(self):
        """Mock environment store orders are rejected before transport."""
        self.store.environment = "mock"
        with self.assertRaises(UserError) as cm:
            self.external_order.with_user(self.manager).action_enrich_from_salla()
        self.assertIn("Mock", str(cm.exception))

    def test_03_ineligible_order_targets_rejected(self):
        """Non-Salla, archived store, imported/cancelled order, linked sale order, missing ID rejected."""
        self.store.active = False
        with self.assertRaises(UserError):
            self.external_order.with_user(self.manager).action_enrich_from_salla()
        self.store.active = True

        sale_order = self.env["sale.order"].create({
            "partner_id": self.env.ref("base.partner_admin").id,
        })
        self.external_order.sale_order_id = sale_order.id
        with self.assertRaises(UserError):
            self.external_order.with_user(self.manager).action_enrich_from_salla()
        self.external_order.sale_order_id = False

        for bad_state in ("imported", "cancelled", "duplicate"):
            self.external_order.state = bad_state
            with self.assertRaises(UserError):
                self.external_order.with_user(self.manager).action_enrich_from_salla()
        self.external_order.state = "draft"

        self.external_order.external_order_id = "   "
        with self.assertRaises(UserError):
            self.external_order.with_user(self.manager).action_enrich_from_salla()

    def test_04_cross_company_access_check(self):
        """Cross-company inaccessible orders raise AccessError."""
        other_store = self.env["ecommerce.store"].create({
            "name": "Other Company Store",
            "platform": "salla",
            "environment": "production",
            "company_id": self.company_other.id,
            "client_id": "client_other",
            "client_secret": "secret_other",
            "access_token": "token_other",
            "refresh_token": "refresh_other",
            "oauth_scope": "offline_access orders.read",
            "access_token_expires_at": fields.Datetime.now() + timedelta(days=10),
            "refresh_token_expires_at": fields.Datetime.now() + relativedelta(months=1),
        })
        other_order = self.env["ecommerce.external.order"].create({
            "name": "EXT/OTHER/COMP",
            "store_id": other_store.id,
            "company_id": self.company_other.id,
            "external_order_id": "9999",
            "currency_id": self.company_other.currency_id.id,
            "state": "draft",
        })
        user_single_company = self.env["res.users"].create({
            "name": "Single Company Manager",
            "login": "single_comp_mgr",
            "company_id": self.env.company.id,
            "company_ids": [(6, 0, [self.env.company.id])],
            "groups_id": [
                (4, self.env.ref("base.group_user").id),
                (4, self.env.ref("ecommerce_connector_base.group_ecommerce_integration_manager").id),
            ],
        })
        with self.assertRaises(AccessError):
            other_order.with_user(user_single_company).action_enrich_from_salla()

    # =========================================================================
    # B. Access-token preflight and UC-16 reuse (6-10)
    # =========================================================================

    def test_06_valid_token_uses_without_refresh(self):
        """Valid token with > 60s expiry does not trigger token refresh."""
        with patch.object(EcommerceStore, "_refresh_salla_token") as mock_refresh:
            token = self.store.with_user(self.manager)._prepare_salla_access_token()
            self.assertEqual(token, "valid_token_uc17")
            mock_refresh.assert_not_called()

    def test_07_expired_or_near_expiry_triggers_refresh_once(self):
        """Missing, expired, or <= 60s expiry triggers _refresh_salla_token once."""
        now = fields.Datetime.now()
        self.store.access_token_expires_at = now + timedelta(seconds=30)

        def mock_refresh_side_effect(store_self):
            store_self.sudo().write({
                "access_token": "refreshed_access_token_uc17",
                "access_token_expires_at": fields.Datetime.now() + timedelta(days=14),
            })

        with patch.object(EcommerceStore, "_refresh_salla_token", side_effect=mock_refresh_side_effect, autospec=True) as mock_ref:
            token = self.store.with_user(self.manager)._prepare_salla_access_token()
            self.assertEqual(token, "refreshed_access_token_uc17")
            mock_ref.assert_called_once()

    def test_08_missing_scope_or_reauth_required_blocks_requests(self):
        """Missing orders.read scope or reauthorization_required makes zero API requests."""
        self.store.oauth_scope = "offline_access products.read"
        with self.assertRaises(UserError) as cm:
            self.store.with_user(self.manager)._prepare_salla_access_token()
        self.assertIn("orders.read", str(cm.exception))

        self.store.oauth_scope = "offline_access orders.read"
        self.store.token_refresh_requires_reauthorization = True
        with self.assertRaises(UserError) as cm:
            self.store.with_user(self.manager)._prepare_salla_access_token()
        self.assertIn("reauthorization", str(cm.exception).lower())

    def test_09_refresh_failure_produces_safe_failure_audit(self):
        """Refresh failure during enrichment records safe failed audit without order mutation."""
        self.store.access_token = False
        with patch.object(EcommerceStore, "_refresh_salla_token", side_effect=UserError("Simulated refresh failure")):
            res = self.external_order.with_user(self.manager).action_enrich_from_salla()
            self.assertEqual(res.get("params", {}).get("type"), "warning")
            self.assertEqual(self.external_order.last_salla_enrichment_status, "failed")
            self.assertEqual(self.external_order.salla_enrichment_count, 1)
            self.assertEqual(self.external_order.customer_name, "Original Customer")

    def test_10_api_401_does_not_retry_or_refresh_automatically(self):
        """Merchant API 401 raises unauthorized and makes no secondary refresh or retry."""
        mock_resp = MockResponse(status_code=401, json_data={"status": 401, "success": False, "error": {"message": "Unauthorized"}})
        with patch("requests.request", return_value=mock_resp) as mock_req, \
             patch.object(EcommerceStore, "_refresh_salla_token") as mock_ref:
            res = self.external_order.with_user(self.manager).action_enrich_from_salla()
            self.assertEqual(res.get("params", {}).get("type"), "warning")
            self.assertEqual(self.external_order.last_salla_enrichment_status, "failed")
            self.assertIn("401", self.external_order.last_salla_enrichment_error)
            mock_ref.assert_not_called()
            mock_req.assert_called_once()

    # =========================================================================
    # C. Transport safety (11-16)
    # =========================================================================

    def test_11_request_transport_headers_and_options(self):
        """Verify request parameters: URL, GET, Bearer, Accept, timeout, allow_redirects=False."""
        mock_resp = MockResponse(status_code=200, json_data=self.valid_order_details)
        with patch("requests.request", return_value=mock_resp) as mock_req:
            client = self.env["ecommerce.salla.client"]
            client.with_user(self.manager)._request(self.store, "GET", "/orders/1001")

            mock_req.assert_called_once()
            args, kwargs = mock_req.call_args
            self.assertEqual(args[0], "GET")
            self.assertEqual(args[1], f"{SALLA_API_BASE_URL}/orders/1001")
            self.assertEqual(kwargs.get("timeout"), (5, 30))
            self.assertFalse(kwargs.get("allow_redirects"))
            headers = kwargs.get("headers", {})
            self.assertEqual(headers.get("Accept"), "application/json")
            self.assertEqual(headers.get("Authorization"), "Bearer valid_token_uc17")

    def test_12_endpoint_and_method_validation(self):
        """Invalid endpoints, non-GET methods are rejected before transport."""
        client = self.env["ecommerce.salla.client"].with_user(self.manager)
        with patch("requests.request") as mock_req:
            with self.assertRaises(SallaAPIError):
                client._request(self.store, "POST", "/orders/1001")

            for bad_ep in ("orders/1001", "//orders/1001", "/orders/../test", "/orders\\test", "/orders#frag", "/orders?query=1"):
                with self.assertRaises(SallaAPIError):
                    client._request(self.store, "GET", bad_ep)

            mock_req.assert_not_called()

    def test_13_order_id_quoting(self):
        """External order ID is safely quoted as a single URL path segment."""
        mock_resp = MockResponse(status_code=200, json_data={
            "status": 200, "success": True, "data": {"id": "ord/123 456"}
        })
        with patch("requests.request", return_value=mock_resp) as mock_req:
            client = self.env["ecommerce.salla.client"].with_user(self.manager)
            client._fetch_order_details(self.store, "ord/123 456")
            args, _ = mock_req.call_args
            self.assertEqual(args[1], f"{SALLA_API_BASE_URL}/orders/ord%2F123%20456")

    def test_14_transport_errors_mapping(self):
        """Redirects, timeouts, connection errors, oversized body map to safe SallaAPIErrors."""
        import requests
        client = self.env["ecommerce.salla.client"].with_user(self.manager)

        mock_redirect = MockResponse(status_code=302, is_redirect=True)
        with patch("requests.request", return_value=mock_redirect):
            with self.assertRaises(SallaAPIError) as cm:
                client._request(self.store, "GET", "/orders/1001")
            self.assertEqual(cm.exception.code, "redirect")

        with patch("requests.request", side_effect=requests.exceptions.Timeout):
            with self.assertRaises(SallaAPIError) as cm:
                client._request(self.store, "GET", "/orders/1001")
            self.assertEqual(cm.exception.code, "timeout")

        with patch("requests.request", side_effect=requests.exceptions.ConnectionError):
            with self.assertRaises(SallaAPIError) as cm:
                client._request(self.store, "GET", "/orders/1001")
            self.assertEqual(cm.exception.code, "connection")

        oversized_content = b"x" * (SALLA_MAX_RESPONSE_BYTES + 10)
        mock_big = MockResponse(status_code=200, content=oversized_content)
        with patch("requests.request", return_value=mock_big):
            with self.assertRaises(SallaAPIError) as cm:
                client._request(self.store, "GET", "/orders/1001")
            self.assertEqual(cm.exception.code, "invalid_response")

    def test_15_secrets_redaction_in_errors(self):
        """Tokens and secrets are never present in error messages or string representations."""
        mock_resp = MockResponse(status_code=500, json_data={"error": "Secret access_token leaked"})
        with patch("requests.request", return_value=mock_resp):
            client = self.env["ecommerce.salla.client"].with_user(self.manager)
            with self.assertRaises(SallaAPIError) as cm:
                client._request(self.store, "GET", "/orders/1001")
            err_msg = str(cm.exception)
            self.assertNotIn("valid_token_uc17", err_msg)
            self.assertNotIn("secret_uc17", err_msg)
            self.assertNotIn("Secret access_token leaked", err_msg)

    def test_16_http_status_codes_mapping(self):
        """400/403/404/422/500/503 map to intended safe codes."""
        client = self.env["ecommerce.salla.client"].with_user(self.manager)
        status_map = {
            403: "forbidden",
            404: "not_found",
            422: "remote_4xx",
            500: "remote_5xx",
            503: "remote_5xx",
        }
        for code, expected_code in status_map.items():
            mock_resp = MockResponse(status_code=code, json_data={"status": code, "success": False})
            with patch("requests.request", return_value=mock_resp):
                with self.assertRaises(SallaAPIError) as cm:
                    client._request(self.store, "GET", "/orders/1001")
                self.assertEqual(cm.exception.code, expected_code)

    # =========================================================================
    # D. Rate limiting (17-23)
    # =========================================================================

    def test_17_rate_limit_headers_persisted(self):
        """Allowlisted rate limit headers update store metadata."""
        headers = {
            "Content-Type": "application/json",
            "X-RateLimit-Limit": "60",
            "X-RateLimit-Remaining": "45",
            "X-RateLimit-Reset": str(int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp())),
            "Retry-After": "30",
        }
        mock_resp = MockResponse(status_code=200, json_data=self.valid_order_details, headers=headers)
        with patch("requests.request", return_value=mock_resp):
            client = self.env["ecommerce.salla.client"].with_user(self.manager)
            client._request(self.store, "GET", "/orders/1001")

            self.assertEqual(self.store.salla_api_rate_limit_limit, 60)
            self.assertEqual(self.store.salla_api_rate_limit_remaining, 45)
            self.assertTrue(self.store.salla_api_rate_limit_reset_at)
            self.assertTrue(self.store.salla_api_retry_after_at)

    def test_18_malformed_rate_headers_ignored(self):
        """Malformed rate headers do not break valid response."""
        headers = {
            "Content-Type": "application/json",
            "X-RateLimit-Limit": "not_an_int",
            "X-RateLimit-Remaining": "invalid",
            "X-RateLimit-Reset": "bad_date",
        }
        mock_resp = MockResponse(status_code=200, json_data=self.valid_order_details, headers=headers)
        with patch("requests.request", return_value=mock_resp):
            client = self.env["ecommerce.salla.client"].with_user(self.manager)
            res = client._request(self.store, "GET", "/orders/1001")
            self.assertTrue(res.get("success"))

    def test_19_429_rate_limited_cooldown(self):
        """429 response stores cooldown timestamp and raises rate_limited."""
        headers = {
            "Content-Type": "application/json",
            "Retry-After": "120",
        }
        mock_resp = MockResponse(status_code=429, json_data={"status": 429, "success": False}, headers=headers)
        with patch("requests.request", return_value=mock_resp):
            client = self.env["ecommerce.salla.client"].with_user(self.manager)
            with self.assertRaises(SallaAPIError) as cm:
                client._request(self.store, "GET", "/orders/1001")
            self.assertEqual(cm.exception.code, "rate_limited")
            self.assertTrue(cm.exception.retry_after_at)

    def test_22_active_cooldown_blocks_requests(self):
        """A call during active cooldown makes zero network requests."""
        self.store.salla_api_retry_after_at = fields.Datetime.now() + timedelta(minutes=5)
        with patch("requests.request") as mock_req:
            client = self.env["ecommerce.salla.client"].with_user(self.manager)
            with self.assertRaises(SallaAPIError) as cm:
                client._request(self.store, "GET", "/orders/1001")
            self.assertEqual(cm.exception.code, "cooldown")
            mock_req.assert_not_called()

    # =========================================================================
    # E. Mapping (24-29)
    # =========================================================================

    def test_24_mapper_order_details_normalization(self):
        """Mapper parses split customer name, mobile code, monetary objects, status object."""
        mapper = self.env["ecommerce.salla.mapper"]
        parsed = mapper._parse_order_details_payload(self.valid_order_details["data"])

        self.assertEqual(parsed["external_order_id"], "1001")
        self.assertEqual(parsed["currency_code"], self.env.company.currency_id.name)
        vals = parsed["update_vals"]
        self.assertEqual(vals["customer_name"], "Ahmed Ali")
        self.assertEqual(vals["customer_phone"], "966512345678")
        self.assertEqual(vals["customer_email"], "ahmed.ali@example.com")
        self.assertEqual(vals["external_customer_id"], "555")
        self.assertEqual(vals["external_status"], "under_review")
        self.assertEqual(vals["total_amount"], 250.0)
        self.assertEqual(vals["shipping_amount"], 35.0)
        self.assertEqual(vals["discount_amount"], 15.0)
        self.assertEqual(vals["tax_amount"], 25.0)

    def test_26_mapper_preserves_explicit_zero_amounts(self):
        """Explicit numeric zero amounts are preserved."""
        data = dict(self.valid_order_details["data"])
        data["amounts"] = {
            "total": 0.0,
            "shipping_cost": 0.0,
            "discounts": 0.0,
            "tax": 0.0,
        }
        mapper = self.env["ecommerce.salla.mapper"]
        parsed = mapper._parse_order_details_payload(data)
        vals = parsed["update_vals"]
        self.assertEqual(vals["total_amount"], 0.0)
        self.assertEqual(vals["shipping_amount"], 0.0)
        self.assertEqual(vals["discount_amount"], 0.0)
        self.assertEqual(vals["tax_amount"], 0.0)

    def test_29_mapper_emits_no_lines_or_forbidden_keys(self):
        """Mapper output contains no line_ids, state, partner_id, or raw_payload."""
        mapper = self.env["ecommerce.salla.mapper"]
        parsed = mapper._parse_order_details_payload(self.valid_order_details["data"])
        vals = parsed["update_vals"]
        forbidden = {"state", "partner_id", "sale_order_id", "line_ids", "raw_payload", "currency_id"}
        self.assertFalse(forbidden.intersection(vals.keys()))

    # =========================================================================
    # F. Enrichment application (30-40)
    # =========================================================================

    def test_30_successful_enrichment_updates_staged_fields_and_audit(self):
        """Successful enrichment updates allowlisted fields and increments audit count."""
        with patch.object(EcommerceSallaClient, "_fetch_order_details", return_value=self.valid_order_details["data"]):
            res = self.external_order.with_user(self.manager).action_enrich_from_salla()
            self.assertEqual(res.get("params", {}).get("type"), "success")

            self.assertEqual(self.external_order.salla_enrichment_count, 1)
            self.assertEqual(self.external_order.last_salla_enrichment_status, "success")
            self.assertEqual(self.external_order.customer_name, "Ahmed Ali")
            self.assertEqual(self.external_order.customer_phone, "966512345678")
            self.assertEqual(self.external_order.normalized_customer_phone, "966512345678")
            self.assertEqual(self.external_order.total_amount, 250.0)
            self.assertEqual(self.external_order.shipping_amount, 35.0)
            self.assertEqual(self.external_order.discount_amount, 15.0)
            self.assertEqual(self.external_order.tax_amount, 25.0)

            # Unchanged fields
            self.assertEqual(self.external_order.state, "draft")
            self.assertFalse(self.external_order.sale_order_id)
            self.assertEqual(self.external_order.raw_payload, '{"original": "payload"}')

    def test_33_returned_id_mismatch_fails_enrichment(self):
        """Returned Salla ID mismatch records failed audit without mutating fields."""
        bad_data = dict(self.valid_order_details["data"])
        bad_data["id"] = 9999
        with patch.object(EcommerceSallaClient, "_fetch_order_details", return_value=bad_data):
            res = self.external_order.with_user(self.manager).action_enrich_from_salla()
            self.assertEqual(res.get("params", {}).get("type"), "warning")
            self.assertEqual(self.external_order.last_salla_enrichment_status, "failed")
            self.assertEqual(self.external_order.customer_name, "Original Customer")

    def test_34_currency_mismatch_fails_enrichment(self):
        """Currency mismatch fails enrichment and preserves staged values."""
        bad_data = dict(self.valid_order_details["data"])
        bad_data["currency"] = "USD"
        with patch.object(EcommerceSallaClient, "_fetch_order_details", return_value=bad_data):
            res = self.external_order.with_user(self.manager).action_enrich_from_salla()
            self.assertEqual(res.get("params", {}).get("type"), "warning")
            self.assertEqual(self.external_order.last_salla_enrichment_status, "failed")
            self.assertEqual(self.external_order.customer_name, "Original Customer")

    def test_35_stale_response_older_than_watermark_fails_enrichment(self):
        """API snapshot older than last_external_update_at skips enrichment."""
        self.external_order.last_external_update_at = fields.Datetime.from_string("2026-08-13 18:00:00")
        stale_data = dict(self.valid_order_details["data"])
        stale_data["updated_at"] = "2026-08-13 15:00:00"

        with patch.object(EcommerceSallaClient, "_fetch_order_details", return_value=stale_data):
            res = self.external_order.with_user(self.manager).action_enrich_from_salla()
            self.assertEqual(res.get("params", {}).get("type"), "warning")
            self.assertEqual(self.external_order.last_salla_enrichment_status, "failed")
            self.assertEqual(self.external_order.customer_name, "Original Customer")

    def test_39_repeat_enrichment_increments_count(self):
        """Repeated enrichment on eligible order increments audit count."""
        with patch.object(EcommerceSallaClient, "_fetch_order_details", return_value=self.valid_order_details["data"]):
            self.external_order.with_user(self.manager).action_enrich_from_salla()
            self.assertEqual(self.external_order.salla_enrichment_count, 1)

            self.external_order.with_user(self.manager).action_enrich_from_salla()
            self.assertEqual(self.external_order.salla_enrichment_count, 2)
