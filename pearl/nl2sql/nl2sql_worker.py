"""Single-call NL2SQL Worker.

This module implements a direct LLM-based NL2SQL worker that generates one SQL
query per question without using smolagents. It replaces the multi-step
ToolCallingAgent approach with a simpler, single-turn LLM call pipeline:

1. Build prompt with schema + context
2. Call LLM directly to get reasoning + SQL
3. Parse and validate SQL
4. Execute SQL 
5. Emit DetailRecordSQLGen event
6. Return final answer

The worker is designed to be called by Manager in orchestration workflows
and produces SQL_GEN nodes with proper parent linkage.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from config import SETTINGS
from database.inspector import describe_sqlite_schema
from history.node_models import DetailRecordSQLGen, NodeType
from history.system_state import SystemState
from preference_learner.learner import prepare_user_preference_context
from utils.model_factory import create_model
from utils.logging_config import get_logger
from detector.prompts import call_model_text

logger = get_logger(__name__)


class NL2SQLWorker:
    """Single-shot NL2SQL worker using direct LLM call.
    
    Attributes:
        model: The LLM model instance (from create_model)
        current_db_path: Path to the currently selected SQLite database
        state: Shared SystemState used to derive user preference context
        _initial_context: Optional conversation history to inject into prompt
        _event_cb: Callback function for emitting DetailRecordSQLGen events
    """

    def __init__(self, state: SystemState | None = None) -> None:
        """Initialize worker with default model."""
        self.model = create_model(LLM_choice="Coder")
        self.current_db_path: Path | None = None
        self.state: SystemState | None = state
        self._initial_context: str = ""
        self._event_cb: Callable[[dict[str, Any]], None] | None = None

    def set_state(self, state: SystemState | None) -> None:
        """Attach the shared state used for preference lookup."""
        self.state = state

    def set_database(self, db_path: Path) -> None:
        """Set the database path for SQL execution.
        
        Args:
            db_path: Path to SQLite database file.
            
        Raises:
            FileNotFoundError: If database file does not exist.
        """
        db_path = Path(db_path) if not isinstance(db_path, Path) else db_path
        if not db_path.exists():
            raise FileNotFoundError(f"Database does not exist: {db_path}")
        self.current_db_path = db_path

    def reset_memory(self, initial_context: str = "") -> None:
        """Reset memory context for next question.
        
        Args:
            initial_context: Optional conversation history summary to inject
                           into the prompt. Will be prefixed to next prompt and
                           cleared after use.
        """
        self._initial_context = initial_context

    def run_question(
        self,
        question: str,
        event_callback: Callable[[dict[str, Any]], None],
    ) -> str:
        """Process a question and return final answer.
        
        Workflow:
        1. Build single-turn prompt with schema + context + question
        2. Call LLM to generate reasoning + SQL
        3. Parse response to extract SQL statement
        4. Execute SQL against database
        5. Emit DetailRecordSQLGen event via callback
        6. Return answer string
        
        Args:
            question: User's natural language question.
            event_callback: Callback function to receive DetailRecordSQLGen
                          event. Called once after SQL execution.
                          
        Returns:
            Final answer string with result summary. Empty string on error.
            
        Raises:
            RuntimeError: If database not set.
        """
        if not self.current_db_path:
            raise RuntimeError("Database is not selected.")

        self._event_cb = event_callback

        # Step 1: Build prompt
        prompt = self._build_prompt(question)

        logger.info("NL2SQL prompt built (len=%d)", len(prompt))

        # Step 2: Call LLM
        llm_response = self._call_llm(prompt)
        logger.info("LLM response received (len=%d)", len(str(llm_response)))
        print(f"[DEBUG] LLM response:\n{llm_response}\n", flush=True)
        reasoning = self._extract_reasoning(llm_response)
        sql_statement = self._extract_sql(llm_response)

        # Step 3-4: Execute SQL and collect results
        result_text = ""
        result_html = ""
        result_df = None
        result_summary = "Error executing SQL"

        if sql_statement:
            try:
                result_text, result_html, result_df, result_summary = (
                    self._execute_sql(sql_statement)
                )
            except Exception as e:
                result_summary = f"SQL Execution Error: {str(e)}"
                result_text = result_summary
                logger.exception("SQL execution failed: %s", e, extra={"sql": sql_statement[:200]})
        else:
            logger.warning("LLM failed to generate SQL for question (short): %s", question[:120])
            result_summary = "No SQL generated"

        # Step 5: Emit event
        self._emit_sql_gen_event(
            reasoning=reasoning,
            sql_text=sql_statement,
            raw_result_text=result_text,
            raw_result_html=result_html,
            raw_result=result_df,
            result_summary=result_summary,
        )

        # Step 6: Return answer
        return result_text

    def _build_prompt(self, question: str) -> str:
        """Build single-turn prompt with schema and context.
        
        Args:
            question: User question to append to prompt.
            
        Returns:
            Complete prompt for LLM.
            
        Raises:
            RuntimeError: If database not set.
        """
        if not self.current_db_path:
            raise RuntimeError("Database is not selected.")

        schema = describe_sqlite_schema(self.current_db_path)

        parts = [
            "You are an expert NL2SQL assistant that is execellent at understanding user questions and generating accurate SQL queries with explicitly specified columns based on the provided information.\n\n",
        ]

        # Instructions
        parts.extend([
            "# Instructions\n"
            "1. First, analyze the user's question carefully.\n"
            "2. Review the schema to understand available tables and columns, indeitify the relevant ones and determine what coloumns to use.\n"
            "3. If the User Preferences section is present, treat it as high-priority guidance when it matches the current question or ambiguity.\n"
            "4. Prefer preference-resolved interpretations over generic heuristics when they are compatible with the schema and the user's request.\n"
            "5. If preferences do not apply or conflict with the current question, fall back to schema-grounded reasoning.\n"
            "6. Generate a SELECT-only SQL query with explicit use of columns that answers the question.\n"
            "7. Return your response in this format:\n\n"
            "SQL:\n<SELECT ... FROM ...;>\n\n"
            "## Important Rules\n"
            "- **Use explicit column names**, not `*`. You will be penalized for using * when using explicit column names is possible.\n"
            "- Generate ONLY SELECT queries (no INSERT, UPDATE, DELETE).\n"
            "- Ensure the SQL is valid SQLite syntax.\n"
            "- Apply filters appropriately based on the question.\n"
            "- Respect explicit user preferences when they resolve ambiguity about tables, columns, values, joins, filters, or aggregation.\n"
            "- Do not contradict a clear user preference unless the new question clearly changes the task.\n"
            "- Return the SQL statement only once.\n\n"
        ])

        parts.append(f"---\n\n # Current Task:\n")
        parts.append(f"## User Question\n{question}\n\n")

        pref_text = self._build_preference_context_text(question)
        if pref_text:
            parts.extend([
                "## User Preferences\n",
                pref_text,
                "\n\n",
            ])

        # Embed schema
        parts.append("## Database Schema\n")
        parts.append(schema)
        parts.append("\n\n")

        return "".join(parts)

    def _build_preference_context_text(self, question: str) -> str:
        """Derive user preference text from attached shared state.

        If state or db name is unavailable, returns an empty string.
        """
        state = self.state
        if state is None or not self.current_db_path:
            return ""

        db_name = str(getattr(state, "selected_db", "") or "").strip()
        if not db_name:
            db_name = self.current_db_path.parent.name.strip()
        if not db_name:
            return ""

        try:
            pref_ctx = prepare_user_preference_context(
                state=state,
                db_name=db_name,
                ambiguity_contexts=[str(question or "").strip() or str(state.get_latest_user_question() or "").strip()],
                similarity_threshold=0.75,
            )
            return str(pref_ctx.get("preferences_text") or "").strip()
        except Exception as exc:
            logger.warning("Failed to build preference context: %s", exc)
            return ""

    def _call_llm(self, prompt: str) -> str:
        """Call LLM directly with prompt.
        
        Args:
            prompt: Prompt for LLM.
            
        Returns:
            Raw response from LLM.
        """
        try:
            # Use detector's stateless helper which handles thinking-mode
            # fallbacks and returns a plain string when possible.
            out = call_model_text(self.model, prompt, max_tokens=2048)

            if isinstance(out, str):
                return out

            # Defensive coercion: try common attributes then fallback to str()
            content = getattr(out, "content", None)
            if content is not None:
                return str(content)
            raw = getattr(out, "raw", None)
            if raw is not None:
                try:
                    # Attempt to read common nested fields
                    msg = raw.choices[0].message
                    if getattr(msg, "content", None):
                        return str(msg.content)
                    reasoning = getattr(msg, "reasoning", None)
                    if reasoning:
                        return str(reasoning)
                except Exception:
                    pass

            # Final fallback
            return str(out)
        except Exception as e:
            logger.error("LLM call failed: %s", e, extra={"prompt": prompt[:200]})
            raise RuntimeError(f"LLM call failed: {e}") from e

    @staticmethod
    def _extract_reasoning(response: str) -> str:
        """Extract reasoning section from LLM response.
        
        Looks for "REASONING:" marker and extracts text until next section
        or SQL marker.
        
        Args:
            response: Raw LLM response.
            
        Returns:
            Extracted reasoning text, or empty string if not found.
        """
        if "REASONING:" not in response:
            return ""

        try:
            reasoning_start = response.index("REASONING:") + len("REASONING:")
            # Find end of reasoning (before SQL: marker or end of string)
            sql_start = response.find("SQL:", reasoning_start)
            if sql_start == -1:
                reasoning_text = response[reasoning_start:]
            else:
                reasoning_text = response[reasoning_start:sql_start]

            return reasoning_text.strip()
        except Exception:
            return ""

    @staticmethod
    def _extract_sql(response: str) -> str:
        """Extract SQL statement from LLM response.
        
        Looks for "SQL:" marker and extracts SELECT query.
        
        Args:
            response: Raw LLM response.
            
        Returns:
            Extracted SQL statement, or empty string if not found.
        """
        if "SQL:" not in response:
            # Fallback: try to find first SELECT statement
            if "SELECT" in response.upper():
                try:
                    sel_idx = response.upper().index("SELECT")
                    sql_end = response.find(";", sel_idx)
                    if sql_end == -1:
                        sql_end = len(response)
                    else:
                        sql_end += 1
                    return response[sel_idx:sql_end].strip()
                except Exception:
                    return ""
            return ""

        try:
            sql_start = response.index("SQL:") + len("SQL:")
            # Extract text after SQL: until semicolon or end
            remaining = response[sql_start:].strip()

            # Remove markdown code blocks if present
            if remaining.startswith("```"):
                remaining = remaining[3:]
                if remaining.startswith("sql"):
                    remaining = remaining[3:]
            remaining = remaining.lstrip()

            # Find end of SQL statement (semicolon or end of response)
            sql_end = remaining.find(";")
            if sql_end == -1:
                sql_statement = remaining
            else:
                sql_statement = remaining[: sql_end + 1]

            # Remove trailing markdown block marker if present
            if "```" in sql_statement:
                sql_statement = sql_statement[: sql_statement.index("```")]

            sql_statement = sql_statement.strip()

            # Validate basic SELECT structure
            if not re.match(r"^\s*SELECT\b", sql_statement, re.IGNORECASE):
                return ""

            return sql_statement
        except Exception:
            return ""

    def _execute_sql(
        self, sql: str
    ) -> tuple[str, str, pd.DataFrame | None, str]:
        """Execute SQL query and return results.
        
        Args:
            sql: SQL query to execute.
            
        Returns:
            Tuple of (result_text, result_html, result_dataframe, summary).
                - result_text: Markdown formatted result
                - result_html: HTML table (truncated if large)
                - result_dataframe: Full dataframe
                - summary: "N rows × M columns" summary
                
        Raises:
            ValueError: If SQL is not SELECT-only or database not set.
            sqlite3.Error: If SQL execution fails.
        """
        if not self.current_db_path:
            raise ValueError("Database is not selected.")

        # Validate SELECT-only
        cleaned = sql.strip().rstrip(";")
        if not re.match(r"^\s*SELECT\b", cleaned, flags=re.IGNORECASE):
            raise ValueError("Only SELECT queries are allowed.")

        # Execute query
        conn = sqlite3.connect(str(self.current_db_path))
        try:
            df = pd.read_sql_query(cleaned, conn)
        finally:
            conn.close()

        # Generate result representations
        max_rows = 200
        limited = df.head(max_rows)
        markdown = (
            limited.to_markdown(index=False)
            if not limited.empty
            else "_No rows returned._"
        )
        html_table = limited.to_html(index=False, escape=False)
        csv_text = df.to_csv(index=False)
        result_summary = f"{len(df)} rows x {len(df.columns)} columns"

        # Optionally save to temp file
        csv_file_path = ""
        if SETTINGS.save_temp_exec:
            stem = "exec_result"
            csv_file = (
                SETTINGS.temp_exec_dir
                / f"{stem}_{abs(hash(cleaned))}.csv"
            )
            csv_file.write_text(csv_text, encoding="utf-8")
            csv_file_path = str(csv_file)

        result_text = f"Returned {len(df)} rows.\n{markdown}"

        return result_text, html_table, df, result_summary

    def _emit_sql_gen_event(
        self,
        reasoning: str,
        sql_text: str,
        raw_result_text: str,
        raw_result_html: str,
        raw_result: pd.DataFrame | None,
        result_summary: str,
    ) -> None:
        """Emit DetailRecordSQLGen event via callback.
        
        Args:
            reasoning: LLM reasoning about SQL generation.
            sql_text: Generated SQL statement.
            raw_result_text: Markdown formatted result.
            raw_result_html: HTML table result.
            raw_result: Pandas dataframe result.
            result_summary: Summary string ("N rows x M columns").
        """
        if not self._event_cb:
            return

        # Prepare CSV for event
        csv_text = ""
        csv_file_path = ""
        if raw_result is not None:
            csv_text_full = raw_result.to_csv(index=False)
            if SETTINGS.save_temp_exec:
                stem = "exec_result"
                csv_file = (
                    SETTINGS.temp_exec_dir
                    / f"{stem}_{abs(hash(sql_text))}.csv"
                )
                csv_file.write_text(csv_text_full, encoding="utf-8")
                csv_file_path = str(csv_file)
            else:
                csv_text = csv_text_full

        # Build event dict with DetailRecordSQLGen fields
        event = {
            "node_type": NodeType.SQL_GEN.value,
            "detail_type": NodeType.SQL_GEN.value,
            "title": "SQL Generation",
            "summary": sql_text or "(No SQL generated)",
            "reasoning": reasoning,
            "details": (
                f"Reasoning:\n{reasoning}\n\n"
                f"SQL:\n{sql_text}\n\n"
                f"Result:\n{raw_result_text}"
            ),
            "detail_records": [
                DetailRecordSQLGen(
                    sql_text=sql_text,
                    raw_result_text=raw_result_text,
                    raw_result_html=raw_result_html,
                    raw_result=raw_result,
                    csv_text=csv_text,
                    csv_file_path=csv_file_path,
                    result_summary=result_summary
                )
            ],
            "parents": [],  # Will be set by Manager/app callback
            "parent_ids": [],  # Backward compatibility for older receivers
        }

        self._event_cb(event)
