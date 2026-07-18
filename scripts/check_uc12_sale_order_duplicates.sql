-- Run this before upgrading ecommerce_connector_base with UC-12.
-- If this query returns rows, resolve the duplicate connector references before
-- the upgrade. Archiving alone is insufficient: the duplicate connector fields
-- must be cleared/relinked, or the duplicate record must be safely removed.
SELECT
    ecommerce_store_id,
    ecommerce_external_reference, 
    COUNT(*) AS duplicate_count,
    ARRAY_AGG(id ORDER BY id) AS sale_order_ids
FROM
    sale_order
WHERE
    ecommerce_store_id IS NOT NULL
    AND ecommerce_external_reference IS NOT NULL
GROUP BY
    ecommerce_store_id,
    ecommerce_external_reference
HAVING
    COUNT(*) > 1
ORDER BY
    ecommerce_store_id,
    ecommerce_external_reference;
