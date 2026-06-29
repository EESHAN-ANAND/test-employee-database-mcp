"""Employee database MCP server (HTTP) — a single, fully generic SQL tool.

This server exposes ONE tool: `execute_sql`. You describe what you want in
plain English; the assistant (LLM) translates it into SQL and calls this tool,
which executes ANY statement against the database:

    - read      : SELECT ...
    - manipulate: INSERT / UPDATE / DELETE
    - schema    : CREATE TABLE / ALTER / DROP / etc.
    - "truncate": DELETE FROM <table>  (SQLite has no TRUNCATE keyword)

No operation is restricted — it has full read/write/DDL power.
"""

import os
import sqlite3
import tempfile

from fastmcp import FastMCP

mcp = FastMCP("test-employee-database-mcp")

# The app directory is READ-ONLY on FastMCP Cloud, so the database lives in the
# system temp directory (writable). Note: temp storage is ephemeral — changes
# reset to the seed data when the instance restarts.
DB_PATH = os.path.join(tempfile.gettempdir(), "emp.db")

SEED = [
    ("Asha Rao", "Engineering", 210000),
    ("Vikram Singh", "Engineering", 175000),
    ("Neha Gupta", "Engineering", 140000),
    ("Rohan Mehta", "Engineering", None),
    ("Priya Nair", "Sales", 160000),
    ("Arjun Das", "Sales", 120000),
    ("Sara Khan", "Sales", 98000),
    ("Karan Joshi", "Sales", None),
    ("Maya Iyer", "Marketing", 135000),
    ("Dev Patel", "Marketing", 110000),
    ("Ananya Bose", "Marketing", None),
    ("Imran Sheikh", "HR", 125000),
    ("Tara Menon", "HR", 90000),
]


def _init_db() -> None:
    """Create and seed the employees table once, if it doesn't exist yet."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS employees ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "name TEXT NOT NULL, department TEXT NOT NULL, salary REAL)"
        )
        if conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO employees (name, department, salary) VALUES (?, ?, ?)",
                SEED,
            )
        conn.commit()


_init_db()


@mcp.tool()
def execute_sql(sql: str) -> dict:
    """Execute ANY SQL statement against the employee database.

    Describe the task in plain English and the assistant will translate it into
    SQL, then call this tool. Supports everything: SELECT (read), INSERT/UPDATE/
    DELETE (manipulate records), and CREATE/ALTER/DROP (schema changes). To
    "truncate" a table use `DELETE FROM <table>` (SQLite has no TRUNCATE).

    Returns the matching rows for queries, or the number of affected rows for
    write/DDL statements.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(sql)
        if cur.description is not None:          # statement produced a result set
            rows = [dict(r) for r in cur.fetchall()]
            return {"type": "rows", "row_count": len(rows), "rows": rows}
        conn.commit()                            # write / DDL
        return {
            "type": "write",
            "rows_affected": cur.rowcount,
            "lastrowid": cur.lastrowid,
        }
    finally:
        conn.close()


if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8000)
