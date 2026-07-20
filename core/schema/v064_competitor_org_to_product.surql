-- v064: Rename org→product on competitor and competitive_signal tables.
--
-- These two tables were missed in the v058-v061 org→product rename wave because
-- they defined org as TYPE string (not record<org>), so the record<org>→record<product>
-- type-check migration didn't apply to them.
--
-- Both tables are currently empty so no data migration is needed.
-- Indexes referencing org are also renamed.

-- ─── competitor ───────────────────────────────────────────────────────────────

REMOVE INDEX idx_competitor_org  ON competitor;
REMOVE INDEX idx_competitor_name ON competitor;

REMOVE FIELD org ON competitor;
DEFINE FIELD product ON competitor TYPE record<product>;

DEFINE INDEX idx_competitor_product     ON competitor FIELDS product;
DEFINE INDEX idx_competitor_product_name ON competitor FIELDS product, name UNIQUE;

-- ─── competitive_signal ───────────────────────────────────────────────────────

REMOVE FIELD org ON competitive_signal;
DEFINE FIELD product ON competitive_signal TYPE record<product>;

DEFINE INDEX idx_csig_product ON competitive_signal FIELDS product;

-- ─── Version bump ─────────────────────────────────────────────────────────────

UPDATE config_entry SET value = '64' WHERE key = 'schema_version';
