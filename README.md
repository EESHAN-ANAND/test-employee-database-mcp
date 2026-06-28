# test-emp-database-mcp

An employee-analytics MCP server (HTTP transport) backed by SQLite. Unlike a
generic SQL toolkit, every tool here runs a specific, hand-written query
demonstrating GROUP BY, window functions, NULL handling, and subqueries.

The database self-seeds 13 sample employees across Engineering, Sales,
Marketing, and HR (three of them interns with `NULL` salary), so the analytics
return meaningful results immediately.

## Schema

`employees(id, name, department, salary)` — `salary` is nullable; interns are NULL.

## Tools

Basic: `add_employee`, `list_employees`

Analytics:
- `top_n_by_salary(n, department)` — top N earners overall or within a department
- `average_salary_by_department` — GROUP BY, AVG (ignores interns), headcount
- `department_salary_stats` — count / min / max / avg per department
- `salary_rank_within_department` — window `RANK() OVER (PARTITION BY ...)`
- `highest_paid_per_department` — window `ROW_NUMBER() = 1`
- `employees_above_company_average` — above the true company-wide average
- `salary_share_within_department` — window `SUM() OVER (PARTITION BY ...)`, % of dept payroll
- `list_interns` — employees with NULL salary
- `headcount_by_department` — COUNT per department

## Run / test locally

```bash
cd ~/Documents/Claude/test-emp-database-mcp
uv add fastmcp
uv run main.py          # serves http://127.0.0.1:8000/mcp (leave running)
```

To test the tools, point the MCP Inspector at the running URL:

```bash
npx @modelcontextprotocol/inspector
# transport: Streamable HTTP, URL: http://127.0.0.1:8000/mcp
```

## Deploy to FastMCP Cloud

1. Lock deps so `fastmcp` is in the lockfile: `uv lock`
2. Push `main.py`, `pyproject.toml`, `uv.lock` to a GitHub repo.
3. On fastmcp.cloud, point at the repo with entrypoint `main.py`.

Notes:
- The `mcp` object name and `from fastmcp import FastMCP` import are what
  FastMCP Cloud requires.
- The platform serves the `mcp` object itself; the `__main__` block (local
  host/port) is ignored in the cloud.
- `emp.db` is git-ignored and re-seeded on startup.
