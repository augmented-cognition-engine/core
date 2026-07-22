from pathlib import Path


def test_conflict_visibility_migration_normalizes_and_indexes_attention_state():
    migration = (Path(__file__).parents[1] / "core/schema/v143_conflict_visibility.surql").read_text()

    assert "status = 'pending' WHERE status = 'open'" in migration
    assert migration.count("status = 'contested'") == 2
    assert "idx_conflict_product_status" in migration
    assert "FIELDS product, status, created_at" in migration
