-- schema/v121_reasoning_run_trace_id.surql

-- Correlate each reasoning_run to its OpenTelemetry trace. create_run() stamps the
-- active trace_id (current_trace_id() — 32-char hex, or '-' when no span is active)
-- so a run can be joined to the gen_ai.* spans emitted per LLM call during it.
-- option<string>: '-' / unset for CLI runs that ran without the FastAPI tracer.
-- reasoning_run is SCHEMALESS (v117) so this is additive; the typed field documents
-- and enforces the column going forward.

DEFINE FIELD trace_id ON reasoning_run TYPE option<string>;
