-- schema/v115_forget_log_tamper_detect.surql

-- Detective control for the append-only forget_log audit table.
-- The PERMISSIONS clause (FOR update/delete NONE) only enforces for non-root
-- scoped connections; ACE-core connects as root, which bypasses it. This EVENT
-- adds a DETECTIVE control that works regardless of who mutates the log: any
-- UPDATE or DELETE on forget_log records a content-free tamper trail. It cannot
-- PREVENT a root mutation (SurrealDB events fire after the change), but it makes
-- audit-log tampering VISIBLE — raising the bar from "undetectable" to "leaves a
-- trace". Recommended follow-up from the forget design spec.

DEFINE TABLE forget_log_tamper SCHEMALESS
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;

DEFINE EVENT forget_log_tamper_detect ON TABLE forget_log
    WHEN $event = "UPDATE" OR $event = "DELETE" THEN (
        CREATE forget_log_tamper SET
            event = $event,
            target = $before.id,
            content_hash = $before.content_hash,
            at = time::now()
    );
