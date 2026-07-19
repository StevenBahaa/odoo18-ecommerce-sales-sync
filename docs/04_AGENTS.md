# AI Agent Operating Manual

This is the persistent working agreement for coding agents. It supplements the root [AGENTS.md](../AGENTS.md); follow the more specific and safer instruction when they conflict.

## General behavior

1. Establish current branch and working-tree state before edits.
2. Read root instructions, the relevant manifest, models/controllers/views, and targeted tests before proposing code changes.
3. Treat current implementation as source of truth. <code>PROJECT_PLAN.md</code> is a useful local roadmap but is ignored and may lag code.
4. Make minimal, reversible changes. Do not change source for an audit, review, explanation, or plan request.
5. Preserve user work; never reset, overwrite, or delete unrelated changes.
6. State “Needs further investigation.” where repository evidence does not establish a fact.

## Planning a UC

Before discussing implementation:

1. Create/update <code>docs/.plans/UC-&lt;short-name&gt;.md</code>.
2. Include: title, goal, in/out scope, numbered checkbox steps, files, notes/open questions.
3. Keep it local: <code>docs/.plans/</code> is intentionally ignored and must never be staged/pushed.
4. Wait for explicit approval before implementation.

## Investigating bugs

1. Reproduce or trace with the smallest safe evidence source: tests, logs, state records, controller input, then code.
2. Identify store/company/user context, external identifier, and state transition.
3. Check authorization, integration user, mapping, and idempotency before touching import code.
4. Inspect both base and Salla overrides.
5. Report root cause and affected behavior. Do not fix unless asked.

## Implementing features

1. Confirm UC scope, prerequisites, and branch.
2. Find the existing extension point; reuse helpers instead of copying lookup, validation, linking, or sale-order creation.
3. Make server-side authorization explicit for each restricted action.
4. Preserve company isolation, store scoping, redaction, staged import, and SQL-backed idempotency.
5. Add/update focused Odoo tests.
6. Update current status, roadmap, architecture, and decisions documentation when behavior materially changes.

## Refactoring rules

Refactor only to avoid correctness-critical duplication, make the requested change safe/testable, repair a blocking defect, or extract a shared behavior required by the change.

Do not refactor for style alone, rename broad APIs, reorganize unrelated files, replace the test framework, or add a frontend/build system during a UC.

## Non-negotiable safety invariants

- Never create <code>sale.order</code> directly from raw webhook JSON.
- Retry only through the configured integration user; missing configuration is an attention-state error.
- Never weaken the store/external-reference uniqueness safeguard.
- Never log, commit, expose, or fabricate secrets.
- Keep external IDs store-scoped and company-safe.
- Preserve event/order audit trails on exceptions.
- Keep Mock Mode functional.

## Testing and diff checks

For code changes:

1. Upgrade affected modules in a local database.
2. Run targeted Odoo tests with <code>--test-enable</code> and appropriate tags.
3. Test relevant negative paths: permissions, missing integration user, mapping/payload failure, duplicate delivery, or concurrency.
4. Run <code>git diff --check</code>.
5. Review <code>git status --short</code>, full diff, and test diff.

There is no configured linter, formatter, coverage gate, or CI workflow. State exactly what ran and what did not.

## Review checklist

- Is the change in requested scope?
- Is it multi-company/multi-store safe?
- Are UI and Python authorization both enforced?
- Are sensitive values redacted?
- Are event/order transitions auditable?
- Does retry use the normal idempotent import path?
- Are manifest, imports, ACLs, and XML updated?
- Are tests meaningful?
- Are status/roadmap documents accurate?

## Communication

- Ask only concise, material questions that cannot be answered from repository evidence.
- Otherwise state a low-risk assumption and proceed.
- Lead handoffs with outcome, files changed, validation, risks, and recommended next task.
- For reviews, distinguish verified facts from concerns and do not edit unless asked.

## Git and releases

Established flow:

~~~text
feature/uc-XX-* -> develop -> main plus milestone tag
~~~

- Use a UC feature branch unless directed otherwise.
- Merge completed UC work into <code>develop</code> only after approval.
- Merge <code>develop</code> to <code>main</code> and tag only for an approved milestone.
- **Never commit or push without explicit user approval.**
- Before a requested commit, confirm branch, status, intended files, and commit scope.
- Match existing concise commit style, for example: <code>feat: implement UC-13 error queue and manual retry</code>.

## Documentation and generated files

- Durable docs belong in <code>docs/</code>; private UC plans belong in ignored <code>docs/.plans/</code>.
- Record consequential choices in [08_DECISIONS.md](08_DECISIONS.md).
- After material work, use [12_AI_HANDOFF_TEMPLATE.md](12_AI_HANDOFF_TEMPLATE.md) and append a concise [07_SESSION_LOG.md](07_SESSION_LOG.md) entry.
- Do not invent deployment/live-API/support claims.
- Do not manually edit/stage caches, logs, PID files, database dumps, local Odoo config, editor folders, or archive artifacts.
- XML, Python, manifests, tests, access CSVs, safe JSON samples, and the SQL duplicate-check script are maintained source files; edit only when in scope.
