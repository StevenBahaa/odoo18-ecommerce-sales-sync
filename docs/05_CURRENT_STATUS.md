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
| UC-17 | Salla API client and optional enrichment | Safe GET-only Merchant API client, token preflight with single-use refresh lock, allowlisted Order Details mapper, rate-limit cooldown persistence, stale/currency row-lock protection, and 43 focused tests covering 44 behaviors. |
| UC-22 | Salla Live Payload Compatibility and Status Normalization | Strict shared status normalizer (slug -> name string hierarchy), timezone-aware Salla datetime parsing, customer identity/mobile normalization, context-safe monetary parsing, nested product/variant ID and line amount mapping, strict malformed-line/quantity/float-boundary validation, and orders.read_write OAuth scope preflight support. |
| UC-23 | Webhook retry status synchronization | Imported external orders now close their linked failed/pending-review order-created webhooks, preserve webhook error audit history, and allow idempotent repair from either retry entry point. |

UC-22 implementation validated: 30/30 focused tests passed, all regression tests (UC-12 to UC-17, 114 total tests) passed. Manual live verification remains pending a new demo-store order after upgrade.

UC-23 focused validation passed: 6/6 UC-13 base retry tests. The affected non-UC-15 regression set passed. The full run's only error was an environmental Windows filestore permission denial while UC-15 created an attachment, not a connector assertion failure.

## Features in progress

No UC implementation is currently in progress. UC-18 is the next planned target.

| Priority | Item | Impact / recommended handling |
| --- | --- | --- |
| High | Stock readiness is deferred | Order sync, OAuth, token refresh, and manual enrichment are delivered; stock reservation/readiness policies remain UC-18 work. |
| Medium | No CI/lint/formatting configuration | Regression checks require local Odoo commands and deliberate review. |
| Medium | Test coverage is selective | Focused tests cover UC-12 through UC-17; controller/security/mapping coverage still needs expansion. |
| Medium | Deployment runbook absent | TLS, proxy, workers, backups, monitoring, and production configuration need investigation. |
| Low | README formatting | An unmatched Markdown fence appears around the integration-user section. |
| Low | Test fixture realism | UC-12/13 retry tests use Odoo admin as integration user; production guidance requires a dedicated technical user. |

## Known bugs

No confirmed connector defect remains in the focused UC-13 retry workflow. The full UC-15 regression requires write access to Odoo's configured Windows filestore before it can be rerun cleanly.

Real Salla payload compatibility, especially product identifier shapes beyond the bundled samples, **needs further investigation** against live documentation/payload captures before production use.

## Milestones

| Item | Status |
| --- | --- |
| Current active development line | <code>develop</code>, including UC-17. |
| Latest recorded main-branch milestone | <code>v0.2.0-product-mapping</code>. |
| Next milestone | Not formally defined in repository metadata. A UC-14 through UC-17 milestone is now fully implemented on develop. |

## Prioritized next work

1. UC-18: stock readiness.
2. UC-19: reporting.
3. UC-20: demo data / bootstrap.

Lower-priority planned work: UC-20 demo bootstrap/scripts, UC-21 release polish, CI, deployment documentation, broader tests, and README/test-case refresh.

## Current blockers

No repository-level code blocker for UC-18 is identified.
