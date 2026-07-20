-- v047: PR review records
-- Stores review results for quality gate lookups and historical analysis

DEFINE TABLE pr_review SCHEMALESS;

DEFINE FIELD owner ON pr_review TYPE string;
DEFINE FIELD repo ON pr_review TYPE string;
DEFINE FIELD pr_number ON pr_review TYPE int;
DEFINE FIELD title ON pr_review TYPE string;
DEFINE FIELD findings_count ON pr_review TYPE int;
DEFINE FIELD findings ON pr_review TYPE array;
DEFINE FIELD summary ON pr_review TYPE string;
DEFINE FIELD discipline_scores ON pr_review TYPE object;
DEFINE FIELD pass_quality_gate ON pr_review TYPE bool;
DEFINE FIELD gate_failures ON pr_review TYPE array;
DEFINE FIELD findings_by_severity ON pr_review TYPE object;
DEFINE FIELD impact ON pr_review TYPE object;
DEFINE FIELD created_at ON pr_review TYPE datetime DEFAULT time::now();

-- Index for quality gate lookups
DEFINE INDEX idx_pr_review_lookup ON pr_review FIELDS owner, repo, pr_number;
