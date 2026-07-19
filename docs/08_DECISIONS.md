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
