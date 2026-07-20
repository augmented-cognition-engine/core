-- schema/v124_roadmap_phase.surql
-- The Living Roadmap's strategic phases (world-class roadmap Phase 1-6).
-- Purpose-built minimal node: NOT `initiative` (which is SCHEMAFULL, requires
-- dropped org/workspace FKs, and is the PM execution-initiative concept).
DEFINE TABLE roadmap_phase SCHEMALESS;
DEFINE FIELD product        ON roadmap_phase TYPE record<product>;
DEFINE FIELD title          ON roadmap_phase TYPE string;
DEFINE FIELD ordinal        ON roadmap_phase TYPE int;
DEFINE FIELD status         ON roadmap_phase TYPE string DEFAULT 'next';  -- active|next|done|parked
DEFINE FIELD summary        ON roadmap_phase TYPE option<string>;
DEFINE FIELD source_ref     ON roadmap_phase TYPE option<string>;
DEFINE FIELD source_created ON roadmap_phase TYPE option<datetime>;
DEFINE FIELD created_at     ON roadmap_phase TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_phase_ord  ON roadmap_phase FIELDS product, ordinal;

-- The spec->phase link (agent_spec is SCHEMALESS; define for clarity/queryability).
DEFINE FIELD phase          ON agent_spec TYPE option<record<roadmap_phase>>;
DEFINE FIELD source_ref     ON agent_spec TYPE option<array<string>>;
DEFINE FIELD source_created ON agent_spec TYPE option<datetime>;
