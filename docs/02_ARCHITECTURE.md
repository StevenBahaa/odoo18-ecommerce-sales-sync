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
    captured --> cancelled: future lifecycle handling
~~~

The current selection also contains <code>draft</code>, <code>duplicate</code>, and <code>cancelled</code>. Not all transitions are implemented; order-update/cancellation behavior is deferred to UC-14.

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

The controller uses narrow privileged operations for store lookup/configuration/audit. Business work is intended to run as the configured integration user. Manager UI visibility is not the authorization control: retry methods also enforce groups in Python.

## Deferred architecture

| Area | Evidence | Status |
| --- | --- | --- |
| Order updates | Salla handler records a UC-14 deferred message | Not implemented |
| OAuth authorization | Store token fields and authorize sample payload | UC-15 |
| Token refresh | Store lock/timestamp fields | UC-16 |
| Live Salla API client | Abstract client raises deferred error | UC-17 |
| Stock readiness | Store policy field | UC-18 |
| Reporting | Model foundations only | UC-19 |

Production topology, queues/workers, observability, backups, and reverse-proxy architecture **need further investigation**.
