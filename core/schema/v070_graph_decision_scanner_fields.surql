-- v070: add scanner-written fields to graph_decision
-- files_changed: number of files modified in the commit
-- decision_type: classifier-assigned category (architecture, convention, trade_off, direction)
DEFINE FIELD files_changed  ON TABLE graph_decision TYPE option<int>;
DEFINE FIELD decision_type  ON TABLE graph_decision TYPE option<string>;
