"""Shared fixtures: a generated dataset, and a way to actually run the SQL.

WHY THE SQL RUNNER EXISTS
-------------------------
The metric tests assert what the *generator* produces. They said nothing about
whether the queries in `sql/analysis/business_questions.sql` compute what their
comments claim — and an audit proved the gap was real by swapping Q8's LEFT JOIN
for an INNER JOIN, the bug that makes month-over-month retention read 100%. Every
test stayed green.

So the queries are now executed. They are written for BigQuery, which is not
something a test can call for free on every push, so `sqlglot` transpiles them to
DuckDB and DuckDB runs them over the generated CSVs. That is not the same engine,
and it does not prove the SQL is valid BigQuery — `sqlfluff` in CI covers the
dialect. What it does prove is that the *logic* produces the documented numbers,
which is the part that was silently unprotected.
"""

import os
import re
import subprocess
import sys

import duckdb
import pandas as pd
import pytest
import sqlglot

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_FILE = os.path.join(ROOT, "sql", "analysis", "business_questions.sql")

# The tables the queries reference, and the CSV each one is loaded from. dbt
# builds fct_streams by enriching the raw fact; for the purposes of these
# queries the enrichment columns are not read, so the raw fact stands in.
TABLES = {
    "streaming.fct_streams": "F_Streams.csv",
    "streaming.dim_user": "D_Users.csv",
    "streaming.dim_track": "D_Tracks.csv",
    "streaming.dim_time": "D_Time.csv",
    "streaming.dim_platform": "D_Platform.csv",
}


@pytest.fixture(scope="session")
def dataset(tmp_path_factory):
    """One generated dataset for the whole run — generating is the slow part."""
    out = tmp_path_factory.mktemp("dataset")
    subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "generate_datasets.py"),
         "--out", str(out), "--users", "20000", "--seed", "42"],
        check=True, capture_output=True,
    )
    return out


@pytest.fixture(scope="session")
def frames(dataset):
    return {
        "streams": pd.read_csv(dataset / "F_Streams.csv"),
        "users": pd.read_csv(dataset / "D_Users.csv"),
        "tracks": pd.read_csv(dataset / "D_Tracks.csv"),
    }


def split_queries(sql_text: str) -> dict:
    """Split the analysis file into {'Q1': sql, ...} on its own Qn headers."""
    queries, current, buffer = {}, None, []
    for line in sql_text.splitlines():
        header = re.match(r"^--\s*(Q\d+)\.", line)
        if header:
            if current:
                queries[current] = "\n".join(buffer).strip()
            current, buffer = header.group(1), []
            continue
        if current is not None:
            buffer.append(line)
    if current:
        queries[current] = "\n".join(buffer).strip()

    # Keep only the statement, dropping the trailing comment block that
    # introduces the next question.
    return {
        name: body[: body.index(";") + 1]
        for name, body in queries.items()
        if ";" in body
    }


@pytest.fixture(scope="session")
def run_query(dataset):
    """Execute a query from the analysis file and return it as a DataFrame."""
    con = duckdb.connect()
    con.execute("CREATE SCHEMA IF NOT EXISTS streaming")
    for table, csv in TABLES.items():
        path = dataset / csv
        if path.exists():
            con.execute(
                f"CREATE OR REPLACE TABLE {table} AS "
                f"SELECT * FROM read_csv_auto('{path}', header=true)"
            )

    with open(SQL_FILE, encoding="utf-8") as fh:
        queries = split_queries(fh.read())

    def run(name: str) -> pd.DataFrame:
        if name not in queries:
            raise KeyError(f"{name} not found in {os.path.basename(SQL_FILE)}: "
                           f"present {sorted(queries)}")
        statement = queries[name].replace("`", '"')
        duck = sqlglot.transpile(statement, read="bigquery", write="duckdb")[0]
        return con.execute(duck).df()

    run.available = sorted(queries)
    return run
