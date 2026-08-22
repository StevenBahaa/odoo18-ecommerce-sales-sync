# Developer Onboarding

## Project philosophy

The connector favors ERP safety and auditability over immediate automation:

1. receive and preserve a redacted event;
2. stage the external order;
3. match and validate data;
4. create exactly one sale order only when safe;
5. make failures repairable and retryable.

Do not bypass those stages for convenience.

## What you need

- A local Odoo 18 Community checkout.
- Python/runtime requirements required by that Odoo checkout.
- PostgreSQL accessible to Odoo.
- A local Odoo configuration file outside this repository.
- This repository included in Odoo's addons path.

Exact versions, dependency installation, PostgreSQL credentials, and database-creation steps are not versioned in this repository and **need further investigation** from the local Odoo environment.

## Install and run

1. Clone the repository into a directory included in Odoo's addons path.
2. Configure Odoo to load the parent addons directory and connect to a development database.
3. Update the two modules:

~~~powershell
python C:\odoo18\odoo-bin -c C:\odoo18\conf\odoo.conf -d salla_test -u ecommerce_connector_base,ecommerce_salla_connector --stop-after-init
~~~

4. Start Odoo normally using your local configuration.
5. In Apps, confirm both addons are installed/upgraded.

The Windows paths/database name are local examples from the existing README. Do not commit an Odoo configuration file or credentials.

## First local demonstration

1. Sign in as a user with Integration Manager permissions.
2. Create an e-commerce store in Mock Mode.
3. Set company/warehouse/pricelist/sales defaults and a dedicated integration user.
4. Create/match products required by a sample payload.
5. Open **E-commerce Connector → Operations → Salla Mock Lab**.
6. Send an order-created sample.
7. Inspect the webhook event, external order, mapping outcome, and sale order.

If a product is unresolved, fix its mapping and use **Retry Import** from the error queue.

## How to debug

Start from the persisted records, not from a guessed code path:

1. Locate the webhook event by store, external ID, or received time.
2. Inspect its safe error, status, related external order, and redacted payload.
3. Inspect external-order state, warnings/errors, customer result, and line mapping states.
4. Confirm the store has an integration user and correct operational defaults.
5. Confirm product/customer mapping scope matches the same store/company.
6. Use the retry audit history to understand prior attempts.
7. Trace controller, event handler, mapper, and external-order methods only after the state evidence is known.

## How to test

Run focused Odoo tests after upgrading affected modules:

~~~powershell
python C:\odoo18\odoo-bin -c C:\odoo18\conf\odoo.conf -d salla_test -u ecommerce_connector_base,ecommerce_salla_connector --test-enable --test-tags /ecommerce_connector_base:TestUC12SaleOrderIdempotency,/ecommerce_salla_connector:TestUC12WebhookIdempotency,/ecommerce_connector_base:TestUC13ManualRetry,/ecommerce_salla_connector:TestUC13WebhookRetry --stop-after-init --no-http --log-level=error
~~~

Use a throwaway/development database when running module upgrades. GitHub Actions workflows (`static-checks` and `odoo-tests`) run automatically on push/PR to `develop` and `main`.

## How to contribute

1. Read [02_ARCHITECTURE.md](02_ARCHITECTURE.md), [03_CODING_STANDARDS.md](03_CODING_STANDARDS.md), and the relevant model/test files.
2. Create a feature branch named for the UC.
3. Create the ignored local UC plan under <code>docs/.plans/</code>.
4. Implement the smallest safe vertical change with tests.
5. Upgrade modules, run focused tests, inspect <code>git diff --check</code>, and review the diff.
6. Update durable docs if behavior/status/decisions changed.
7. Do not commit or push without explicit approval.

## Common pitfalls

| Pitfall | Correct approach |
| --- | --- |
| Creating sale orders in a controller | Always use staged external orders and validation. |
| Missing integration user | Treat as a configuration attention state; do not run under a manager or broad privileged user. |
| Assuming external IDs are global | Scope searches/mappings by store and company. |
| Testing only the happy path | Cover missing mapping, permissions, duplicates, and retry behavior. |
| Copying duplicate handling into a retry | Reuse existing lookup/link/import helpers. |
| Logging samples casually | Payloads may contain sensitive fields; use redaction. |
| Editing local config | Keep it outside Git; do not expose secrets in issues/commits/docs. |
| Relying on README milestone text | Check current Git history and [05_CURRENT_STATUS.md](05_CURRENT_STATUS.md). |

## Build and deployment

Odoo module update is the effective build/install step. No Docker image, CI artifact, deployment manifest, release automation, or production runbook is present. Production deployment procedures **need further investigation** before operating this connector outside a local portfolio environment.
