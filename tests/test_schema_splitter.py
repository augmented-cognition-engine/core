# tests/test_schema_splitter.py
"""Unit tests for engine.core.schema._split_statements.

Regression: prior to the comment-aware fix, a semicolon inside a `--` line
comment was treated as a statement boundary, causing the parser to emit
malformed statements like `training negatives for future contrastive learning`
(real bug from schema/v107_world_model.surql) which SurrealDB then rejected
with "Parse error: Unexpected token `an identifier`".
"""

from __future__ import annotations

from core.engine.core.schema import _split_statements


def test_single_statement():
    assert _split_statements("DEFINE TABLE foo SCHEMALESS;") == ["DEFINE TABLE foo SCHEMALESS"]


def test_two_statements():
    sql = "DEFINE TABLE foo SCHEMALESS;\nDEFINE TABLE bar SCHEMALESS;"
    assert _split_statements(sql) == [
        "DEFINE TABLE foo SCHEMALESS",
        "DEFINE TABLE bar SCHEMALESS",
    ]


def test_line_comment_stripped():
    sql = "-- a comment\nDEFINE TABLE foo SCHEMALESS;"
    assert _split_statements(sql) == ["DEFINE TABLE foo SCHEMALESS"]


def test_semicolon_inside_line_comment_does_not_split():
    """The v107 bug: prose with ';' inside a comment caused split."""
    sql = (
        "-- Non-best rollout branches (TTL 7d); training negatives for future contrastive learning\n"
        "DEFINE TABLE speculative_decision SCHEMALESS;"
    )
    stmts = _split_statements(sql)
    assert stmts == ["DEFINE TABLE speculative_decision SCHEMALESS"]
    # Sentinel: the prose must never appear as a parsed statement.
    assert not any("training negatives" in s for s in stmts), (
        f"prose from inside comment leaked into statements: {stmts!r}"
    )


def test_block_brace_balance():
    """FOR/IF blocks with internal `;` are not split."""
    sql = "FOR $x IN [1, 2] { CREATE foo SET val = $x; };\nDEFINE TABLE bar SCHEMALESS;"
    stmts = _split_statements(sql)
    assert len(stmts) == 2
    assert stmts[0].startswith("FOR")
    assert stmts[1] == "DEFINE TABLE bar SCHEMALESS"


def test_block_comment_with_semicolon_does_not_split():
    """Semicolons inside /* ... */ must not trigger a split.

    We don't strip the block-comment text (no real .surql uses block comments,
    and SurrealQL passes them through), but the splitter must not see internal
    `;` as a statement boundary.
    """
    sql = "/* old: CREATE foo; CREATE bar; */\nDEFINE TABLE baz SCHEMALESS;"
    stmts = _split_statements(sql)
    assert len(stmts) == 1
    assert "DEFINE TABLE baz SCHEMALESS" in stmts[0]
    # Sentinel: no stray fragment from inside the block comment.
    assert not any(s.strip() == "CREATE bar" for s in stmts)


def test_empty_input():
    assert _split_statements("") == []
    assert _split_statements("\n  \n") == []
    assert _split_statements("-- only a comment\n") == []
