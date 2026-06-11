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

## Development Roadmap

Current milestone:

```text
UC-00 — Repository Setup & Project Rules
```

Next milestone:

```text
UC-01 — Connector Base & Store Configuration
```
