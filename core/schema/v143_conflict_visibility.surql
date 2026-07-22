-- Product-scoped conflict attention needs the same lookup key used by the
-- conflict list, portal attention, and resolution paths.
UPDATE conflict SET status = 'pending' WHERE status = 'open';
UPDATE insight SET status = 'contested', updated_at = time::now()
    WHERE id IN (SELECT VALUE insight_a FROM conflict WHERE status = 'pending');
UPDATE insight SET status = 'contested', updated_at = time::now()
    WHERE id IN (SELECT VALUE insight_b FROM conflict WHERE status = 'pending' AND insight_b IS NOT NONE);
REMOVE INDEX IF EXISTS idx_conflict_org ON TABLE conflict;
DEFINE INDEX IF NOT EXISTS idx_conflict_product_status ON TABLE conflict FIELDS product, status, created_at;
