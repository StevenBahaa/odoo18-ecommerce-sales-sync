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

## Next

### UC-18 — Stock Readiness and Inventory Reservation Policies

Implement stock readiness policies and inventory availability checks:
- Verify physical stock availability in mapped warehouse before sale order confirmation.
- Configurable store stock policies (auto-reserve, stock warning guard).
- Prevent overselling and flag staged orders with insufficient stock.

## Future

| UC | Theme | Current evidence |
| --- | --- | --- |
| UC-18 | Stock readiness | Store policy field exists; fulfillment logic scheduled. |
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
