# tests/test_schema_v024.py
"""Test v024 experiment narrative fields."""

import subprocess
import sys

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_v024_experiment_log_narrative_fields(db_pool):
    """experiment_log table accepts new narrative fields."""
    result = subprocess.run([sys.executable, "scripts/schema_apply.py"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

    async with db_pool.connection() as db:
        result = await db.query("""
            CREATE experiment_log SET
                product = product:default,
                domain_path = 'test',
                variant_desc = 'test',
                change_type = 'intelligence',
                control_mean = 0.5,
                variant_mean = 0.8,
                improvement = 0.3,
                effect_size_d = 0.6,
                p_value = 0.01,
                significant = true,
                committed = true,
                cost = 0.05,
                task_count = 12,
                best_example_control = 'Before text',
                best_example_variant = 'After text',
                best_example_task = 'Task description',
                narrative_why = 'Because X was wrong',
                narrative_what_changed = 'Changed Y',
                narrative_impact = 'Now Z is better',
                experiment_type = 'intelligence'
        """)
        row = result[0][0] if isinstance(result[0], list) else result[0]
        assert row["narrative_why"] == "Because X was wrong"
        assert row["experiment_type"] == "intelligence"
        await db.query(f"DELETE {row['id']}")
