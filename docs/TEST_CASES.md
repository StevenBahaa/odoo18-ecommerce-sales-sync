# Manual Test Cases

## UC-07 — Customer Matching & Phone Normalization

### TC-1 — Existing mapping
Same Store + External Customer ID finds mapping and reuses the mapped partner.

### TC-2 — Existing Odoo partner by email
No mapping exists; exact email finds existing partner; create mapping; do not create a partner.

### TC-3 — Existing Odoo partner by normalized phone
No mapping and no email match; differently formatted equivalent phone finds existing partner; create mapping; do not create a partner.

### TC-4 — New customer
No mapping, no matching email, no matching normalized phone; create one partner and one mapping.

### TC-5 — Missing external customer ID
Partner may still be found/created through email or phone, but no customer mapping is created with an empty external customer ID.

### TC-6 — Existing-customer reuse across a new order
Use a second payload with a DIFFERENT external_order_id but the same external customer data.
Verify that exactly one res.partner is reused and the mapping is reused.
(Use `salla_order_created_same_customer_new_order.json`).

### TC-7 — Existing UC-06 duplicate behavior
Replay the exact same payload with the same external_order_id.
Verify a new webhook event becomes `duplicate`, links to the existing external order, and creates neither a new external order nor a new partner.

### TC-8 — Company Scope
Create/import a new external customer through a Store belonging to Company A.
Verify the created partner has company_id = Company A and is correctly linked to the Company A external order.
Do not change cross-company customer reuse policy in UC-07.

## UC-12 — Duplicate Protection & Idempotency

### TC-UC12-1 — Pre-upgrade duplicate check
Run `scripts/check_uc12_sale_order_duplicates.sql` against the development database before upgrading the base module.
Resolve every returned store/reference pair before applying the sale-order uniqueness constraint.

### TC-UC12-2 — Repeated webhook payload
Send the same order payload twice.
Verify that exactly one external order is created, the second webhook event is `duplicate`, and both events link to the existing external order.

### TC-UC12-3 — Repeated sale-order import
Create a sale order from a ready external order, then invoke the import action again.
Verify that the existing sale order is opened and no second sale order is created.

### TC-UC12-4 — Existing sale order during validation
Create an external order and an existing sale order with the same store and external reference.
Validate the external order and verify that it links the existing sale order and becomes `imported`.

### TC-UC12-5 — Database uniqueness
Attempt to create two sale orders with the same non-null store and external reference.
Verify that PostgreSQL rejects the second record while normal sale orders without connector fields remain allowed.

### TC-UC12-6 — Race recovery
Exercise the protected create-race path so a uniqueness conflict is raised after the initial lookup.
Verify that the winning sale order is re-found, linked, and returned without a user-facing traceback.

### TC-UC12-7 — Cross-store external references
Use the same external reference for two different stores.
Verify that each store can have one sale order and that the stores do not conflict with each other.

## UC-15 — Secure OAuth Authorization Handling

### TC-UC15-1 — Successful Authorization Ingest
Send a valid `app.store.authorize` payload with `access_token`, `refresh_token`, and `offline_access` scope.
Verify the raw payload is redacted, but the store's credentials are updated with the correct expiry times.

### TC-UC15-2 — Missing/Redacted Credentials Rejected
Send a payload with missing tokens or `[REDACTED]` tokens.
Verify the event fails validation before modifying the store.

### TC-UC15-3 — Missing Offline Access Scope Rejected
Send a payload missing `offline_access` in the scope string.
Verify the event fails validation.

### TC-UC15-4 — Cross-Store Merchant ID Protection
Send an authorization payload where the `merchant` ID does not match the store's `store_identifier`.
Verify the event is parked as `pending_review` and credentials are not updated.

### TC-UC15-5 — Replay Ordering and Deduplication
Send an authorization payload with a timestamp older than the store's `last_oauth_authorized_at`.
Verify it is rejected.
Send a payload with the exact same timestamp and tokens.
Verify it is marked as `duplicate`.
Send a payload with the same timestamp but different tokens.
Verify it is parked as `pending_review` (ambiguous).

### TC-UC15-6 — Manager-only Retry Bypass
Attempt to manually retry an `app.store.authorize` event as a standard integration user (non-manager).
Verify an `AccessError` is raised.
Attempt to manually retry it as an integration manager.
Verify a `UserError` is raised, instructing the user to re-authorize from Salla.

## UC-16 — Token Refresh Locking & Expiry Warnings

### TC-UC16-1 — Successful Token Refresh
Trigger manual refresh on a store with valid refresh token.
Verify access token and refresh token are rotated, expiry dates advanced, and refresh lock cleared.

### TC-UC16-2 — Concurrent Token Refresh Rejection
Attempt concurrent token refresh on a locked store.
Verify `FOR UPDATE NOWAIT` immediately rejects concurrent attempt without double-refreshing.

### TC-UC16-3 — Refresh Failure and Re-authorization Flag
Simulate network failure or 400 Bad Request during token refresh.
Verify store is marked `token_refresh_requires_reauthorization = True` and refresh lock remains held until re-authorized.

## UC-17 — Salla API Client & Optional Order Enrichment

### TC-UC17-1 — Manual Enrichment Permission Guard
Attempt `action_enrich_from_salla` as standard connector user or connector manager.
Verify `AccessError` is raised. Verify only E-commerce Integration Manager is permitted.

### TC-UC17-2 — Staged Order Target Eligibility
Attempt enrichment on an archived store, Mock store, cancelled/imported order, or order linked to a `sale.order`.
Verify action is rejected with a descriptive user message.

### TC-UC17-3 — Access Token Preflight
Invoke enrichment on a store with valid token (> 60s to expiry).
Verify no refresh request is issued.
Invoke enrichment on a store with near-expired token (<= 60s to expiry).
Verify `_refresh_salla_token` is called exactly once before issuing the Merchant API call.

### TC-UC17-4 — Transport Safety & Error Redaction
Simulate HTTP redirects, network timeouts, connection drops, and oversized responses (> 2 MiB).
Verify safe `SallaAPIError` is raised without exposing tokens or raw payloads.

### TC-UC17-5 — Rate Limit Cooldown Persistence
Simulate HTTP 429 Too Many Requests with `Retry-After: 120`.
Verify `salla_api_retry_after_at` is persisted on `ecommerce.store` and subsequent calls within 120s are blocked before network socket creation.

### TC-UC17-6 — Successful Field Enrichment & Audit Trail
Enrich a draft staged order with valid Merchant API response.
Verify customer details (name join, phone normalization), monetary totals, and external status are updated.
Verify `salla_enrichment_count` increments to 1, `last_salla_enrichment_status` is `success`, and `raw_payload`, `state`, and `line_ids` are unmodified.

### TC-UC17-7 — Stale API Snapshot Protection
Set order watermark `last_external_update_at` to a timestamp newer than the API response `updated_at`.
Verify enrichment is rejected as stale, recorded as failed in audit, and staged fields remain unchanged.
