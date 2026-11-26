from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import html
import json
import uuid
from typing import Any

import markdown
import pandas as pd

from utils.profile import df_profile_markdown


class NodeType(str, Enum):
    USER_QUESTION = "USER_QUESTION"
    USER_SPECIFICATION = "USER_SPECIFICATION"
    GET_SCHEMA = "GET_SCHEMA"
    SQL_GEN = "SQL_GEN"
    CAND_GEN = "CAND_GEN"
    AMBI_DETECT = "AMBI_DETECT"
    AMBI_EVAL = "AMBI_EVAL"
    EXEC_SQL = "EXEC_SQL"
    RETRY_SQL_GEN = "RETRY_SQL_GEN"
    FINAL_ANSWER = "FINAL_ANSWER"
    MANAGER_ENRICH_PROMPT = "MANAGER_ENRICH_PROMPT"
    MANAGER_SUMMARY = "MANAGER_SUMMARY"
    MANAGER_AUTO_FIX = "MANAGER_AUTO_FIX"
    COMPACT_SUMMARY = "COMPACT_SUMMARY"
    PREFERENCE_SAVE = "PREFERENCE_SAVE"
    MIXTURE = "MIXTURE"


class DetailType(str, Enum):
    USER_QUESTION = "USER_QUESTION"
    USER_SPECIFICATION = "USER_SPECIFICATION"
    GET_SCHEMA = "GET_SCHEMA"
    SQL_GEN = "SQL_GEN"
    CAND_GEN = "CAND_GEN"
    AMBI_DETECT = "AMBI_DETECT"
    AMBI_EVAL = "AMBI_EVAL"
    EXEC_SQL = "EXEC_SQL"
    RETRY_SQL_GEN = "RETRY_SQL_GEN"
    FINAL_ANSWER = "FINAL_ANSWER"
    MANAGER_STEP = "MANAGER_STEP"
    MANAGER_AUTO_FIX = "MANAGER_AUTO_FIX"
    PREFERENCE_SAVE = "PREFERENCE_SAVE"


STANDARD_TITLES = {
    NodeType.USER_QUESTION: "User Question",
    NodeType.USER_SPECIFICATION: "User Specification",
    NodeType.SQL_GEN: "SQL Generation",
    NodeType.CAND_GEN: "Candidates Exploration",
    NodeType.AMBI_DETECT: "Ambiguity Detection",
    NodeType.AMBI_EVAL: "Ambiguity Option Evaluation",
    NodeType.EXEC_SQL: "SQL Execution",
    NodeType.RETRY_SQL_GEN: "SQL Generation (Retry)",
    NodeType.FINAL_ANSWER: "Final Answer",
    NodeType.MIXTURE: "Mixed Actions",
    NodeType.MANAGER_ENRICH_PROMPT: "Manager Enriched Prompt",
    NodeType.MANAGER_SUMMARY: "Manager Summary",
    NodeType.MANAGER_AUTO_FIX: "Manager Auto Fix",
    NodeType.COMPACT_SUMMARY: "Compact Summary",
    NodeType.PREFERENCE_SAVE: "Preference Save",
}

def get_selectable_node_types() -> set[NodeType]:
    """Returns set of node types that are selectable by users in UI."""
    return {
        NodeType.USER_SPECIFICATION,
        NodeType.SQL_GEN,
        NodeType.CAND_GEN,
        NodeType.AMBI_DETECT,
        NodeType.AMBI_EVAL,
        NodeType.EXEC_SQL,
        NodeType.MANAGER_ENRICH_PROMPT,
        NodeType.RETRY_SQL_GEN,
    }


def get_info_only_node_types() -> set[NodeType]:
    """Returns set of node types that are info-only and not selectable."""
    return {
        NodeType.USER_QUESTION,
        NodeType.MANAGER_SUMMARY,
        NodeType.MANAGER_AUTO_FIX,
        NodeType.COMPACT_SUMMARY,
        NodeType.PREFERENCE_SAVE,
    }


SQL_EXEC_LIKE_NODE_TYPES = {
    NodeType.SQL_GEN,
    NodeType.CAND_GEN,
    NodeType.AMBI_DETECT,
    NodeType.AMBI_EVAL,
    NodeType.EXEC_SQL,
    NodeType.RETRY_SQL_GEN,
}


def _new_detail_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def is_sql_exec_like_node_type(node_type: NodeType) -> bool:
    return node_type in SQL_EXEC_LIKE_NODE_TYPES


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, dict, tuple)):
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            return str(value)
    return str(value)


def _esc(text: Any) -> str:
    return html.escape(_stringify(text), quote=True)


def _render_list(items: list[str]) -> str:
    if not items:
        return ""
    content = "".join(f"<li>{_esc(item)}</li>" for item in items)
    return f"<ul class='detail-list'>{content}</ul>"


def _split_issue_lines(text: str) -> str:
    compact = " ".join((text or "").split()).strip()
    if not compact:
        return ""
    compact = compact.replace(" - [", "\n- [")
    return compact


def _markdown_to_html(markdown_text: str) -> str:
    """Convert markdown text to HTML with safe rendering.
    
    Uses markdown library with extensions for:
    - Extra formatting (tables, footnotes, etc.)
    - Code highlighting with classes
    - Safe HTML output
    
    Args:
        markdown_text: Raw markdown string from LLM
    
    Returns:
        HTML string with markdown rendered, wrapped in a div for styling.
        Returns empty string if input is empty or conversion fails.
    """
    if not markdown_text or not markdown_text.strip():
        return ""
    
    try:
        # Convert markdown to HTML with useful extensions
        html_content = markdown.markdown(
            markdown_text.strip(),
            extensions=['extra', 'codehilite', 'nl2br'],
            extension_configs={
                'codehilite': {
                    'css_class': 'highlight',
                    'linenums': False,
                }
            }
        )
        # Wrap in a div for styling
        return f'<div class="markdown-rendered">{html_content}</div>'
    except Exception as e:
        # Fallback: escape and return as preformatted text
        safe_text = _esc(markdown_text.strip())
        return f'<div class="markdown-rendered markdown-fallback"><pre>{safe_text}</pre></div>'


def _render_retrieved_options(retrieved_options: Any) -> str:
    if not retrieved_options:
        return ""

    blocks: list[str] = []
    if not isinstance(retrieved_options, dict):
        return "<div class='detail-text'>" + _esc(retrieved_options) + "</div>"

    def _render_option_item(item: Any) -> str:
        if not isinstance(item, dict):
            return _esc(item)
        kind = str(item.get("kind") or item.get("eleType") or item.get("type") or "").lower().strip()
        table = str(item.get("table") or "").strip()
        column = str(item.get("column") or item.get("col") or "").strip()
        value = str(item.get("value") or "").strip()
        if kind == "column" and table and column:
            return f"<code>{_esc(table)}.{_esc(column)}</code>"
        if kind == "value" and table and column and value:
            return f"<code>{_esc(value)}</code> in <code>{_esc(table)}.{_esc(column)}</code>"
        if table and column and value:
            return f"<code>{_esc(value)}</code> in <code>{_esc(table)}.{_esc(column)}</code>"
        if table and column:
            return f"<code>{_esc(table)}.{_esc(column)}</code>"
        if value:
            return f"<code>{_esc(value)}</code>"
        return _esc(item)

    columns = retrieved_options.get("columns") or {}
    seen_col = set()
    if isinstance(columns, dict):
        for column_name, options in columns.items():
            if column_name in seen_col:
                continue
            option_items = options if isinstance(options, list) else [options]
            rendered_items = [_render_option_item(opt) for opt in option_items if opt is not None]
            if rendered_items:
                blocks.append(
                    "<div class='retrieved-option-group'>"
                    f"<div class='detail-label'>Column <u>{_esc(column_name)}</u> has confusing options in the database:</div>"
                    f"<ul class='detail-list'>{''.join(f'<li>{item}</li>' for item in rendered_items)}</ul>"
                    "</div>"
                )
            seen_col.add(column_name)

    values = retrieved_options.get("values") or {}
    seen_val =set()
    if isinstance(values, dict):
        for value_name, options in values.items():
            if value_name in seen_val:
                continue
            option_items = options if isinstance(options, list) else [options]
            rendered_items = [_render_option_item(opt) for opt in option_items if opt is not None]
            if rendered_items:
                blocks.append(
                    "<div class='retrieved-option-group'>"
                    f"<div class='detail-label'>Value <u>{_esc(value_name)}</u> has confusing options in the database:</div>"
                    f"<ul class='detail-list'>{''.join(f'<li>{item}</li>' for item in rendered_items)}</ul>"
                    "</div>"
                )
            seen_val.add(value_name)

    # functions = retrieved_options.get("functions") or []
    # if isinstance(functions, list) and functions:
    #     func_items = [f"<code>{_esc(func)}</code>" for func in functions if str(func).strip()]
    #     if func_items:
    #         blocks.append(
    #             "<div class='retrieved-option-group'>"
    #             "<div class='detail-label'>Potential confusing functions:</div>"
    #             f"<ul class='detail-list'>{''.join(f'<li>{item}</li>' for item in func_items)}</ul>"
    #             "</div>"
    #         )

    if not blocks:
        return ""
    return "<div class='retrieved-options'>" + "".join(blocks) + "</div>"


@dataclass
class DetailRecord:
    detail_type: DetailType
    detail_id: str = ""
    raw_action_step: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.detail_id:
            self.detail_id = _new_detail_id(self.detail_type.value.lower())

    def format_details(self, mode: str = "tech") -> str:
        return ""

    def render_html(self, mode: str = "tech") -> str:
        details = self.format_details(mode=mode)
        if not details:
            return ""
        return f"<div class='detail-block detail-{self.detail_type.value.lower()}'><pre>{_esc(details)}</pre></div>"


@dataclass
class DetailRecordUserQuestion(DetailRecord):
    question: str = ""

    def __init__(self, question: str, raw_action_step: dict[str, Any] | None = None, detail_id: str = "") -> None:
        super().__init__(detail_type=DetailType.USER_QUESTION, raw_action_step=raw_action_step, detail_id=detail_id)
        self.question = question

    def format_details(self, mode: str = "tech") -> str:
        return self.question.strip()

    def render_html(self, mode: str = "tech") -> str:
        question = self.question.strip()
        if not question:
            return ""
        return (
            "<div class='detail-block detail-user-question'>"
            "<div class='detail-label'>Question</div>"
            f"<div class='detail-text'>{_esc(question)}</div>"
            "</div>"
        )


@dataclass
class DetailRecordGetSchema(DetailRecord):
    schema_text: str = ""

    def __init__(self, schema_text: str = "", raw_action_step: dict[str, Any] | None = None, detail_id: str = "") -> None:
        super().__init__(detail_type=DetailType.GET_SCHEMA, raw_action_step=raw_action_step, detail_id=detail_id)
        self.schema_text = schema_text

    def format_details(self, mode: str = "tech") -> str:
        return ""

    def render_html(self, mode: str = "tech") -> str:
        if mode != "tech":
            return ""
        if not self.schema_text.strip():
            return ""
        preview = self.schema_text.strip()[:1200]
        suffix = "..." if len(self.schema_text.strip()) > len(preview) else ""
        return (
            "<div class='detail-block detail-get-schema'>"
            "<div class='detail-label'>Schema Preview</div>"
            f"<pre>{_esc(preview + suffix)}</pre>"
            "</div>"
        )


@dataclass
class DetailRecordExecSQL(DetailRecord):
    sql_text: str = ""
    raw_result_text: str = ""
    raw_result_html: str = ""
    raw_result: Any = None
    csv_text: str = ""
    csv_file_path: str = ""
    result_summary: str = ""
    retrieved_options: Any = field(default_factory=list)
    generated_sql_options: Any = field(default_factory=list)

    def __init__(
        self,
        sql_text: str,
        raw_result_text: str = "",
        raw_result_html: str = "",
        raw_result: Any = None,
        csv_text: str = "",
        csv_file_path: str = "",
        result_summary: str = "",
        retrieved_options: Any = None,
        generated_sql_options: Any = None,
        raw_action_step: dict[str, Any] | None = None,
        detail_id: str = "",
    ) -> None:
        super().__init__(detail_type=DetailType.SQL_GEN, raw_action_step=raw_action_step, detail_id=detail_id)
        self.sql_text = sql_text
        self.raw_result_text = raw_result_text
        self.raw_result_html = raw_result_html
        self.raw_result = raw_result
        self.csv_text = csv_text
        self.csv_file_path = csv_file_path
        self.result_summary = result_summary
        self.retrieved_options = retrieved_options or []
        self.generated_sql_options = generated_sql_options or []

    def format_details(self, mode: str = "tech") -> str:
        lines: list[str] = []
        sql_text = self.sql_text.strip()
        if sql_text:
            lines.append(f"SQL:\n{sql_text}")

        preview = (self.raw_result_text or "").strip()
        if preview and len(preview) < 1200:
            lines.append(f"Result:\n{preview}")
        else:
            if self.raw_result is not None and hasattr(self.raw_result, "empty") and not self.raw_result.empty:
                # further limit to first 3 rows if it's a large table
                limited = self.raw_result.head(3)
                preview = limited.to_markdown(index=False) if not limited.empty else "_No rows returned._"
                lines.append(f"Result:\n{preview}\n...")

            shape = self.result_summary.strip()
            if shape:
                lines.append(f"Result shape: {shape}")

            if self.csv_file_path:
                lines.append(f"CSV file: {self.csv_file_path}")

        if mode == "tech":
            if self.retrieved_options:
                lines.append(f"Retrieved options:\n{_stringify(self.retrieved_options)}")
            if self.generated_sql_options:
                lines.append(f"Generated SQL options:\n{_stringify(self.generated_sql_options)}")

        return "\n\n".join(line for line in lines if line).strip()

    def render_html(self, mode: str = "tech") -> str:
        sections: list[str] = []
        sql_text = self.sql_text.strip()
        if sql_text:
            sections.append(
                "<div class='detail-label'>SQL</div>"
                f"<pre class='sql-block'>{_esc(sql_text)}</pre>"
            )

        # Trusted HTML path for dataframe preview produced in backend code.
        result_html = (self.raw_result_html or "").strip()
        if result_html and len(result_html) < 3000:
            sections.append(
                "<div class='detail-label'>Result Preview</div>"
                f"<div class='result-table-wrap'>{result_html}</div>"
            )
        else:
            summary = self.result_summary.strip()
            if summary:
                sections.append(f"<div class='detail-text'>Result shape: {_esc(summary)}</div>")
            if self.csv_file_path:
                sections.append(
                    "<div class='detail-text'>"
                    f"CSV saved at: <code>{_esc(self.csv_file_path)}</code>"
                    "</div>"
                )

        if mode == "tech":
            rendered_options = _render_retrieved_options(self.retrieved_options)
            if rendered_options:
                sections.append(rendered_options)

            if isinstance(self.generated_sql_options, list) and self.generated_sql_options:
                sections.append("<div class='detail-label'>Generated SQL Options</div>" + _render_list([_stringify(v) for v in self.generated_sql_options]))

        if not sections:
            return ""
        return "<div class='detail-block detail-exec-sql'>" + "".join(sections) + "</div>"


@dataclass
class DetailRecordSQLGen(DetailRecord):
    sql_text: str = ""
    raw_result_text: str = ""
    raw_result_html: str = ""
    raw_result: Any = None
    csv_text: str = ""
    csv_file_path: str = ""
    result_summary: str = ""

    def __init__(
        self,
        sql_text: str,
        raw_result_text: str = "",
        raw_result_html: str = "",
        raw_result: Any = None,
        csv_text: str = "",
        csv_file_path: str = "",
        result_summary: str = "",
        retrieved_options: Any = None,
        generated_sql_options: Any = None,
        raw_action_step: dict[str, Any] | None = None,
        detail_id: str = "",
    ) -> None:
        super().__init__(detail_type=DetailType.SQL_GEN, raw_action_step=raw_action_step, detail_id=detail_id)
        self.sql_text = sql_text
        self.raw_result_text = raw_result_text
        self.raw_result_html = raw_result_html
        self.raw_result = raw_result
        self.csv_text = csv_text
        self.csv_file_path = csv_file_path
        self.result_summary = result_summary

    def format_details(self, mode: str = "tech") -> str:
        lines: list[str] = []
        sql_text = self.sql_text.strip()
        if sql_text:
            lines.append(f"SQL:\n{sql_text}")

        preview = (self.raw_result_text or "").strip()
        if preview and len(preview) < 1200:
            lines.append(f"Result:\n{preview}")
        else:
            if self.raw_result is not None and hasattr(self.raw_result, "empty") and not self.raw_result.empty:
                # further limit to first 3 rows if it's a large table
                limited = self.raw_result.head(3)
                preview = limited.to_markdown(index=False) if not limited.empty else "_No rows returned._"
                lines.append(f"Result:\n{preview}\n...")

            shape = self.result_summary.strip()
            if shape:
                lines.append(f"Result shape: {shape}")

            if self.csv_file_path:
                lines.append(f"CSV file: {self.csv_file_path}")

        return "\n\n".join(line for line in lines if line).strip()

    def render_html(self, mode: str = "tech") -> str:
        sections: list[str] = []
        sql_text = self.sql_text.strip()
        if sql_text:
            sections.append(
                "<div class='detail-label'>SQL</div>"
                f"<pre class='sql-block'>{_esc(sql_text)}</pre>"
            )

        # Trusted HTML path for dataframe preview produced in backend code.
        result_html = (self.raw_result_html or "").strip()
        if result_html and len(result_html) < 3000:
            sections.append(
                "<div class='detail-label'>Result Preview</div>"
                f"<div class='result-table-wrap'>{result_html}</div>"
            )
        else:
            summary = self.result_summary.strip()
            if summary:
                sections.append(f"<div class='detail-text'>Result shape: {_esc(summary)}</div>")
            if self.csv_file_path:
                sections.append(
                    "<div class='detail-text'>"
                    f"CSV saved at: <code>{_esc(self.csv_file_path)}</code>"
                    "</div>"
                )
        if not sections:
            return ""
        return "<div class='detail-block detail-exec-sql'>" + "".join(sections) + "</div>"

@dataclass
class DetailRecordCandGeneration(DetailRecord):
    original_sql: str = ""
    mode: str = "newCand"
    reused_from_cand_gen_id: str = ""
    candidates: list[dict[str, Any]] = field(default_factory=list)
    majority_vote_result: dict[str, Any] = field(default_factory=dict)
    execution_stats: dict[str, Any] = field(default_factory=dict)
    # Structured ambiguity entries (used by "structured" cand_gen_type path).
    # Each entry: {AmbiContext, AmbiType, InterpretationOpts: [{snippet, interpretation, full_sql}]}
    ambiguity_entries: list[dict[str, Any]] = field(default_factory=list)
    # Per-entry execution + refinement results (from DetectionEvaluator).
    # Each entry: refined options with exec_status, row_count, profile_text, rank, etc.
    per_entry_results: list[dict[str, Any]] = field(default_factory=list)

    def __init__(
        self,
        original_sql: str,
        mode: str = "newCand",
        candidates: list[dict[str, Any]] | None = None,
        majority_vote_result: dict[str, Any] | None = None,
        execution_stats: dict[str, Any] | None = None,
        reused_from_cand_gen_id: str = "",
        ambiguity_entries: list[dict[str, Any]] | None = None,
        per_entry_results: list[dict[str, Any]] | None = None,
        raw_action_step: dict[str, Any] | None = None,
        detail_id: str = "",
    ) -> None:
        super().__init__(detail_type=DetailType.CAND_GEN, raw_action_step=raw_action_step, detail_id=detail_id)
        self.original_sql = original_sql
        self.mode = mode
        self.reused_from_cand_gen_id = reused_from_cand_gen_id
        self.candidates = list(candidates or [])
        self.majority_vote_result = majority_vote_result or {}
        self.execution_stats = execution_stats or {}
        self.ambiguity_entries = list(ambiguity_entries or [])
        self.per_entry_results = list(per_entry_results or [])

    @staticmethod
    def _cluster_sqls(cluster: dict[str, Any]) -> list[str]:
        sqls = cluster.get("SQLs")
        if isinstance(sqls, list):
            cleaned = [str(item).strip() for item in sqls if str(item).strip()]
            if cleaned:
                return cleaned
        legacy = cluster.get("sqls_with_results") or []
        if isinstance(legacy, list):
            return [str(item.get("sql") or "").strip() for item in legacy if isinstance(item, dict) and str(item.get("sql") or "").strip()]
        return []

    @staticmethod
    def _cluster_shared_results(cluster: dict[str, Any]) -> Any:
        return cluster.get("shared_results") if isinstance(cluster, dict) else None

    @staticmethod
    def _cluster_shared_summary(cluster: dict[str, Any]) -> str:
        return str(
            cluster.get("shared_result_summary")
            or cluster.get("shared_summary")
            or cluster.get("res_summary")
            or ""
        ).strip()

    @staticmethod
    def _result_to_dataframe(shared_results: dict[str, Any] | None) -> pd.DataFrame | None:
        """Convert shared_results dict (from majority_vote) to pandas DataFrame.
        
        Returns DataFrame or None if conversion fails.
        """
        if not shared_results or not isinstance(shared_results, dict):
            return None
        
        result_data = shared_results.get("result")
        column_names = shared_results.get("column_names")
        
        if not result_data:
            return None
        
        try:
            if isinstance(result_data, list):
                if not result_data:
                    return None
                
                # Infer column names if not provided
                if not column_names:
                    if isinstance(result_data[0], (list, tuple)):
                        num_cols = len(result_data[0])
                        column_names = [f"col{i+1}" for i in range(num_cols)]
                    else:
                        column_names = ["value"]
                
                df = pd.DataFrame(result_data, columns=column_names)
                return df if not df.empty else None
            
            return None
        except Exception:
            return None

    @staticmethod
    def _get_cluster_profile_text(cluster: dict[str, Any]) -> str | None:
        """Get df_profile_markdown output for a cluster's shared_results.
        
        Returns formatted profile text or None.
        """
        shared_results = cluster.get("shared_results") if isinstance(cluster, dict) else None
        if not shared_results or not isinstance(shared_results, dict):
            return None
        
        df = DetailRecordCandGeneration._result_to_dataframe(shared_results)
        if df is None:
            return None
        
        try:
            return df_profile_markdown(df)
        except Exception:
            return None

    def format_details(self, mode: str = "tech") -> str:
        lines: list[str] = []
        if self.original_sql:
            lines.append(f"Original SQL:\n{self.original_sql}")
        if self.mode:
            lines.append(f"Mode: {self.mode}")
        if self.reused_from_cand_gen_id:
            lines.append(f"Reused from CAND_GEN node: {self.reused_from_cand_gen_id}")

        mv = self.majority_vote_result or {}
        clusters = mv.get("clusters") or []
        if clusters:
            cluster_blocks: list[str] = []
            for idx, cluster in enumerate(clusters):
                if not isinstance(cluster, dict):
                    continue
                rank = cluster.get("rnk", idx + 1)
                sqls = self._cluster_sqls(cluster)
                shared_summary = self._cluster_shared_summary(cluster)
                
                # Add header
                header = f"  Cluster {idx + 1} ({len(sqls)} candidate{'s' if len(sqls) != 1 else ''})"
                cluster_blocks.append(header)
                
                # Add enhanced profile if available
                profile_text = self._get_cluster_profile_text(cluster)
                if profile_text:
                    # Indent profile text for readability
                    profile_indented = "\n".join(f"    {line}" for line in profile_text.split("\n"))
                    cluster_blocks.append(profile_indented)
                elif shared_summary:
                    cluster_blocks.append(f"    {shared_summary}")
                
                # Add SQL list
                for s in sqls:
                    truncated = s[:120] + ("..." if len(s) > 120 else "")
                    cluster_blocks.append(f"    - {truncated}")
            
            lines.append("Result clusters:\n" + "\n".join(cluster_blocks))
        # Structured ambiguity entries (cand_gen_type="structured" path)
        if self.ambiguity_entries:
            lines.append("--- Structured Ambiguity Entries ---")
            for idx, entry in enumerate(self.ambiguity_entries, 1):
                ctx = entry.get("AmbiContext", "")
                atype = entry.get("AmbiType", "")
                opts = entry.get("InterpretationOpts", [])
                lines.append(f"  Entry {idx}: '{ctx}' ({atype})")
                for oi, opt in enumerate(opts, 1):
                    snip = opt.get("snippet", "")[:80]
                    interp = opt.get("interpretation", "")[:80]
                    lines.append(f"    Opt {oi}: snippet={snip}, interp={interp}")

            # Per-entry execution results
            if self.per_entry_results:
                lines.append("  --- Execution Results ---")
                for idx, result in enumerate(self.per_entry_results, 1):
                    ctx = result.get("AmbiContext", "")[:40]
                    ref_log = result.get("refinement_log", "")
                    opts = result.get("options", [])
                    statuses = ", ".join(
                        f"Opt{oi}: {o.get('exec_status','?')}({o.get('row_count',0)} rows)"
                        for oi, o in enumerate(opts, 1)
                    )
                    lines.append(f"  Entry {idx}: '{ctx}' | {statuses}")
                    if ref_log:
                        lines.append(f"    {ref_log}")

        if self.execution_stats:
            lines.append(f"Execution stats: {json.dumps(self.execution_stats, ensure_ascii=False)}")
        return "\n\n".join(line for line in lines if line).strip()

    def render_html(self, mode: str = "tech") -> str:
        """Render candidates grouped by cluster with shared execution results."""
        sections: list[str] = []
        
        if self.original_sql:
            sections.append(
                "<div class='detail-label'>Original SQL</div>"
                f"<pre class='sql-block'>{_esc(self.original_sql)}</pre>"
            )
        
        sections.append(f"<div class='detail-text'>Mode: {_esc(self.mode)}</div>")
        
        if self.reused_from_cand_gen_id:
            sections.append(f"<div class='detail-text'>Reused from: <code>{_esc(self.reused_from_cand_gen_id)}</code></div>")
        
        # Render candidates grouped by cluster with shared execution results
        mv = self.majority_vote_result or {}
        clusters = mv.get("clusters") or []
        
        if clusters:
            for cluster_idx, cluster in enumerate(clusters):
                cluster_rank = cluster.get("rnk", cluster_idx + 1) if isinstance(cluster, dict) else cluster_idx + 1
                sqls = self._cluster_sqls(cluster) if isinstance(cluster, dict) else []
                shared_results = self._cluster_shared_results(cluster) if isinstance(cluster, dict) else None
                shared_summary = self._cluster_shared_summary(cluster) if isinstance(cluster, dict) else ""
                
                # Render cluster header
                sections.append(
                    f"<div class='detail-label'>Cluster {cluster_rank} ({len(sqls)} candidate{'s' if len(sqls) != 1 else ''})</div>"
                )
                
                # Render profile section if available
                profile_text = self._get_cluster_profile_text(cluster) if isinstance(cluster, dict) else None
                if profile_text:
                    # Render profile as formatted markdown-like text
                    profile_html = f"<div class='detail-text' style='margin-left: 20px; margin-top: 8px; font-family: monospace; font-size: 0.9em;'><b>Data Profile:</b><pre style='background: #f5f5f5; padding: 8px; border-radius: 4px;'>{_esc(profile_text)}</pre></div>"
                    sections.append(profile_html)
                
                # Render shared result section (once per cluster)
                if not isinstance(shared_results, dict) or shared_results.get("status") == "error":
                    # Error case
                    error_msg = shared_summary or (shared_results.get("result_summary") if isinstance(shared_results, dict) else "Unknown error")
                    sections.append(
                        f"<div class='detail-text' style='color: red;'><b>Result:</b> {_esc(error_msg)}</div>"
                    )
                else:
                    # Success case - render result table
                    result_data = shared_results.get("result")
                    column_names = shared_results.get("column_names", [])
                    
                    if isinstance(result_data, list) and result_data:
                        try:
                            # Convert result rows to HTML table
                            rows = result_data
                            cols = column_names if column_names else [f"col{i}" for i in range(len(rows[0]) if isinstance(rows[0], (list, tuple)) else 1)]
                            
                            # Limit to first 20 rows for display
                            display_rows = rows[:20]
                            total_rows = len(rows)
                            
                            table_html = "<div style='margin-left: 20px; margin-top: 8px; margin-bottom: 8px;'>"
                            table_html += "<b>Result:</b>"
                            table_html += "<table style='border-collapse: collapse; margin-top: 5px; font-size: 0.9em;'>"
                            table_html += "<tr style='background-color: #f0f0f0;'>"
                            
                            for col in cols:
                                table_html += f"<th style='border: 1px solid #ddd; padding: 6px;'>{_esc(str(col))}</th>"
                            
                            table_html += "</tr>"
                            
                            for row in display_rows:
                                table_html += "<tr>"
                                if isinstance(row, (list, tuple)):
                                    for cell in row:
                                        cell_str = str(cell) if cell is not None else "NULL"
                                        table_html += f"<td style='border: 1px solid #ddd; padding: 6px;'>{_esc(cell_str)}</td>"
                                else:
                                    table_html += f"<td style='border: 1px solid #ddd; padding: 6px;'>{_esc(str(row))}</td>"
                                table_html += "</tr>"
                            
                            if total_rows > 20:
                                table_html += f"<tr><td colspan='{len(cols)}' style='padding: 8px; font-style: italic; text-align: center; background-color: #f9f9f9;'>... and {total_rows - 20} more rows</td></tr>"
                            
                            table_html += "</table></div>"
                            sections.append(table_html)
                        except Exception as e:
                            sections.append(f"<div style='color: red; margin-left: 20px;'><b>Result:</b> Error rendering table: {_esc(str(e))}</div>")
                    else:
                        # Empty result or summary only
                        sections.append(
                            f"<div class='detail-text' style='margin-left: 20px;'><b>Result:</b> {_esc(shared_summary)}</div>"
                        )
                
                # Render SQL list section
                sections.append(
                    "<div class='detail-text' style='margin-left: 20px; margin-top: 8px;'><b>SQLs:</b></div>"
                )
                
                sql_list_html = "<ul style='margin-left: 35px; margin-top: 4px;'>"
                for sql_idx, sql_text in enumerate(sqls, 1):
                    sql_display = sql_text[:120] + ("..." if len(sql_text) > 120 else "")
                    sql_list_html += f"<li style='margin-bottom: 4px;'><code style='font-size: 0.85em;'>{_esc(sql_display)}</code></li>"
                
                sql_list_html += "</ul>"
                sections.append(sql_list_html)

        # Structured ambiguity entries (cand_gen_type="structured" path)
        if self.ambiguity_entries:
            sections.append("<div style='margin-top:12px'><div class='detail-label'>Structured Ambiguity Entries</div></div>")
            for idx, entry in enumerate(self.ambiguity_entries, 1):
                ctx = entry.get("AmbiContext", "")
                atype = entry.get("AmbiType", "")
                opts = entry.get("InterpretationOpts", [])
                sections.append(
                    f"<div class='detail-text' style='margin-top:6px'><b>Entry {idx}:</b> "
                    f"<i>{_esc(ctx)}</i> ({_esc(atype)}) — {len(opts)} option(s)</div>"
                )
                # Check if we have per-entry execution results for this entry
                exec_result = self.per_entry_results[idx - 1] if idx - 1 < len(self.per_entry_results) else None
                if exec_result:
                    ref_log = exec_result.get("refinement_log", "")
                    if ref_log:
                        sections.append(
                            f"<div class='detail-text' style='margin-left:16px;color:#666;font-style:italic'>{_esc(ref_log)}</div>"
                        )
                for oi, opt in enumerate(opts, 1):
                    snip = opt.get("snippet", "")
                    interp = opt.get("interpretation", "")
                    fsql = opt.get("full_sql", "")
                    # Check execution result if available
                    exec_info = ""
                    if exec_result:
                        er_opts = exec_result.get("options", [])
                        if oi - 1 < len(er_opts):
                            eo = er_opts[oi - 1]
                            status = eo.get("exec_status", "")
                            rows = eo.get("row_count", 0)
                            color = "green" if status == "success" else "red"
                            exec_info = f" <span style='color:{color}'>({status}, {rows} rows)</span>"
                    sections.append(
                        f"<div style='margin-left:20px;margin-top:4px'>"
                        f"<b>Opt {oi}:</b> <code>{_esc(snip)}</code> — {_esc(interp)}{exec_info}</div>"
                    )
                    if fsql and len(fsql) < 200:
                        sections.append(
                            f"<pre style='margin-left:24px;font-size:0.85em'>{_esc(fsql)}</pre>"
                        )

        return "<div class='detail-block detail-cand-gen'>" + "".join(sections) + "</div>"


@dataclass
class DetailRecordPairAmbiDetect(DetailRecord):
    pair_id: str = ""
    left_cluster_label: str = ""
    right_cluster_label: str = ""
    comparison_report: str = ""
    ambiguity_entries: list[dict[str, Any]] = field(default_factory=list)

    def __init__(
        self,
        pair_id: str,
        left_cluster_label: str,
        right_cluster_label: str,
        comparison_report: str,
        ambiguity_entries: list[dict[str, Any]] | None = None,
        raw_action_step: dict[str, Any] | None = None,
        detail_id: str = "",
    ) -> None:
        super().__init__(detail_type=DetailType.AMBI_DETECT, raw_action_step=raw_action_step, detail_id=detail_id)
        self.pair_id = pair_id
        self.left_cluster_label = left_cluster_label
        self.right_cluster_label = right_cluster_label
        self.comparison_report = comparison_report
        self.ambiguity_entries = list(ambiguity_entries or [])

    def format_details(self, mode: str = "tech") -> str:
        lines = [
            f"Pair: {self.left_cluster_label} vs {self.right_cluster_label}",
            f"Comparison report:\n{self.comparison_report.strip()}" if self.comparison_report.strip() else "",
            f"Ambiguity entries:\n{_stringify(self.ambiguity_entries)}" if self.ambiguity_entries else "",
        ]
        return "\n\n".join(line for line in lines if line).strip()

    def render_html(self, mode: str = "tech") -> str:
        sections = [
            "<div class='detail-label'>Pairwise Detection</div>",
            f"<div class='detail-text'><code>{_esc(self.left_cluster_label)}</code> vs <code>{_esc(self.right_cluster_label)}</code></div>",
        ]
        if self.comparison_report.strip():
            sections.append(f"<pre>{_esc(self.comparison_report.strip())}</pre>")
        if self.ambiguity_entries:
            entries_html = []
            for entry in self.ambiguity_entries:
                ctx = _esc(str(entry.get("AmbiContext") or entry.get("ambiguity_context") or "")).strip()
                atype = _esc(str(entry.get("AmbiType") or entry.get("ambiguity_type") or "")).strip()
                header = f"<b>AmbiContext:</b> {ctx}" if ctx else ""
                if atype:
                    header += f" | <b>AmbiType:</b> {atype}" if header else f"<b>AmbiType:</b> {atype}"
                raw_opts = entry.get("Options") or entry.get("options") or entry.get("AmbiOpts") or []
                opt_lines = []
                for opt in raw_opts:
                    if isinstance(opt, dict):
                        snip = str(opt.get("snippet") or "").strip()
                        interp = str(opt.get("interpretation") or "").strip()
                        opt_text = f"{snip} -- {interp}" if snip and interp else (snip or interp)
                    elif isinstance(opt, (list, tuple)):
                        snip = str(opt[0]).strip() if len(opt) > 0 else ""
                        interp = str(opt[1]).strip() if len(opt) > 1 else ""
                        opt_text = f"{snip} -- {interp}" if snip and interp else (snip or interp)
                    else:
                        opt_text = str(opt).strip()
                    if opt_text:
                        opt_lines.append(f"<li>&bull; {_esc(opt_text)}</li>")
                if header:
                    entries_html.append(f"<div class='detail-text' style='margin-top:6px'>{header}</div>")
                if opt_lines:
                    entries_html.append(f"<ul class='detail-list' style='margin:2px 0 4px 20px'>{''.join(opt_lines)}</ul>")
            if entries_html:
                sections.append("<div class='detail-entries'>" + "".join(entries_html) + "</div>")
        return "<div class='detail-block detail-ambi-detect'>" + "".join(sections) + "</div>"


@dataclass
class DetailRecordScoredAmbiEntry(DetailRecord):
    ambiguity_context: str = ""
    ambiguity_context_descrip: str = ""
    ambi_type: str = ""
    options: list[dict[str, Any]] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)
    justification: str = ""
    manager_rationale: str = ""
    evaluator_justification: str = ""
    question_format: str = "spec_multi_choices"
    preselect_option_idxs: list[int] = field(default_factory=list)
    source_pair_ids: list[str] = field(default_factory=list)
    entropy: float | None = None
    score_gap: float | None = None
    is_fixed: bool = False
    fixed_by: str = ""
    fixed_round_id: str = ""

    def __init__(
        self,
        ambiguity_context: str,
        options: list[Any],
        scores: list[float],
        ambiguity_context_descrip: str = "",
        ambi_type: str = "",
        justification: str = "",
        manager_rationale: str = "",
        evaluator_justification: str = "",
        question_format: str = "spec_multi_choices",
        preselect_option_idxs: list[int] | None = None,
        source_pair_ids: list[str] | None = None,
        entropy: float | None = None,
        score_gap: float | None = None,
        is_fixed: bool = False,
        fixed_by: str = "",
        fixed_round_id: str = "",
        raw_action_step: dict[str, Any] | None = None,
        detail_id: str = "",
    ) -> None:
        super().__init__(detail_type=DetailType.AMBI_EVAL, raw_action_step=raw_action_step, detail_id=detail_id)
        self.ambiguity_context = ambiguity_context
        self.ambiguity_context_descrip = str(ambiguity_context_descrip or "").strip()
        self.ambi_type = str(ambi_type or "").strip()
        self.options = self._normalize_options(options or [])
        normalized_scores = [float(s) for s in (scores or [])]
        if len(normalized_scores) < len(self.options):
            normalized_scores.extend([0.0] * (len(self.options) - len(normalized_scores)))
        self.scores = normalized_scores[: len(self.options)]

        # Keep score mirrored inside each option payload for easier downstream display/debug.
        for idx, opt in enumerate(self.options):
            opt["score"] = float(self.scores[idx]) if idx < len(self.scores) else 0.0
        self.justification = justification
        self.manager_rationale = manager_rationale
        self.evaluator_justification = evaluator_justification
        self.question_format = question_format or "spec_multi_choices"
        self.preselect_option_idxs = [int(idx) for idx in (preselect_option_idxs or [])]
        self.source_pair_ids = [str(item).strip() for item in (source_pair_ids or []) if str(item).strip()]
        self.entropy = entropy
        self.score_gap = score_gap
        self.is_fixed = bool(is_fixed)
        self.fixed_by = fixed_by
        self.fixed_round_id = fixed_round_id

    @staticmethod
    def _option_text_from_payload(payload: dict[str, Any]) -> str:
        snippet = str(payload.get("snippet") or "").strip()
        interp = str(payload.get("interpretation") or "").strip()
        if snippet and interp:
            return f"{snippet} -- {interp}"
        return snippet or interp

    @classmethod
    def _normalize_options(cls, options: list[Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in options:
            if isinstance(item, dict):
                snippet = str(
                    item.get("snippet")
                    or item.get("option_content")
                    or item.get("option")
                    or item.get("content")
                    or ""
                ).strip()
                interpretation = str(
                    item.get("interpretation")
                    or item.get("option_note")
                    or item.get("note")
                    or item.get("description")
                    or ""
                ).strip()
                justification = str(item.get("justification") or "").strip()
                score_raw = item.get("score", 0.0)
                try:
                    score = float(score_raw)
                except Exception:
                    score = 0.0
                normalized.append(
                    {
                        "snippet": snippet,
                        "interpretation": interpretation,
                        "justification": justification,
                        "score": score,
                    }
                )
                continue

            text = str(item or "").strip()
            if not text:
                continue
            normalized.append(
                {
                    "snippet": text,
                    "interpretation": "",
                    "justification": "",
                    "score": 0.0,
                }
            )
        return normalized

    def option_display_texts(self) -> list[str]:
        outputs: list[str] = []
        for opt in self.options:
            text = self._option_text_from_payload(opt)
            if text:
                outputs.append(text)
        return outputs

    def top_option_index(self) -> int:
        if not self.options:
            return 0
        limit = min(len(self.options), len(self.scores))
        if limit <= 0:
            return 0
        return max(range(limit), key=lambda idx: self.scores[idx])

    def is_normalized(self, eps: float = 1e-6) -> bool:
        if not self.scores:
            return False
        total = sum(self.scores)
        return abs(total - 1.0) <= eps

    def format_details(self, mode: str = "tech") -> str:
        scored: list[str] = []
        for idx, opt in enumerate(self.options):
            score = self.scores[idx] if idx < len(self.scores) else 0.0
            label = self._option_text_from_payload(opt) or f"option {idx}"
            opt_just = str(opt.get("justification") or "").strip()
            line = f"- {label}: {score:.4f}"
            if opt_just:
                line += f"\n  justification: {opt_just}"
            scored.append(line)
        status = "fixed" if self.is_fixed else "not fixed"
        lines = [
            f"Context: {self.ambiguity_context}",
            f"Context description: {self.ambiguity_context_descrip}" if self.ambiguity_context_descrip else "",
            f"Ambiguity type: {self.ambi_type}" if self.ambi_type else "",
            f"Status: {status}",
            f"Question format: {self.question_format}",
            f"Preselected option indexes: {self.preselect_option_idxs}" if self.preselect_option_idxs else "",
            f"Entropy: {self.entropy:.4f}" if isinstance(self.entropy, (float, int)) else "",
            f"Score gap: {self.score_gap:.4f}" if isinstance(self.score_gap, (float, int)) else "",
            "Options and scores:\n" + "\n".join(scored) if scored else "",
            f"Justification:\n{self.justification.strip()}" if self.justification.strip() else "",
            f"Manager rationale:\n{self.manager_rationale.strip()}" if self.manager_rationale.strip() else "",
            f"Evaluator justification:\n{self.evaluator_justification.strip()}" if self.evaluator_justification.strip() else "",
        ]
        return "\n\n".join(line for line in lines if line).strip()

    def render_html(self, mode: str = "tech") -> str:
        opt_lines: list[str] = []
        for idx, opt in enumerate(self.options):
            score = self.scores[idx] if idx < len(self.scores) else 0.0
            label = self._option_text_from_payload(opt) or f"option {idx}"
            opt_lines.append(f"<div class='detail-text' style='margin-left:12px'>Op{idx + 1}: <code>{_esc(label)}</code> ({_esc(f'{score:.4f}')})</div>")
        status = "Fixed" if self.is_fixed else "Open"
        status_cls = "fixed" if self.is_fixed else "open"
        meta_bits: list[str] = []
        if self.ambi_type:
            meta_bits.append(f"<b>Type:</b> {_esc(self.ambi_type)}")
        if isinstance(self.entropy, (float, int)):
            meta_bits.append(f"<b>Entropy:</b> {_esc(f'{float(self.entropy):.4f}')}")
        if isinstance(self.score_gap, (float, int)):
            meta_bits.append(f"<b>Score gap:</b> {_esc(f'{float(self.score_gap):.4f}')}")
        return (
            "<div class='detail-block detail-ambi-eval'>"
            + "<div class='detail-label'>Scored Ambiguity Entry</div>"
            + f"<div class='detail-text'><b>Context:</b> {_esc(self.ambiguity_context)}</div>"
            + ("".join(opt_lines) if opt_lines else "")
            + (f"<div class='detail-text' style='margin-top:6px'>{' · '.join(meta_bits)}</div>" if meta_bits else "")
            + f"<div class='detail-text'><b>Status:</b> <span class='detail-status-{status_cls}'>{_esc(status)}</span></div>"
            + (f"<pre>{_esc(self.justification.strip())}</pre>" if self.justification.strip() else "")
            + (f"<pre>{_esc(self.manager_rationale.strip())}</pre>" if self.manager_rationale.strip() else "")
            + "</div>"
        )


@dataclass
class DetailRecordPreferenceSave(DetailRecord):
    """Record for preference base save operations.
    
    Tracks which preference entries were updated, added, or merged.
    Format:
    {
        updated_entries: [
            {
                "AmbiContext": str,
                "old_opts": [...],
                "new_opts": [...],
                "decision": "new" | "merged" | "merged_with_llm",
                "change_summary": "X options updated, Y added"
            },
            ...
        ],
        summary: "Updated X preferences: Y added, Z merged"
    }
    """
    updated_entries: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""

    def __init__(
        self,
        updated_entries: list[dict[str, Any]] | None = None,
        summary: str = "",
        raw_action_step: dict[str, Any] | None = None,
        detail_id: str = "",
    ) -> None:
        super().__init__(detail_type=DetailType.PREFERENCE_SAVE, raw_action_step=raw_action_step, detail_id=detail_id)
        self.updated_entries = updated_entries or []
        self.summary = summary

    def format_details(self, mode: str = "tech") -> str:
        lines = [self.summary.strip()] if self.summary.strip() else []
        for entry in self.updated_entries:
            ctx = str(entry.get("AmbiContext", "?")).strip()
            decision = str(entry.get("decision", "?")).strip().upper()
            change = str(entry.get("change_summary", "")).strip()
            line = f"- [{decision}] {ctx}"
            if change:
                line += f" — {change}"
            lines.append(line)
        return "\n".join(lines).strip()

    def render_html(self, mode: str = "tech") -> str:
        def _badge_style(decision: str) -> tuple[str, str]:
            d = decision.upper()
            if d == "NEW":
                return "#2d6cdf", "#eaf2ff"
            if d == "MERGED_WITH_LLM":
                return "#1f8b63", "#e9fbf3"
            return "#8a5fd3", "#f4efff"

        def _row_style(status: str) -> tuple[str, str]:
            s = status.lower()
            if s in {"incremented", "selected_new"}:
                return "#eaf9f0", "#1f8b63"
            if s == "new":
                return "#eef5ff", "#2d6cdf"
            if s == "decremented":
                return "#fff0f0", "#c43b3b"
            return "#ffffff", "#7a8598"

        lines = ["<div class='detail-block detail-pref-save'>"]
        lines.append("<div class='detail-label'>Preference Save</div>")
        if self.summary.strip():
            lines.append(f"<div class='detail-text'><b>Summary:</b> {_esc(self.summary)}</div>")

        if not self.updated_entries:
            lines.append("<div class='detail-text' style='margin-top:6px'>No preference diffs were recorded.</div>")
            lines.append("</div>")
            return "".join(lines)

        lines.append("<div style='margin-top:8px;display:grid;gap:10px'>")
        for entry in self.updated_entries:
            ctx = str(entry.get("AmbiContext") or "").strip()
            decision = str(entry.get("decision") or "").strip().upper() or "UNKNOWN"
            change_summary = str(entry.get("change_summary") or "").strip()
            badge_fg, badge_bg = _badge_style(decision)

            lines.append(
                "<div style='border:1px solid #dce4ef;border-radius:8px;background:#fff;padding:8px 10px'>"
                f"<div style='display:flex;align-items:center;justify-content:space-between;gap:8px'>"
                f"<div class='detail-text'><b>Context:</b> {_esc(ctx)}</div>"
                f"<span style='padding:2px 8px;border-radius:999px;background:{badge_bg};color:{badge_fg};font-size:11px;font-weight:700'>{_esc(decision)}</span>"
                "</div>"
            )
            if change_summary:
                lines.append(f"<div class='detail-text' style='margin-top:4px'>{_esc(change_summary)}</div>")

            opt_diffs = entry.get("option_diffs") or []
            if isinstance(opt_diffs, list) and opt_diffs:
                lines.append(
                    "<div class='result-table-wrap' style='margin-top:8px;max-height:240px'>"
                    "<table class='pref-save-table'>"
                    "<thead><tr>"
                    "<th>Option</th><th>Old</th><th>New</th><th>Change</th><th>Status</th>"
                    "</tr></thead><tbody>"
                )
                for opt in opt_diffs:
                    if not isinstance(opt, dict):
                        continue
                    status = str(opt.get("status") or "").strip()
                    row_bg, row_fg = _row_style(status)
                    snippet = str(opt.get("snippet") or "").strip()
                    interp = str(opt.get("interpretation") or "").strip()
                    old_freq = opt.get("old_freq")
                    new_freq = opt.get("new_freq")
                    delta = opt.get("delta")
                    label = snippet if not interp else f"{snippet} -- {interp}"
                    status_label = status.replace("_", " ").title() if status else "Unknown"
                    lines.append(
                        f"<tr style='background:{row_bg};color:{row_fg}'>"
                        f"<td style='vertical-align:top'><code>{_esc(label)}</code></td>"
                        f"<td style='text-align:center'>{_esc('—' if old_freq is None else old_freq)}</td>"
                        f"<td style='text-align:center;font-weight:700'>{_esc(new_freq)}</td>"
                        f"<td style='text-align:center'>{_esc('+' if isinstance(delta, (int, float)) and delta > 0 else '')}{_esc(delta)}</td>"
                        f"<td style='text-align:center'>{_esc(status_label)}</td>"
                        "</tr>"
                    )
                lines.append("</tbody></table></div>")
            lines.append("</div>")

        lines.append("</div>")
        lines.append("</div>")
        return "".join(lines)


@dataclass
class DetailRecordManagerAutoFix(DetailRecord):
    fixed_entries: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    threshold: float | None = None

    def __init__(
        self,
        fixed_entries: list[dict[str, Any]] | None = None,
        summary: str = "",
        threshold: float | None = None,
        raw_action_step: dict[str, Any] | None = None,
        detail_id: str = "",
    ) -> None:
        super().__init__(detail_type=DetailType.MANAGER_AUTO_FIX, raw_action_step=raw_action_step, detail_id=detail_id)
        self.fixed_entries = list(fixed_entries or [])
        self.summary = summary
        self.threshold = threshold

    @staticmethod
    def _option_text(option: Any) -> str:
        if isinstance(option, dict):
            snippet = str(option.get("snippet") or "").strip()
            interpretation = str(option.get("interpretation") or "").strip()
            if snippet and interpretation:
                return f"{snippet} -- {interpretation}"
            if snippet:
                return snippet
            if interpretation:
                return interpretation
            return _stringify(option)
        return str(option or "").strip()

    def format_details(self, mode: str = "tech") -> str:
        lines: list[str] = []
        if self.summary.strip():
            lines.append(self.summary.strip())
        if isinstance(self.threshold, (float, int)):
            lines.append(f"Auto-fix threshold: {float(self.threshold):.4f}")

        for idx, entry in enumerate(self.fixed_entries, start=1):
            ctx = str(entry.get("ambiguity_context") or "").strip()
            top_score = entry.get("top_score")
            selected_idx = entry.get("selected_option_index")
            selected_option = entry.get("selected_option")
            all_scores = entry.get("all_scores") or []
            entropy = entry.get("entropy")
            score_gap = entry.get("score_gap")

            block: list[str] = [f"Entry {idx}"]
            if ctx:
                block.append(f"Context: {ctx}")
            if isinstance(top_score, (float, int)):
                block.append(f"Top score: {float(top_score):.4f}")
            if selected_idx is not None:
                block.append(f"Selected option index: {selected_idx}")
            if selected_option is not None:
                block.append(f"Selected option: {self._option_text(selected_option)}")
            if isinstance(entropy, (float, int)):
                block.append(f"Entropy: {float(entropy):.4f}")
            if isinstance(score_gap, (float, int)):
                block.append(f"Score gap: {float(score_gap):.4f}")
            if isinstance(all_scores, list) and all_scores:
                block.append(f"All scores: {all_scores}")
            lines.append("\n".join(block))

        return "\n\n".join(line for line in lines if line).strip()

    def render_html(self, mode: str = "tech") -> str:
        def _badge_color(score: float | int | None) -> tuple[str, str]:
            if not isinstance(score, (float, int)):
                return "#7a8598", "#f3f5f7"
            val = float(score)
            if val >= 0.95:
                return "#0f7a3f", "#e8f8ee"
            if val >= 0.8:
                return "#2d6cdf", "#eaf2ff"
            if val >= 0.5:
                return "#b06b00", "#fff4de"
            return "#c43b3b", "#fff0f0"

        def _row_scores(scores: Any) -> str:
            if not isinstance(scores, list) or not scores:
                return "(none)"
            return ", ".join(f"{float(s):.4f}" if isinstance(s, (float, int)) else str(s) for s in scores)

        lines = ["<div class='detail-block detail-manager-auto-fix'>"]
        lines.append("<div class='detail-label'>Manager Auto Fix</div>")
        if self.summary.strip():
            lines.append(f"<div class='detail-text'><b>Summary:</b> {_esc(self.summary)}</div>")
        if isinstance(self.threshold, (float, int)):
            lines.append(f"<div class='detail-text'><b>Threshold:</b> {_esc(f'{float(self.threshold):.4f}')}</div>")

        if not self.fixed_entries:
            lines.append("<div class='detail-text' style='margin-top:6px'>No auto-fix entries were recorded.</div>")
            lines.append("</div>")
            return "".join(lines)

        lines.append("<div style='margin-top:8px;display:grid;gap:10px'>")
        for idx, entry in enumerate(self.fixed_entries, start=1):
            ctx = str(entry.get("ambiguity_context") or "").strip()
            top_score = entry.get("top_score")
            selected_idx = entry.get("selected_option_index")
            selected_option = entry.get("selected_option")
            all_scores = entry.get("all_scores") or []
            entropy = entry.get("entropy")
            score_gap = entry.get("score_gap")
            score_fg, score_bg = _badge_color(top_score if isinstance(top_score, (float, int)) else None)

            lines.append(
                "<div style='border:1px solid #dce4ef;border-radius:8px;background:#fff;padding:8px 10px'>"
                f"<div style='display:flex;align-items:center;justify-content:space-between;gap:8px'>"
                f"<div class='detail-text'><b>Entry {idx}</b></div>"
                f"<span style='padding:2px 8px;border-radius:999px;background:{score_bg};color:{score_fg};font-size:11px;font-weight:700'>"
                f"Top {_esc(f'{float(top_score):.4f}' if isinstance(top_score, (float, int)) else 'n/a')}"
                "</span>"
                "</div>"
            )
            if ctx:
                lines.append(f"<div class='detail-text' style='margin-top:4px'><b>Context:</b> {_esc(ctx)}</div>")
            if selected_idx is not None:
                lines.append(f"<div class='detail-text'><b>Selected option index:</b> {_esc(selected_idx)}</div>")
            if selected_option is not None:
                lines.append(
                    f"<div class='detail-text'><b>Selected option:</b> <code>{_esc(self._option_text(selected_option))}</code></div>"
                )
            if isinstance(entropy, (float, int)):
                lines.append(f"<div class='detail-text'><b>Entropy:</b> {_esc(f'{float(entropy):.4f}')}</div>")
            if isinstance(score_gap, (float, int)):
                lines.append(f"<div class='detail-text'><b>Score gap:</b> {_esc(f'{float(score_gap):.4f}')}</div>")
            if isinstance(all_scores, list) and all_scores:
                lines.append(f"<div class='detail-text'><b>All scores:</b> {_esc(_row_scores(all_scores))}</div>")
            lines.append("</div>")

        lines.append("</div>")
        lines.append("</div>")
        return "".join(lines)


@dataclass
class DetailRecordFinalAnswer(DetailRecord):
    answer: str = ""

    def __init__(self, answer: str, raw_action_step: dict[str, Any] | None = None, detail_id: str = "") -> None:
        super().__init__(detail_type=DetailType.FINAL_ANSWER, raw_action_step=raw_action_step, detail_id=detail_id)
        self.answer = answer

    def format_details(self, mode: str = "tech", raw_res_mode="html") -> str:
        return self.answer.strip()

    def render_html(self, mode: str = "tech") -> str:
        answer = self.answer.strip()
        if not answer:
            return ""
        return (
            "<div class='detail-block detail-final-answer'>"
            "<div class='detail-label'>Final Answer</div>"
            f"<div class='detail-text'>{_esc(answer)}</div>"
            "</div>"
        )


@dataclass
class DetailRecordManagerStep(DetailRecord):
    manager_mode: str = ""
    content: str = ""
    set_attended_node_ids: list[str] = field(default_factory=list)
    read_round_ids: list[str] = field(default_factory=list)
    read_node_ids: list[str] = field(default_factory=list)

    def __init__(
        self,
        manager_mode: str,
        content: str,
        set_attended_node_ids: list[str] | None = None,
        read_round_ids: list[str] | None = None,
        read_node_ids: list[str] | None = None,
        raw_action_step: dict[str, Any] | None = None,
        detail_id: str = "",
    ) -> None:
        super().__init__(detail_type=DetailType.MANAGER_STEP, raw_action_step=raw_action_step, detail_id=detail_id)
        self.manager_mode = manager_mode
        self.content = content
        self.set_attended_node_ids = list(set_attended_node_ids or [])
        self.read_round_ids = list(read_round_ids or [])
        self.read_node_ids = list(read_node_ids or [])

    def format_details(self, mode: str = "tech") -> str:
        lines: list[str] = []
        if self.content.strip():
            lines.append(self.content.strip())
        if self.set_attended_node_ids:
            lines.append(f"Set attended node IDs: {', '.join(self.set_attended_node_ids)}")
        if mode == "tech":
            if self.read_round_ids:
                lines.append(f"Read round IDs: {', '.join(self.read_round_ids)}")
            if self.read_node_ids:
                lines.append(f"Read node IDs: {', '.join(self.read_node_ids)}")
        return "\n\n".join(lines).strip()

    def render_html(self, mode: str = "tech") -> str:
        content = self.content.strip()
        sections: list[str] = []
        if content:
            # Render LLM content as markdown for better readability
            content_html = _markdown_to_html(content)
            sections.append(
                "<div class='detail-label'>Manager Output</div>"
                f"<div class='detail-text'>{content_html}</div>"
            )
        if self.set_attended_node_ids:
            sections.append(
                "<div class='detail-label'>Set Attended Node IDs</div>"
                f"<div class='detail-text'>{_esc(', '.join(self.set_attended_node_ids))}</div>"
            )
        if mode == "tech":
            if self.read_round_ids:
                sections.append(
                    "<div class='detail-label'>Read Round IDs</div>"
                    f"<div class='detail-text'>{_esc(', '.join(self.read_round_ids))}</div>"
                )
            if self.read_node_ids:
                sections.append(
                    "<div class='detail-label'>Read Node IDs</div>"
                    f"<div class='detail-text'>{_esc(', '.join(self.read_node_ids))}</div>"
                )
        if not sections:
            return ""
        return "<div class='detail-block detail-manager-step'>" + "".join(sections) + "</div>"


def detail_records_to_node_type(detail_records: list[DetailRecord]) -> NodeType:
    if not detail_records:
        return NodeType.MIXTURE

    unique_types = {record.detail_type for record in detail_records}
    if len(unique_types) > 1:
        return NodeType.MIXTURE

    detail_type = next(iter(unique_types))
    if detail_type == DetailType.USER_QUESTION:
        return NodeType.USER_QUESTION
    if detail_type == DetailType.SQL_GEN:
        return NodeType.SQL_GEN
    if detail_type == DetailType.CAND_GEN:
        return NodeType.CAND_GEN
    if detail_type == DetailType.AMBI_DETECT:
        return NodeType.AMBI_DETECT
    if detail_type == DetailType.AMBI_EVAL:
        return NodeType.AMBI_EVAL
    if detail_type == DetailType.EXEC_SQL:
        return NodeType.SQL_GEN
    return NodeType.MIXTURE


@dataclass
class NodeRecord:
    node_id: str
    round_id: str
    step_index: int
    node_type: NodeType
    title: str
    summary: str
    details: str = ""
    reasoning: str = ""
    parents: list[str] = field(default_factory=list)
    detail_records: list[DetailRecord] = field(default_factory=list)
    being_selected: bool = False
    is_selectable: bool = True
    has_potential_issue: bool = False
    issue_status_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Set `is_selectable` automatically based on node type."""
        try:
            self.is_selectable = self.node_type in get_selectable_node_types()
        except Exception:
            # Fallback: keep existing value
            self.is_selectable = bool(self.is_selectable)

    def display_title(self) -> str:
        if self.node_type in {NodeType.MANAGER_ENRICH_PROMPT, NodeType.MANAGER_SUMMARY, NodeType.MANAGER_AUTO_FIX, NodeType.COMPACT_SUMMARY}:
            return self.title.strip() or STANDARD_TITLES.get(self.node_type, self.node_type.value)
        if self.node_type == NodeType.MIXTURE:
            tool_calls = (self.metadata or {}).get("tool_calls") or []
            actions_sets: dict[str, bool] = {}
            for tc in tool_calls:
                name = str(getattr(tc, "name", tc.get("name", "")) if isinstance(tc, dict) else getattr(tc, "name", "")).strip()
                if name:
                    actions_sets[name] = True

            action_list: list[str] = []
            if actions_sets:
                if "get_schema" in actions_sets:
                    action_list.append("Schema Inspection")
                if "exec_sql" in actions_sets:
                    action_list.append("SQL Execution")
                if "final_answer" in actions_sets:
                    action_list.append("Final Answer")
            if action_list:
                return ", ".join(action_list)

        if self.title.strip():
            return self.title.strip()
        return STANDARD_TITLES.get(self.node_type, self.node_type.value)

    def build_details(self, mode: str = "tech", details_level: str = "display") -> str:
        detail_lines: list[str] = []

        if details_level == "display":
            if self.reasoning.strip() and mode == "tech":
                detail_lines.append(f"LLM reasoning:\n{self.reasoning.strip()}")
            elif self.reasoning.strip() and (is_sql_exec_like_node_type(self.node_type) or self.node_type == NodeType.MIXTURE):
                detail_lines.append(f"LLM reasoning:\n{self.reasoning.strip()}")

        if mode == "tech" and self.parents:
            detail_lines.append("Parents:\n" + ", ".join(self.parents))

        if self.issue_status_text.strip():
            detail_lines.append(f"Issue status:\n{self.issue_status_text.strip()}")

        for record in self.detail_records:
            rendered = record.format_details(mode=mode)
            if rendered:
                detail_lines.append(rendered)

        if not detail_lines and self.details.strip():
            detail_lines.append(self.details.strip())

        return "\n\n".join(detail_lines).strip()

    def _collect_scored_ambi_entries_for_frontend(self) -> str:
        """Collect scored ambiguity entries for frontend visualization.
        
        Returns empty string if node_type is not AMBI_EVAL.
        Otherwise returns JSON string with list of detail records.
        Handles exceptions gracefully.
        """
        if self.node_type != NodeType.AMBI_EVAL:
            return ""
        
        try:
            entries = []
            for record in self.detail_records:
                if isinstance(record, DetailRecordScoredAmbiEntry):
                    context_preview = record.ambiguity_context[:80] if record.ambiguity_context else ""
                    entries.append({
                        "detail_id": record.detail_id,
                        "context": context_preview,
                        "is_fixed": record.is_fixed,
                        "fixed_by": record.fixed_by
                    })
            return json.dumps(entries, ensure_ascii=False) if entries else ""
        except Exception:
            return ""

    def render_html(self, mode: str = "tech", is_selected: bool = False) -> str:
        style = make_node_style(self)
        effective_selected = self.being_selected or is_selected
        selected_cls = " chain-node-selected" if effective_selected else ""

        detail_chunks: list[str] = []
        if self.reasoning.strip() and mode == "tech":
            detail_chunks.append(
                "<div class='detail-block detail-reasoning'>"
                "<div class='detail-label'>LLM Reasoning</div>"
                f"<pre>{_esc(self.reasoning.strip())}</pre>"
                "</div>"
            )
        elif self.reasoning.strip() and (is_sql_exec_like_node_type(self.node_type) or self.node_type == NodeType.MIXTURE):
            detail_chunks.append(
                "<div class='detail-block detail-reasoning'>"
                "<div class='detail-label'>Reasoning</div>"
                f"<pre>{_esc(self.reasoning.strip())}</pre>"
                "</div>"
            )

        if mode == "tech" and self.parents:
            detail_chunks.append(
                "<div class='detail-block detail-parents'>"
                "<div class='detail-label'>Parents</div>"
                f"<div class='detail-text'>{_esc(', '.join(self.parents))}</div>"
                "</div>"
            )

        if self.issue_status_text.strip():
            issue_text = _split_issue_lines(self.issue_status_text.strip())
            detail_chunks.append(
                "<div class='detail-block detail-issue'>"
                "<div class='detail-label'>Issue Status</div>"
                f"<div class='detail-text'>{_esc(issue_text)}</div>"
                "</div>"
            )

        for record in self.detail_records:
            rendered = record.render_html(mode=mode)
            if rendered:
                detail_chunks.append(rendered)

        if not detail_chunks and self.details.strip():
            if self.node_type == NodeType.USER_SPECIFICATION:
                detail_chunks.append(
                    f"<div class='detail-block detail-specification'>{self.details.strip()}</div>"
                )
            else:
                detail_chunks.append(
                    "<div class='detail-block detail-fallback'>"
                    f"<pre>{_esc(self.details.strip())}</pre>"
                    "</div>"
                )

        summary_source = self.summary.strip() or self.details.strip() or self.display_title()
        summary = _split_issue_lines(summary_source) if is_sql_exec_like_node_type(self.node_type) else summary_source
        issue_html = (
            f"<div class='chain-node-issue'>{_esc(_split_issue_lines(self.issue_status_text.strip()))}</div>"
            if self.issue_status_text.strip()
            else ""
        )

        detail_records_json = self._collect_scored_ambi_entries_for_frontend()
        parents_json = json.dumps(self.parents, ensure_ascii=False) if self.parents else ""
        
        return (
            f"<div class='chain-node chain-node-{style}{selected_cls}' data-node-id='{_esc(self.node_id)}' "
            f"data-round-id='{_esc(self.round_id)}' data-detail-records='{html.escape(detail_records_json)}' "
            f"data-parents='{html.escape(parents_json)}' title='Click to toggle selection'>"
            "<div class='chain-node-header'>"
            f"<div class='chain-node-title'>{_esc(self.display_title())}</div>"
            "<div class='chain-node-id-wrap'>"
            f"<div class='chain-node-id'>{_esc(self.node_id)}</div>"
            + ("<span class='chain-node-pill'>Selected</span>" if effective_selected else "")
            + "</div>"
            "</div>"
            f"<div class='chain-node-summary'>{_esc(summary)}</div>"
            f"{issue_html}"
            "<div class='chain-node-hover-details'>"
            + "".join(detail_chunks)
            + "</div></div>"
        )

    def get_payload(self, mode: str = "tech", is_selected: bool = False, details_level: str = "display") -> dict[str, Any]: # details_level: str = "display" or "prompt"
        details_text = self.build_details(mode=mode, details_level=details_level)
        summary_source = self.summary.strip() or self.details.strip() or self.display_title()
        summary = _split_issue_lines(summary_source) if is_sql_exec_like_node_type(self.node_type) else summary_source
        return {
            "node_id": self.node_id,
            "round_id": self.round_id,
            "step_index": self.step_index,
            "title": self.display_title(),
            "summary": summary,
            "details": details_text,
            "issue_status_text": self.issue_status_text.strip(),
            "style": make_node_style(self),
            "is_selected": self.being_selected or is_selected,
            "node_type": self.node_type.value,
            "round_label": self.round_id,
            "is_selectable": self.is_selectable,
            "parents": list(self.parents),
        }


def make_node_style(node: NodeRecord) -> str:
    if node.node_type == NodeType.COMPACT_SUMMARY:
        return "compact-summary"
    if node.node_type in {NodeType.MANAGER_ENRICH_PROMPT, NodeType.MANAGER_SUMMARY, NodeType.MANAGER_AUTO_FIX}:
        return "manager"
    if node.node_type == NodeType.SQL_GEN:
        return "sql-gen"
    if node.node_type == NodeType.CAND_GEN:
        return "cand-gen"
    if node.node_type == NodeType.AMBI_DETECT:
        return "ambi-detect"
    if node.node_type == NodeType.AMBI_EVAL:
        return "ambi-eval"
    if node.node_type == NodeType.PREFERENCE_SAVE:
        return "preference-save"
    if node.has_potential_issue:
        return "exec-sql-issue"
    if is_sql_exec_like_node_type(node.node_type):
        return "exec-sql"
    if node.node_type == NodeType.MIXTURE:
        return "mixture"
    return "normal"
