from __future__ import annotations

from typing import Any

from config import SETTINGS
from detector.prompts import (
    build_structured_candgen_prompt,
    build_taxonomy_guidance,
    call_model_text,
    parse_structured_candgen_output,
)
from detector.sql_parser import ParsedSql, parse_sql_for_detector
from utils.logging_config import get_logger
from utils.model_factory import create_model

logger = get_logger(__name__)


class CandidateGenerator:
    """Generates structured ambiguity entries from a SQL_GEN node.

    Instead of producing flat SQL strings, the LLM outputs ambiguity entries
    directly — each with AmbiContext, AmbiType, and InterpretationOpts
    (snippet / interpretation / full_sql).
    """

    def __init__(self, index_manager: Any) -> None:
        self.index_manager = index_manager
        self.model = create_model(llm_choice="Coder")

    def generate(
        self,
        db_name: str,
        user_question: str,
        sql_text: str,
        schema_text: str,
        preferences_text: str = "",
        fixing_history: str = "",
    ) -> list[dict[str, Any]]:
        """Run the full generation pipeline.

        1. Parse SQL → extract columns, literals, functions
        2. Retrieve confusing DB options from LSH/embedding index
        3. Call LLM with structured prompt
        4. Parse response into ambiguity entries

        Returns a list of entries, each with:
          - AmbiContext: str
          - AmbiType: str
          - InterpretationOpts: [{"snippet", "interpretation", "full_sql"}, ...]
        """
        # Step 1: Parse SQL
        parsed = parse_sql_for_detector(sql_text)
        logger.info(
            "Parsed SQL: %d columns, %d literals, %d functions",
            len(parsed.columns), len(parsed.literals), len(parsed.functions),
        )

        # Step 2: Retrieve confusing options from index
        retrieved = self._retrieve_options(db_name, parsed)
        col_opts = retrieved.get("columns", {})
        val_opts = retrieved.get("values", {})

        # Flatten to list format for the prompt
        flat_col_opts = self._flatten_options(col_opts, "COLUMN")
        flat_val_opts = self._flatten_options(val_opts, "VALUE")

        # Step 3: Build structured prompt and call LLM
        prompt = build_structured_candgen_prompt(
            user_question=user_question,
            sql_text=sql_text,
            schema_text=schema_text,
            retrieved_column_options=flat_col_opts,
            retrieved_value_options=flat_val_opts,
            preferences_text=preferences_text,
            fixing_history=fixing_history,
        )

        logger.info("Structured candidate generation prompt (chars=%d)", len(prompt))
        response = call_model_text(self.model, prompt, max_tokens=49152)
        logger.info("Structured candidate generation response (chars=%d)", len(response))

        # Step 4: Parse structured output
        entries = parse_structured_candgen_output(response)
        logger.info("Parsed %d structured ambiguity entries", len(entries))

        return entries

    def _retrieve_options(self, db_name: str, parsed: ParsedSql) -> dict[str, Any]:
        """Query the index manager for confusing column/value options."""
        result: dict[str, Any] = {"columns": {}, "values": {}, "functions": parsed.functions}

        if not hasattr(self.index_manager, "query_keyword"):
            return result

        top_n = getattr(SETTINGS, "detector_lsh_top_n", 5)

        for col in parsed.columns[:12]:
            try:
                matches = self.index_manager.query_keyword(db_name, col, top_n, kind="column")
                if matches:
                    result["columns"][col] = matches
            except Exception as e:
                logger.debug("Column retrieval error for '%s': %s", col, e)

        for lit in parsed.literals[:12]:
            try:
                matches = self.index_manager.query_keyword(db_name, lit, top_n, kind="value")
                if matches:
                    result["values"][lit] = matches
            except Exception as e:
                logger.debug("Value retrieval error for '%s': %s", lit, e)

        return result

    @staticmethod
    def _flatten_options(options_dict: dict[str, list], kind: str) -> list[dict[str, Any]]:
        """Flatten column/value options dict into a list for prompt display."""
        flat: list[dict[str, Any]] = []
        seen = set()
        for key, items in options_dict.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                # Deduplicate by table+column
                table = str(item.get("table") or "").strip()
                column = str(item.get("column") or item.get("col") or "").strip()
                value = str(item.get("value") or "").strip()
                dedup_key = f"{table}.{column}.{value}"
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                entry: dict[str, Any] = {"type": kind, "table": table, "column": column}
                if value:
                    entry["value"] = value
                flat.append(entry)
        return flat
