-- v055: Fix resource_lock to use product field with unique index
-- The org field (record<org>) was causing silent write failures when
-- product IDs were passed. Switch to product field + correct unique index.

-- Make org optional: REMOVE+REDEFINE required since SurrealDB won't update TYPE in-place
REMOVE FIELD IF EXISTS org ON resource_lock;
DEFINE FIELD org ON resource_lock TYPE none | record<org> PERMISSIONS FULL;

-- Ensure product field exists and is indexed
DEFINE FIELD product ON resource_lock TYPE none | record<product> PERMISSIONS FULL;

-- Ensure state field exists (may have been missed in v037 on some DBs)
DEFINE FIELD IF NOT EXISTS state ON resource_lock TYPE string DEFAULT 'held'
    ASSERT $value IN ['acquired', 'held', 'releasing', 'released', 'stolen', 'expired'];

-- Replace unique index: org+resource → product+resource
REMOVE INDEX IF EXISTS idx_lock ON resource_lock;
DEFINE INDEX idx_lock_product ON resource_lock
    FIELDS product, resource_type, resource_id UNIQUE;
