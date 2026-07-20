-- schema/v131_task_grader_score.surql
-- Un-starve calibration (payoff half of keystone #1). The cross-model grader (v-grader, keystone #1)
-- produces an automated, independent (non-Claude) outcome score; these two additive fields let a
-- background grading engine record that score ON the task, so calibration can use it as the "actual"
-- outcome when no human feedback exists (today calibration only learns from feedback_human-bearing
-- tasks → starved). Additive + optional only — no bare required field (SCHEMAFULL CREATEs elsewhere
-- on `task` keep working). Human feedback still takes precedence in the calibration consumer.
DEFINE FIELD grader_score  ON TABLE task TYPE option<float>;   -- 0..1 cross-model grade (automated "actual")
DEFINE FIELD grader_source ON TABLE task TYPE option<string>;  -- provenance, e.g. "cross_model:qwen2.5-coder:14b"
