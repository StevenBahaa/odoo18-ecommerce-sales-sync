# Coding Standards

These standards describe patterns actually present in this repository. Where there is no tool or frontend, that absence is recorded rather than replaced with a generic convention.

## General conventions

- Follow the surrounding module's style before introducing a new pattern.
- Use Python <code>snake_case</code> for variables, methods, fields, and filenames; use <code>PascalCase</code> for classes.
- Prefer small Odoo model methods with meaningful prefixes: <code>action_...</code> for UI actions, <code>_...</code> for helpers, <code>_compute_...</code> for computes, and <code>_check_...</code> for guards.
- Keep generic behavior in the base addon and Salla schema/payload behavior in the Salla addon.
- Keep changes scoped to the requested UC; do not add broad cleanup to a focused fix.

## Folder organization

| Location | Convention |
| --- | --- |
| <code>models/</code> | Cohesive Odoo concern per file; export from <code>models/__init__.py</code>. |
| <code>controllers/</code> | Custom HTTP routes; export from <code>controllers/__init__.py</code>. |
| <code>views/</code> | XML list, form, search, action, and menu definitions. |
| <code>security/</code> | Group XML and model-access CSV. |
| <code>data/</code> | Sequences and safe fixture/sample data. |
| <code>wizard/</code> | Transient-model workflows such as the Mock Lab. |
| <code>tests/</code> | Odoo tests grouped by UC/behavior. |
| <code>utils/</code> | Small pure helpers, currently phone normalization. |

When adding Python/XML source, update the relevant import and manifest list. A file that is not imported/listed is not active in Odoo.

## Odoo model practices

- Add <code>_description</code> to models.
- Preserve company isolation with the existing company checks and <code>check_company=True</code> relational fields.
- Use Odoo fields, constraints, and SQL constraints for integrity that must survive concurrent requests.
- Use batch-safe create overrides such as <code>@api.model_create_multi</code> when appropriate.
- Scope external identifiers by store; never assume they are globally unique.
- Keep raw external values separate from normalized/matched Odoo values.
- Reuse existing lookup and validation helpers instead of copying their logic.

## Error handling and retries

- Use <code>UserError</code> for user-facing invalid actions and <code>AccessError</code> for authorization violations.
- Webhook business failures should record a safe event/order error and attention state, not crash the request.
- Preserve retry audit information before reset: count, user/time, and error-history snapshot.
- Use a database savepoint when an <code>IntegrityError</code> must be recovered without aborting the complete transaction.
- Recover duplicate sale-order races through the existing lookup/link helpers. Do not create a second import path.
- A retry must require <code>store.integration_user_id</code>; do not fall back to the manager or broad privileged execution.

## Logging and secrets

- Never log or persist plaintext credentials, access/refresh tokens, webhook secrets, OAuth codes, authorization headers, cookies, or database passwords.
- Reuse the existing webhook redaction approach for payloads, headers, and error text.
- Keep operational errors useful but bounded; the controller already truncates/redacts safe error text.
- Use the module logger for failures and avoid noisy success logs.

## Security and API conventions

- Protect restricted operations in both XML and Python. A hidden button is not authorization.
- Keep credential fields restricted to Integration Managers.
- Public-controller work must remain narrow: validate token/rate/signature, save redacted audit data, then use the integration-user gate.
- Do not introduce broad <code>sudo()</code> for business work. Document any narrow privileged configuration/audit use.
- Preserve HMAC verification outside Mock Mode and never enable a production bypass.
- The current custom route is a public POST at <code>/ecommerce/webhook/&lt;platform&gt;/&lt;store_token&gt;</code>. Parse JSON defensively and return safe JSON/statuses without stack traces or secrets.
- Store first, process second. A valid event receives a receipt response after storage even if downstream work fails.

## XML/Odoo UI conventions

- Keep operational records discoverable through list, form, search, and action views.
- Use group attributes on restricted fields/buttons and match them with model checks.
- Keep audit/raw fields readonly and sensitive values hidden.
- Use clear action names such as “Retry Import” and “Import Error Queue.”
- There is no custom JavaScript component or separate accessibility policy. Use native Odoo widgets and visible labels. Custom frontend accessibility requirements **need further investigation** before adding custom UI.

## TypeScript and React

TypeScript and React are not used. Do not add a Node/React stack for an Odoo view task without an explicit architecture decision that first defines tooling, state, testing, and accessibility expectations.

## Tests

- Use Odoo <code>TransactionCase</code> and standard <code>unittest</code> helpers.
- Test state transitions, permissions, mappings, idempotency, recorded errors, and retry recovery.
- Include cross-store and duplicate/concurrency cases when changing identity/import logic.
- Put Salla behavior in the Salla addon tests.
- Upgrade affected modules and run targeted tests with <code>--test-enable</code> and <code>--test-tags</code>.

No repository-configured formatter, linter, coverage gate, pytest setup, or CI workflow exists. Do not claim lint/CI passed unless a concrete command was available and run.

## Performance

- Use existing indexed/unique identifiers for store, external order, and sale-order lookups.
- Scope domains by store and company.
- Avoid unbounded controller queries; rate limiting already uses a time window.
- Avoid repeated mapping searches when a resolved mapping is available.
- Consider webhook volume before adding stored computes or database work to the request path.

## SHOULD and SHOULD NEVER

### SHOULD

- Stage and validate before sale-order creation.
- Reuse matching, validation, and idempotency helpers.
- Make every manager action authorization-safe and test it.
- Update project status/roadmap documentation after a UC changes status.
- Create an ignored UC plan before implementation.

### SHOULD NEVER

- Create a sale order directly from unvalidated webhook JSON.
- Bypass the integration-user guard with broad privileged execution.
- Remove the database uniqueness safeguard for external references.
- Treat duplicate delivery as permission for a second staging/sale order.
- Commit secrets, local Odoo config, database dumps, runtime artifacts, or ignored plans.
- Refactor unrelated models/XML/formatting in a narrow UC.
