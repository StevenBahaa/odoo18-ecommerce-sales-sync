# Screenshot Guide

This guide outlines the recommended portfolio screenshots for demonstrating the Odoo 18 E-commerce Sales Sync Connector. For consistent, professional presentation, use the pre-seeded **UC-20 Demo Salla Store** data on a demo-enabled database, maintain a consistent browser window size (e.g. 1920x1080), use Odoo's standard Community theme, and ensure any real API tokens or secrets are redacted.

---

## Recommended Screenshot Sequence

### 1. Store Configuration & Token Status
- **Menu Path:** E-commerce Connector → Configuration → Stores
- **Focus:** Open "UC-20 Demo Salla Store" form view. Show platform settings (**Salla**), environment (**Mock**), stock synchronization policy, webhook identity, and the **Token Status** page highlighting OAuth token lifetime and status indicators.

### 2. Salla Mock Payload Lab Wizard
- **Menu Path:** E-commerce Connector → Operations → Salla Mock Lab
- **Focus:** Open the wizard with a payload template selected (e.g., `order.created` or `app.store.authorize`). Show the scenario dropdown, store selection, and the read-only JSON payload preview ready for submission.

### 3. Processed Webhook Event & Audit Trail
- **Menu Path:** E-commerce Connector → Operations → Webhook Events
- **Focus:** Open a processed webhook event record (e.g., `order.created`). Show event metadata (type, timestamp, processing state `processed`), the linked staged external order, and the audit log page showing formatted JSON with sensitive tokens redacted.

### 4. External Order Staging & Line Mapping
- **Menu Path:** E-commerce Connector → Operations → External Orders
- **Focus:** Open an external order in `imported` state. Show customer matching, financial amounts, payment/fulfillment status, order lines with resolved Odoo products/SKUs, and the smart button linking directly to the created Odoo Sale Order.

### 5. Import Error Queue & Manual Resolution
- **Menu Path:** E-commerce Connector → Operations → Import Error Queue
- **Focus:** Show the error queue list view displaying orders in `pending_mapping` or `pending_review`. Open a `pending_mapping` record displaying the exact missing SKU / unmapped line error banner and the manager-only "Retry Import" button.

### 6. Imported Sale Orders
- **Menu Path:** E-commerce Connector → Reporting → Imported Sale Orders
- **Focus:** List view showing sale orders originated through the connector (`ecommerce_store_id != False`). Highlight the e-commerce store name, external reference, amount total, and platform status columns.

### 7. Orders by Store & Status Pivot
- **Menu Path:** E-commerce Connector → Reporting → Orders by Store & Status
- **Focus:** Pivot table view displaying order volume and total monetary value aggregated by store (rows) and processing state (columns), with the bar graph view toggle visible.

### 8. Webhook Health Analytics
- **Menu Path:** E-commerce Connector → Reporting → Webhook Health
- **Focus:** Pivot/graph view showing webhook event counts broken down by store and processing status (`processed`, `duplicate`, `pending_review`, `failed`).

### 9. Credential Lifecycle & Audit Chatter
- **Menu Path:** E-commerce Connector → Configuration → Stores
- **Focus:** Bottom chatter of the store form showing automated audit log entries (OAuth token update, expiry warnings, rate-limit cooldown notifications).
