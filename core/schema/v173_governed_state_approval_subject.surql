-- Bind every opaque Core state revision to the exact subject named by its
-- already-resolved approval receipt. Kept additive because v172 may already
-- have been applied before the stricter invariant was introduced.

DEFINE FIELD IF NOT EXISTS approval_subject_ref ON TABLE governed_state_revision TYPE string;

