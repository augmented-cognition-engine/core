-- schema/v132_calibrated_assessment_float.surql
-- Close the calibration loop at the WRITE seam. v034 typed task.calibrated_assessment as
-- option<object>; v035 fixed the SIBLING self_assessment (object → any, see v035:19-20) but MISSED
-- calibrated_assessment — it only added the `.*` sub-rule, leaving the parent object-typed.
-- apply_calibration writes a plain FLOAT (UPDATE ... SET calibrated_assessment = <float> in
-- orchestration/hooks.py + orchestrator/executor.py), so on a fresh DB built from these migrations the
-- write is a TYPE violation that silently no-ops (swallowed by the post-task hook catch-all) — the loop
-- reaches "apply" but the corrected confidence never persists, so the consumers (failure_analysis /
-- gap_researcher, which now gate on `calibrated_assessment ?? self_assessment`) never see it.
-- Mirror the v035 self_assessment fix so the loop closes on ANY DB. No-op where it is already float.
REMOVE FIELD IF EXISTS calibrated_assessment ON task;
DEFINE FIELD calibrated_assessment ON task TYPE any;
