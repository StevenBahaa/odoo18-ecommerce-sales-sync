# Current Status

Snapshot date: **2026-08-02 (updated)**
Evidence: current <code>develop</code> branch, implementation, targeted tests, Git history, and local <code>PROJECT_PLAN.md</code>.

## Completed features

| Use case | Delivered capability | Evidence |
| --- | --- | --- |
| UC-00 | Repository/addon foundation | Two installable addon modules and base layout. |
| UC-01 | Store configuration and webhook identity | Store model, generated webhook tokens, views/security. |
| UC-02 | Webhook intake and audit capture | Public controller and redacted webhook-event records. |
| UC-03 | Secure processing gate | Integration-user guard, signature/rate-limit behavior. |
| UC-04 | External-order staging | External order/line models and state UI. |
| UC-05 | Salla payload mapping | Mapper and order-created event processing. |
| UC-06 | Product mapping | Explicit mapping and SKU fallback. |
| UC-07 | Customer matching | Mapping, exact email, normalized-phone matching. |
| UC-08 | Validation/import readiness | Validation errors/warnings before sale-order creation. |
| UC-09 | Store policies and discounts | Defaults, import policies, discount strategies. |

| UC-10 | Mock webhook lab | Salla wizard and bundled JSON samples. |
| UC-11 | Sale-order creation | Validated staged import, shipping/discount handling. |
| UC-12 | Duplicate protection/idempotency | SQL uniqueness, lookup/link helpers, race recovery, tests. |
| UC-13 | Error queue/manual retry | Queue action, retry audit history, guarded retry behavior, tests. |
| UC-14 | External order status updates | Partial-update mapper, watermark ordering, row-lock serialization, safe mirroring to sale order, 15 focused tests. |
| UC-15 | Secure OAuth authorization handling | Authorization-only transient credentials, redacted audit payloads, store lock/watermark, narrow sudo helper, and 17 focused tests. |
| UC-16 | Token refresh locking/expiry warnings | Token refresh concurrency locks, strict response parser, expiry warning cron, UX alerts, and 15 focused tests. |

UC-16 implementation and review fixes validated: 15/15 focused tests passed.

## Features in progress

No UC implementation is currently in progress. UC-17 is the next planned target.

| Priority | Item | Impact / recommended handling |
| --- | --- | --- |
| High | Live Salla API client is deferred | OAuth authorization and refresh are delivered; authenticated resource calls remain UC-17 work. |
| Medium | No CI/lint/formatting configuration | Regression checks require local Odoo commands and deliberate review. |
| Medium | Test coverage is selective | Focused tests cover UC-12 through UC-16; controller/security/mapping coverage still needs expansion. |
| Medium | Deployment runbook absent | TLS, proxy, workers, backups, monitoring, and production configuration need investigation. |
| Low | README formatting | An unmatched Markdown fence appears around the integration-user section. |
| Low | Test fixture realism | UC-12/13 retry tests use Odoo admin as integration user; production guidance requires a dedicated technical user. |

## Known bugs

No confirmed unresolved defect was found in the focused UC-12 through UC-16 regression run.

Real Salla payload compatibility, especially product identifier shapes beyond the bundled samples, **needs further investigation** against live documentation/payload captures before production use.

## Milestones

| Item | Status |
| --- | --- |
| Current active development line | <code>develop</code>, including UC-16. |
| Latest recorded main-branch milestone | <code>v0.2.0-product-mapping</code>. |
| Next milestone | Not formally defined in repository metadata. A UC-14 through UC-17 milestone is only a planning suggestion, not an approved release decision. |

## Prioritized next work

1. UC-17: Salla API client and optional enrichment.
2. UC-18: stock readiness.
3. UC-19: reporting.

Lower-priority planned work: UC-20 demo bootstrap/scripts, UC-21 release polish, CI, deployment documentation, broader tests, and README/test-case refresh.

## Current blockers

No repository-level code blocker for UC-17 is identified.

Live OAuth/API work may depend on Salla developer credentials, payload documentation, and a demo/client store. Exact external account prerequisites **need further investigation**.
