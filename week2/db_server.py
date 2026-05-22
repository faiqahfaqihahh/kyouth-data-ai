from fastmcp import FastMCP
import sqlite3
import json
import os

mcp = FastMCP("SQLite-Service")

# Read DB path from the environment variable set by tag_data.py
DB_PATH = os.environ.get("DB_PATH", "data/jobs_d1.db")

@mcp.tool()  # <-- Added parentheses
def query_db(sql_query: str) -> str:
    """Executes a SELECT SQL query and returns results as a JSON string."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(sql_query)
        return json.dumps(cursor.fetchall())

@mcp.tool()  # <-- Added parentheses
def execute_db(sql_query: str, params: list = None) -> str:
    """Executes a write SQL query (INSERT/UPDATE/DELETE) with optional params."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        if params:
            cursor.execute(sql_query, params)
        else:
            cursor.execute(sql_query)
        conn.commit()
        return json.dumps({"rowcount": cursor.rowcount})

@mcp.tool()  # <-- Added parentheses
def get_tech_stacks() -> list:
    """Retrieves all non-empty tech stacks from the database."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT tech_stack FROM jobs WHERE tech_stack IS NOT NULL AND tech_stack != ''"
        )
        rows = cursor.fetchall()
    return [row[0] for row in rows]

if __name__ == "__main__":
    mcp.run()