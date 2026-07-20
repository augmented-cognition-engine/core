-- v048: Review reaction tracking for adaptive learning

DEFINE TABLE review_reaction SCHEMALESS;

DEFINE FIELD owner ON review_reaction TYPE string;
DEFINE FIELD repo ON review_reaction TYPE string;
DEFINE FIELD pr_number ON review_reaction TYPE int;
DEFINE FIELD finding_index ON review_reaction TYPE int;
DEFINE FIELD reaction ON review_reaction TYPE string;
DEFINE FIELD comment ON review_reaction TYPE string;
DEFINE FIELD meta ON review_reaction TYPE option<object>;
DEFINE FIELD created_at ON review_reaction TYPE datetime DEFAULT time::now();

DEFINE INDEX idx_review_reaction_lookup ON review_reaction FIELDS owner, repo, pr_number;
