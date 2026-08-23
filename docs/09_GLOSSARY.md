# Glossary

## Business terminology

| Term | Meaning in this project |
| --- | --- |
| E-commerce platform | Customer-facing sales channel. Salla is the first supported platform. |
| Store | An <code>ecommerce.store</code> configuration record representing one platform/store/company context. |
| External order | Staged representation of a platform order before an Odoo sale order is created. |
| Sale order | Standard Odoo <code>sale.order</code> created or linked after validation. |
| Import | The controlled process that turns a ready external order into an Odoo sale order. |
| Error queue | Manager worklist of external orders requiring attention, such as failed, pending mapping, or pending review. |
| Manual retry | Explicit manager action that reruns import work after an issue is corrected. |
| Mock Mode | Store mode that accepts mock events without live Salla credentials/signature validation. |
| Demo Mode | Configured store environment intended for realistic demo-store use; live behavior is not fully implemented. |
| Production Mode | Configured store environment for a real client; deployment/live API readiness is not yet established. |

## Project terminology

| Term | Meaning |
| --- | --- |
| Base addon | <code>ecommerce_connector_base</code>, shared connector implementation. |
| Salla addon | <code>ecommerce_salla_connector</code>, Salla-specific extension. |
| Webhook event | Redacted audit record of an inbound platform callback. |
| Processing gate | Method that validates integration-user availability and executes business work in that user's company context. |
| Staging layer | External-order and line records that isolate raw events from Odoo sales records. |
| Mapping | Explicit store-specific relationship from an external ID to an Odoo partner/product. |
| Raw payload | Original event JSON stored in redacted form for troubleshooting/audit. |
| Error history | Retry-time snapshots of prior error/warning/state information. |

## State terminology

| State | Meaning |
| --- | --- |
| received | Webhook was recorded but not yet processed. |
| processing | Event work is underway. |
| processed | Supported event processing completed. |
| failed | Processing/import encountered a recorded error. |
| pending_mapping | Product or customer mapping is incomplete. |
| pending_review | An ambiguity, configuration issue, or unsupported condition needs operator attention. |
| ready | Staged order passed validation and may create a sale order. |
| imported | Sale order was created or linked. |
| duplicate | A delivery/event was recognized as already represented. |
| invalid_signature | Non-mock webhook failed signature verification. |
| rate_limited | Webhook exceeded configured per-store limit. |
| ignored | Event is known but deliberately not processed. |
| cancelled | External-order terminal state set by an order.cancelled webhook (watermark-ordered) or by a manager's manual Mark Cancelled action. |

## Security and identity terminology

| Term | Meaning |
| --- | --- |
| Store token | Generated opaque value embedded in the public webhook URL to locate a store. |
| Webhook secret | Restricted store credential used to verify a platform signature. |
| HMAC SHA-256 | Signature algorithm used by the controller for non-mock Salla webhooks. |
| Integration user | Dedicated Odoo user under whose permissions/company business processing runs. |
| Connector User | Read-oriented connector role. |
| Connector Manager | Operational manager role with repair/retry abilities. |
| Integration Manager | Restricted administrative role for credentials and integration safety configuration. |
| Redaction | Removal/masking of secrets from stored payloads, headers, and errors. |

## Database and API terminology

| Term | Meaning |
| --- | --- |
| SQL constraint | Database-enforced integrity rule. The sale-order store/external-reference constraint is the final duplicate safeguard. |
| Savepoint | Transaction boundary used to catch/recover expected database race errors without losing the entire transaction. |
| Idempotency | Repeating the same external import should link/return the same outcome rather than create duplicates. |
| External reference | Platform order identifier stored on staging and sale-order records. |
| SKU fallback | Product matching by SKU when no explicit product mapping resolves the external item. |
| API enrichment | Future optional retrieval of additional Salla data after webhook receipt. |
| OAuth authorization | Future workflow for accepting/recording platform authorization data. |

## Abbreviations

| Abbreviation | Meaning |
| --- | --- |
| ACL | Odoo access-control list, defined in model access CSV. |
| API | Application programming interface. |
| ERP | Enterprise resource planning; Odoo is the ERP here. |
| HMAC | Hash-based message authentication code. |
| ORM | Object-relational mapper; Odoo's Python data layer. |
| UC | Use Case; a planned vertical slice of project work. |
| UI | User interface. |
