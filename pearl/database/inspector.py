from __future__ import annotations

import random
import sqlite3
from pathlib import Path

import pandas as pd

from .csv_utils import load_tables_description, resolve_database_description_path


def get_db_file(created_dbs_dir: Path, db_name: str) -> Path:
    return created_dbs_dir / db_name / f"{db_name}.sqlite"


def list_db_names(created_dbs_dir: Path) -> list[str]:
    if not created_dbs_dir.exists():
        return []
    return sorted([p.name for p in created_dbs_dir.iterdir() if p.is_dir()])


def list_tables(db_file: Path) -> list[str]:
    try:
        conn = sqlite3.connect(str(db_file))
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = [row[0] for row in cur.fetchall()]
        conn.close()
        # random order of tables
        # random.shuffle(tables)
        return tables
    except Exception:
        return []


def describe_sqlite_schema(db_file: Path, num_samples: int = 3) -> str:
    if not db_file.exists():
        return f"Database not found: {db_file}"

    ### Rounting ###
    description_path = resolve_database_description_path(db_file)
    if description_path.exists() or "MINIDEV" in db_file.name.upper() or "BIRD" in db_file.name.upper():
        return describe_sqlite_schema_BIRD(db_file, num_samples)
    ### Rounting ###

    lines = [f"Database: {db_file.name}"]
    try:
        with sqlite3.connect(str(db_file)) as conn:
            for table in list_tables(db_file):
                lines.append(f"\nTable `{table}`")
                df = pd.read_sql_query(f"SELECT * FROM '{table}'", conn)
                cols = pd.read_sql_query(f"PRAGMA table_info('{table}')", conn)
                for _, row in cols.iterrows():
                    col_name = str(row["name"])
                    col_type = str(row["type"])
                    not_null = bool(row["notnull"])
                    nullable = "NOT NULL" if not_null else "NULL"
                    if col_name in df.columns:
                        series = df[col_name]
                        n_unique = int(series.nunique(dropna=True))
                        n_null = int(series.isnull().sum())
                        samples = [str(v) for v in series.dropna().unique()[:num_samples]]
                        sample_str = f" | Sample: {', '.join(samples)}" if samples else ""
                        lines.append(
                            f"- {col_name}: {col_type} ({nullable}) | Unique: {n_unique} | Missing: {n_null}{sample_str}"
                        )
                    else:
                        lines.append(f"- {col_name}: {col_type} ({nullable})")
    except Exception as exc:
        lines.append(f"\nSchema inspection failed: {exc}")
    return "\n".join(lines)


def sample_table(db_file: Path, table_name: str, n_rows: int) -> pd.DataFrame:
    conn = sqlite3.connect(str(db_file))
    try:
        return pd.read_sql_query(
            f"SELECT * FROM '{table_name}' ORDER BY RANDOM() LIMIT {int(max(1, n_rows))}",
            conn,
        )
    finally:
        conn.close()


def execute_sql(db_file: Path, sql: str) -> pd.DataFrame:
    conn = sqlite3.connect(str(db_file))
    try:
        return pd.read_sql_query(sql, conn)
    finally:
        conn.close()











###################### Router Database Inspector ######################
def describe_sqlite_schema_BIRD(db_file: Path, num_samples: int = 3) -> str:
    """
    if "MINIDEV"  or "BIRD" in db_file, routner to this function, add description for each column 
    """
    if not db_file.exists():
        return f"Database not found: {db_file}"

    lines = [f"Database: {db_file.name}"]
    table_descriptions = load_tables_description(db_file, use_value_description=True)

    def _format_description(column_info: dict[str, str]) -> str:
        description_bits: list[str] = []
        column_description = column_info.get("column_description", "").strip()
        data_format = column_info.get("data_format", "").strip()
        value_description = column_info.get("value_description", "").strip()

        if column_description:
            description_bits.append(column_description)
        if data_format:
            description_bits.append(f"Format: {data_format}")
        if value_description:
            description_bits.append(f"Value notes: {value_description}")

        if not description_bits:
            return ""
        return " | Description: " + " ; ".join(description_bits)

    try:
        with sqlite3.connect(str(db_file)) as conn:
            for table in list_tables(db_file):
                lines.append(f"\nTable `{table}`")
                df = pd.read_sql_query(f"SELECT * FROM '{table}'", conn)
                cols = pd.read_sql_query(f"PRAGMA table_info('{table}')", conn)
                table_description = table_descriptions.get(table.lower(), {})

                for _, row in cols.iterrows():
                    col_name = str(row["name"])
                    col_type = str(row["type"])
                    not_null = bool(row["notnull"])
                    nullable = "NOT NULL" if not_null else "NULL"
                    if col_name in df.columns:
                        series = df[col_name]
                        n_unique = int(series.nunique(dropna=True))
                        n_null = int(series.isnull().sum())
                        samples = [str(v) for v in series.dropna().unique()[:num_samples]]
                        sample_str = f" | Sample: {', '.join(samples)}" if samples else ""
                        this_line = f"- {col_name}: {col_type} ({nullable}) | Unique: {n_unique} | Missing: {n_null}{sample_str}"
                    else:
                        this_line = f"- {col_name}: {col_type} ({nullable})"

                    column_description = table_description.get(col_name.lower())
                    if column_description:
                        this_line += _format_description(column_description)

                    lines.append(this_line)

    except Exception as exc:
        lines.append(f"\nSchema inspection failed: {exc}")
    return "\n".join(lines)