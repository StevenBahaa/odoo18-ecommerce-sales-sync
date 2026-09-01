# Troubleshooting

Use safe, redacted evidence. Do not paste credentials, raw authorization headers, database passwords, or unredacted production payloads into tickets or logs.

## Module does not appear or changes do not load

| Symptom | Likely cause | Diagnose and resolve |
| --- | --- | --- |
| Addon missing in Apps | Repository parent not in Odoo addons path | Verify local Odoo configuration; update app list. |
| Python model change has no effect | Module was not upgraded or file is not imported | Check package <code>__init__.py</code>, then upgrade affected module. |
| XML view/action missing | XML file absent from manifest data list | Add it to the correct manifest only when implementing the feature, then upgrade. |
| Access error after adding a model | ACL/group XML or access CSV is incomplete | Verify security XML, CSV model ID, manifest order, and Python-side checks. |

## Database and upgrade issues

| Symptom | Likely cause | Diagnose and resolve |
| --- | --- | --- |
| Unique-constraint install fails | Existing duplicate sale orders by store/external reference | Run <code>scripts/check_uc12_sale_order_duplicates.sql</code> against a copy/approved target, resolve records deliberately, then retry upgrade. |
| Cross-company validation error | Relational records do not share company context | Check store, partner, product, warehouse, and order company fields; preserve company-safe domains. |
| Database connection failure | Local PostgreSQL/Odoo config mismatch | Inspect local configuration without exposing secrets. Database provisioning details need further investigation. |
| Test database state is unexpected | Tests/upgrades reused a development database | Use a disposable database and confirm module-update command/database name. |

## Webhook errors

| Symptom | Likely cause | Diagnose and resolve |
| --- | --- | --- |
| HTTP 404 invalid store | URL platform/token does not identify an active store | Re-copy the computed webhook URL; check store active/platform/token. Regenerating token invalidates old URLs. |
| HTTP 401 invalid signature | Non-mock signature missing/incorrect or secret mismatch | Verify sender signing algorithm/header and restricted webhook secret. Do not log the secret. Mock Mode intentionally bypasses signature verification. |
| HTTP 429 | Per-store rate-limit window exceeded | Inspect store rate-limit configuration and event timestamps; avoid blindly increasing limits. |
| HTTP 500 logging failure | Odoo could not persist the event | Inspect server/database logs and model access/schema condition; do not lose payload evidence by retrying unknown writes blindly. |
| HTTP 200 but no sale order | This is expected when capture succeeds but business processing needs attention | Open webhook event and external order; inspect state/error/mappings. |

## Import, mapping, and retry issues

| Symptom | Likely cause | Diagnose and resolve |
| --- | --- | --- |
| Event/external order is pending review | Missing integration user, ambiguous customer, unsupported/deferred event, or other attention condition | Read the safe error, correct configuration/data, then retry if state permits. |
| External order is pending mapping | Product/customer mapping cannot resolve safely | Add/fix store-scoped mapping or SKU/product data, then use Retry Import. |
| Retry says integration user is not configured | Store has no <code>integration_user_id</code> | Configure a dedicated technical user with required Odoo permissions; do not use broad privileged fallback. |
| Retry action is denied | Current user lacks Connector Manager rights | Use an authorized role; UI visibility alone is not enough. |
| Duplicate delivery occurred | Platform redelivery or concurrent import | Confirm linked external/sale order. The intended outcome is one sale order due to lookup and SQL uniqueness. |
| Currency warning | External currency differs or is incomplete | Inspect raw normalized values and store/company currency; current behavior may warn without blocking. |

## Authentication and API issues

| Symptom | Likely cause | Diagnose and resolve |
| --- | --- | --- |
| OAuth token refresh locked | A prior refresh encountered a network timeout or connection ambiguity | Store is marked `token_refresh_requires_reauthorization`. Complete a new `app.store.authorize` flow to rotate tokens safely. |
| Enrichment blocked by cooldown | Salla API returned HTTP 429 (Too Many Requests) | Store is subject to active cooldown until `salla_api_retry_after_at`. Wait until the cooldown window expires before retrying. |
| API 401 Unauthorized | Access token revoked or invalid on Salla | Verify merchant app authorization; re-authorize the app via Salla App Store. |
| Enrichment currency mismatch | Salla order currency differs from staged order currency | Staged order was created with a different currency. Inspect store/company currency configuration. |
| Enrichment skipped as stale | Salla API snapshot `updated_at` is older than `last_external_update_at` | Staged order has already received newer webhook updates. No action needed; existing data is newer. |
| Enrichment action denied | User lacks E-commerce Integration Manager group | Only users in `group_ecommerce_integration_manager` can trigger manual API calls. |

## Localization & RTL issues

| Symptom | Likely cause | Diagnose and resolve |
| --- | --- | --- |
| Arabic language selected but layout is LTR | `rtlcss` is not installed on the host system | Install `rtlcss` globally via `npm install -g rtlcss`, clear cached assets (`ir_attachment` records with URL `%/assets/%`), and hard-refresh browser (`Ctrl + F5`). |
| New translations not appearing | Modules were not upgraded after adding or editing `.po` files | Upgrade `ecommerce_connector_base` and `ecommerce_salla_connector` (`-u` flag) to load new `.po` catalogs into the database. |


## Test failures

1. Confirm the Odoo server version and addons path contain this checkout.
2. Upgrade both connector modules before targeted tests.
3. Run the smallest relevant <code>--test-tags</code> selection first.
4. Check for stale custom data, missing fixtures, or permission assumptions.
5. Read the full traceback, then examine event/order state records and affected model overrides.
6. Run <code>git diff --check</code> before treating a whitespace/patch issue as a runtime failure.

No repository CI/lint configuration exists, so a CI/dependency failure outside these commands **needs further investigation**.

## Deployment problems

Deployment configuration is absent from this repository. Before any production deployment, establish and document:

- TLS/reverse-proxy route to the Odoo webhook endpoint;
- secure Odoo/PostgreSQL credentials and backups;
- worker/time-limit strategy;
- monitoring and redacted log retention;
- failure/retry operating procedure;
- Salla account, signature, OAuth, and API requirements.

Do not infer a production-ready deployment process from the local development README.
