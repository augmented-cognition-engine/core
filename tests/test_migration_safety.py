from __future__ import annotations

from core.engine.arms.migration_safety import parse_schema_dir, scan_migration_violations


def test_clean_additive_new_table_passes():
    sql = (
        "DEFINE TABLE widget SCHEMALESS;\n"
        "DEFINE FIELD name ON widget TYPE string;\n"  # required field OK on a NEW table
        "DEFINE FIELD note ON widget TYPE option<string>;\n"
    )
    v = scan_migration_violations(
        sql, existing_max_version=126, filename="v127_widget.surql", prior_tables={"agent_spec"}, prior_enums={}
    )
    assert v == [], v


def test_required_field_no_default_on_existing_table_flagged():
    sql = "DEFINE FIELD org ON agent_spec TYPE string;\n"  # required, no DEFAULT, existing table
    v = scan_migration_violations(
        sql, existing_max_version=126, filename="v127_org.surql", prior_tables={"agent_spec"}, prior_enums={}
    )
    assert any("org" in x and "DEFAULT" in x for x in v), v


def test_optional_or_default_field_on_existing_table_ok():
    sql = "DEFINE FIELD a ON agent_spec TYPE option<string>;\nDEFINE FIELD b ON agent_spec TYPE string DEFAULT 'x';\n"
    v = scan_migration_violations(
        sql, existing_max_version=126, filename="v127_x.surql", prior_tables={"agent_spec"}, prior_enums={}
    )
    assert v == [], v


def test_enum_narrowing_flagged():
    sql = "DEFINE FIELD status ON agent_spec TYPE string ASSERT $value INSIDE ['draft','approved'];\n"
    v = scan_migration_violations(
        sql,
        existing_max_version=126,
        filename="v127_status.surql",
        prior_tables={"agent_spec"},
        prior_enums={("agent_spec", "status"): {"draft", "approved", "built", "shipped"}},
    )
    assert any("enum" in x.lower() and ("built" in x or "shipped" in x) for x in v), v


def test_record_cast_in_relate_flagged():
    sql = "RELATE <record>$from -> produced -> <record>$to;\n"
    v = scan_migration_violations(
        sql, existing_max_version=126, filename="v127_rel.surql", prior_tables=set(), prior_enums={}
    )
    assert any("RELATE" in x for x in v), v


def test_wrong_version_number_flagged():
    sql = "DEFINE TABLE t SCHEMALESS;\n"
    v = scan_migration_violations(
        sql, existing_max_version=126, filename="v200_t.surql", prior_tables=set(), prior_enums={}
    )
    assert any("version" in x.lower() for x in v), v


def test_multiline_default_not_false_flagged():
    # I1: DEFAULT on the line AFTER TYPE must be seen (statement-scope, not line-scope).
    sql = "DEFINE FIELD region ON agent_spec TYPE string\n    DEFAULT 'us';\n"
    v = scan_migration_violations(
        sql, existing_max_version=126, filename="v127_region.surql", prior_tables={"agent_spec"}, prior_enums={}
    )
    assert v == [], v


def test_multiline_assert_enum_narrowing_detected():
    # I2: ASSERT far below TYPE (multi-line / commented) must still be checked.
    sql = (
        "DEFINE FIELD status ON agent_spec TYPE string\n"
        "    -- a long explanatory comment that pushes the ASSERT past any fixed window\n"
        "    -- more comment, more comment, padding padding padding padding padding padding\n"
        "    DEFAULT 'draft'\n"
        "    ASSERT $value INSIDE ['draft', 'approved'];\n"
    )
    v = scan_migration_violations(
        sql,
        existing_max_version=126,
        filename="v127_status.surql",
        prior_tables={"agent_spec"},
        prior_enums={("agent_spec", "status"): {"draft", "approved", "built"}},
    )
    assert any("enum" in x.lower() and "built" in x for x in v), v


def test_flexible_type_field_is_checked_not_invisible():
    # I3: FLEXIBLE TYPE fields must be visible to the rules (required-no-default on existing table).
    sql = "DEFINE FIELD meta ON agent_spec FLEXIBLE TYPE object;\n"
    v = scan_migration_violations(
        sql, existing_max_version=126, filename="v127_meta.surql", prior_tables={"agent_spec"}, prior_enums={}
    )
    assert any("meta" in x and "DEFAULT" in x for x in v), v


def test_parse_schema_dir(tmp_path):
    d = tmp_path / "schema"
    d.mkdir()
    (d / "v001_a.surql").write_text(
        "DEFINE TABLE agent_spec SCHEMALESS;\n"
        "DEFINE FIELD status ON agent_spec TYPE string "
        "ASSERT $value INSIDE ['draft','approved'];\n"
    )
    (d / "v126_b.surql").write_text("DEFINE TABLE widget SCHEMALESS;\n")
    max_v, tables, enums = parse_schema_dir(str(d))
    assert max_v == 126
    assert "agent_spec" in tables and "widget" in tables
    assert enums[("agent_spec", "status")] == {"draft", "approved"}
