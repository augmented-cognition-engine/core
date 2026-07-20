-- schema/v119_instrument_perf_product_index.surql

-- The learned-selection loop (activated alongside the v118 tool_perf work) now
-- writes AND queries instrument_perf by `product`. But v057's only index is on
-- the legacy `org` column (no longer written), so every FrameworkClassifier
-- lookup full-scans. Add a product-anchored index matching the query's primary
-- equality columns (WHERE product = ... AND cognitive_function = ...), mirroring
-- v118's idx_tool_perf_lookup. Additive — the legacy index is left in place.

DEFINE INDEX idx_instrument_perf_product_lookup
  ON TABLE instrument_perf
  FIELDS product, cognitive_function;
