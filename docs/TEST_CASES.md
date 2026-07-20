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
