-- Wave 5: Self-Improvement Loops schema

-- Successful reasoning traces (STaR)
-- Populated when VerificationGate returns verdict="clean"
-- Indexed by product + discipline for retrieval on similar tasks
DEFINE TABLE star_trace SCHEMALESS;
DEFINE INDEX idx_star_trace_product_discipline
  ON TABLE star_trace
  FIELDS product, discipline;

-- per-phase pass@k proxy metric (fraction of Best-of-N candidates above confidence threshold)
-- Written by executor.py after multiphase execution
DEFINE TABLE pass_at_k_log SCHEMALESS;
DEFINE INDEX idx_pass_at_k_log_product
  ON TABLE pass_at_k_log
  FIELDS product;

-- CRM calibration report: outcome-conditioned confidence adjustment factors
-- Written by CrmCalibrator, read by context_assembler or loader
DEFINE TABLE calibration_report SCHEMALESS;
DEFINE INDEX idx_calibration_report_product_discipline
  ON TABLE calibration_report
  FIELDS product, discipline;

UPDATE config_entry SET value = '68' WHERE key = 'schema_version';
