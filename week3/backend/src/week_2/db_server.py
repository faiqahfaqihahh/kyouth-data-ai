from fastmcp import FastMCP
import sqlite3
import os
import sys

mcp = FastMCP("SQLite-Service")

if len(sys.argv) > 1:
    DB_PATH = sys.argv[1]
else:
    DB_PATH = os.environ.get("DB_PATH", "resources/jobs_d1.db")

@mcp.tool
def query_db(sql_query: str):
    """Executes a SQL query against the SQLite database and returns results."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(sql_query)
        conn.commit()
        return cursor.fetchall()

@mcp.tool
def get_tech_stacks() -> list:
    """Returns all non-empty tech_stack values from the jobs table."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT tech_stack FROM jobs WHERE tech_stack IS NOT NULL AND tech_stack != ''"
        )
        rows = cursor.fetchall()
    return [row[0] for row in rows]

if __name__ == "__main__":
    mcp.run()