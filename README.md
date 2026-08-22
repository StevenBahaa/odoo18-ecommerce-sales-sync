# Odoo 18 E-commerce Sales Sync Connector

Portfolio-grade Odoo 18 Community integration that receives Salla e-commerce order webhooks, stages and validates them, and creates exactly one audited, idempotent Odoo sale order.

**Positioning:** portfolio MVP, not a certified production marketplace connector.

## The business problem

- Online orders are re-entered into Odoo by hand, wasting time and introducing errors.
- Customer/product mapping failures surface late or silently produce wrong orders.
- Platform delivery retries and races create duplicate sale orders.
- There is no auditable trail between what the platform sent and what Odoo booked.

## How it works

```text
Webhook Event -> External Order staging -> Customer/Product matching + validation -> Sale Order
```

Sale orders are NEVER created directly from raw webhook payloads.

## Modules

### ecommerce_connector_base

Generic connector layer containing shared ERP concepts:

* Store configuration
* Webhook event logging
* External order staging
* External order lines
* Customer mappings
* Product mappings
* Sale order extension
* Error queue and retry foundations
* Reporting foundations

### ecommerce_salla_connector

Salla-specific layer containing:

* Salla platform settings
* Salla webhook handling
* Salla payload mapping
* Salla OAuth/token handling
* Salla sample payloads

## Feature highlights

- Webhook intake with store token, HMAC signature, rate limiting, redacted audit (UC-02/03)
- External-order staging, state machine, error queue, guarded manual retry (UC-04/08/13)
- Customer matching via mapping/exact email/normalized phone; product mapping + SKU fallback (UC-06/07)
- Idempotent sale-order creation backed by a DB uniqueness constraint and race recovery (UC-11/12)
- Salla live-payload compatibility: status slugs, timezone-aware datetimes, strict Decimal money parsing, payment_method/shipping_status fallbacks (UC-22)
- OAuth authorization ingest + single-use refresh-token locking + expiry warnings (UC-15/16)
- GET-only manual Salla API enrichment with rate-limit cooldown and stale-response protection (UC-17)
- Stock readiness gate before import (UC-18)
- Reporting pivot/graph views: Orders by Store & Status, Webhook Health, Imported Sale Orders (UC-19)
- Webhook retry status synchronization (UC-23); idempotent demo bootstrap data (UC-20)

## Mandatory Mock Mode

Mock Mode demonstrates the full flow without paid/live Salla access. It is the guaranteed free demo path. Mock stores skip signature verification by design.

## Quick demo flow

1. Install both addons:
   ```powershell
   python C:\odoo18\odoo-bin -c C:\odoo18\conf\odoo.conf -d <dev-db> -u ecommerce_connector_base,ecommerce_salla_connector --stop-after-init
   ```
2. Create a store: platform **Salla**, environment **Mock**, company set, integration user set, stock policy **No Stock Sync**.
3. Demo-enabled database: demo data auto-creates "UC-20 Demo Salla Store" with five webhook events, three external orders (imported / pending_mapping / ready-with-currency-warning), and one real sale order. Re-running the upgrade creates nothing twice (idempotent).
4. Manual path: Operations -> Salla Mock Lab -> pick a template (order.created, Missing SKU, Multi-currency SAR, app.installed, app.store.authorize, ...) -> Create Event.
5. Fix mappings, then Retry Import from the Import Error Queue.
6. Inspect webhook event -> external order -> sale order; explore the Reporting menus.

## Security notes

* Credentials and secrets must never be committed.
* API tokens must never be logged.
* Webhook secrets must never be logged.
* Token-bearing payloads must be redacted before storage.
* Production webhooks must use layered protection.

## Known limitations

- Portfolio MVP, not a certified Salla marketplace app.
- Mock Mode is the guaranteed free demo path; Demo/Production access depends on a real Salla account/app setup and is not fully established here.
- Stock push/synchronization is out of MVP (UC-18 gates imports on stock readiness only).
- Refunds, returns, and partial fulfillment are out of MVP.
- Payment reconciliation is out of MVP.
- Reverse-proxy rate limiting is recommended for production deployments.
- The proportional discount-allocation strategy has allocation limitations.
- UI password masking is not database encryption; secrets are access-restricted only.
- `order.cancelled` webhooks are recorded but have no dedicated handling yet.

## Documentation map

- [01 Project Context](docs/01_PROJECT_CONTEXT.md)
- [02 Architecture](docs/02_ARCHITECTURE.md)
- [03 Coding Standards](docs/03_CODING_STANDARDS.md)
- [05 Current Status](docs/05_CURRENT_STATUS.md)
- [06 Roadmap](docs/06_ROADMAP.md)
- [08 Decisions](docs/08_DECISIONS.md)
- [09 Glossary](docs/09_GLOSSARY.md)
- [10 Onboarding](docs/10_ONBOARDING.md)
- [11 Troubleshooting](docs/11_TROUBLESHOOTING.md)
- [13 Screenshot Guide](docs/13_SCREENSHOT_GUIDE.md)
- [Release Checklist](docs/RELEASE_CHECKLIST.md)
- [Test Cases](docs/TEST_CASES.md)

## Local development context

Project path `C:\odoo18\dev\odoo18-ecommerce-sales-sync`, config `C:\odoo18\conf\odoo.conf`, port 8070.

```powershell
python C:\odoo18\odoo-bin -c C:\odoo18\conf\odoo.conf -d salla_test -u ecommerce_connector_base,ecommerce_salla_connector --stop-after-init
```

## Integration User Setup

The connector is designed to avoid broad uncontrolled sudo usage during webhook business processing.

For real processing, create a dedicated Odoo technical user, for example:

E-commerce Integration Bot

Recommended access:

- Sales access needed to create quotations/sale orders later.
- Inventory read access for stock-readiness checks later.
- Contact access needed to match or create customers later.
- E-commerce Connector Manager access.
- E-commerce Integration Manager access only if the user is also responsible for connector configuration.

The integration user should not be the main Administrator user.

If no integration user is configured on the store, future webhook handling may only store the raw webhook event with minimal controlled elevation. It must not create partners, products, external orders, or sale orders using broad unrestricted superuser access.

## Phone Normalization Note (MVP Limit)

Phone normalization in this MVP strictly removes formatting (spaces, dashes, parentheses) to produce a digits-only string.
It does not infer country-code equivalence.
For example, `01000000000` is not considered equivalent to `+201000000000`.

## Release & upgrade notes

Before upgrading after the UC-12 constraint was introduced, run `scripts/check_uc12_sale_order_duplicates.sql`. See [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) for the full release procedure. Roadmap lives in [docs/06_ROADMAP.md](docs/06_ROADMAP.md).
