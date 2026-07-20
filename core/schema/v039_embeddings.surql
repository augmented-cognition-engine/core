-- v039_embeddings.surql
-- Add embedding fields to CODE layer tables for semantic search

DEFINE FIELD embedding ON graph_file TYPE option<array>;
DEFINE FIELD embedding ON graph_function TYPE option<array>;
DEFINE FIELD embedded_at ON graph_file TYPE option<datetime>;
DEFINE FIELD embedded_at ON graph_function TYPE option<datetime>;
DEFINE FIELD embedding_model ON graph_file TYPE option<string>;

UPDATE config_entry:schema_version SET value = '039';
