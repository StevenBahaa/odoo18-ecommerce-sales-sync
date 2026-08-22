# Architecture Decisions

Record decisions that affect future implementation. Add new entries rather than rewriting historical context; revise an entry only to correct factual errors.

## ADR-001 — Split generic connector logic from Salla logic

### Context

The connector must support Salla first while remaining a portfolio foundation for future platforms.

### Decision

Keep generic records, security, staging, and sale-order import in <code>ecommerce_connector_base</code>. Keep Salla payload parsing and Salla-specific event behavior in <code>ecommerce_salla_connector</code>.

### Alternatives considered

- One Salla-only addon.
- A separate external microservice.

### Reasoning

Odoo addon inheritance lets the Salla module extend generic event processing without duplicating the shared import domain.

### Tradeoffs

Two manifests, addon imports, and extension points add navigation overhead.

### Future implications

Future platform addons should implement their payload translation at this boundary rather than fork the base workflow.

## ADR-002 — Webhook-first, staging-first import

### Context

Raw external payloads can be incomplete, duplicated, malformed, or arrive out of order.

### Decision

Persist a redacted webhook event first, create an external-order staging record, validate/match it, then create a sale order only when ready.

### Alternatives considered

- Create sale orders directly in the controller.
- Drop failed webhooks after returning an error.

### Reasoning

Staging preserves evidence, supports manual repair/retry, and prevents invalid input from directly polluting sales data.

### Tradeoffs

The system has additional states and manager workflow.

### Future implications

All new platform events must preserve this audit boundary.

## ADR-003 — Mock Mode is mandatory

### Context

Portfolio demonstrations and local development cannot depend on paid/live Salla access.

### Decision

Support Mock Mode stores and a Salla Mock Lab with bundled payloads.

### Alternatives considered

- Require live demo/production credentials.
- Use only unit-test fixtures.

### Reasoning

Mock Mode exercises the real Odoo event/staging/import path without external account dependency.

### Tradeoffs

Mock payloads can drift from the real platform contract.

### Future implications

Maintain mock samples as live schemas are verified.

## ADR-004 — Public webhooks use layered trust controls

### Context

The route is public so the platform can call it, but it must not permit uncontrolled business writes.

### Decision

Use a store token in the route, per-store rate limits, HMAC SHA-256 signature checks outside Mock Mode, redacted event logging, and an integration-user processing gate.

### Alternatives considered

- Authentication only.
- Signature only.
- Broad privileged controller processing.

### Reasoning

Each layer protects a different failure mode while retaining a reliable audit trail.

### Tradeoffs

Configuration is more involved; missing integration user intentionally blocks business processing.

### Future implications

Do not weaken checks for production convenience. Add platform-specific signature rules at the addon boundary when needed.

## ADR-005 — Store-scoped mappings and multi-company safety

### Context

The same external IDs, SKUs, or references may exist in multiple stores/companies.

### Decision

Scope mapping and idempotency keys by store, retain company-aware fields/checks, and use store-specific configuration.

### Alternatives considered

- Global external-ID mappings.
- Single-company-only implementation.

### Reasoning

Store scope prevents cross-store identity collisions and supports multi-company operation.

### Tradeoffs

Queries and fixtures must always carry the correct store/company context.

### Future implications

New identity fields and event handlers must be reviewed for scope leakage.

## ADR-006 — Database-backed idempotency

### Context

Webhook redelivery and concurrent imports can produce duplicate sale orders.

### Decision

Use both application lookup/link helpers and a sale-order SQL uniqueness constraint; recover constraint races in a savepoint and link the winner.

### Alternatives considered

- Application lookup only.
- Webhook-event uniqueness only.

### Reasoning

Only a database constraint closes the concurrency race.

### Tradeoffs

Existing databases require duplicate inspection before constraint installation.

### Future implications

Reuse the existing import path and duplicate recovery logic for retries and future event handlers.

## ADR-007 — Manual retry is an explicit import decision

### Context

An order may be blocked because mappings/configuration were incomplete and later repaired.

### Decision

Manager retry records retry history, runs as the integration user, repeats matching/validation, and proceeds to sale-order creation when the order is ready.

### Alternatives considered

- Retry only the parsing stage.
- Force a manager to press a second import button.

### Reasoning

An explicit manual retry is the operator's import decision; reusing normal creation keeps idempotency central.

### Tradeoffs

Retry must be carefully permissioned and auditable.

### Future implications

Automated retries, if added, need separate policy/backoff/observability decisions.

## ADR-008 — External update ordering with per-order watermark and row lock

### Context

Salla `order.updated` webhooks can arrive out of order, be duplicated, or contain only a partial set of fields. Applying them naively risks overwriting newer data with stale values or clearing fields that were not included in the update.

### Decision

UC-14 implements a per-staged-order update watermark (`last_external_update_at`, `last_external_update_event_id`) rather than a global webhook-event uniqueness constraint. Before comparing or writing, the handler acquires a PostgreSQL `FOR UPDATE NOWAIT` row lock on the staged order, reloads the watermark fields, and applies the ordering matrix:

| Scenario | Outcome |
| --- | --- |
| No staged order | `pending_review`; no mutation |
| Missing/invalid event time | `pending_review`; no mutation |
| No prior watermark | Apply update and set watermark |
| Incoming time newer than watermark | Apply update and advance watermark |
| Incoming time older than watermark | `pending_review`; no mutation |
| Same time and same event ID | `duplicate`; no mutation |
| Same time but different/missing event ID | `pending_review`; no mutation |

A dedicated partial-update mapper (`_parse_partial_update_payload`) emits only fields that were explicitly present and valid in the payload. Omitted fields produce no key in the result dictionary and are therefore never written, preventing accidental clears.

### Alternatives considered

- Global `UNIQUE(external_event_id)` constraint on `ecommerce.webhook.event`: simpler for true duplicates but cannot detect stale out-of-order events or partially-distinct payloads.
- Timestamp-only comparison without row lock: susceptible to concurrent update races.
- Accepting all updates and letting the UI resolve conflicts: destroys audit integrity.

### Reasoning

A per-order watermark is the minimal addition that closes stale-update and concurrent-delivery races without a global migration. The row lock ensures that concurrent deliveries for the same order serialize rather than race to compare the same pre-lock watermark value.

### Tradeoffs

- Two new nullable fields are required on `ecommerce.external.order`; both addons must be upgraded together.
- `FOR UPDATE NOWAIT` will raise an exception if another transaction already holds the lock; the processing gate records the failure rather than silently dropping the event.
- The correctness of ordering depends on Salla's event timestamps representing emission order; this assumption is stated explicitly and treated as unverified for production.

### Future implications

- If a global webhook-event uniqueness constraint is added later, it can complement (not replace) the per-order watermark.
- The watermark pattern can be reused by future platform addons that need ordered update processing.
- Do not remove the row lock when moving to background/queue processing; the lock scope must remain per staged order.

## ADR-009 — Narrow Sudo and Ephemeral Unredacted Payloads for OAuth

### Context

OAuth access tokens and refresh tokens must not be persisted in raw webhook logs where any regular support user can view them, but they still need to be reliably passed from the controller, through the business processing gate, to a protected store update function.

### Decision

1. The controller and Mock Lab parse the unredacted JSON dictionary in memory and pass it to the processing gate (`processing_payload`).
2. The controller immediately replaces sensitive token fields with `[REDACTED]` before saving the raw payload to the database.
3. Only the `app.store.authorize` handler uses the unredacted `processing_payload` to parse tokens. All other handlers reload the persisted redacted payload, then the authorization handler calls a specific `_apply_salla_authorization_credentials` helper on `ecommerce_store`.
4. This helper uses `sudo()` to lock the store, check replay ordering against restricted manager-only OAuth tracking fields, and atomically update the tokens, returning a clean non-sensitive outcome to the event handler.

### Alternatives considered

- Skip webhook event creation for authorization events. (Destroys audit trail of authorization failures).
- Encrypt tokens in the raw payload log. (Too complex for simple event logging).
- Execute the whole event processor under `sudo()`. (Violates the principle of least privilege, opening up other operations to privilege escalation).

### Reasoning

Passing the parsed ephemeral dictionary down the call stack prevents secrets from hitting the database in plain text in the `raw_payload` field, while the narrow `sudo()` helper encapsulates the privilege escalation safely, keeping the rest of the webhook processor running as the intended `integration_user_id`.

### Tradeoffs

- Requires passing `processing_payload` explicitly down the inheritance chain, increasing method signatures.

### Future implications

- Token refresh payloads will also use this authorization-only ephemeral passing pattern to update the store securely.

## ADR-010: Persistent Single-Use Refresh Claims and Safe Ambiguity Handling

**Status:** Accepted (2026-08-02)

### Context

UC-16 implements Salla OAuth token refresh. Salla's refresh tokens are single-use; a successful refresh returns a new access token and a new refresh token, invalidating the old refresh token. If two concurrent requests use the same refresh token, Salla may revoke the credentials entirely. Furthermore, if a refresh request times out or a connection error occurs after the token was sent to Salla, Odoo cannot know whether Salla processed the rotation or not.

### Decision

1.  **Persistent Claim:** A token refresh claim is recorded durably (token_refresh_lock=True) in a dedicated PostgreSQL cursor with a FOR UPDATE NOWAIT row lock before any external network request is made.
2.  **Strict Safe Ambiguity:** If the refresh request encounters a timeout, connection error, or invalid response, the lock is intentionally not cleared. The store is marked as token_refresh_requires_reauthorization.
3.  **No Automatic Retry:** Odoo will never automatically retry an ambiguous refresh or allow an operator to "clear the lock" and retry manually, as reusing a potentially consumed token is unsafe.
4.  **Recovery:** The only way to recover from an ambiguous refresh is to complete a new app.store.authorize flow (UC-15), which securely supersedes the stalled refresh and clears the lock.

### Alternatives considered

-   **"Finally" Lock Release:** Releasing the lock in a finally block or when an error is caught. (Rejected: unsafe for single-use tokens; a timeout could mean Salla consumed the token, so retrying the old token would cause revocation).
-   **Timeout-based Lock Expiry:** Automatically clearing the lock after 10 minutes. (Rejected: same reason; time does not make the old token reusable).

### Reasoning

For single-use tokens, a distributed transaction gap exists between Odoo's network request and Salla's database commit. Failing closed (requiring reauthorization) is the only mathematically safe response to ambiguity, ensuring we never inadvertently trigger Salla's security revocations.

### Tradeoffs

-   Operators must manually re-authorize the app if a network glitch occurs exactly during token refresh, which is a worse UX than automatic recovery but guarantees credential safety.

## ADR-011: Manual Salla API Client, Rate-Limit Boundaries, and Stale-Response Protection

**Status:** Accepted (2026-08-13)

### Context

UC-17 introduces authenticated Salla Merchant API calls (`https://api.salla.dev/admin/v2/orders/{id}`) to fetch full order details before staged order import. Key architectural risks include webhook throughput degradation from synchronous remote calls, credential exposure in logs/UIs, token refresh loops on 401 errors, rate limit exhaustion, and overwriting fresh webhook updates with stale API snapshots.

### Decision

1. **Manual Pre-Import Enrichment Only:** API calls are strictly initiated manually via `action_enrich_from_salla()` by authorized E-commerce Integration Managers. No synchronous or background API requests execute on the webhook intake or processing paths.
2. **GET-Only and URL Path Segment Quoting:** All Merchant API requests are restricted to HTTP GET. External order IDs are quoted as single URL path segments using `urllib.parse.quote(str(id), safe="")` to eliminate path traversal and SSRF vectors.
3. **Safe Redacted Exceptions:** All remote errors, HTTP codes, and transport exceptions are mapped to `SallaAPIError(UserError)` with generic sanitized messages. Tokens, authorization headers, and raw responses are strictly excluded from exception messages and tracebacks.
4. **Rate-Limit Metadata and Cooldown Enforcement:** Allowlisted rate limit headers (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After`) update protected `ecommerce.store` fields. Active cooldown timestamps immediately reject subsequent outbound requests before opening any network sockets.
5. **No Automatic 401 Retries or Refreshes:** An API 401 (Unauthorized) response is treated as a terminal failure for that request. It records an audit failure and does not trigger automatic secondary token refresh or retry, preventing infinite loops or rate quota burn.
6. **Row Locking and Stale-Response Protection:** Before mutating any staged fields, `action_enrich_from_salla()` acquires a PostgreSQL `FOR UPDATE NOWAIT` row lock on `ecommerce.external.order`. If the API snapshot `updated_at` is older than the existing watermark `last_external_update_at`, the update is rejected as stale without field mutation.
7. **Preservation of Core Integrity Fields:** Enrichment updates only allowlisted staged fields (customer details, monetary totals, external status). It never modifies `state`, `partner_id`, `sale_order_id`, `line_ids`, or `raw_payload`.

### Alternatives considered

- **Automatic Webhook Enrichment:** Enriching every incoming webhook automatically before staging. (Rejected: creates severe webhook latency, exposes the system to external API downtime, and rapidly exhausts API rate limits).
- **Automatic Token Refresh on 401:** Triggering `_refresh_salla_token()` when an API call returns 401. (Rejected: Salla refresh tokens are single-use; ambiguous failures or bad permissions could trigger uncontrolled refresh attempts).

### Reasoning

Decoupling API enrichment from webhook intake preserves webhook reliability and performance. Combining preflight token preparation, row locking, and watermark checks ensures safe concurrency without risking data regressions or credential leakage.

### Tradeoffs

- Operators must manually click "Enrich from Salla" if they require additional remote details before importing an order.
- Orders already imported into `sale.order` cannot be enriched from the external API to maintain sales document immutability.
