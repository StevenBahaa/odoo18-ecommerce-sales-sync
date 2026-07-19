# Project Context

## Project name

**Odoo 18 E-commerce Sales Sync Connector**

| Module | Purpose |
| --- | --- |
| <code>ecommerce_connector_base</code> | Reusable connector domain, staging models, webhook intake, security, mappings, and sale-order import. |
| <code>ecommerce_salla_connector</code> | Salla-specific payload mapping, event processing, mock lab, and future API boundary. |

## Purpose and business goals

This portfolio-grade Odoo 18 Community integration receives e-commerce order webhooks, preserves an auditable event, stages an external order, resolves customers and products, and creates an Odoo sale order only when valid. The initial platform is **Salla**; the generic/base module is separated so later platform addons can reuse the workflow.

Verified business goals:

- reduce manual online-order entry into Odoo;
- make customer/product failures visible and recoverable;
- prevent duplicate sale orders from delivery retries or races;
- protect webhook credentials and redact sensitive payload data;
- support a full local demonstration without live Salla credentials through Mock Mode.

It is a portfolio MVP, not a certified production marketplace connector.

## Current status

Snapshot: **2026-07-19**, based on the current <code>develop</code> branch, source, tests, and Git history.

- UC-00 through UC-13 are implemented; UC-13 (Error Queue and Manual Retry) is merged into <code>develop</code>.
- UC-14, external order status updates and event ordering, is next.
- Live Salla API calls, OAuth authorization processing, token refresh, stock readiness, reporting, demo bootstrap data, and release work remain deferred.
- <code>README.md</code> and <code>docs/TEST_CASES.md</code> still describe an earlier milestone. Treat current code and [05_CURRENT_STATUS.md](05_CURRENT_STATUS.md) as the more accurate implementation snapshot until those files are refreshed.

## High-level architecture

~~~text
Salla or Mock payload
  -> public Odoo webhook route
  -> redacted ecommerce.webhook.event audit record
  -> integration-user processing gate
  -> ecommerce.external.order staging record + lines
  -> customer/product matching and validation
  -> idempotent sale.order creation, or an attention/error queue state
~~~

This is an Odoo addon, not a separate web application. Odoo's Python ORM, PostgreSQL database, HTTP controller layer, XML views, ACLs, and server-rendered web client provide the backend and user interface.

## Main technologies

| Area | Technology used |
| --- | --- |
| ERP framework | Odoo 18 Community |
| Application language | Python |
| Database | PostgreSQL through the Odoo ORM |
| User interface | Odoo XML views, actions, menus, and web client |
| Webhook transport | Odoo HTTP controller and JSON payloads |
| Signature validation | HMAC SHA-256 for non-mock webhooks |
| Tests | Odoo <code>TransactionCase</code> and <code>unittest</code> |
| Configuration | XML data files and an Odoo configuration file outside the repository |
| Version control | Git and GitHub |

There is no <code>package.json</code>, TypeScript, React application, Docker setup, CI workflow, dependency lockfile, or repository-managed deployment configuration.

## Repository structure

~~~text
ecommerce_connector_base/
  controllers/        Public webhook endpoint
  models/             Generic connector domain and Odoo extensions
  security/           Groups and model access CSV
  data/               Sequences
  views/              Odoo XML views, actions, menus
  tests/              Odoo TransactionCase tests
ecommerce_salla_connector/
  models/             Salla mapper, webhook handler, future API boundary
  wizard/             Mock webhook lab
  security/           Salla wizard access
  views/              Salla store and mock-lab XML views
  data/               Sample webhook payload JSON
  tests/              Salla integration tests
scripts/
  check_uc12_sale_order_duplicates.sql
docs/
  TEST_CASES.md       Existing, currently partial test-case document
  .plans/             Local UC plans; intentionally gitignored
PROJECT_PLAN.md       Local detailed UC roadmap; intentionally gitignored
README.md              Project overview and local-development notes
AGENTS.md              Repository-level Git safety instruction
~~~

## External services and APIs

| Service/interface | Current use | Status |
| --- | --- | --- |
| Salla webhooks | Order-created ingestion and Salla-shaped mock payloads | Implemented |
| Salla API | Abstract client boundary only | Deferred to UC-17 |
| Salla OAuth authorization | Store fields and mock payload exist | Processing deferred to UC-15 |
| Odoo/PostgreSQL | Persistent application and database layer | Required |
| GitHub | Remote source control | Used by the project workflow |

No real outbound Salla API request is implemented in the repository today.

## Database and key records

Odoo manages the PostgreSQL schema from model declarations.

| Model | Responsibility |
| --- | --- |
| <code>ecommerce.store</code> | Per-platform/store configuration, policies, secrets, integration user, and rate limits. |
| <code>ecommerce.webhook.event</code> | Redacted raw webhook audit log and processing/retry state. |
| <code>ecommerce.external.order</code> | Staging record between a webhook and an Odoo sale order. |
| <code>ecommerce.external.order.line</code> | Imported external line and mapping state. |
| <code>ecommerce.customer.mapping</code> | Store-specific external customer ID to Odoo partner mapping. |
| <code>ecommerce.product.mapping</code> | Store-specific external product/variant to Odoo product mapping. |
| <code>sale.order</code> (extended) | E-commerce origin and external reference for idempotency. |
| <code>res.partner</code> (extended) | Normalized phone digits for matching. |

The database enforces uniqueness for a store/external-order pair and for a sale order's store/external reference pair.

## Authentication and authorization

- The public webhook route uses a generated store token in its URL.
- Non-mock webhooks require HMAC SHA-256 verification using the configured webhook secret. Mock Mode bypasses this requirement.
- Odoo groups separate Connector User, Connector Manager, and Integration Manager roles.
- Business processing runs as the configured <code>integration_user_id</code>, not as the anonymous request or retrying manager. Missing configuration holds processing in an attention state.
- Sensitive store fields and webhook values are protected/redacted. Never log or commit credentials, tokens, secrets, authorization codes, cookies, or database passwords.

## Configuration and environment variables

The repository does **not** define an environment-file example or a documented environment-variable contract. Configuration currently comes from:

- an Odoo configuration file outside the repository (the existing local README uses <code>C:\odoo18\conf\odoo.conf</code> as an example);
- Odoo system parameter <code>web.base.url</code>, used to compute the webhook URL;
- <code>ecommerce.store</code> fields for store identity, defaults, policies, rate limits, integration user, and restricted credentials.

Exact production environment variables, reverse-proxy settings, PostgreSQL provisioning, backup policy, and deployment secrets **need further investigation**. Do not add them to Git.

## Important commands

Run from repository root, adapting the Odoo checkout, config, database, and addons path. These paths are examples from the existing Windows setup.

~~~powershell
# Update both addons in a local development database.
python C:\odoo18\odoo-bin -c C:\odoo18\conf\odoo.conf -d ecommerce_sales_sync_dev -u ecommerce_connector_base,ecommerce_salla_connector --stop-after-init

# Run the implemented UC-12 and UC-13 targeted tests.
python C:\odoo18\odoo-bin -c C:\odoo18\conf\odoo.conf -d ecommerce_sales_sync_dev -u ecommerce_connector_base,ecommerce_salla_connector --test-enable --test-tags /ecommerce_connector_base:TestUC12SaleOrderIdempotency,/ecommerce_salla_connector:TestUC12WebhookIdempotency,/ecommerce_connector_base:TestUC13ManualRetry,/ecommerce_salla_connector:TestUC13WebhookRetry --stop-after-init --no-http --log-level=error

# Inspect duplicates before installing the UC-12 uniqueness constraint on an older database.
psql -d <database_name> -f scripts/check_uc12_sale_order_duplicates.sql
~~~

The exact dependency-installation command and database bootstrap procedure are not versioned here and **need further investigation**.

## Common workflows

### Develop a use case

1. Start from updated <code>develop</code>.
2. Create a UC-specific feature branch (established pattern: <code>feature/uc-XX-...</code>).
3. Create/update the ignored local plan at <code>docs/.plans/UC-&lt;short-name&gt;.md</code>.
4. Make the smallest compatible model/controller/view/test changes.
5. Upgrade affected modules and run focused Odoo tests.
6. Review the diff, then commit and push only with explicit user approval.
7. Merge an approved UC branch into <code>develop</code>. Approved milestones merge <code>develop</code> into <code>main</code> and receive a tag.

### Diagnose an import

1. Open **E-commerce Connector → Operations → Import Error Queue**.
2. Inspect the external order, lines, mapping state, and redacted payload.
3. Correct the customer/product/store configuration issue.
4. Use the manager retry action; it records history and imports as the configured integration user.

### Demonstrate locally

1. Create a Mock Mode store with an integration user and operational defaults.
2. Configure products or mappings required by a sample.
3. Use **Salla Mock Lab** to create an event from a bundled JSON payload.
4. Trace the event, staged external order, and resulting sale order.
