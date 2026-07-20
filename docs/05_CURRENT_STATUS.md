# Current Status

Snapshot date: **2026-07-19 (updated)**
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
| UC-14 | External order status updates | Partial-update mapper, watermark ordering, row-lock serialization, safe mirroring to sale order, 12 focused tests. |

UC-14 implementation validated 2026-07-19: 12/12 tests passed, UC-12/13 regression clean.

## Features in progress

No UC implementation is currently in progress. UC-15 is the next planned target.

## Known gaps and technical debt

| Priority | Item | Impact / recommended handling |
| --- | --- | --- |
| High | Live OAuth/API is deferred | Token fields exist, but authorization ingest, refresh, and outbound API calls are UC-15 through UC-17 work. |
| Medium | Documentation drift | README says UC-12 is current and TEST_CASES lacks UC-13/14. Refresh them in a documentation/release task. |
| Medium | No CI/lint/formatting configuration | Regression checks require local Odoo commands and deliberate review. |
| Medium | Test coverage is selective | Focused tests cover UC-12/13/14; controller/security/mapping coverage needs expansion. |
| Medium | Deployment runbook absent | TLS, proxy, workers, backups, monitoring, and production configuration need investigation. |
| Low | README formatting | An unmatched Markdown fence appears around the integration-user section. |
| Low | Test fixture realism | UC-12/13 retry tests use Odoo admin as integration user; production guidance requires a dedicated technical user. |

## Known bugs

No confirmed unresolved defect was found in the current UC-12/UC-13 implementation during the last targeted test run.

Real Salla payload compatibility, especially product identifier shapes beyond the bundled samples, **needs further investigation** against live documentation/payload captures before production use.

## Milestones

| Item | Status |
| --- | --- |
| Current active development line | <code>develop</code>, including UC-13. |
| Latest recorded main-branch milestone | <code>v0.2.0-product-mapping</code>. |
| Next milestone | Not formally defined in repository metadata. A UC-14 through UC-17 milestone is only a planning suggestion, not an approved release decision. |

## Prioritized next work

1. UC-15: secure OAuth authorization handling.
2. UC-16: token refresh lock/expiry behavior.
3. UC-17: Salla API client and optional enrichment.

Lower-priority planned work: UC-18 stock readiness, UC-19 reporting, UC-20 demo bootstrap/scripts, UC-21 release polish, CI, deployment documentation, broader tests, and README/test-case refresh.

## Current blockers

No repository-level code blocker for UC-15 is identified.

Live OAuth/API work may depend on Salla developer credentials, payload documentation, and a demo/client store. Exact external account prerequisites **need further investigation**.
