import hashlib
import hmac
import json
import logging
import re
from datetime import timedelta

from odoo import http , fields
from odoo.http import request

_logger = logging.getLogger(__name__)


class EcommerceWebhookController(http.Controller):

    _SENSITIVE_HEADER_NAMES ={
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-auth-token",
        "x-access-token",
        "x-refresh-token",
    }

    _SENSITIVE_PAYLOAD_KEYS = {
        "access_token",
        "refresh_token",
        "client_secret",
        "webhook_secret",
        "authorization_code",
        "auth_code",
        "oauth_code",
        "token",
        "secret",
    }


    @http.route(
        '/ecommerce/webhook/<string:platform>/<string:store_token>',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False
    )
    def receive_webhook(self, platform, store_token, **kwargs):
        store = self._find_store(platform, store_token)

        if not store:
            return request.make_json_response(
                {"status": "invalid_store"},
                status=404,
            )

        if self._is_rate_limited(store):
            self._log_rate_limited_event(store)
            return request.make_json_response(
                {"status": "rate_limited"},
                status=429,
            )

        raw_body = request.httprequest.get_data() or b""

        signature_valid = True
        if store.environment != "mock":
            signature_valid = self._verify_signature(store, raw_body)
            if not signature_valid:
                self._log_invalid_signature_event(store, raw_body)
                return request.make_json_response(
                    {"status": "invalid_signature"},
                    status=401,
                )

        payload_dict, parsed_payload = self._parse_payload(raw_body)

        try:
            event = self._create_raw_event(
                store=store,
                raw_body=raw_body,
                payload_dict=payload_dict,
                parsed_payload=parsed_payload,
                signature_valid=signature_valid,
                http_status_returned=200,
                processing_status="received",
            )
        except Exception:
            _logger.exception(
                "Failed to store e-commerce webhook event for store id %s.",
                store.id,
            )
            return request.make_json_response(
                {"status": "logging_failed"},
                status=500,
            )

        self._update_last_webhook_received_at(store)

        try:
            event._apply_uc03_processing_gate()
        except Exception as exc:
            _logger.exception(
                "Failed to apply UC-03 processing gate for webhook event id %s.",
                event.id,
            )
            event.sudo().write({
                "processing_status": "failed",
                "error_message": self._safe_error_message(exc),
                "processed_at": fields.Datetime.now(),
            })

        return request.make_json_response(
            {"status": "received"},
            status=200,
        )

    def _find_store(self, platform, store_token):
        return request.env["ecommerce.store"].sudo().search(
            [
                ("platform", "=", platform),
                ("webhook_token", "=", store_token),
                ("active", "=", True),
            ],
            limit=1,
        )

    def _is_rate_limited(self, store):
        if not store.rate_limit_window_seconds or not store.rate_limit_max_events:
            return False

        cutoff = fields.Datetime.now() - timedelta(
            seconds=store.rate_limit_window_seconds
        )

        event_count = request.env["ecommerce.webhook.event"].sudo().search_count([
            ("store_id", "=", store.id),
            ("create_date", ">=", cutoff),
        ])

        return event_count >= store.rate_limit_max_events

    def _verify_signature(self, store, raw_body):
        if not store.webhook_secret:
            return False

        received_signature = self._get_received_signature()
        if not received_signature:
            return False

        expected_signature = hmac.new(
            store.webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected_signature, received_signature)

    def _get_received_signature(self):
        headers = request.httprequest.headers
        return (
            headers.get("X-Salla-Signature")
            or headers.get("x-salla-signature")
            or ""
        )

    def _parse_payload(self, raw_body):
        if not raw_body:
            return {}, {}

        try:
            decoded_body = raw_body.decode("utf-8")
            parsed_payload = json.loads(decoded_body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}, None

        if isinstance(parsed_payload, dict):
            return parsed_payload, parsed_payload

        return {}, parsed_payload

    def _create_raw_event(
        self,
        store,
        raw_body,
        payload_dict,
        parsed_payload,
        signature_valid,
        http_status_returned,
        processing_status,
    ):
        return request.env["ecommerce.webhook.event"].sudo().create({
            "store_id": store.id,
            "company_id": store.company_id.id,
            "event_type": self._extract_event_type(payload_dict),
            "external_event_id": self._extract_external_event_id(payload_dict),
            "external_order_id": self._extract_external_order_id(payload_dict),
            "raw_payload": self._prepare_stored_payload(raw_body, parsed_payload),
            "headers_json": self._prepare_stored_headers(),
            "signature_valid": signature_valid,
            "processing_status": processing_status,
            "http_status_returned": http_status_returned,
        })

    def _log_rate_limited_event(self, store):
        try:
            request.env["ecommerce.webhook.event"].sudo().create({
                "store_id": store.id,
                "company_id": store.company_id.id,
                "event_type": "rate_limited",
                "headers_json": self._prepare_stored_headers(),
                "signature_valid": False,
                "processing_status": "rate_limited",
                "http_status_returned": 429,
                "error_message": "Webhook request rejected by per-store rate limit.",
                "processed_at": fields.Datetime.now(),
            })
        except Exception:
            _logger.exception(
                "Failed to log rate-limited webhook event for store id %s.",
                store.id,
            )

    def _log_invalid_signature_event(self, store, raw_body):
        payload_dict, parsed_payload = self._parse_payload(raw_body)

        try:
            request.env["ecommerce.webhook.event"].sudo().create({
                "store_id": store.id,
                "company_id": store.company_id.id,
                "event_type": self._extract_event_type(payload_dict),
                "external_event_id": self._extract_external_event_id(payload_dict),
                "external_order_id": self._extract_external_order_id(payload_dict),
                "raw_payload": self._prepare_stored_payload(raw_body, parsed_payload),
                "headers_json": self._prepare_stored_headers(),
                "signature_valid": False,
                "processing_status": "invalid_signature",
                "http_status_returned": 401,
                "error_message": "Invalid webhook signature.",
                "processed_at": fields.Datetime.now(),
            })
        except Exception:
            _logger.exception(
                "Failed to log invalid-signature webhook event for store id %s.",
                store.id,
            )

    def _update_last_webhook_received_at(self, store):
        try:
            store.sudo().write({
                "last_webhook_received_at": fields.Datetime.now(),
            })
        except Exception:
            _logger.exception(
                "Failed to update last webhook timestamp for store id %s.",
                store.id,
            )

    def _prepare_stored_headers(self):
        safe_headers = {}

        for key, value in request.httprequest.headers.items():
            key_lower = key.lower()

            if key_lower in self._SENSITIVE_HEADER_NAMES:
                safe_headers[key] = "[REDACTED]"
            else:
                safe_headers[key] = value

        return json.dumps(
            safe_headers,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )

    def _prepare_stored_payload(self, raw_body, parsed_payload):
        decoded_body = raw_body.decode("utf-8", errors="replace") if raw_body else ""

        if parsed_payload is not None:
            redacted_payload, changed = self._redact_payload(parsed_payload)
            if changed:
                return json.dumps(
                    redacted_payload,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )

        return self._redact_text(decoded_body)

    def _redact_payload(self, value):
        changed = False

        if isinstance(value, dict):
            redacted = {}
            for key, item_value in value.items():
                key_string = str(key)
                key_lower = key_string.lower()

                if key_lower in self._SENSITIVE_PAYLOAD_KEYS:
                    redacted[key] = "[REDACTED]"
                    changed = True
                    continue

                redacted_value, child_changed = self._redact_payload(item_value)
                redacted[key] = redacted_value
                changed = changed or child_changed

            return redacted, changed

        if isinstance(value, list):
            redacted_list = []
            for item in value:
                redacted_item, child_changed = self._redact_payload(item)
                redacted_list.append(redacted_item)
                changed = changed or child_changed

            return redacted_list, changed

        return value, False

    def _redact_text(self, text):
        if not text:
            return text

        sensitive_keys_pattern = "|".join(
            re.escape(key) for key in sorted(self._SENSITIVE_PAYLOAD_KEYS)
        )

        json_like_pattern = re.compile(
            r'("(?P<key>%s)"\s*:\s*)"[^"]*"'
            % sensitive_keys_pattern,
            flags=re.IGNORECASE,
        )

        return json_like_pattern.sub(
            lambda match: '%s"[REDACTED]"' % match.group(1),
            text,
        )

    def _safe_error_message(self, exception):
        return self._redact_text(str(exception or ""))[:1000]

    def _extract_event_type(self, payload_dict):
        if not isinstance(payload_dict, dict):
            return "unknown"

        return (
            payload_dict.get("event")
            or payload_dict.get("event_type")
            or payload_dict.get("type")
            or "unknown"
        )

    def _extract_external_event_id(self, payload_dict):
        if not isinstance(payload_dict, dict):
            return False

        external_event_id = (
            payload_dict.get("id")
            or payload_dict.get("event_id")
            or payload_dict.get("uuid")
        )

        return str(external_event_id) if external_event_id else False

    def _extract_external_order_id(self, payload_dict):
        if not isinstance(payload_dict, dict):
            return False

        data = payload_dict.get("data")
        if not isinstance(data, dict):
            return False

        order = data.get("order")
        if isinstance(order, dict):
            order_id = order.get("id") or order.get("order_id")
            if order_id:
                return str(order_id)

        order_id = (
            data.get("id")
            or data.get("order_id")
            or data.get("order_reference")
        )

        return str(order_id) if order_id else False
