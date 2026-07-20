-- schema/v133_community_summary.surql
-- Graph community summaries (GraphRAG/LightRAG) — Phase 2 brain item. The community_summarizer engine
-- runs Louvain detection (graph/cluster.py) over the cognify insight edges, LLM-summarizes the largest
-- communities, and writes one row per community here; the briefing surfaces them so the partner sees the
-- SHAPE of accumulated knowledge, not just counts. Replace-on-run (the engine deletes prior rows per
-- product), so no dedup needed. Additive table; no bare required field beyond the obvious.
DEFINE TABLE community_summary SCHEMALESS;
DEFINE FIELD product        ON community_summary TYPE record<product>;
DEFINE FIELD cluster_label  ON community_summary TYPE string;
DEFINE FIELD summary        ON community_summary TYPE string;
DEFINE FIELD member_count   ON community_summary TYPE int;
DEFINE FIELD dominant_layer ON community_summary TYPE option<string>;
DEFINE FIELD created_at      ON community_summary TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_comm_summary_product ON community_summary FIELDS product, created_at;
