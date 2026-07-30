-- v160: make self-optimizer proposal payloads persistable and product-scoped.
--
-- The classifier writes arbitrary nested draft/evidence maps. On a SCHEMAFULL
-- table, plain object fields reject those keys. The legacy index also retained
-- the removed `org` field, so product-scoped proposal reads were unindexed.
DEFINE FIELD OVERWRITE draft
    ON self_optimizer_proposal TYPE option<object> FLEXIBLE;
DEFINE FIELD OVERWRITE evidence
    ON self_optimizer_proposal TYPE object FLEXIBLE DEFAULT {};
DEFINE INDEX OVERWRITE idx_prop_org
    ON self_optimizer_proposal FIELDS product, status, type;
