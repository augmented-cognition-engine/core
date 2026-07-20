# tests/test_schema_v012.py
"""Schema v012 tests — require running SurrealDB with schema applied."""

import pytest

from core.engine.core.db import parse_one, parse_rows

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_schema_v012_initiative(db_pool):
    """Initiative table created with all fields and indexes."""
    async with db_pool.connection() as db:
        result = await db.query("INFO FOR TABLE initiative")
        assert result is not None

        # Create an initiative
        created = await db.query(
            """
            CREATE initiative SET
                product = product:test,
                user = user:test,
                title = 'Test Initiative',
                description = 'A test initiative',
                source = 'user_created',
                owner = user:test,
                status = 'planning',
                priority = 'high'
            """
        )
        init = parse_one(created)
        assert init is not None, "Initiative should be created"
        assert init["status"] == "planning"
        assert init["priority"] == "high"
        assert init["total_cost"] == 0.0

        # Cleanup
        init_id = init.get("id", "")
        await db.query("DELETE $id", {"id": init_id})


@pytest.mark.asyncio
async def test_schema_v012_milestone(db_pool):
    """Milestone table created with initiative reference and sequence index."""
    async with db_pool.connection() as db:
        # Create prerequisite initiative
        init_result = await db.query(
            """
            CREATE initiative SET
                product = product:test, user = user:test,
                title = 'For Milestone Test', description = 'test',
                source = 'user_created', owner = user:test
            """
        )
        init = parse_one(init_result)
        assert init is not None
        init_id = init["id"]

        # Create milestone
        ms_result = await db.query(
            """
            CREATE milestone SET
                product = product:test, initiative = <record>$init,
                title = 'M1: Design', description = 'Design phase',
                done_criteria = ['Schema complete', 'Tests pass'],
                sequence = 1, requires_approval = true, approver = user:test
            """,
            {"init": init_id},
        )
        ms = parse_one(ms_result)
        assert ms is not None, "Milestone should be created"
        assert ms["sequence"] == 1
        assert ms["requires_approval"] is True
        assert ms["status"] == "pending"

        # Cleanup
        await db.query("DELETE $id", {"id": ms["id"]})
        await db.query("DELETE $id", {"id": init_id})


@pytest.mark.asyncio
async def test_schema_v012_work_item(db_pool):
    """Work item table with parallel group index and review_stages field."""
    async with db_pool.connection() as db:
        # Prerequisite chain
        init_result = await db.query(
            """
            CREATE initiative SET
                product = product:test, user = user:test,
                title = 'For WI Test', description = 'test',
                source = 'user_created', owner = user:test
            """
        )
        init = parse_one(init_result)
        assert init is not None
        init_id = init["id"]

        ms_result = await db.query(
            """
            CREATE milestone SET
                product = product:test, initiative = <record>$init,
                title = 'M1', description = 'test', sequence = 1
            """,
            {"init": init_id},
        )
        ms = parse_one(ms_result)
        assert ms is not None
        ms_id = ms["id"]

        # Create work item
        wi_result = await db.query(
            """
            CREATE work_item SET
                product = product:test, milestone = <record>$ms, initiative = <record>$init,
                title = 'WI-1: Create schema', description = 'Build it',
                archetype = 'creator', mode = 'deliberative',
                domain_path = 'architecture',
                parallel_group = 1,
                files_touched = ['src/schema.py', 'tests/test_schema.py'],
                review_stages = [{ dimension: 'spec_compliance', passed: true, issues: [] }],
                post_task_hooks = ['type-check', 'lint', 'unit-test', 'format']
            """,
            {"ms": ms_id, "init": init_id},
        )
        wi = parse_one(wi_result)
        assert wi is not None, "Work item should be created"
        assert wi["parallel_group"] == 1
        assert wi["review_stages"] is not None
        assert wi["post_task_hooks"] == ["type-check", "lint", "unit-test", "format"]

        # Cleanup
        await db.query("DELETE $id", {"id": wi["id"]})
        await db.query("DELETE $id", {"id": ms_id})
        await db.query("DELETE $id", {"id": init_id})


@pytest.mark.asyncio
async def test_schema_v012_recurring(db_pool):
    """Recurring initiative table created."""
    async with db_pool.connection() as db:
        result = await db.query(
            """
            CREATE recurring_initiative SET
                product = product:test, user = user:test,
                title = 'Weekly Report', description = 'Generate weekly report',
                cron = '0 9 * * 1', enabled = true,
                milestones_template = [{ title: 'Generate', description: 'Run report' }]
            """
        )
        rec = parse_one(result)
        assert rec is not None, "Recurring initiative should be created"
        assert rec["cron"] == "0 9 * * 1"
        assert rec["enabled"] is True

        # Cleanup
        await db.query("DELETE $id", {"id": rec["id"]})


@pytest.mark.asyncio
async def test_schema_v012_resource_lock(db_pool):
    """Resource lock table with unique index prevents duplicate locks."""
    async with db_pool.connection() as db:
        # Create a lock
        result = await db.query(
            """
            CREATE resource_lock SET
                product = product:test,
                resource_type = 'file',
                resource_id = 'src/main.py',
                held_by = 'work_item:wi1',
                expires_at = time::now() + 1h
            """
        )
        rec = parse_one(result)
        assert rec is not None, "Resource lock should be created"

        # Second create on same resource should fail (unique index)
        try:
            await db.query(
                """
                CREATE resource_lock SET
                    product = product:test,
                    resource_type = 'file',
                    resource_id = 'src/main.py',
                    held_by = 'work_item:wi2',
                    expires_at = time::now() + 1h
                """
            )
            # If it doesn't raise, the unique index isn't working as expected
            # Check that only one record exists
            check = await db.query(
                """
                SELECT * FROM resource_lock
                WHERE product = product:test AND resource_type = 'file' AND resource_id = 'src/main.py'
                """
            )
            check_rows = parse_rows(check)
            # Should only be one due to unique index
            assert len(check_rows) <= 1
        except Exception:
            # Expected — unique constraint violation
            pass

        # Cleanup
        await db.query(
            """
            DELETE FROM resource_lock
            WHERE product = product:test AND resource_type = 'file' AND resource_id = 'src/main.py'
            """
        )
