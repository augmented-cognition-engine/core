# engine/intelligence/schema.py
"""SurrealDB schema for the code intelligence pipeline."""

SCHEMA_STATEMENTS = [
    # Code symbols (more precise than graph_function)
    "DEFINE TABLE IF NOT EXISTS code_symbol SCHEMALESS",
    "DEFINE TABLE IF NOT EXISTS code_analysis SCHEMALESS",
    # Accurate edges from LSP
    "DEFINE TABLE IF NOT EXISTS calls SCHEMALESS",
    "DEFINE TABLE IF NOT EXISTS references SCHEMALESS",
    "DEFINE TABLE IF NOT EXISTS implements SCHEMALESS",
]


async def apply_schema():
    """Apply intelligence schema to SurrealDB."""
    from core.engine.core.db import pool

    async with pool.connection() as db:
        for stmt in SCHEMA_STATEMENTS:
            try:
                await db.query(stmt)
            except Exception as exc:
                import logging

                logging.getLogger(__name__).debug("Schema statement failed (may already exist): %s — %s", stmt, exc)
