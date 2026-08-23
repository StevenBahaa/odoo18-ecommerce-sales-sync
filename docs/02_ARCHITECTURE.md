# Architecture

## System shape

This repository contains two Odoo addons. The base addon owns generic e-commerce concepts; the Salla addon plugs Salla-specific parsing and processing into those concepts. Odoo provides the HTTP server, ORM, PostgreSQL persistence, authorization framework, and browser UI.

~~~mermaid
flowchart LR
    S["Salla or Mock sender"] -->|POST JSON| C["Public webhook controller"]
    C --> V["Route token, rate limit, signature checks"]
    V --> E["Webhook Event: redacted audit record"]
    E --> G["Integration-user processing gate"]
    G --> M["Salla payload mapper"]
    M --> O["External Order staging and lines"]
    O --> X["Customer and product matching"]
    X --> SO["Sale Order"]
    X --> Q["Attention / error queue"]
    U["Odoo XML views / manager"] --> Q
    U -->|manual retry| G
~~~

## Module relationships

~~~mermaid
flowchart TB
    Odoo["Odoo 18 Community: base, sale_management, stock, mail"]
    Base["ecommerce_connector_base"]
    Salla["ecommerce_salla_connector"]
    Odoo --> Base
    Base --> Salla
    Salla -->|extends| Store["Store platform selection"]
    Salla -->|extends| Event["Webhook Event business processing"]
    Salla -->|uses| Order["External Order"]
~~~

| Module | Depends on | Owns |
| --- | --- | --- |
| <code>ecommerce_connector_base</code> | <code>base</code>, <code>sale_management</code>, <code>stock</code>, <code>mail</code> | Generic models, HTTP controller, security groups, mappings, sale-order import, XML UI, sequence, tests. |
| <code>ecommerce_salla_connector</code> | <code>ecommerce_connector_base</code> | Salla platform selection, mapper/handler, mock wizard, sample payloads, Salla tests. |

The Salla addon does not replace the public route. It extends the base event-processing hook, keeping the controller platform-neutral.

## Webhook request lifecycle

~~~mermaid
sequenceDiagram
    participant P as Salla / Mock sender
    participant C as Odoo webhook controller
    participant W as Webhook Event
    participant G as Processing Gate
    participant H as Salla Event Handler
    participant O as External Order
    participant S as Sale Order
    P->>C: POST webhook JSON
    C->>C: Locate store and apply rate limit
    alt non-mock store
        C->>C: Verify X-Salla-Signature (HMAC SHA-256)
    end
    C->>W: Persist redacted payload, headers, identifiers
    C->>G: Apply integration-user and company context
    G->>H: Process supported event
    H->>O: Create/find staged order and lines
    O->>O: Match customer, resolve products, validate
    alt ready
        O->>S: Create/link idempotent sale order
        H->>W: Mark processed
    else needs attention
        H->>W: Mark pending review or failed
    end
    C-->>P: Safe HTTP response
~~~

Important behavior:

- Invalid store token returns a safe invalid-store response.
- A rate-limited event is recorded as rate limited and returns HTTP 429.
- An invalid non-mock signature is redacted, does not enter business processing, and returns HTTP 401.
- After a valid event is stored, the controller returns HTTP 200 even if business processing later fails; the event/order records preserve the failure.

## Staged import flow

The central safety boundary is:

~~~text
Raw webhook event -> external order staging -> validation -> sale order
~~~

The system intentionally does not create a sale order directly from raw HTTP JSON.

~~~mermaid
stateDiagram-v2
    [*] --> captured
    captured --> pending_mapping: incomplete product/customer mapping
    captured --> pending_review: ambiguity or configuration attention
    captured --> ready: validation succeeds
    ready --> imported: sale order created or linked
    captured --> failed: processing exception
    pending_mapping --> ready: mapping fixed and retry
    pending_review --> ready: issue fixed and retry
    failed --> ready: retry succeeds
    pending_mapping --> failed: retry exception
    pending_review --> failed: retry exception
    captured --> cancelled: order.cancelled event or manager action
~~~

The selection also contains <code>draft</code>, <code>duplicate</code>, and <code>cancelled</code>. The transition to <code>cancelled</code> is fully implemented in UC-24 for watermark-ordered <code>order.cancelled</code> webhooks and manual manager cancellation; subsequent updates adhering to watermark rules do not resurrect a cancelled order.

## Data model and constraints

| Record | Important relationships | Integrity design |
| --- | --- | --- |
| Store | Company, warehouse, pricelist, sales team, integration user | Unique platform/store identifier/company; unique webhook token. |
| Webhook event | Store, optional external order/partner/product/sale order | Immutable-style audit fields; status and retry history. |
| External order | Store, customer mapping/partner, lines, optional sale order | Unique store plus external order ID. |
| External line | External order, optional product/mapping | Per-line mapping outcome and raw line data. |
| Customer mapping | Store + external customer ID to partner | Unique store plus external customer ID. |
| Product mapping | Store + external product/variant to product | Unique store plus external product plus variant. |
| Sale order extension | Store + external reference + external order | Unique store plus external reference prevents duplicate imports. |

The principal models are company-aware and use Odoo company checks on cross-record fields. The same external reference may legitimately exist in different stores.

## Idempotency and concurrency

Duplicate protection has two layers:

1. Application lookup: <code>_find_existing_sale_order()</code> searches by store and external order ID; <code>_link_existing_sale_order()</code> links the winner to the staging record.
2. Database constraint: the extended sale-order model has a unique store/external-reference constraint.

Creation handles an <code>IntegrityError</code> inside a savepoint, re-queries the winning order, and links it. This covers duplicate deliveries and concurrent imports. The pre-upgrade inspection script is <code>scripts/check_uc12_sale_order_duplicates.sql</code>.

## External update ordering (UC-14)

The `order.updated` handler applies a per-staged-order watermark strategy rather than a global event uniqueness constraint. Before comparing or writing, the handler acquires a PostgreSQL `FOR UPDATE NOWAIT` row lock on the staged order row, then reloads `last_external_update_at` and `last_external_update_event_id`. All comparison and write operations occur in a single savepoint-backed transaction.

Only fields explicitly present and valid in the update payload are written. Omitted fields are not included in the write dictionary and cannot be cleared. Monetary updates require the payload to declare a currency that matches the staged order's existing currency; a mismatch parks the entire event without mutating any field.

Status fields accepted from an `order.updated` payload are mirrored to the linked `sale.order`'s connector informational fields (`ecommerce_payment_status`, `ecommerce_fulfillment_status`) when the staged order is already imported. No Odoo workflow, financial, delivery, or line field on the sale order is written by an update event. See ADR-008 for the full ordering decision.

## Processing boundaries

There is no separate Python service package. The current boundaries are Odoo models:

| Boundary | Current implementation |
| --- | --- |
| HTTP ingress | <code>EcommerceWebhookController</code> |
| Security/rate/signature | Controller helpers and store/event configuration |
| Event orchestration | <code>ecommerce.webhook.event</code> processing gate |
| Platform translation | Abstract Salla mapper and Salla event handler |
| Staging/validation/import | <code>ecommerce.external.order</code> |
| Customer identity | Customer mapping plus exact email/normalized phone matching |
| Product identity | Product mapping plus store-scoped SKU fallback |
| External API | Abstract Salla client placeholder; live calls deferred |
| Test/demo ingress | Salla Mock Webhook wizard |

The reusable utility is <code>utils/phone_utils.py</code>, which removes non-digits only; it deliberately does not infer country-code equivalence.

## Frontend/backend communication and state

There is no React frontend, TypeScript application, client-side state store, or separately versioned API. Odoo XML views render in the Odoo web client and invoke model methods through Odoo actions/RPC. Persistent ORM records are the source of state.

The public JSON webhook endpoint is the only custom HTTP API. It is platform-to-server traffic, not a browser SPA API.

## Security boundary

~~~mermaid
flowchart LR
    Public["Anonymous public request"] --> Token["URL store token"]
    Token --> Rate["Rate limit"]
    Rate --> Signature["HMAC check outside Mock Mode"]
    Signature --> Audit["Redacted audit log"]
    Audit --> User["Configured integration user and company"]
    User --> Records["Business records"]
    Manager["Connector Manager"] --> Retry["Retry action"]
    Retry --> User
~~~

The controller uses narrow privileged operations for store lookup/configuration/audit. Business work is intended to run as the configured integration user. Manager UI visibility is not the authorization control: retry and enrichment methods also enforce groups in Python.

## Salla API client and order enrichment architecture (UC-17)

~~~mermaid
flowchart TD
    Manager["Integration Manager"] --> Action["action_enrich_from_salla()"]
    Action --> Preflight["_prepare_salla_access_token()"]
    Preflight -->|Valid token| Client["EcommerceSallaClient._request()"]
    Preflight -->|Expired / Near-expiry| Lock["_refresh_salla_token() (FOR UPDATE NOWAIT)"]
    Lock --> Client
    Client --> API["Salla Merchant API (/orders/{id})"]
    API --> RateHeaders["Rate-Limit & Cooldown Metadata"]
    RateHeaders --> Store["ecommerce.store (metadata update)"]
    API --> Mapper["_parse_order_details_payload()"]
    Mapper --> LockOrder["Row Lock & Stale/Currency Check"]
    LockOrder --> Enrich["Atomic Update of Staged Fields & Audit"]
~~~

The Salla API client is strictly GET-only and manual. It enforces integration-manager authorization, access-token preflight with single-use refresh token locking, safe error mapping (masking credentials), rate-limit cooldown persistence, and atomic row-locked stale-response protection without modifying linked sale orders or raw webhook payloads.

## Formerly deferred, now implemented

OAuth authorization (UC-15), token refresh safety (UC-16), GET-only Salla API client and
enrichment (UC-17), stock readiness gating (UC-18), reporting views (UC-19), demo
bootstrap data (UC-20), and order cancellation handling (UC-24).

## Still deferred

| Area | Status |
| --- | --- |
| Outbound stock synchronization | Out of MVP; stock readiness gating implemented in UC-18. |
| Production topology | TLS/reverse proxy, workers/queues, observability, backups **need further investigation**. |
