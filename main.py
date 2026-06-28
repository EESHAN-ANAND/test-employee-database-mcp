"""Employee analytics MCP server (HTTP transport).

A SQLite-backed employee database with PURPOSE-BUILT analytical query tools
(not the generic SQLDatabaseToolkit approach). Each tool runs a specific,
hand-written SQL query showcasing GROUP BY, window functions, NULL handling,
and subqueries.

Schema:  employees(id, name, department, salary)
         - salary is nullable; interns have salary = NULL.

Served over HTTP so it can be deployed (e.g. FastMCP Cloud).
"""

import os
import re
import sqlite3

from fastmcp import FastMCP

mcp = FastMCP("test-emp-database-mcp")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emp.db")

# Sample data: (name, department, salary).  None salary => intern.
SEED = [
    ("Asha Rao", "Engineering", 210000),
    ("Vikram Singh", "Engineering", 175000),
    ("Neha Gupta", "Engineering", 140000),
    ("Rohan Mehta", "Engineering", None),       # intern
    ("Priya Nair", "Sales", 160000),
    ("Arjun Das", "Sales", 120000),
    ("Sara Khan", "Sales", 98000),
    ("Karan Joshi", "Sales", None),             # intern
    ("Maya Iyer", "Marketing", 135000),
    ("Dev Patel", "Marketing", 110000),
    ("Ananya Bose", "Marketing", None),         # intern
    ("Imran Sheikh", "HR", 125000),
    ("Tara Menon", "HR", 90000),
]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    """Create the employees table and seed sample data if empty."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS employees (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                department TEXT NOT NULL,
                salary     REAL          -- NULL allowed (interns)
            )
            """
        )
        count = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
        if count == 0:
            conn.executemany(
                "INSERT INTO employees (name, department, salary) VALUES (?, ?, ?)",
                SEED,
            )
        conn.commit()


def _q(sql: str, params: tuple = ()) -> list[dict]:
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


_init_db()


# ---------------------------------------------------------------------------
# Basic access
# ---------------------------------------------------------------------------
@mcp.tool()
def add_employee(name: str, department: str, salary: float | None = None) -> dict:
    """Add an employee. Omit salary (or pass null) for interns."""
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO employees (name, department, salary) VALUES (?, ?, ?)",
            (name, department, salary),
        )
        conn.commit()
        new_id = cur.lastrowid
    return {"status": "added", "id": new_id, "name": name,
            "department": department, "salary": salary}


@mcp.tool()
def list_employees() -> list[dict]:
    """List all employees."""
    return _q("SELECT id, name, department, salary FROM employees ORDER BY id")


# ---------------------------------------------------------------------------
# Analytical queries (the interesting part)
# ---------------------------------------------------------------------------
@mcp.tool()
def top_n_by_salary(n: int = 3, department: str = "") -> list[dict]:
    """Top N highest-paid employees, optionally within a department.

    Interns (NULL salary) are excluded. Example: top 3 earners in Engineering.
    """
    if department:
        sql = (
            "SELECT name, department, salary FROM employees "
            "WHERE salary IS NOT NULL AND department = ? "
            "ORDER BY salary DESC LIMIT ?"
        )
        return _q(sql, (department, n))
    sql = (
        "SELECT name, department, salary FROM employees "
        "WHERE salary IS NOT NULL ORDER BY salary DESC LIMIT ?"
    )
    return _q(sql, (n,))


@mcp.tool()
def average_salary_by_department() -> list[dict]:
    """Average salary per department (GROUP BY). NULL salaries are ignored by AVG.

    Also reports total headcount and how many are paid (non-intern).
    """
    sql = """
        SELECT department,
               COUNT(*)               AS headcount,
               COUNT(salary)          AS paid_employees,
               ROUND(AVG(salary), 2)  AS avg_salary
        FROM employees
        GROUP BY department
        ORDER BY avg_salary DESC
    """
    return _q(sql)


@mcp.tool()
def department_salary_stats() -> list[dict]:
    """Per-department salary summary: count, min, max, and average (GROUP BY)."""
    sql = """
        SELECT department,
               COUNT(salary)         AS paid_employees,
               MIN(salary)           AS min_salary,
               MAX(salary)           AS max_salary,
               ROUND(AVG(salary), 2) AS avg_salary
        FROM employees
        GROUP BY department
        ORDER BY avg_salary DESC
    """
    return _q(sql)


@mcp.tool()
def salary_rank_within_department() -> list[dict]:
    """Rank each employee by salary inside their department (WINDOW: RANK)."""
    sql = """
        SELECT name, department, salary,
               RANK() OVER (
                   PARTITION BY department ORDER BY salary DESC
               ) AS dept_rank
        FROM employees
        WHERE salary IS NOT NULL
        ORDER BY department, dept_rank
    """
    return _q(sql)


@mcp.tool()
def highest_paid_per_department() -> list[dict]:
    """The single top earner in each department (WINDOW: ROW_NUMBER = 1)."""
    sql = """
        WITH ranked AS (
            SELECT name, department, salary,
                   ROW_NUMBER() OVER (
                       PARTITION BY department ORDER BY salary DESC
                   ) AS rn
            FROM employees
            WHERE salary IS NOT NULL
        )
        SELECT name, department, salary
        FROM ranked
        WHERE rn = 1
        ORDER BY salary DESC
    """
    return _q(sql)


@mcp.tool()
def employees_above_company_average() -> list[dict]:
    """Employees earning above the company-wide average salary.

    company_avg is the true average across ALL paid employees (a window
    AVG() OVER () would be wrong here, since it runs after the WHERE filter
    and would only average the rows that already survived).
    """
    sql = """
        SELECT name, department, salary,
               ROUND((SELECT AVG(salary) FROM employees), 2) AS company_avg
        FROM employees
        WHERE salary IS NOT NULL
          AND salary > (SELECT AVG(salary) FROM employees)
        ORDER BY salary DESC
    """
    return _q(sql)


@mcp.tool()
def salary_share_within_department() -> list[dict]:
    """Each employee's salary as a % of their department's total payroll.

    Uses a window SUM() OVER (PARTITION BY department).
    """
    sql = """
        SELECT name, department, salary,
               SUM(salary) OVER (PARTITION BY department) AS dept_payroll,
               ROUND(
                   100.0 * salary / SUM(salary) OVER (PARTITION BY department), 2
               ) AS pct_of_department
        FROM employees
        WHERE salary IS NOT NULL
        ORDER BY department, pct_of_department DESC
    """
    return _q(sql)


@mcp.tool()
def list_interns() -> list[dict]:
    """List interns — employees with no salary (NULL)."""
    return _q(
        "SELECT id, name, department FROM employees "
        "WHERE salary IS NULL ORDER BY department, name"
    )


@mcp.tool()
def headcount_by_department() -> list[dict]:
    """Number of employees in each department (GROUP BY + COUNT)."""
    return _q(
        "SELECT department, COUNT(*) AS headcount FROM employees "
        "GROUP BY department ORDER BY headcount DESC"
    )


# ---------------------------------------------------------------------------
# Write / manipulate tools (admin actions)
# ---------------------------------------------------------------------------
def _write(sql: str, params: tuple) -> int:
    """Execute an INSERT/UPDATE/DELETE; return affected row count (or lastrowid)."""
    with _connect() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.rowcount


@mcp.tool()
def update_salary(id: int, salary: float | None) -> dict:
    """Set an employee's salary by id. Pass null to mark them an intern."""
    n = _write("UPDATE employees SET salary = ? WHERE id = ?", (salary, id))
    return {"status": "updated" if n else "not_found", "id": id, "salary": salary}


@mcp.tool()
def update_department(id: int, department: str) -> dict:
    """Move an employee to a different department."""
    n = _write("UPDATE employees SET department = ? WHERE id = ?", (department, id))
    return {"status": "updated" if n else "not_found", "id": id, "department": department}


@mcp.tool()
def update_name(id: int, name: str) -> dict:
    """Rename an employee by id."""
    n = _write("UPDATE employees SET name = ? WHERE id = ?", (name, id))
    return {"status": "updated" if n else "not_found", "id": id, "name": name}


@mcp.tool()
def give_raise(id: int, amount: float) -> dict:
    """Increase an employee's salary by `amount` (interns with NULL salary are skipped)."""
    n = _write(
        "UPDATE employees SET salary = salary + ? WHERE id = ? AND salary IS NOT NULL",
        (amount, id),
    )
    if n == 0:
        return {"status": "no_change", "id": id,
                "message": "Employee not found, or is an intern with no salary."}
    row = _q("SELECT name, salary FROM employees WHERE id = ?", (id,))[0]
    return {"status": "updated", "id": id, "name": row["name"], "new_salary": row["salary"]}


@mcp.tool()
def delete_employee(id: int) -> dict:
    """Delete an employee by id."""
    n = _write("DELETE FROM employees WHERE id = ?", (id,))
    return {"status": "deleted" if n else "not_found", "id": id}


# ---------------------------------------------------------------------------
# Generic "text-to-SQL" tools (the flexible, screenshot-style approach)
# ---------------------------------------------------------------------------
# These let an LLM answer ARBITRARY questions by discovering the schema and
# writing its own SQL, instead of relying on a pre-built tool per question.

@mcp.tool()
def list_tables() -> list[str]:
    """List the tables available in the database."""
    rows = _q(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [r["name"] for r in rows]


@mcp.tool()
def describe_table(table: str = "employees") -> dict:
    """Return a table's columns (name, type, nullable) so SQL can be written."""
    valid = [r["name"] for r in _q("SELECT name FROM sqlite_master WHERE type='table'")]
    if table not in valid:
        raise ValueError(f"Unknown table '{table}'. Available: {valid}")
    cols = _q(f"PRAGMA table_info({table})")  # safe: table validated above
    return {
        "table": table,
        "columns": [
            {"name": c["name"], "type": c["type"], "nullable": not c["notnull"]}
            for c in cols
        ],
    }


_FORBIDDEN = (
    "insert", "update", "delete", "drop", "alter", "create",
    "replace", "attach", "detach", "pragma", "vacuum",
)


@mcp.tool()
def run_query(sql: str) -> list[dict]:
    """Run a READ-ONLY SQL SELECT and return the rows.

    Use this for any question the specific tools don't cover (custom GROUP BY,
    filters, CASE expressions, etc.). The LLM writes the SQL; this tool just
    executes it safely. Only a single SELECT/WITH statement is allowed — any
    write or DDL is rejected, and the database is opened read-only.
    """
    cleaned = sql.strip().rstrip(";").strip()
    lowered = cleaned.lower()

    if ";" in cleaned:
        raise ValueError("Only a single statement is allowed (no semicolons).")
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise ValueError("Only SELECT/WITH (read-only) queries are allowed.")
    for kw in _FORBIDDEN:
        if re.search(rf"\b{kw}\b", lowered):
            raise ValueError(f"'{kw}' statements are not allowed (read-only).")

    # Open the database in read-only mode for an extra layer of safety.
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(cleaned).fetchall()]
    finally:
        conn.close()


if __name__ == "__main__":
    # Local run. On FastMCP Cloud this block is not executed; the platform
    # imports the `mcp` object and serves it over HTTP itself.
    mcp.run(transport="http", host="127.0.0.1", port=8000)
