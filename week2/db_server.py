"""
db_server.py  –  FastMCP server that exposes SQLite read/write operations.

This file is launched as a subprocess by tag_data.py (MCP bonus).
Do NOT run it directly.

The DB path is passed as a command-line argument so the client
can configure which database to use:
    python db_server.py data/jobs_d1.db
"""

import sqlite3
import sys
from fastmcp import FastMCP

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else "data/jobs_d1.db"

mcp = FastMCP("SQLite-Jobs-Service")


@mcp.tool
def read_untagged_jobs() -> list[dict]:
    """Return all jobs whose tech_stack column is NULL or empty."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT source_id, description FROM jobs "
            "WHERE tech_stack IS NULL OR tech_stack = ''"
        )
        return [dict(row) for row in cur.fetchall()]


@mcp.tool
def update_tech_stack(source_id: str, tech_stack: str) -> bool:
    """Write a tech_stack string for one job row. Returns True on success."""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE jobs SET tech_stack = ? WHERE source_id = ?",
            (tech_stack, source_id),
        )
        conn.commit()
        return cur.rowcount > 0


@mcp.tool
def read_all_tech_stacks() -> list[dict]:
    """Return source_id + tech_stack for all tagged rows."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT source_id, tech_stack FROM jobs "
            "WHERE tech_stack IS NOT NULL AND tech_stack != ''"
        )
        return [dict(row) for row in cur.fetchall()]


if __name__ == "__main__":
    mcp.run()
