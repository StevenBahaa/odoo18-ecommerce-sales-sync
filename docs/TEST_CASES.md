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

## UC-13 — Error Queue & Manual Retry

### TC-UC13-1 — Error Queue Visibility
Create external orders in `pending_mapping`, `pending_review`, and `failed` states for a store.
Verify the Import Error Queue lists all three and excludes imported/duplicate orders.

### TC-UC13-2 — Retry Requires Connector Manager
Call retry as Connector User. Verify `AccessError`; UI button hidden AND Python guard enforced.

### TC-UC13-3 — Retry Blocked Without Integration User
Remove `integration_user_id` from the store; retry as manager. Verify explicit configuration
error and NO partner/product/sale-order writes occur under broad privileges.

### TC-UC13-4 — Successful Retry Uses Idempotent Import
Fix the mapping, retry. Verify state reaches `imported`, exactly one sale order exists, and a
redelivery afterwards links to the same sale order.

### TC-UC13-5 — Retry Preserves Audit History
Before retry, snapshot error/warning/state. After a failed retry attempt verify retry count
incremented, user/time recorded, and prior error text preserved in history fields.

## UC-14 — External Order Status Updates

### TC-UC14-1 — Newer Update Applied
Send `order.updated` newer than the watermark. Verify accepted fields written and both
watermark fields advanced.

### TC-UC14-2 — Older Update Parked
Send update older than watermark. Verify event `pending_review`, staged order unchanged.

### TC-UC14-3 — Exact Duplicate Update
Same timestamp + same event ID as last applied. Verify event `duplicate`, nothing mutated.

### TC-UC14-4 — Ambiguous Same-Time Update
Same timestamp, different event ID. Verify `pending_review` with ambiguity message.

### TC-UC14-5 — Omitted Fields Never Cleared
Update payload containing only `status`. Verify customer/amounts/payment fields untouched.

### TC-UC14-6 — Currency Mismatch Parks Atomically
Monetary update whose currency differs from the staged order currency. Verify entire event
parked with no field written, including no partial amount write.

### TC-UC14-7 — Safe Sale-Order Mirroring
On an imported order, send payment/shipping status update. Verify linked sale order's
connector informational fields updated; state/totals/lines never modified.

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

## UC-22 — Salla Live Payload Compatibility & Status Normalization

### TC-UC22-1 — Live Status Object Normalization
Receive a live Salla webhook or API response where `status` is a JSON object containing `id`, `name`, and `slug`.
Verify `external_status` is stored strictly as the scalar string `slug` (e.g. `under_review`) and never stringifies a Python dictionary or JSON container.

### TC-UC22-2 — Status Fallback to Name
Receive a status object with missing/blank slug and valid string `name`.
Verify `external_status` falls back to `name`. Verify numeric slugs and container IDs do not override string names.

### TC-UC22-3 — Timezone-Aware Datetime Normalization
Receive a Salla datetime object (`{"date": "2026-08-15 03:17:11.000000", "timezone": "Asia/Riyadh"}`) or top-level RFC/GMT timestamp with explicit offset (`Sat Aug 15 2026 03:17:13 GMT+0300`).
Verify the timestamp is converted accurately to UTC-naive datetime string (`2026-08-15 00:17:11` / `2026-08-15 00:17:13`).

### TC-UC22-4 — Customer Identity & Canonical Phone Normalization
Receive a payload with `full_name`, numeric `mobile`, and `mobile_code`.
Verify customer name is extracted and phone is stored in canonical digits without duplicate country codes.

### TC-UC22-5 — Nested Line Item Identifiers & Amounts
Receive line items exposing product ID at `item.product.id`, variant at `item.product_sku_id`, and unit price at `item.amounts.price_without_tax`.
Verify external product/variant IDs and nonzero unit prices/subtotals are mapped accurately.

### TC-UC22-6 — Strict Price Ambiguity & Malformed Value Protection
Simulate a line with unparseable price string or an ambiguous line total derivation with non-zero discount.
Verify `UserError` is raised and the line price is never silently defaulted to `0.0`.

### TC-UC22-7 — OAuth Scope Preflight (orders.read and orders.read_write)
Authorize store with exact `orders.read_write` or `orders.read`.
Verify `_prepare_salla_access_token` succeeds. Verify lookalike tokens (`orders.read_all`, `orders.readonly`) are rejected.

### TC-UC22-8 — End-to-End Workflow & Idempotency
Process a live-like webhook payload with mapped products and SAR currency.
Verify the external order and lines transition to `ready`.
Process a payload with unmapped products.
Verify lines remain in `pending_mapping` and event is parked for review.
Redeliver the event and verify idempotency.

### TC-UC22-9 — Malformed Line, Quantity, Range, and Identifier Safety
Receive an item list containing a non-object entry, or an item with an explicitly
null quantity. Verify the payload is rejected rather than silently importing a
partial order or treating null as quantity one. Submit a finite Decimal exponent
that overflows Python/Odoo Float storage and verify it is rejected. Submit an
invalid truthy primary identifier plus a valid fallback identifier and verify the
valid scalar fallback is used; floating-point IDs must be rejected.

### TC-UC22-10 — Monetary Context, Datetime Type, and Full Idempotency
Verify a list is summed only for a discount collection and is rejected for a
total, price, tax, or shipping field. Verify a partial update accepts the shared
`{"total": ...}` monetary wrapper. Verify a naive datetime object with a present
invalid or blank timezone is rejected. Process a malformed-line webhook and
verify no external order is created; then redeliver a successfully imported order
and verify the existing external order, partner, and sale order are reused.

## UC-23 — Webhook Retry Status Synchronization

### TC-UC23-1 — Direct External-Order Retry Closes Webhook Review
Create an `order.created` webhook whose staged order is `pending_mapping` because
of an unmapped SKU. Create a matching Odoo product and click **Retry Import** on
the external order. Verify the external order is `imported`, its webhook is
`processed`, the webhook links the matched partner and created sale order, its
active error is cleared, and its former error remains in webhook error history.

### TC-UC23-2 — Stale Webhook Retry Is Idempotent
Create a `pending_review` order-created webhook linked to an already imported
external order and sale order. Click **Retry Processing**. Verify it becomes
`processed` without attempting a terminal external-order retry or creating a
second sale order; the retry audit and previous error history remain available.

## UC-18 — Stock Readiness and Inventory Reservation Policies

### TC-UC18-1 — Policy None Skips Check
`stock_sync_policy = "none"`, zero stock. Verify sale order created without stock warning.

### TC-UC18-2 — No Warehouse: Fail Closed
`readiness_only`, no warehouse. Verify parked in `pending_review`; no SO; "no warehouse is configured" in `warning_message`.

### TC-UC18-3 — Sufficient Free Stock Allows Import
`readiness_only` + warehouse + `free_qty >= ordered` for all storables. Verify SO created, no stock warning.

### TC-UC18-4 — Insufficient Stock Parks Order
`free_qty < ordered` for a storable. Verify `pending_review`, no SO, `warning_message` names product+ordered+unreserved+warehouse.

### TC-UC18-5 — All Stock Reserved Parks Order
On-hand stock exists but fully reserved (`free_qty=0`). Verify parked in `pending_review`.

### TC-UC18-6 — Partially Reserved: Only Free Qty Counts
4 on-hand, 3 reserved (1 free), order requests 2. Verify parked in `pending_review`.

### TC-UC18-7 — Non-Storable Consumable Never Triggers Warning
`is_storable=False` consumable lines only. Verify SO created.

### TC-UC18-8 — Service Product Never Triggers Warning
Service lines only. Verify SO created.

### TC-UC18-9 — Mixed Lines: One Short Parks Whole Order
One short storable + one service. Verify parked, storable named, service not named.

### TC-UC18-10 — Exact Free Stock Match Allows Import
`free_qty == ordered`. Verify SO created.

### TC-UC18-11 — Stock Warning Appended, Existing Warning Preserved
Pre-existing currency warning + zero free stock. Verify both exist in `warning_message` and `error_message` is untouched.

### TC-UC18-12 — Duplicate Product Lines Aggregated
Two lines same product, combined qty > free_qty. Verify parked; aggregated qty in `warning_message`.

### TC-UC18-13 — Warehouse Context Key `warehouse`
Stock only in second warehouse (same company); store uses first (0 stock). Verify parked; context key `warehouse` properly scopes stock computation.

### TC-UC18-14 — UOM Rounding Boundary Passes
`free_qty` within half UOM rounding unit of ordered. `float_compare` treats as equal; SO created.

### TC-UC18-15 — Retry After Stock Resolved
Park an order due to shortage (`pending_review`). Resolve stock. Call `action_retry_import()` (as the store's Connector Manager). Verify the order transitions through `captured` -> `ready` -> `imported`, and that a sale order is created.

### TC-UC18-16 — Retry When Stock Still Short
Same as TC-UC18-15 but do not resolve stock. Verify order reparks in `pending_review` and `warning_message` contains the shortage reason.

### TC-UC18-17 — Multi-Company Stock Scoped
Stock only in second company's WH. Order in first company. Verify parked.

### TC-UC18-18 — Retry Notification Displays Warning
Trigger a retry while stock is short. Verify the returned UI dictionary includes the stock warning in its message.

### TC-UC18-19 — Stock Recheck and Resolution Cleans Warning
Park due to shortage with pre-existing currency advisory. Recheck with partial stock updates shortage numbers without duplicating warnings. When stock resolved, verify stock warning is cleared while preserving currency advisory.

### TC-UC18-20 — Switch Policy to None Clears Stale Stock Warning
Order with stale stock warning transitions to imported when policy changed to 'none' and stock warning is stripped from `warning_message`.

### TC-UC18-21 — Strip Stock Warning Helper
Unit test verifying `_strip_stock_warning` removes stock shortage and no-warehouse blocks while preserving non-stock advisories.

## UC-19 — Reporting and Manager Views

### TC-UC19-1 — Connector-Only User Can Read E-commerce Sale Orders
A user with only `group_ecommerce_connector_user` (no Sales-app group) can read a `sale.order`
record linked to an e-commerce store, via the new access right.

### TC-UC19-2 — Connector-Only User Cannot Write Sale Orders
The same user cannot write any field on a `sale.order` record — the new access right is read-only.

### TC-UC19-3 — Connector-Only User Cannot Create Sale Orders
The same user cannot create a new `sale.order` record — the new access right grants no create
permission.

### TC-UC19-4 — Imported Sale Orders Domain Excludes Non-E-commerce Orders
`action_ecommerce_sale_order`'s domain includes an order with `ecommerce_store_id` set and
excludes a plain, manually created sale order with no `ecommerce_store_id`.

### TC-UC19-5 — Orders by Store & Status Exposes Pivot and Graph
`action_ecommerce_external_order_report`'s `view_mode` includes both `pivot` and `graph`.

### TC-UC19-6 — Webhook Health Exposes Pivot and Graph
`action_ecommerce_webhook_event_report`'s `view_mode` includes both `pivot` and `graph`.

### TC-UC19-7 — Imported Sale Orders Exposes Pivot and Graph
`action_ecommerce_sale_order`'s `view_mode` includes both `pivot` and `graph`.

### TC-UC19-8 — Reporting Menu Items Exist and Point to the Correct Actions
The "Reporting" menu section and its three child menu items exist and each resolves to the
expected action.

## UC-20 — Demo Data, Sample Payloads, and Scripts

### TC-UC20-1 — Orphaned Sample Payloads Are Now Wired
`salla_order_missing_sku` and `salla_order_multicurrency_sar` are selectable in the Mock Payload
Lab and load their real file content.

### TC-UC20-2 — New app.installed Template Is Wired
`salla_app_installed` is selectable and loads real file content.

### TC-UC20-3 — Bootstrap Creates Expected Demo Records
Calling the bootstrap once creates one demo store, five webhook events, and three external
orders in states `imported`, `pending_mapping`, and `ready`.

### TC-UC20-4 — Bootstrap Is Idempotent
Calling the bootstrap twice does not create a second demo store or duplicate any webhook events.

### TC-UC20-5 — OAuth Tokens Are Correctly Ingested From the Sanitized Payload
The demo store's `access_token`/`refresh_token`/expiry fields are populated with the sanitized
sample values after the bootstrap runs, confirming the authorize payload's `merchant` value
correctly matched the demo store's `store_identifier`.

### TC-UC20-6 — Imported Demo Order Has a Real Linked Sale Order
The successful demo order actually produces a `sale.order` record, not just a state change.

## UC-24 — Order Cancellation

### TC-UC24-1 — Known Non-Imported Order Cancelled
Send a valid `order.cancelled` payload for a captured external order. Verify the external order transitions to `cancelled`, watermark fields are set, raw payload is preserved, and the webhook event is marked `processed`.

### TC-UC24-2 — Unknown Order Parks as Pending Review
Send `order.cancelled` for an unknown `external_order_id`. Verify the webhook event is parked in `pending_review` with an explanatory error message and no external order is created.

### TC-UC24-3 — Stale Cancellation Parked
Send `order.cancelled` with a timestamp older than the staged order's existing watermark. Verify the event is parked as `pending_review` and the external order remains unchanged.

### TC-UC24-4 — Exact Duplicate Cancellation
Send an identical cancellation payload with the same timestamp and event ID as the applied watermark. Verify the event is marked `duplicate` with no further mutations.

### TC-UC24-5 — Same-Timestamp Ambiguous Cancellation
Send a cancellation payload with the same timestamp as the watermark but a different/missing event ID. Verify the event is parked in `pending_review`.

### TC-UC24-6 — Missing Timestamp Parks
Send `order.cancelled` without any valid datetime keys. Verify the event is parked in `pending_review`.

### TC-UC24-7 — Malformed Data Object Parks
Send `order.cancelled` where `data` is not a dictionary. Verify the event is parked in `pending_review` without crashing.

### TC-UC24-8 — Imported Order Under Stage-Only Policy
Send `order.cancelled` for an already imported order on a store with default `cancellation_policy = 'stage_only'`. Verify the external order is marked `cancelled` while the linked `sale.order` remains in `draft` state untouched.

### TC-UC24-9 — Imported Order Under Cancel-Sale-Order Policy
Send `order.cancelled` for an imported order on a store with `cancellation_policy = 'cancel_linked_sale_order'`. Verify both the external order is marked `cancelled` and the linked quotation is cancelled (`so.state == 'cancel'`).

### TC-UC24-10 — Uncancellable Sale Order Fails Atomically
On a store with `cancel_linked_sale_order`, send cancellation for an order whose linked `sale.order` is confirmed (`state == 'sale'`). Verify the event parks in `pending_review` and the external order remains `imported` (atomicity preserved).

### TC-UC24-11 — Manual Cancel Requires Connector Manager
Attempt `action_cancel_external_order` as a user without Connector Manager group. Verify an `AccessError` is raised.

### TC-UC24-12 — Manual Cancel Success and State Guards
As Connector Manager, call `action_cancel_external_order` on a captured order. Verify it transitions to `cancelled` and errors are cleared. Verify re-cancelling or cancelling an imported order raises `UserError`.

### TC-UC24-13 — Retry Blocked After Cancellation
Attempt `action_retry_import` on a cancelled order. Verify it is blocked with `UserError`.

### TC-UC24-14 — Redelivery After Cancellation Is Duplicate
Re-deliver the identical cancellation payload. Verify the second event is marked `duplicate` and staging remains `cancelled`.
