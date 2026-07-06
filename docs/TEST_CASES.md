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
