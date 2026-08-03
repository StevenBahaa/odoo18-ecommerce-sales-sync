# Odoo 18 E-commerce Sales Sync Connector

Portfolio-grade Odoo 18 Community integration project for synchronizing e-commerce sales into Odoo.

## Purpose

This project demonstrates ERP integration skills around e-commerce order capture, webhook handling, staging records, customer matching, product mapping, sale order creation, duplicate protection, error handling, and reporting.

The first supported platform is **Salla**.

## Important Positioning

This is a portfolio MVP, not a certified production marketplace connector.

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

## Mandatory Mock Mode

Mock Mode is mandatory.

It allows the full demo flow without live Salla credentials, paid access, or external account dependency.

## High-Level Flow

Webhook Event -> External Order -> Validation -> Sale Order

Sale orders must never be created directly from raw webhook payloads.

## Security Notes

* Credentials and secrets must never be committed.
* API tokens must never be logged.
* Webhook secrets must never be logged.
* Token-bearing payloads must be redacted before storage.
* Production webhooks must use layered protection.

## Local Development Context

Project path:

```text
C:\odoo18\dev\odoo18-ecommerce-sales-sync
```

Odoo config:

```text
C:\odoo18\conf\odoo.conf
```

Odoo port:

```text
8070
```

```text
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

- Duplicate protection and idempotent external events (UC-12)
- Error queue and manual retry (UC-13)
- Order status updates (UC-14)
- Salla OAuth token ingestion and validation (UC-15)
- Token refresh locking and expiry warnings (UC-16)

## Roadmap

Upcoming capabilities:
- **UC-17**: Salla API Client and Optional Enrichment & Credential Safety UX

Before upgrading `ecommerce_connector_base` after adding the UC-12 sale-order
uniqueness constraint, run `scripts/check_uc12_sale_order_duplicates.sql` against
the development database. Resolve any duplicate store/reference pairs before the
upgrade. Archiving alone does not remove a normal SQL uniqueness conflict; the
connector fields must be corrected/relinked or the duplicate must be safely deleted.
