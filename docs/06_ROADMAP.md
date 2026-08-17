# Roadmap

This combines the local UC plan with code currently present on <code>develop</code>. It is a planning reference, not a commitment to deploy unimplemented integrations.

## Completed

| Range | Outcome |
| --- | --- |
| UC-00–UC-03 | Addon foundation, store setup, webhook receipt/audit, signature/rate-limit/integration-user gate. |
| UC-04–UC-08 | External-order staging, Salla order-created mapping, customer/product matching, validation. |
| UC-09–UC-11 | Store policies, Mock Lab, sale-order creation. |
| UC-12 | Database-backed duplicate protection and idempotent import. |
| UC-13 | Error queue, retry audit trail, manual retry via standard import path. |
| UC-14 | External order status updates with watermark ordering and row-lock serialization. |
| UC-15 | Salla OAuth authorization token ingest, replay ordering, integration-user guards, and redacted audit payloads. |

| UC-16 | Token refresh locking/expiry warnings and credential safety UX. |
| UC-17 | Salla API client and optional enrichment: GET-only Merchant API client, token preflight with single-use refresh lock, allowlisted Order Details mapper, rate-limit cooldown persistence, and stale/currency row-lock protection. |
| UC-18 | Stock readiness and inventory reservation policies: stock_sync_policy gate in action_create_sale_order(), warehouse-scoped free_qty check, product aggregation, float_compare UOM rounding, with_company scoping, and fail-closed no-warehouse behavior. |
| UC-22 | Salla live payload compatibility and status normalization: strict shared status normalizer, Salla datetime object parsing with timezone conversion to UTC, customer identity/mobile normalization, nested product/variant ID and line amount mapping, orders.read_write OAuth scope preflight. |
| UC-23 | Webhook retry status synchronization: direct external-order retry and webhook retry now converge the related `order.created` event to `processed` after a successful import. |

## Next

### UC-19 — Connector Reporting and Dashboards

Define sales reconciliation, sync volume, error rate metrics, and platform reporting views.

## Future

| UC | Theme | Current evidence |
| --- | --- | --- |
| UC-19 | Reporting | Records support reporting; dedicated reporting absent. |
| UC-20 | Demo data/scripts | Mock payloads/wizard exist; full demo bootstrap absent. |
| UC-21 | Documentation/release polish | Durable docs now exist; release work remains. |

## Nice-to-have

- CI that installs modules and runs targeted tests.
- Controller signature/rate-limit/redaction and matching edge-case tests.
- Documented local database bootstrap and demo walkthrough.
- README and TEST_CASES refresh through the current UC.
- Repeatable upgrade/migration checklist for database constraints.

## Long-term improvements

- Additional platform addons using the base connector contract.
- Production topology: TLS/reverse proxy, monitoring, backups, and operational alerting.
- Queue/worker design if webhook volume makes synchronous processing unsuitable.
- Formal external-payload schema/version compatibility strategy using captured payload tests.
- Country-aware phone normalization, only after explicit business rules.
- Reporting/dashboard definitions tied to business adoption metrics.

## Guardrails

- Do not pursue outbound stock synchronization before the scoped stock-readiness work.
- Do not implement live API calls ahead of OAuth/token safety work.
- Do not treat order updates as harmless; preserve audit trail and avoid destructive out-of-order changes.
- Keep Mock Mode functional as external integration features are added.
