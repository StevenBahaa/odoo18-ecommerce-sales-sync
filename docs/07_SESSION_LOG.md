# Session Log

Append one entry per material coding, investigation, or documentation session. Keep entries factual and short enough for the next engineer or AI agent to act on.

## Entry template

### Date

YYYY-MM-DD

### Goal

What the session was intended to accomplish.

### Work completed

- Item completed.

### Files modified

- <code>relative/path</code> — purpose of the change.

### Important decisions

- Decision and rationale. Link to [08_DECISIONS.md](08_DECISIONS.md) when it is architectural.

### Problems discovered

- Confirmed issue, affected behavior, and evidence.

### Risks

- Remaining uncertainty, migration concern, security concern, or test gap.

### Validation

- Commands/tests run and outcome.
- Checks not run, with reason.

### Next recommended task

The smallest high-value follow-up.

### Questions for next session

- Material unanswered question, or “None.”

## 2026-07-19 — Documentation baseline

### Goal

Create repository-derived long-term documentation and AI collaboration guidance without changing application source.

### Work completed

- Added the documentation system under <code>docs/</code>.
- Recorded the implementation through UC-13 and the UC-14 next-step status.
- Documented known documentation drift and deferred live integration/deployment work.

### Files modified

- <code>docs/01_PROJECT_CONTEXT.md</code> through <code>docs/12_AI_HANDOFF_TEMPLATE.md</code> — initial documentation baseline.

### Important decisions

- Current code, tests, and Git history are treated as the status source of truth when ignored/local plans or README content lag.

### Problems discovered

- Existing README and TEST_CASES content is stale relative to UC-13.

### Risks

- Production deployment and real Salla OAuth/API behavior are not established by this repository.

### Validation

- Documentation files reviewed with Git diff checks.
- Application tests were not rerun because this session changes documentation only.

### Next recommended task

Plan UC-14 in the ignored <code>docs/.plans/</code> workflow, then implement only after approval.

### Questions for next session

- Confirm the desired UC-14 event-ordering semantics against the Salla payload contract.

## 2026-07-19 — UC-14 implementation: external order status updates

### Goal

Implement Salla `order.updated` handling: replace the placeholder handler with a real partial-update mapper, per-order watermark ordering, row-lock serialization, and safe mirroring to linked sale orders. Deliver focused tests covering all ordering/safety scenarios.

### Work completed

- Added `last_external_update_at` (Datetime, readonly, tracking) and `last_external_update_event_id` (Char, readonly) watermark fields to `ecommerce.external.order`.
- Added both fields to the "Statuses" group in `ecommerce_external_order_views.xml`.
- Added `_parse_partial_update_payload()` to `EcommerceSallaMapper`: strict partial-update parser that emits only explicitly present, valid fields; explicit zero amounts accepted; omitted fields produce no key; returns `external_order_id`, `external_event_time`, `currency_code`, `update_vals`, and `event_id`.
- Replaced `_process_salla_order_updated_placeholder()` with `_process_salla_order_updated()` in `EcommerceWebhookEvent` (Salla addon):
  - validates event time and non-empty `update_vals`;
  - looks up the staged order by store + external order ID;
  - populates event relations (`related_external_order_id`, `related_partner_id`, `related_sale_order_id`);
  - parks mismatched-currency monetary updates without mutation;
  - acquires `FOR UPDATE NOWAIT` row lock and reloads watermark;
  - applies full ordering matrix (newer → apply; older → `pending_review`; same+same ID → `duplicate`; same+different ID → `pending_review`);
  - writes only accepted fields + watermark values in a savepoint;
  - mirrors `payment_status` and `fulfillment_status` to linked `sale.order` connector fields when present;
  - never writes `state`, `partner_id`, `line_ids`, `sale_order_id`, `currency_id`, or `raw_payload`.
- Added `ecommerce_salla_connector/tests/test_uc14_order_status_updates.py` with 12 focused test cases.
- Imported the new test module in `ecommerce_salla_connector/tests/__init__.py`.
- Updated `docs/02_ARCHITECTURE.md`, `docs/05_CURRENT_STATUS.md`, `docs/06_ROADMAP.md`, `docs/08_DECISIONS.md` (ADR-008 added).

### Files modified

- `ecommerce_connector_base/models/ecommerce_external_order.py` — two watermark fields.
- `ecommerce_connector_base/views/ecommerce_external_order_views.xml` — two watermark fields in Statuses group.
- `ecommerce_salla_connector/models/salla_mapper.py` — `_parse_partial_update_payload()`.
- `ecommerce_salla_connector/models/ecommerce_webhook_event.py` — `_process_salla_order_updated()` replaces placeholder; dispatch updated.
- `ecommerce_salla_connector/tests/test_uc14_order_status_updates.py` — created.
- `ecommerce_salla_connector/tests/__init__.py` — UC-14 test import added.
- `docs/02_ARCHITECTURE.md`, `docs/05_CURRENT_STATUS.md`, `docs/06_ROADMAP.md`, `docs/08_DECISIONS.md` — updated.

### Important decisions

- Used a per-order watermark + row lock instead of a global webhook-event uniqueness constraint. See ADR-008.
- Dedicated partial-update mapper rather than reusing the creation-oriented `_parse_order_payload`; omitted fields produce no key (cannot be cleared).
- Monetary updates require matching currency; mismatch parks the entire event atomically.
- `raw_payload` on the staged order is never overwritten; update payloads are audited via their redacted `ecommerce.webhook.event` records.
- No `sudo()` fallback for staged order or sale order writes; integration user permission failures must roll back.

### Problems discovered

- Test `setUpClass` initially used a custom company and `secret_key` on store creation, which triggered the `_ensure_integration_manager` guard. Fixed by following the UC-12/13 pattern: use `env.company` and `base.user_admin`, create the store without sensitive fields, write `integration_user_id` separately via the integration manager user.
- Event creation in tests used a non-existent `event_name` field (correct field is `event_type`, which is populated automatically). Fixed by omitting the field and only passing `store_id` + `raw_payload`.

### Risks

- Salla's `created_at` / `updated_at` timestamp semantics are assumed to represent event emission order. This is stated as an unverified assumption; ambiguous timestamps are parked for review rather than silently accepted.
- `FOR UPDATE NOWAIT` raises an exception under lock contention; the processing gate records this as `failed`. If high concurrency is expected, consider `FOR UPDATE SKIP LOCKED` with a retry or queue design.

### Validation

Ran on 2026-07-19 against `ecommerce_sales_sync_dev`:

```
python C:\odoo18\odoo-bin -c C:\odoo18\conf\odoo.conf -d ecommerce_sales_sync_dev \
  -u ecommerce_connector_base,ecommerce_salla_connector \
  --test-enable --test-tags /ecommerce_salla_connector:TestUC14OrderStatusUpdates \
  --stop-after-init --no-http --log-level=error
```

Result: **12/12 tests passed, 0 failures, 0 errors.**

```
python C:\odoo18\odoo-bin -c C:\odoo18\conf\odoo.conf -d ecommerce_sales_sync_dev \
  -u ecommerce_connector_base,ecommerce_salla_connector \
  --test-enable --test-tags /ecommerce_connector_base:TestUC12SaleOrderIdempotency,/ecommerce_connector_base:TestUC13ManualRetry,/ecommerce_salla_connector:TestUC12WebhookIdempotency,/ecommerce_salla_connector:TestUC13WebhookRetry \
  --stop-after-init --no-http --log-level=error
```

Result: **Base and Salla UC-12/13 regression clean, 0 failures, 0 errors.**

Not run: live Salla payload capture, Mock Lab manual exercise, `git diff --check`.

### Next recommended task

Plan and implement UC-15 (Salla OAuth authorization token ingest).

### Questions for next session

- What is the exact shape of Salla's live `order.updated` payload? Are `data.updated_at` and `data.created_at` always present?
- Does the `order.authorize` payload shape match the bundled sample exactly, or does it need re-verification before UC-15 starts?

## 2026-08-02 — UC-15 implementation: OAuth authorization

### Goal

Implement Salla `app.store.authorize` handling: parse and validate OAuth payloads, safely lock and ingest tokens, enforce replay ordering, and prevent `raw_payload` credential leakage.

### Work completed

- Created mock payload with valid timestamps.
- Added `_apply_salla_authorization_credentials()` in Salla store extension to narrow `sudo()` credential writes.
- Fixed `_ensure_integration_manager()` to respect `self.env.su`.
- Refactored processing gate to accept `processing_payload` dynamically to decouple in-memory JSON from database `raw_payload`.
- Implemented `app.store.authorize` and `app.updated` handlers with token unpacking and `FOR UPDATE` lock.
- Blocked retry logic explicitly for authorization payloads.
- Added `test_uc15_oauth_authorization.py` covering success, rejection, cross-store, ordering, and retry rules.
- Documented ADR-009 for the ephemeral processing payload pattern.

### Files modified

- `ecommerce_connector_base/models/ecommerce_store.py` — `_ensure_integration_manager` `sudo` fix.
- `ecommerce_salla_connector/models/ecommerce_store.py` — `_apply_salla_authorization_credentials` helper.
- `ecommerce_salla_connector/models/salla_mapper.py` — `_parse_authorize_payload` token and scope validation.
- `ecommerce_salla_connector/models/ecommerce_webhook_event.py` — Authorization event handler and retry override.
- `ecommerce_connector_base/models/ecommerce_webhook_event.py` — `processing_payload` propagation.
- `ecommerce_salla_connector/tests/test_uc15_oauth_authorization.py` — 6 new tests.
- Documentation under `docs/`.

### Important decisions

- Pass unredacted payload dictionary as `processing_payload` parameter to avoid unredacted secrets touching the `raw_payload` database column (ADR-009).
- Run store credential writes via narrow `sudo()` helper rather than executing the entire event as a superuser.

### Problems discovered

- `has_group` ignores `self.env.su`, meaning `_ensure_integration_manager` blocked `sudo()` writes for integration users. Fixed by explicitly short-circuiting on `self.env.su`.
- Salla Mock Lab's bundled timestamp resolved to the exact same second for `created_at` and `expires`, which was correctly rejected by the mapper.

### Risks

- Expiration calculations use `dateutil.relativedelta(months=1)`. Real Salla token logic might differ slightly.

### Validation

- `test_uc15_oauth_authorization.py` passes (6/6).

### Next recommended task

Plan and implement UC-16 (Token Refresh Locking).

## 2026-08-02 — UC-15 review fixes

### Changes

- Restricted transient, unredacted payload use to `app.store.authorize`; all ordinary Salla events now parse the persisted redacted audit payload.
- Restored normal integration-user access checks for routine webhook-event writes. The credential helper remains the only narrow `sudo()` path.
- Added regression coverage for nested order-line redaction, missing integration users, newer credential rotation, `app.updated`, direct credential-write denial, and no-transient-data reprocessing.
- Restored the UC-14 roadmap entry and synchronized the UC-15 status/decision documentation.

### Validation

Ran on 2026-08-02 against `ecommerce_sales_sync_dev`:

```
python C:\odoo18\odoo-bin -c C:\odoo18\conf\odoo.conf -d ecommerce_sales_sync_dev -u ecommerce_connector_base,ecommerce_salla_connector --test-enable --test-tags /ecommerce_salla_connector:TestUC15OAuthAuthorization --stop-after-init --no-http --log-level=error
```

Result: **12/12 tests passed, 0 failures, 0 errors.**

## 2026-08-02 — UC-15 test-stability fixes

### Changes

- Made the newer-authorization fixture relative to the current time so it
  exercises a genuinely newer event.
- Replaced the unstable local `HttpCase` with deterministic tests of the
  controller's exact stored-payload redaction helper for valid and malformed
  bodies. Public-route behavior remains a manual smoke check in this setup.
- Removed trailing whitespace reported by `git diff --check`.

### Validation

Ran the two UC-15 test classes with `--no-http` against
`ecommerce_sales_sync_dev`.

Result: **14/14 tests passed, 0 failures, 0 errors.**

## 2026-08-02 — UC-15 final coverage fixes

### Changes

- Mock Lab now refreshes the loaded authorization sample's issue and expiry
  timestamps, preventing the bundled sample from expiring in 2030.
- Added regression tests for same-merchant cross-company protection and full
  OAuth-field rollback when the credential write fails.
- Replaced the deprecated Odoo sample-resource lookup with the Odoo 18
  `file_path()` helper.

### Validation

Ran the UC-15 model and controller-helper test classes with `--no-http`.
The local HTTP server test harness remains unsuitable for public-route testing;
that route requires the documented manual smoke check.

Result: **17/17 tests passed, 0 failures, 0 errors.**

## Session 2026-08-02 (UC-16)

**Goal:** Implement UC-16 Token Refresh Lock, Expiry Warnings & Credential Safety UX.

**Actions:**
- Rewrote ecommerce_salla_connector/models/ecommerce_store.py to add token_refresh_requires_reauthorization, last_token_refresh_error, oauth_credential_state, and oauth_credential_warning.
- Implemented _claim_salla_refresh_token using dedicated cursor and FOR UPDATE NOWAIT to lock the store for refresh.
- Implemented _refresh_salla_token orchestrator and strict response parser _parse_salla_refresh_response.
- Added action_refresh_salla_token button to the Salla store view.
- Added daily ir.cron task to check for expiring tokens and schedule mail.activity warnings for integration managers.
- Added 15 focused tests in test_uc16_token_refresh.py (all passed).
- Updated documentation.

**Outcome:**
UC-16 successfully implemented and verified. All 15 targeted tests pass.

## 2026-08-13 — UC-17 implementation: Salla API client and optional order enrichment

### Goal

Implement the Salla API client (`EcommerceSallaClient`) and manual order detail enrichment (`action_enrich_from_salla()`) with token preflight, single-use refresh token locking, safe credential redaction, rate-limit cooldown persistence, and atomic row-locked stale-response protection.

### Work completed

- Implemented `SallaAPIError(UserError)` masking raw remote payloads, exception strings, tokens, and credentials in user interfaces, logs, and error strings.
- Implemented `EcommerceSallaClient._request()` for GET-only Salla Merchant API calls (`https://api.salla.dev/admin/v2`), enforcing URL path validation, token preflight via `store._prepare_salla_access_token()`, allowlisted rate-limit header parsing (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After`), and 2 MiB response size limit.
- Implemented `EcommerceSallaClient._fetch_order_details()` with URL segment quoting (`urllib.parse.quote(..., safe="")`) and ID verification.
- Added 5 rate-limiting and audit metadata fields to `ecommerce.store` protected by `_check_sensitive_field_access()`: `last_salla_api_call_at`, `salla_api_rate_limit_limit`, `salla_api_rate_limit_remaining`, `salla_api_rate_limit_reset_at`, `salla_api_retry_after_at`.
- Implemented `_ensure_salla_api_caller()`, `_update_salla_api_usage_metadata()`, and `_prepare_salla_access_token()` with single-use refresh token preflight (refreshing if expired or within 60s of expiry).
- Implemented pure `EcommerceSallaMapper._parse_order_details_payload()` normalizing customer name (first/last join), phone code prefixing, status dictionary extraction, and amount parsing with explicit zero amount preservation.
- Created `ecommerce_salla_connector/models/ecommerce_external_order.py` extending `ecommerce.external.order` with `salla_enrichment_count`, `last_salla_enriched_at`, `last_salla_enriched_by_id`, `last_salla_enrichment_status`, and `last_salla_enrichment_error`.
- Implemented `action_enrich_from_salla()` with `group_ecommerce_integration_manager` authorization, row locking (`FOR UPDATE NOWAIT`), stale-response protection against `last_external_update_at`, and currency check.
- Created `ecommerce_salla_connector/views/ecommerce_external_order_views.xml` adding the "Enrich from Salla" button and Salla Enrichment audit tab.
- Added 27 focused unit tests in `ecommerce_salla_connector/tests/test_uc17_salla_api_enrichment.py`.
- Documented ADR-011 in `docs/08_DECISIONS.md`.

### Files modified

- `ecommerce_salla_connector/models/salla_client.py` — `SallaAPIError`, `_request()`, `_fetch_order_details()`.
- `ecommerce_salla_connector/models/ecommerce_store.py` — rate metadata fields, `_prepare_salla_access_token()`, `_update_salla_api_usage_metadata()`.
- `ecommerce_salla_connector/models/salla_mapper.py` — `_parse_order_details_payload()`.
- `ecommerce_salla_connector/models/ecommerce_external_order.py` — model extension, audit fields, `action_enrich_from_salla()`.
- `ecommerce_salla_connector/models/__init__.py` — import `ecommerce_external_order`.
- `ecommerce_salla_connector/views/ecommerce_external_order_views.xml` — created view extension.
- `ecommerce_salla_connector/__manifest__.py` — added view XML to data.
- `ecommerce_salla_connector/tests/test_uc17_salla_api_enrichment.py` — 27 focused tests.
- `ecommerce_salla_connector/tests/__init__.py` — import test module.
- `docs/02_ARCHITECTURE.md`, `docs/05_CURRENT_STATUS.md`, `docs/06_ROADMAP.md`, `docs/07_SESSION_LOG.md`, `docs/08_DECISIONS.md`, `docs/TEST_CASES.md`, `docs/11_TROUBLESHOOTING.md` — updated.

### Important decisions

- Manual pre-import enrichment only: no synchronous API calls on the webhook intake path.
- API 401 returns unauthorized and records failure; it does not automatically trigger token refresh or retry.
- Rate limits parsed strictly from allowlisted headers; 429 enforces cooldown.
- Stale responses older than `last_external_update_at` are rejected without mutating staged fields (ADR-011).

### Problems discovered & Review Fixes

- **[P1 Fix] Malformed amounts overwriting valid staged data**: Added `_extract_amount_numeric()` helper. Missing or malformed optional amounts (`shipping_cost`, `discounts`, `tax`) are omitted from `update_vals` so existing valid staged data is never overwritten with `0.0`. Corrupted `total_amount` explicitly rejects the payload.
- **[P2 Fix] Swallowed AccessErrors**: Added `except AccessError: raise` before general error handlers to ensure permissions and record-rule failures propagate immediately. Replaced `self.sudo().write(update_vals)` with `self.write(update_vals)` so the Integration Manager writes business fields under standard ACLs and record rules.
- **[P2 Fix] Full 44-behavior test suite**: Expanded unit test suite from 27 to 43 comprehensive test methods covering independent missing/expired tokens, refresh locks, JSON envelope malformations, HTTP-date parsing, 60s fallback, cooldown clamping (1-3600s), malformed amount rejection, missing optional field omission, watermark comparisons, concurrent state changes, immutable field preservation, and network-free mock lab.

### Validation

- UC-17 comprehensive test suite:
  ```powershell
  python C:\odoo18\odoo-bin -c C:\odoo18\conf\odoo.conf -d ecommerce_sales_sync_dev -u ecommerce_connector_base,ecommerce_salla_connector --test-enable --test-tags /ecommerce_salla_connector:TestUC17SallaAPIEnrichment --stop-after-init --no-http --log-level=error
  ```
  Result: **43/43 tests passed (covering all 44 plan behaviors), 0 failures, 0 errors.**
- Regression suite (UC-14, UC-15, UC-16):
  ```powershell
  python C:\odoo18\odoo-bin -c C:\odoo18\conf\odoo.conf -d ecommerce_sales_sync_dev -u ecommerce_connector_base,ecommerce_salla_connector --test-enable --test-tags /ecommerce_salla_connector:TestUC14OrderStatusUpdates,/ecommerce_salla_connector:TestUC15OAuthAuthorization,/ecommerce_salla_connector:TestUC16TokenRefresh --stop-after-init --no-http --log-level=error
  ```
  Result: **44/44 tests passed, 0 failures, 0 errors.**
- Regression suite (UC-12, UC-13):
  ```powershell
  python C:\odoo18\odoo-bin -c C:\odoo18\conf\odoo.conf -d ecommerce_sales_sync_dev -u ecommerce_connector_base,ecommerce_salla_connector --test-enable --test-tags /ecommerce_connector_base:TestUC12SaleOrderIdempotency,/ecommerce_connector_base:TestUC13ManualRetry,/ecommerce_salla_connector:TestUC12WebhookIdempotency,/ecommerce_salla_connector:TestUC13WebhookRetry --stop-after-init --no-http --log-level=error
  ```
  Result: **Clean pass, 0 failures, 0 errors.**
- `git diff --check`: **Clean pass (0 whitespace issues).**

### Next recommended task

Plan and implement UC-18 (Stock Readiness and Inventory Reservation Policies).

## 2026-08-15 — UC-22 implementation: Salla Live Payload Compatibility and Status Normalization

### Goal

Correct Salla mapper defects exposed by real demo-store `order.created` webhook payloads:
1. Normalize `status` objects to stable string slugs (e.g. `under_review`) rather than stringifying Python dictionaries.
2. Parse Salla datetime objects (`{"date": "...", "timezone": "Asia/Riyadh"}`) and convert timezone-aware timestamps to UTC-naive datetimes.
3. Cleanly extract customer `full_name`, numeric `mobile` with `mobile_code` prefixing without code duplication.
4. Extract nested line item identifiers (`item.product.id`, `item.product_sku_id`) and amounts (`item.amounts.price_without_tax`, `item.amounts.total`).
5. Support `orders.read_write` in addition to `orders.read` in OAuth scope preflight for Salla order reading.

### Work completed

- Implemented pure `_normalize_status(value)` helper returning stripped string `slug`, fallback to string `name`, or top-level string; rejecting non-string/nested objects without container stringification.
- Extended `_parse_datetime()` to support Salla datetime dictionaries with `zoneinfo` (and `pytz` fallback) and explicit RFC/GMT offset parsing (e.g. `GMT+0300`) to convert IANA timezone dates to UTC-naive strings for Odoo `fields.Datetime`.
- Implemented `_extract_customer_name()` and `_extract_customer_phone()` with canonical digit normalization without country code duplication.
- Enhanced bounded `_extract_amount_decimal()` (max depth 3) to unwrap nested monetary objects (e.g. `tax.amount.amount`) and list summation for discounts using pure `Decimal` arithmetic.
- Updated `_extract_items()` with exact live item field precedence: `product.id`, `product_sku_id`, `amounts.price_without_tax`, and `amounts.total` with strict fallback handling (total / quantity derivation only without discount/tax ambiguity).
- Cleaned scalar IDs to prevent container stringification (`_clean_scalar_id`) in storage and exception interpolation.
- Validated quantities strictly as finite positive Decimals (`quantity_dec > 0 and quantity_dec.is_finite()`), rejecting malformed, zero, negative, boolean, container, and infinite quantities.
- Updated `ecommerce.store._prepare_salla_access_token()` to accept exact `orders.read` or `orders.read_write` scopes.
- Created `test_uc22_live_payload_compatibility.py` with 30 focused tests covering status normalization, Salla datetime parsing, GMT offsets, customer identity, container ID protection, nested item amounts/identifiers, price ambiguity rules, quantity validation, container ID error redaction, partial updates, scope preflight, mapped product ready state assertion, unmapped pending review assertion, malformed line rejection, explicit null quantity rejection, float-boundary overflow rejection, identifier fallback safety, field-safe monetary list handling, partial-update `total` wrapper parity, invalid timezone rejection, and event-level failure/idempotency behavior.
- Registered test in `ecommerce_salla_connector/tests/__init__.py`.
- Updated `docs/TEST_CASES.md` with TC-UC22-1 through TC-UC22-8.

### Review Resolutions (Rounds 1 & 2)

- **[P1 Resolved] Malformed/ambiguous prices becoming zero:** Line item prices now use `Decimal` arithmetic; total / quantity derivation is permitted ONLY when discount and tax are 0.0; malformed or unparseable prices raise `UserError` rather than defaulting to 0.0.
- **[P1 Resolved] Sanitized fixture identifiers:** Replaced all real merchant, order, reference, customer, line, product, and variant IDs in `test_uc22_live_payload_compatibility.py` with invented test fixtures (`999000111`, `9001001`, `8002001`, `5001`, `101`, `201`, `301`, etc.).
- **[P1 Resolved] Quantity validation and infinity rejection:** Explicit quantity values must be finite positive Decimals. Non-positive, boolean, container, malformed string, and infinite (`Infinity`/`NaN`) quantities raise `UserError`. Genuinely missing quantities default to `1.0`.
- **[P1 Resolved] Raw container ID error leakage:** Sanitized line labels (`_clean_scalar_id(raw_item.get("id")) or sku or f"#{idx + 1}"`) are used in all validation exception messages, preventing dictionaries/tokens from leaking into persisted `error_message`.
- **[P2 Resolved] Salla top-level GMT offset:** Extended parser with regex offset normalization (`GMT+0300` -> `+0300`) converting `Sat Aug 15 2026 03:17:13 GMT+0300` to `2026-08-15 00:17:13` UTC.
- **[P2 Resolved] Null legacy ID precedence:** Evaluated `_clean_scalar_id(raw_item.get("product_id")) or _clean_scalar_id(product_obj.get("id"))` so that explicit `None` on legacy keys cleanly falls back to valid live nested keys.
- **[P2 Resolved] Full Decimal monetary parsing:** Replaced intermediate float conversions with pure `_extract_amount_decimal()`, converting to `float` only at the model field boundary.
- **[P2 Resolved] Container identifier stringification:** Added `_clean_scalar_id` rejecting dictionaries, lists, and booleans for order, product, variant, line, and customer IDs.
- **[P2 Resolved] Consistent canonical phone normalization:** Phone numbers are normalized to canonical digits in `_extract_customer_phone`.
- **[P2 Resolved] Complete workflow coverage & state assertions:** Asserted `ext_order.state == "ready"` and `event.processing_status == "processed"` on mapped payloads, and `ext_order.state == "pending_mapping"` and `event.processing_status == "pending_review"` with actionable error messages on unmapped payloads.
- **[Final Review Resolved] Financial and identifier edge cases:** Non-object line items and explicit null quantities are rejected; finite Decimals that overflow Odoo Float storage are rejected; scalar identifier fallbacks ignore invalid truthy candidates; and floating-point IDs are not accepted.
- **[Final Review Resolved] Monetary parser and E2E contract:** Monetary lists are accepted only for discounts, generic wrappers are limited to `amount`/`value`/`total`, partial updates share the same wrapper contract, invalid naive datetime timezones are rejected, and event-level tests prove malformed lines do not create partial orders or duplicate partners/sale orders.

### Files modified

- `ecommerce_salla_connector/models/salla_mapper.py` — shared normalizers for status, datetime, customer, monetary, and items.
- `ecommerce_salla_connector/models/ecommerce_store.py` — OAuth scope check accepting `orders.read_write`.
- `ecommerce_salla_connector/tests/test_uc22_live_payload_compatibility.py` — 22 focused tests with sanitized fixtures.
- `ecommerce_salla_connector/tests/test_uc17_salla_api_enrichment.py` — phone normalization assertion sync.
- `ecommerce_salla_connector/tests/__init__.py` — test import registration.
- `docs/05_CURRENT_STATUS.md`, `docs/06_ROADMAP.md`, `docs/07_SESSION_LOG.md`, `docs/TEST_CASES.md` — updated.

### Validation

- UC-22 test suite (`TestSallaLivePayloadCompatibility`): **30/30 tests passed, 0 failures, 0 errors.**
- Full regression suite (UC-12, UC-13, UC-14, UC-15, UC-16, UC-17): **114/114 tests passed, 0 failures, 0 errors.**
- `python -m compileall ecommerce_salla_connector`: **Clean compile.**
- `git diff --check`: **Clean pass (0 whitespace issues).**

### Manual live verification

Pending: create one new demo-store order after the connector upgrade, because
replaying the earlier event cannot prove the new mapper behavior due to
idempotency.

## 2026-08-15 — UC-23 implementation: webhook retry status synchronization

### Live finding

A live Salla order correctly remained in review while its SKU was unmapped. Once
the SKU was created and **Retry Import** succeeded, the external order and sale
order were imported but the original webhook remained `pending_review`. The
external-order retry path had not re-entered webhook processing.

### Work completed

- Added base-model synchronization from imported external orders to linked
  failed/pending-review `order.created` webhook events.
- Preserved a webhook's active error in its audit history before clearing it and
  setting terminal `processed` status and related partner/sale-order links.
- Covered successful sale creation, linking an existing sale order, and
  validation of an already-linked order.
- Made webhook retry idempotently repair its own stale status if its external
  order is already imported.
- Added two UC-13 regression tests for direct external-order retry and the stale
  webhook-retry repair path.

### Validation

- `TestUC13ManualRetry`: **6/6 passed**.
- Affected UC-12, UC-13, UC-14, UC-16, UC-17, and UC-22 regression classes
  passed. The expected UC-16 row-lock contention test logged its controlled
  database lock message and exited successfully.
- Full combined regression attempted 116 tests with **0 assertion failures**;
  UC-15 setup errored because Windows denied Odoo filestore attachment creation
  at the configured path. This is an environment permission issue, not a
  connector regression.
- `python -m compileall ecommerce_connector_base` and `git diff --check` passed.

## 2026-08-15 — UC-18 implementation: stock readiness and inventory reservation policies

### Goal

Implement a stock readiness gate in `action_create_sale_order()` to prevent overselling by verifying unreserved physical inventory (`free_qty`) in the store's configured default warehouse before creating an Odoo sale order.

### Work completed

- Implemented `_check_stock_readiness()` on `ecommerce.external.order`:
  - Enforced `product.is_storable` (Odoo 18 compliant) check so physical goods are tracked and non-tracked consumables / services are skipped.
  - Aggregated ordered line quantities by `product_id` to prevent multi-line overselling.
  - Read `free_qty` (unreserved on-hand) scoped to store warehouse via `with_context(warehouse_id=...)` and order company via `with_company(...)`.
  - Used `odoo.tools.float_compare` at UOM rounding precision for safe boundary comparisons.
  - Fails closed when no warehouse is configured on a `readiness_only` store, parking the order in `pending_review` with an actionable message.
  - Surfaces stock shortage explanations directly in `error_message` for clear visibility across review and retry UI notifications.
- Hooked `_check_stock_readiness()` into `action_create_sale_order()`.
- Updated `action_retry_import()` UI feedback notification to display `error_message or warning_message`.
- Created comprehensive test suite `ecommerce_connector_base/tests/test_uc18_stock_readiness.py` containing 19 test cases.
- Registered test in `ecommerce_connector_base/tests/__init__.py`.
- Updated existing unit test fixtures across base and salla modules where stock checking is out of scope to set `stock_sync_policy: 'none'`.
- Updated documentation in `docs/TEST_CASES.md`, `docs/05_CURRENT_STATUS.md`, `docs/06_ROADMAP.md`, `docs/07_SESSION_LOG.md`.

### Files modified

- `ecommerce_connector_base/models/ecommerce_external_order.py` — added `_check_stock_readiness()`, `float_compare` import, hook, and updated retry notification.
- `ecommerce_connector_base/tests/test_uc18_stock_readiness.py` — 19 focused test cases.
- `ecommerce_connector_base/tests/__init__.py` — registered test suite.
- `ecommerce_connector_base/tests/test_uc12_sale_order_idempotency.py` — test store stock policy isolation.
- `ecommerce_connector_base/tests/test_uc13_manual_retry.py` — test store stock policy isolation.
- `ecommerce_salla_connector/tests/test_uc12_webhook_idempotency.py` — test store stock policy isolation.
- `ecommerce_salla_connector/tests/test_uc13_webhook_retry.py` — test store stock policy isolation.
- `ecommerce_salla_connector/tests/test_uc14_order_status_updates.py` — test store stock policy isolation.
- `ecommerce_salla_connector/tests/test_uc22_live_payload_compatibility.py` — test store stock policy isolation.
- `docs/TEST_CASES.md`, `docs/05_CURRENT_STATUS.md`, `docs/06_ROADMAP.md`, `docs/07_SESSION_LOG.md` — updated status, roadmap, test cases, and log.

### Validation

- `TestUC18StockReadiness`: **19/19 passed, 0 failures, 0 errors.**
- Full regression suite (UC-12 through UC-22 across all modules): **152/152 passed, 0 failures, 0 errors.**
- `python -m compileall ecommerce_connector_base ecommerce_salla_connector`: **Clean pass (0 errors).**
- `git diff --check`: **Clean pass (0 whitespace issues).**

## 2026-08-20 — UC-18 refinement: warehouse scoping & stale warning cleanup

### Goal

Fix stock readiness context key scoping in Odoo 18, use `warning_message` for stock advisories to match `pending_review` conventions, append rather than overwrite existing advisories, and ensure stale stock warnings are cleanly stripped on resolution/policy change.

### Work completed

- Fixed context key in `_check_stock_readiness()`: passed both `warehouse` and `warehouse_id` to ensure compatibility with Odoo 18's `_get_domain_locations()` which checks `warehouse_id`.
- Migrated stock readiness shortage and no-warehouse notices from `error_message` to `warning_message`, consistent with `pending_review` state conventions.
- Added `_strip_stock_warning(self, text)` helper to cleanly isolate and remove stock/no-warehouse warning blocks while preserving pre-existing non-stock advisories (such as currency mismatches).
- Updated `_check_stock_readiness()` on all paths:
  - On shortage: strips prior stock warning block before appending fresh shortage text (avoids message duplication on repeated checks).
  - On success (sufficient stock or no storable lines): strips prior stock warning block and cleans `warning_message` (sets `False` if empty or restores original advisory).
  - On policy `'none'`: strips prior stock warning block and clears stale warning.
- Expanded `ecommerce_connector_base/tests/test_uc18_stock_readiness.py` from 19 to 21 tests:
  - Updated `test_19` to verify rechecks update shortage numbers without duplication, and resolution clears stock warning while preserving currency advisory.
  - Added `test_20` covering store policy change from `'readiness_only'` to `'none'` clearing stale stock warnings.
  - Added `test_21` testing `_strip_stock_warning` helper directly against multiple advisory formats.
- Updated documentation in `docs/TEST_CASES.md`, `docs/05_CURRENT_STATUS.md`, `docs/07_SESSION_LOG.md`.

### Files modified

- `ecommerce_connector_base/models/ecommerce_external_order.py` — added `_strip_stock_warning()`, updated `_check_stock_readiness()` context keys and cleanup on success/none.
- `ecommerce_connector_base/tests/test_uc18_stock_readiness.py` — updated assertions, expanded to 21 tests.
- `docs/TEST_CASES.md` — updated UC-18 test specifications.
- `docs/05_CURRENT_STATUS.md` — updated UC-18 status summary and test count.
- `docs/07_SESSION_LOG.md` — recorded session changes.

### Validation

- `TestUC18StockReadiness`: **21/21 passed, 0 failures, 0 errors.**

## 2026-08-20 — UC-19 implementation: reporting and manager views

### Goal

Give store managers and connector users portfolio-quality, screenshot-ready visibility into e-commerce sync health inside Odoo's native UI: order volume/value by store and status, webhook delivery health by store and status, and the sale orders that actually resulted from e-commerce imports.

### Work completed

- Added pivot & graph views and `action_ecommerce_external_order_report` ("Orders by Store & Status") for `ecommerce.external.order`.
- Added pivot & graph views and `action_ecommerce_webhook_event_report` ("Webhook Health") for `ecommerce.webhook.event`.
- Created `ecommerce_connector_base/views/sale_order_views.xml` with list, search, pivot, graph views, and `action_ecommerce_sale_order` ("Imported Sale Orders") filtered to `[('ecommerce_store_id', '!=', False)]`.
- Added read-only `sale.order` access right in `ir.model.access.csv` for `group_ecommerce_connector_user` (and inherited manager tiers via `implied_ids`), allowing pure connector users to view imported sale orders without granting write/create access.
- Added new "Reporting" top-level menu section (`menu_ecommerce_connector_reporting`) in `ecommerce_connector_base/views/ecommerce_menu.xml` with three child menu items for the reporting actions.
- Created `ecommerce_connector_base/tests/test_uc19_reporting_manager_views.py` with 8 focused unit tests.
- Registered view in manifest and test in `tests/__init__.py`.
- Updated documentation in `docs/TEST_CASES.md`, `docs/05_CURRENT_STATUS.md`, `docs/06_ROADMAP.md`, `docs/07_SESSION_LOG.md`.

### Files modified

- `ecommerce_connector_base/views/ecommerce_external_order_views.xml` — added pivot/graph views and reporting action.
- `ecommerce_connector_base/views/ecommerce_webhook_event_views.xml` — added pivot/graph views and reporting action.
- `ecommerce_connector_base/views/sale_order_views.xml` — new file for imported sale orders reporting.
- `ecommerce_connector_base/__manifest__.py` — registered sale_order_views.xml.
- `ecommerce_connector_base/security/ir.model.access.csv` — added read-only sale.order access rule.
- `ecommerce_connector_base/views/ecommerce_menu.xml` — added Reporting menu section and 3 items.
- `ecommerce_connector_base/tests/test_uc19_reporting_manager_views.py` — 8 focused unit tests.
- `ecommerce_connector_base/tests/__init__.py` — registered test suite.
- `docs/TEST_CASES.md`, `docs/05_CURRENT_STATUS.md`, `docs/06_ROADMAP.md`, `docs/07_SESSION_LOG.md` — updated status, roadmap, test cases, and log.

### Validation

- `TestUC19ReportingManagerViews`: **8/8 passed, 0 failures, 0 errors.**
- `python -m compileall ecommerce_connector_base`: **Clean pass (0 errors).**
- `git diff --check`: **Clean pass (0 whitespace issues).**

## 2026-08-21 — UC-20 implementation: demo data, sample payloads, and scripts

### Goal

Make the project demonstrable end-to-end without live Salla credentials: wire every shipped
sample payload into the Mock Payload Lab, align OAuth samples with the real Salla shape using
sanitized values, fix the payment/fulfillment status field-name gap against real payloads, and
add an idempotent demo bootstrap producing screenshot-ready records.

### Work completed

- Mapper fallback: `_parse_order_payload()` now reads `payment_status` from `payment_method`
  and `fulfillment_status` from `shipping_status` when the explicit fields are absent (real
  Salla payloads never send `payment_status`/`fulfillment_status`).
  `_parse_partial_update_payload()` accepts the same fallbacks while staying strict:
  a malformed explicit key or malformed fallback value raises `UserError`.
- Replaced `sample_payloads/salla_app_store_authorize.json` with the sanitized real-shape
  version (bare-integer `merchant`, absolute Unix `expires`) and added
  `sample_payloads/salla_app_installed.json`. Both use merchant `999000111` / app id
  `555000111` with placeholder tokens only; no live capture data is present.
- Wired `salla_order_missing_sku`, `salla_order_multicurrency_sar`, and `salla_app_installed`
  into the Mock Payload Lab wizard selection and filename map. The authorize-timestamp refresh
  guard remains limited to `salla_app_store_authorize`.
- Added `action_bootstrap_demo_scenario()` to the wizard: idempotent (lookup by store
  identifier `999000111`), creates a mock-mode demo store plus get-or-created demo products,
  then runs app.installed → app.store.authorize → order.created (imported via explicit
  `action_create_sale_order()`) → missing-SKU (pending_mapping) → multicurrency SAR
  (ready with currency warning, left un-imported) through the standard
  `action_create_webhook_event()` path.
- Registered the bootstrap as Odoo demo data (`data/salla_demo_data.xml` + manifest `"demo"`
  key); it never runs on production installs that opt out of demo data.
- Added 5 mapper tests (`test_31`–`test_35`) to `test_uc22_live_payload_compatibility.py`,
  extended its fixture with `payment_method`/`shipping_status`, and created
  `test_uc20_demo_data_bootstrap.py` with 6 focused tests.
- Updated `docs/TEST_CASES.md` (TC-UC20-1..6), `docs/05_CURRENT_STATUS.md`, `docs/06_ROADMAP.md`
  (UC-20 completed; deliberate `order.cancelled` exclusion recorded).

The real payload shapes used to identify the payment/fulfillment field-name gap and to build
the sanitized OAuth samples came from an actual Salla demo-store connection; all customer PII
and real tokens were stripped before anything was written to repository files.

### Files modified

- `ecommerce_salla_connector/models/salla_mapper.py` — payment_method/shipping_status fallbacks.
- `ecommerce_salla_connector/tests/test_uc22_live_payload_compatibility.py` — fixture update + tests 31–35.
- `ecommerce_salla_connector/sample_payloads/salla_app_store_authorize.json` — sanitized replacement.
- `ecommerce_salla_connector/sample_payloads/salla_app_installed.json` — new sample.
- `ecommerce_salla_connector/wizards/ecommerce_mock_payload_wizard.py` — template wiring + bootstrap method.
- `ecommerce_salla_connector/data/salla_demo_data.xml` — new demo registration.
- `ecommerce_salla_connector/__manifest__.py` — added `"demo"` key.
- `ecommerce_salla_connector/tests/test_uc20_demo_data_bootstrap.py` — new, 6 tests.
- `ecommerce_salla_connector/tests/__init__.py` — registered UC-20 test module.
- `docs/TEST_CASES.md`, `docs/05_CURRENT_STATUS.md`, `docs/06_ROADMAP.md` — updated.

### Important decisions

- Demo store `store_identifier` fixed at `999000111` to satisfy the strict equality check in
  `_process_salla_app_store_authorize`; coupled to both OAuth samples' `merchant` value.
- Demo products use get-or-create by `default_code` instead of blind create: on databases that
  already contain products with these codes, blind duplicates made the SKU fallback ambiguous.
- Bootstrap reuses `action_create_webhook_event()` end-to-end so demo data can never drift from
  real business logic; importing stays an explicit `action_create_sale_order()` call.
- `salla_order_cancelled.json` deliberately not created: `order.cancelled` has no backing
  business logic anywhere; recorded in the roadmap Future table.

### Problems discovered

- First focused-test run failed: this dev database already contained committed products with
  `MOCK-SKU-001/002`; duplicate demo copies produced "Ambiguous SKU match" and parked the
  success-path order in `pending_mapping`. Fixed via get-or-create product seeding.
- Initial `test_35` forgot to seed matching products for the fixture SKUs (unlike tests 17/30);
  the event correctly parked as `pending_review`. Fixed by creating the two products in-test.

### Risks

- The demo store identifier (`999000111`) is a magic string coupling the two OAuth payload files
  and the bootstrap method; all three must change together.
- If a developer's company currency is SAR, the currency-warning demo order imports cleanly with
  no warning banner; accepted as harmless degradation for a portfolio demo.

### Validation

Ran on 2026-08-21 against `ecommerce_sales_sync_dev`:

```
python C:\odoo18\odoo-bin -c C:\odoo18\conf\odoo.conf -d ecommerce_sales_sync_dev \
  -u ecommerce_salla_connector --test-enable \
  --test-tags /ecommerce_salla_connector:TestUC20DemoDataBootstrap \
  --stop-after-init --no-http --log-level=error
```

Result: **6/6 tests passed, 0 failures, 0 errors.**

Full regression suite (UC-12 through UC-20 base + Salla classes, both modules upgraded):

```
python C:\odoo18\odoo-bin -c C:\odoo18\conf\odoo.conf -d ecommerce_sales_sync_dev \
  -u ecommerce_connector_base,ecommerce_salla_connector --test-enable \
  --test-tags /ecommerce_connector_base:TestUC12SaleOrderIdempotency,...,/ecommerce_salla_connector:TestUC20DemoDataBootstrap \
  --stop-after-init --no-http
```

Result: **173 tests passed, 0 failures, 0 errors** (includes the expanded 35-test UC-22 suite).
The post-run registry teardown noise (`cursor already closed`) after the result summary matches
all previous sessions on this Windows setup and is not a test failure.

- `python -m compileall ecommerce_salla_connector`: **Clean pass.**
- `git diff --check`: **Clean pass (0 whitespace issues).**
- Secrets check: `git grep "mock-access-token-not-real"` returns nothing; only sanitized
  placeholder token strings ship in the two OAuth sample files.

Not run: manual fresh-database demo walkthrough with demo data enabled (this dev database has
demo data disabled, so the bootstrap was validated through the direct method calls in the UC-20
tests rather than XML loading); live Salla verification remains out of scope for this UC.

### Next recommended task

Plan and implement UC-21 (documentation/release polish): README and TEST_CASES alignment, CI
wiring, and packaging checks.

### Questions for next session

- None.
