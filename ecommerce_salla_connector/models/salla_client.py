import email.utils
from datetime import datetime, timezone, timedelta
import urllib.parse
import requests

from odoo import models, fields, _
from odoo.exceptions import UserError

SALLA_API_BASE_URL = "https://api.salla.dev/admin/v2"
SALLA_CONNECT_TIMEOUT = 5
SALLA_READ_TIMEOUT = 30
SALLA_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class SallaAPIError(UserError):
    """Safe exception class for Salla API client errors.

    Prevents raw remote payloads, exception strings, or tokens from being
    exposed in tracebacks, user interfaces, or logs.
    """
    def __init__(self, message, code="invalid_response", retry_after_at=None):
        super().__init__(message)
        self.code = code
        self.retry_after_at = retry_after_at

    def __str__(self):
        return str(self.args[0]) if self.args else ""


class EcommerceSallaClient(models.AbstractModel):
    _name = "ecommerce.salla.client"
    _description = "Salla API Client"

    def _ensure_salla_store(self, store):
        if not store or store.platform != "salla":
            raise UserError(_("This operation requires a Salla store."))
        return True

    def _parse_retry_after_header(self, raw_value, now_dt):
        if not raw_value:
            return None
        raw_str = str(raw_value).strip()
        try:
            seconds = int(raw_str)
            if seconds < 1:
                seconds = 1
            elif seconds > 3600:
                seconds = 3600
            return now_dt + timedelta(seconds=seconds)
        except (ValueError, TypeError):
            pass

        try:
            parsed_http = email.utils.parsedate_to_datetime(raw_str)
            if parsed_http.tzinfo:
                parsed_utc = parsed_http.astimezone(timezone.utc).replace(tzinfo=None)
            else:
                parsed_utc = parsed_http
            delta_sec = (parsed_utc - now_dt).total_seconds()
            if delta_sec < 1:
                delta_sec = 1
            elif delta_sec > 3600:
                delta_sec = 3600
            return now_dt + timedelta(seconds=delta_sec)
        except Exception:
            return None

    def _request(self, store, method, endpoint, *, params=None):
        """Execute a secure GET-only Merchant API request to Salla."""
        self._ensure_salla_store(store)
        store._ensure_salla_api_caller()

        if method != "GET":
            raise SallaAPIError(
                _("Unsupported HTTP method for Salla API request."),
                code="configuration"
            )

        if (
            not isinstance(endpoint, str)
            or not endpoint.startswith("/")
            or endpoint.startswith("//")
            or "\\" in endpoint
            or ".." in endpoint
            or "#" in endpoint
            or "?" in endpoint
        ):
            raise SallaAPIError(
                _("Invalid Salla API endpoint path."),
                code="configuration"
            )

        now = fields.Datetime.now()
        if store.salla_api_retry_after_at and store.salla_api_retry_after_at > now:
            raise SallaAPIError(
                _("Salla API request cooldown active until %s.") % fields.Datetime.to_string(store.salla_api_retry_after_at),
                code="cooldown",
                retry_after_at=store.salla_api_retry_after_at
            )

        token = store._prepare_salla_access_token()

        url = f"{SALLA_API_BASE_URL}{endpoint}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }

        try:
            response = requests.request(
                "GET",
                url,
                headers=headers,
                params=params or None,
                timeout=(SALLA_CONNECT_TIMEOUT, SALLA_READ_TIMEOUT),
                allow_redirects=False,
            )
        except requests.exceptions.Timeout:
            raise SallaAPIError(_("Salla API request timed out."), code="timeout")
        except requests.exceptions.ConnectionError:
            raise SallaAPIError(_("Could not connect to Salla API."), code="connection")
        except requests.exceptions.RequestException:
            raise SallaAPIError(_("Salla API network error."), code="connection")

        if response.is_redirect or (300 <= response.status_code < 400):
            raise SallaAPIError(
                _("Unexpected redirect response from Salla API."),
                code="redirect"
            )

        # Parse allowlisted rate limit headers
        last_salla_api_call_at = now
        salla_api_rate_limit_limit = False
        salla_api_rate_limit_remaining = False
        salla_api_rate_limit_reset_at = False
        salla_api_retry_after_at = False

        if "X-RateLimit-Limit" in response.headers:
            try:
                salla_api_rate_limit_limit = int(str(response.headers["X-RateLimit-Limit"]).strip())
            except Exception:
                pass

        if "X-RateLimit-Remaining" in response.headers:
            try:
                salla_api_rate_limit_remaining = int(str(response.headers["X-RateLimit-Remaining"]).strip())
            except Exception:
                pass

        if "X-RateLimit-Reset" in response.headers:
            try:
                reset_epoch = int(str(response.headers["X-RateLimit-Reset"]).strip())
                reset_dt = datetime.fromtimestamp(reset_epoch, tz=timezone.utc).replace(tzinfo=None)
                if 0 <= (reset_dt - now).total_seconds() <= 3600:
                    salla_api_rate_limit_reset_at = reset_dt
            except Exception:
                pass

        if "Retry-After" in response.headers:
            salla_api_retry_after_at = self._parse_retry_after_header(
                response.headers["Retry-After"], now
            )

        if response.status_code == 429 and not salla_api_retry_after_at:
            salla_api_retry_after_at = now + timedelta(seconds=60)

        # Update metadata on store before handling error status codes
        usage_metadata = {
            "last_salla_api_call_at": last_salla_api_call_at,
            "salla_api_rate_limit_limit": salla_api_rate_limit_limit,
            "salla_api_rate_limit_remaining": salla_api_rate_limit_remaining,
            "salla_api_rate_limit_reset_at": salla_api_rate_limit_reset_at,
            "salla_api_retry_after_at": salla_api_retry_after_at,
        }
        store._update_salla_api_usage_metadata(usage_metadata)

        status_code = response.status_code
        if status_code == 401:
            raise SallaAPIError(
                _("Salla API authentication failed (401 Unauthorized)."),
                code="unauthorized"
            )
        elif status_code == 403:
            raise SallaAPIError(
                _("Salla API request forbidden (403 Forbidden)."),
                code="forbidden"
            )
        elif status_code == 404:
            raise SallaAPIError(
                _("Requested Salla resource not found (404 Not Found)."),
                code="not_found"
            )
        elif status_code == 429:
            raise SallaAPIError(
                _("Salla API rate limit exceeded (429 Too Many Requests)."),
                code="rate_limited",
                retry_after_at=salla_api_retry_after_at
            )
        elif 400 <= status_code < 500:
            raise SallaAPIError(
                _("Salla API client error (HTTP %d).") % status_code,
                code="remote_4xx"
            )
        elif status_code >= 500:
            raise SallaAPIError(
                _("Salla API server error (HTTP %d).") % status_code,
                code="remote_5xx"
            )

        # Body size checks
        content_length_header = response.headers.get("Content-Length")
        if content_length_header:
            try:
                cl_val = int(content_length_header)
                if cl_val > SALLA_MAX_RESPONSE_BYTES:
                    raise SallaAPIError(
                        _("Salla API response exceeded maximum allowed size."),
                        code="invalid_response"
                    )
            except ValueError:
                pass

        if len(response.content) > SALLA_MAX_RESPONSE_BYTES:
            raise SallaAPIError(
                _("Salla API response exceeded maximum allowed size."),
                code="invalid_response"
            )

        try:
            payload = response.json()
        except ValueError:
            raise SallaAPIError(
                _("Salla API returned an invalid JSON response."),
                code="invalid_json"
            )

        if not isinstance(payload, dict):
            raise SallaAPIError(
                _("Salla API response is not a valid JSON object."),
                code="invalid_response"
            )

        if payload.get("success") is not True:
            raise SallaAPIError(
                _("Salla API response indicated unsuccessful request."),
                code="invalid_response"
            )

        resp_status = payload.get("status")
        if type(resp_status) is not int or not (200 <= resp_status < 300):
            raise SallaAPIError(
                _("Salla API response status code is not 2xx."),
                code="invalid_response"
            )

        if "data" not in payload:
            raise SallaAPIError(
                _("Salla API response is missing data property."),
                code="invalid_response"
            )

        return payload

    def _fetch_order_details(self, store, external_order_id):
        """Fetch full order details for a given external order ID from Salla."""
        if not external_order_id or not isinstance(external_order_id, (str, int)):
            raise SallaAPIError(
                _("External order ID must be a non-empty string or integer."),
                code="configuration"
            )

        order_id_str = str(external_order_id).strip()
        if not order_id_str or len(order_id_str) > 128 or any(c < " " or c == "\x7f" for c in order_id_str):
            raise SallaAPIError(
                _("External order ID is invalid."),
                code="configuration"
            )

        quoted_id = urllib.parse.quote(order_id_str, safe="")
        envelope = self._request(store, "GET", f"/orders/{quoted_id}")

        data = envelope.get("data")
        if not isinstance(data, dict):
            raise SallaAPIError(
                _("Salla order details data is not a dictionary."),
                code="invalid_response"
            )

        if str(data.get("id", "")).strip() != order_id_str:
            raise SallaAPIError(
                _("Returned Salla order ID does not match the requested order ID."),
                code="invalid_response"
            )

        return data

    def _refresh_oauth_token(self, client_id, client_secret, refresh_token):
        url = "https://accounts.salla.sa/oauth2/token"
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        try:
            response = requests.post(url, data=data, timeout=(5, 30), allow_redirects=False)
            if getattr(response, "is_redirect", False) or (
                isinstance(getattr(response, "status_code", None), int)
                and (300 <= response.status_code < 400)
            ):
                raise UserError(_("Unexpected redirect response from Salla token endpoint."))
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            # Mask the exception because it might contain token strings in URL/params.
            # Only return the HTTP status code or a safe message.
            status_code = getattr(e.response, "status_code", "Unknown")
            raise UserError(_(f"Salla token refresh request failed (Status: {status_code})."))
        except ValueError:
            raise UserError(_("Salla returned an invalid JSON response during token refresh."))
