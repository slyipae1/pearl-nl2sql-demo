from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from utils.logging_config import get_logger

logger = get_logger(__name__)


_LITERAL_TEXT_RE = re.compile(r"'([^']+)'|\"([^\"]+)\"")
_COLUMN_HINT_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)\b")


@dataclass
class ParsedSql:
    sql: str
    columns: list[str] = field(default_factory=list)
    literals: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    parse_error: str = ""


WINDOW_AMBIG_FUNCTIONS = {
    "RANK",
    "DENSE_RANK",
    "ROW_NUMBER",
    "AVG",
    "SUM",
    "COUNT",
    "MIN",
    "MAX",
    "COALESCE",
    "IFNULL",
    "NVL",
}


def _dedup_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = value.strip()
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        output.append(key)
    return output


def parse_sql_for_detector(sql: str) -> ParsedSql:
    sql_text = (sql or "").strip()
    if not sql_text:
        return ParsedSql(sql=sql_text, parse_error="Empty SQL")

    try:
        import sqlglot
        from sqlglot import exp

        ast = sqlglot.parse_one(sql_text)

        columns: list[str] = []
        for col in ast.find_all(exp.Column):
            col_name = col.sql(dialect="sqlite")
            columns.append(col_name)

        literals: list[str] = []
        for literal in ast.find_all(exp.Literal):
            if literal.is_string:
                literals.append(str(literal.this))
                continue
            raw = str(literal.this)
            if raw and len(raw) <= 64:
                literals.append(raw)
        # special handle like literals remove %%
        for lit in literals:
            if isinstance(lit, str) and lit.startswith("%") and lit.endswith("%") and len(lit) > 2:
                cleaned = lit.strip("%")
                if cleaned:
                    literals.append(cleaned)

        functions: list[str] = []
        for func in ast.find_all(exp.Func):
            func_sql = func.sql(dialect="sqlite")
            functions.append(func_sql)
        for win in ast.find_all(exp.Window):
            functions.append(win.sql(dialect="sqlite"))

        return ParsedSql(
            sql=sql_text,
            columns=_dedup_keep_order(columns),
            literals=_dedup_keep_order(literals),
            functions=_dedup_keep_order(functions),
            parse_error="",
        )
    except Exception as exc:
        # Safe fallback: light regex extraction keeps detector running even when parser fails.
        logger.warning("SQL parsing failed: %s. Falling back to regex-based extraction.", exc)
        literals: list[str] = []
        for left, right in _LITERAL_TEXT_RE.findall(sql_text):
            value = left or right
            if value:
                literals.append(value)

        candidate_columns = [m.group(1) for m in _COLUMN_HINT_RE.finditer(sql_text)]
        ignore_tokens = {
            "select",
            "from",
            "where",
            "join",
            "left",
            "right",
            "inner",
            "outer",
            "on",
            "group",
            "by",
            "order",
            "limit",
            "as",
            "and",
            "or",
            "not",
            "case",
            "when",
            "then",
            "else",
            "end",
            "desc",
            "asc",
            "distinct",
            "having",
            "union",
            "all",
            "with",
            "over",
            "partition",
            "rows",
            "range",
            "current",
            "row",
            "between",
            "null",
            "is",
            "in",
            "like",
        }
        filtered_columns = [
            c
            for c in candidate_columns
            if c.lower() not in ignore_tokens and not c.isdigit() and len(c) > 1
        ]

        function_hits = [fn for fn in WINDOW_AMBIG_FUNCTIONS if re.search(rf"\b{re.escape(fn)}\s*\(", sql_text, re.IGNORECASE)]

        return ParsedSql(
            sql=sql_text,
            columns=_dedup_keep_order(filtered_columns),
            literals=_dedup_keep_order(literals),
            functions=_dedup_keep_order(function_hits),
            parse_error=str(exc),
        )


def parse_multiple_sql(sql_list: list[str]) -> list[ParsedSql]:
    return [parse_sql_for_detector(sql) for sql in sql_list]
