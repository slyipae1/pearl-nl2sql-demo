from __future__ import annotations

from pathlib import Path

import pandas as pd

from database.inspector import describe_sqlite_schema, execute_sql, list_tables, sample_table


def load_schema_text(db_file: Path) -> str:
    return describe_sqlite_schema(db_file)


def get_table_choices(db_file: Path) -> list[str]:
    return list_tables(db_file)


def sample_table_markdown(db_file: Path, table_name: str, n_rows: int) -> str:
    if not table_name:
        return "Select a table first."
    try:
        df = sample_table(db_file, table_name, n_rows)
    except Exception as exc:
        return f"_Error: {exc}_"
    if df.empty:
        return "_No rows returned._"
    return df.to_markdown(index=False)


def execute_sql_markdown(db_file: Path, sql: str) -> str:
    if not sql.strip():
        return "Provide SQL first."
    try:
        df: pd.DataFrame = execute_sql(db_file, sql)
    except Exception as exc:
        return f"_Error: {exc}_"
    if df.empty:
        return "_No rows returned._"
    return df.to_markdown(index=False)
