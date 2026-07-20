-- v026_engagement.surql
-- Engagement model fields for multi-spin orchestration

DEFINE FIELD engagement                  ON TABLE task TYPE option<object>;
DEFINE FIELD engagement.perspectives     ON TABLE task TYPE option<array<string>>;
DEFINE FIELD engagement.adversarial_pair ON TABLE task TYPE option<array<string>>;
DEFINE FIELD engagement.rationale        ON TABLE task TYPE option<string>;
DEFINE FIELD engagement.injected         ON TABLE task TYPE option<array<object>>;
DEFINE FIELD engagement.spin_count       ON TABLE task TYPE option<int>;
DEFINE FIELD perspective                 ON TABLE task TYPE option<string>;

UPSERT config_entry SET value = '26' WHERE key = 'schema_version';
