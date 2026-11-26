from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import threading
from typing import Any

import pandas as pd

from config import SETTINGS
from detector.candidate_generator import CandidateGenerator
from detector.detection_evaluator import DetectionEvaluator
from detector.lsh_index import LSHIndexManager
from detector.prompts import (
    build_sql_options_prompt,
    build_pairwise_ambiguity_prompt,
    build_taxonomy_guidance,
    call_model_text,
    parse_pairwise_ambiguity_output,
    parse_sql_options_json,
)
from database.inspector import describe_sqlite_schema, get_db_file
from detector.sql_parser import ParsedSql, parse_sql_for_detector
from history.node_models import (
    DetailRecordExecSQL,
    DetailRecordSQLGen,
    DetailRecordCandGeneration,
    DetailRecordPairAmbiDetect,
    NodeType,
)
from utils.model_factory import create_model
from utils.logging_config import get_logger
from utils.profile import df_profile_markdown

logger = get_logger(__name__)

from detector.majority_vote import perform_majority_vote
from preference_learner.learner import prepare_user_preference_context

MAX_THREAD = 1

@dataclass
class DetectorContext:
    db_name: str
    user_question: str
    current_round_steps: str
    previous_summary: str
    reasoning: str
    preferences_text: str = ""


def _create_index_manager():
    """Factory to create appropriate index manager based on similarity measure config."""
    if SETTINGS.similarity_measure == "embedding_cosine":
        from detector.embed_index import EmbedIndexManager
        return EmbedIndexManager()
    else:
        return LSHIndexManager()


class IssueDetector:
    def __init__(self) -> None:
        self.index_manager = _create_index_manager()

    @staticmethod
    def _candidate_generation_type() -> str:
        return str(getattr(SETTINGS, "cand_gen_type", os.environ.get("CAND_GEN_TYPE", "default")) or "default").strip().lower()

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
    def _cluster_summary(cluster: dict[str, Any]) -> str:
        return str(
            cluster.get("shared_result_summary")
            or cluster.get("shared_summary")
            or cluster.get("res_summary")
            or ""
        ).strip()

    @staticmethod
    def _result_to_dataframe(shared_results: dict[str, Any] | None) -> pd.DataFrame | None:
        """Convert shared_results dict (from majority_vote) to pandas DataFrame.
        
        Handles:
        - None or missing results
        - Empty results
        - Missing column_names
        - Result data as list of tuples
        
        Returns DataFrame or None.
        """
        if not shared_results or not isinstance(shared_results, dict):
            return None
        
        result_data = shared_results.get("result")
        column_names = shared_results.get("column_names")
        
        if not result_data:
            return None
        
        try:
            # Convert list of tuples to DataFrame
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
        except Exception as e:
            logger.warning(f"Failed to convert shared_results to DataFrame: {e}")
            return None

    @staticmethod
    def _build_enhanced_summary(cluster: dict[str, Any]) -> str:
        """Build enhanced cluster summary with df_profile_markdown output.
        
        Combines current text summary with structured data profile:
        "{text_summary}\n\n{df_profile_markdown_output}"
        
        Falls back to text summary if DataFrame conversion fails.
        """
        text_summary = IssueDetector._cluster_summary(cluster)
        
        # Try to enhance with data profile
        shared_results = cluster.get("shared_results") if isinstance(cluster, dict) else None
        if shared_results and isinstance(shared_results, dict):
            df = IssueDetector._result_to_dataframe(shared_results)
            if df is not None:
                try:
                    profile_text = df_profile_markdown(df)
                    if profile_text:
                        return f"{text_summary}\n\n{profile_text}"
                except Exception as e:
                    logger.debug(f"Failed to create df_profile_markdown: {e}")
        
        return text_summary

    @staticmethod
    def _has_grammar_trigger(user_question: str, sql_text: str) -> bool:
        q = str(user_question or "").lower()
        s = str(sql_text or "").lower()
        return ("every" in q) or ("all" in q) or (" where " in f" {s} ")

    @staticmethod
    def _split_sql_and_comment(sql: str) -> tuple[str, str]:
        """Split SQL into core SQL and trailing comment.
        
        Handles trailing `-- comment` format.
        Returns (sql_core, comment) where comment includes the '-- ' prefix or is empty.
        
        Example:
            "SELECT * -- notes" → ("SELECT *", "-- notes")
            "SELECT * WHERE x=1" → ("SELECT * WHERE x=1", "")
        """
        sql_text = str(sql or "").strip()
        if not sql_text:
            return ("", "")
        
        # Find the first occurrence of '-- '
        comment_marker = " -- "
        idx = sql_text.find(comment_marker)
        
        if idx >= 0:
            core = sql_text[:idx].rstrip()
            comment = sql_text[idx:].lstrip()  # Include the '-- ' part
            return (core, comment)
        
        # remove the ";" if exists
        if sql_text.endswith(";"):
            sql_text = sql_text[:-1].rstrip()
        
        return (sql_text, "")

    @staticmethod
    def _get_comment_length(sql: str) -> int:
        """Return the length of the comment portion of a SQL string.
        
        Used to determine which duplicate variant has the longer note.
        """
        _, comment = IssueDetector._split_sql_and_comment(sql)
        return len(comment)

    @staticmethod
    def _dedupe_sql_list(items: list[str]) -> list[str]:
        """Deduplicate SQL list, preserving comments from richer variants.
        
        Groups by SQL core (ignoring trailing comments), and within each group
        keeps the variant with the longest comment.
        
        Args:
            items: List of SQL strings, potentially with trailing '-- comment' notes
        
        Returns:
            Deduplicated list with comments preserved (longest comment per SQL variant)
        """
        # Group by SQL core
        core_to_entries: dict[str, list[str]] = {}
        
        for item in items:
            sql = str(item or "").strip()
            if not sql:
                continue
            
            core, comment = IssueDetector._split_sql_and_comment(sql)
            core_normalized = core.strip()
            
            if not core_normalized:
                continue
            
            if core_normalized not in core_to_entries:
                core_to_entries[core_normalized] = []
            core_to_entries[core_normalized].append(sql)
        
        # For each core, select the variant with the longest comment
        output: list[str] = []
        for core in core_to_entries:
            variants = core_to_entries[core]
            # Select the one with the longest comment
            best = max(variants, key=lambda s: IssueDetector._get_comment_length(s))
            output.append(best)
        
        return output

    def detect_from_node(
        self,
        sql_gen_node_id: str,
        mode: str,
        state: Any,
        step_callback: Any | None = None,
    ) -> dict[str, Any]:
        """New detector entrypoint: operate from a SQL_GEN node id.

        mode: "newCand" | "reuserCand"
        state: SystemState instance
        step_callback: optional callback to push partial updates to UI
        """
        try:
            node = state.get_node_snapshot(sql_gen_node_id)
        except Exception as exc:
            return {"success": False, "error": f"Failed to fetch node: {exc}", "cand_gen_node_id": None, "ambi_detect_node_id": None}

        if not node:
            return {"success": False, "error": "SQL_GEN node not found", "cand_gen_node_id": None, "ambi_detect_node_id": None}

        # find SQL generation detail record
        sql_text = ""
        for dr in node.detail_records:
            if isinstance(dr, (DetailRecordSQLGen, DetailRecordExecSQL)):
                sql_text = getattr(dr, "sql_text", "") or ""
                break

        if not sql_text:
            return {"success": False, "error": "No SQL text found in SQL_GEN node", "cand_gen_node_id": None, "ambi_detect_node_id": None}

        db_name = str(state.selected_db or "")
        if not db_name:
            return {"success": False, "error": "No DB selected in SystemState", "cand_gen_node_id": None, "ambi_detect_node_id": None}

        current_db_path = get_db_file(SETTINGS.created_dbs_dir, db_name)
        schema_text = describe_sqlite_schema(current_db_path) if current_db_path else "No schema available"

        pref_ctx = prepare_user_preference_context(
            state=state,
            db_name=db_name,
            ambiguity_contexts=[state.get_latest_user_question() or ""],
            similarity_threshold=0.75,
        )
        preferences_text = str(pref_ctx.get("preferences_text") or "")

        # Stage 1: candidate generation
        # Attempt reuse if requested
        reused_from = ""
        candidates_sqls: list[str] = [sql_text]
        if mode == "reuserCand":
            prev = state.find_last_node(NodeType.CAND_GEN)
            if prev is not None:
                # try to extract candidates from previous CAND_GEN detail record
                for det in prev.detail_records:
                    if isinstance(det, DetailRecordCandGeneration):
                        for item in det.candidates:
                            s = str(item.get("sql") or "").strip()
                            if s and s not in candidates_sqls:
                                candidates_sqls.append(s)
                        reused_from = prev.node_id
                        break
        # If no reused candidates found and mode was reuser, fallback to newCand
        if mode == "reuserCand" and len(candidates_sqls) <= 1:
            mode = "newCand"

        cand_node_id: str | None = None

        if mode == "newCand":
            gen_type = self._candidate_generation_type()

            # === STRUCTURED PATH ===
            if gen_type == "structured":
                parsed = parse_sql_for_detector(sql_text)
                try:
                    retrieved = self._retrieve_options(db_name, parsed)
                except Exception:
                    retrieved = {"columns": {}, "values": {}}

                generator = CandidateGenerator(self.index_manager)
                entries = generator.generate(
                    db_name=db_name,
                    user_question=str(state.get_latest_user_question() or ""),
                    sql_text=sql_text,
                    schema_text=schema_text,
                    preferences_text=preferences_text,
                )
                logger.info("Structured candidate generation produced %d entries", len(entries))

                # Evaluate entries (per-entry execution + refinement)
                evaluator = DetectionEvaluator()
                per_entry_results = evaluator.evaluate_entries(entries, db_name)
                logger.info("Per-entry evaluation produced %d results", len(per_entry_results))

                cand_detail = DetailRecordCandGeneration(
                    original_sql=sql_text,
                    mode=mode,
                    candidates=[],
                    majority_vote_result={},
                    execution_stats={"total_entries": len(entries)},
                    ambiguity_entries=entries,
                    per_entry_results=per_entry_results,
                )

                # Build summary
                if not entries:
                    summary = "No ambiguity entries detected"
                else:
                    parts = []
                    for idx, entry in enumerate(entries, 1):
                        ctx = entry.get("AmbiContext", "")[:40]
                        opts_count = len(entry.get("InterpretationOpts", []))
                        parts.append(f"{idx}: '{ctx}' ({opts_count} opts)")
                    summary = "; ".join(parts)

                parents = [sql_gen_node_id]
                if step_callback:
                    cand_node_id = step_callback(
                        {
                            "node_type": NodeType.CAND_GEN.value,
                            "title": "Candidates Exploration",
                            "summary": summary,
                            "details": "",
                            "reasoning": (node.reasoning or ""),
                            "detail_records": [cand_detail],
                            "metadata": {"mode": mode, "cand_gen_type": "structured"},
                            "parents": parents,
                        }
                    )
                if not cand_node_id:
                    cand_node = state.create_node(
                        node_type=NodeType.CAND_GEN,
                        summary=summary,
                        details="",
                        reasoning=(node.reasoning or ""),
                        title="Candidates Exploration",
                        parents=parents,
                        detail_records=[cand_detail],
                        metadata={"mode": mode, "cand_gen_type": "structured"},
                    )
                    cand_node_id = cand_node.node_id

                if step_callback:
                    step_callback({"type": "cand_gen_complete", "cand_gen_node_id": cand_node_id})

                # Skip pairwise stage — entries are already structured with AmbiContext+AmbiType+options
                return {"success": True, "error": None, "cand_gen_node_id": cand_node_id, "ambi_detect_node_id": None}

            # === EXISTING PATH (default / diverse) ===
            parsed = parse_sql_for_detector(sql_text)
            try:
                retrieved = self._retrieve_options(db_name, parsed)
            except Exception:
                retrieved = {"columns": {}, "values": {}}
            sql_items = [
                {
                    "original_sql": sql_text,
                    "parsed": {"columns": parsed.columns, "literals": parsed.literals, "functions": parsed.functions},
                    "retrieved_options": retrieved,
                }
            ]
            try:
                context = DetectorContext(
                    db_name=db_name,
                    user_question=str(state.get_latest_user_question() or ""),
                    current_round_steps="",
                    previous_summary="",
                    reasoning="",
                    preferences_text=preferences_text,
                )
                if gen_type == "diverse":
                    _early_parents = [sql_gen_node_id]
                    if step_callback:
                        cand_node_id = step_callback(
                            {
                                "node_type": NodeType.CAND_GEN.value,
                                "title": "Candidates Exploration",
                                "summary": "Generating candidates...",
                                "details": "",
                                "reasoning": (node.reasoning or ""),
                                "detail_records": [],
                                "metadata": {"mode": mode, "process_status": "running"},
                                "parents": _early_parents,
                            }
                        )
                    if not cand_node_id:
                        _early_node = state.create_node(
                            node_type=NodeType.CAND_GEN,
                            summary="Generating candidates...",
                            details="",
                            reasoning=(node.reasoning or ""),
                            title="Candidates Exploration",
                            parents=_early_parents,
                            detail_records=[],
                            metadata={"mode": mode, "process_status": "running"},
                        )
                        cand_node_id = _early_node.node_id
                    generated = self._generate_sql_options_diverse(context, sql_items, cand_node_id, state)
                    logger.info("Diverse generation produced items")
                    logger.info(generated)
                else:
                    generated = self._generate_sql_options(context, sql_items)
            except Exception:
                generated = []
            if generated and isinstance(generated, list):
                for item in generated:
                    opts = item.get("more_possible_sqls") or []
                    for s in opts:
                        sstr = str(s or "").strip()
                        if sstr and sstr not in candidates_sqls:
                            candidates_sqls.append(sstr)
            candidates_sqls = self._dedupe_sql_list(candidates_sqls)

        # perform majority vote clustering
        try:
            # drop SQLs that failed execution to avoid using erroneous queries as ambiguity options
            mj = perform_majority_vote(candidates_sqls, db_name, drop_failed=True)
            logger.info(f"Majority vote result: {mj}")
        except Exception as exc:
            return {"success": False, "error": f"Majority vote failed: {exc}", "cand_gen_node_id": None, "ambi_detect_node_id": None}

        # build DetailRecordCandGeneration
        cand_detail = DetailRecordCandGeneration(
            original_sql=sql_text,
            mode=mode,
            candidates=[{"sql": s, "source": "generated" if s != sql_text else "original"} for s in candidates_sqls],
            majority_vote_result={"clusters": mj},
            execution_stats={"total_candidates": len(candidates_sqls)},
            reused_from_cand_gen_id=reused_from,
        )

        # create CAND_GEN node through the passed callback
        summary = "No clusters"
        try:
            total_clusters = len(mj) if isinstance(mj, list) else 0
            if total_clusters:
                summary = ", ".join([f"cluster {i+1}: {len(self._cluster_sqls(item))} candidates" for i, item in enumerate(mj)])
        except Exception:
            summary = "Candidates generated"

        parents = [sql_gen_node_id]
        if reused_from:
            parents.append(reused_from)

        if cand_node_id is None:
            # Non-diverse path: create CAND_GEN node now
            if step_callback:
                cand_node_id = step_callback(
                    {
                        "node_type": NodeType.CAND_GEN.value,
                        "title": "Candidates Exploration",
                        "summary": summary,
                        "details": "",
                        "reasoning": (node.reasoning or ""),
                        "detail_records": [cand_detail],
                        "metadata": {"mode": mode},
                        "parents": parents,
                    }
                )
            if not cand_node_id:
                cand_node = state.create_node(
                    node_type=NodeType.CAND_GEN,
                    summary=summary,
                    details="",
                    reasoning=(node.reasoning or ""),
                    title="Candidates Exploration",
                    parents=parents,
                    detail_records=[cand_detail],
                    metadata={"mode": mode},
                )
                cand_node_id = cand_node.node_id
        else:
            # Diverse path: update the early-created node with final data
            state.update_node(
                cand_node_id,
                {
                    "summary": summary,
                    "detail_records": [cand_detail],
                    "parents": parents,
                    "metadata": {"mode": mode, "process_status": "done"},
                },
            )
        if step_callback:
            step_callback({"type": "cand_gen_complete", "cand_gen_node_id": cand_node_id})

        # Stage 2: pairwise detection
        cluster_list = mj if isinstance(mj, list) else []
        total_pairs = len(cluster_list) * (len(cluster_list) - 1) // 2
        pair_progress = {"finished": 0}
        pair_progress_lock = __import__("threading").Lock()

        # Create AMBI_DETECT node early with placeholder summary (progressive updates)
        ambi_node_id = None
        if cluster_list:
            ambi_node = state.create_node(
                node_type=NodeType.AMBI_DETECT,
                summary="Detecting ambiguity...",
                details="",
                reasoning=(node.reasoning or ""),
                title="Ambiguity Detection",
                parents=[cand_node_id],
                detail_records=[],
            )
            ambi_node_id = ambi_node.node_id
            try:
                state.update_node(
                    ambi_node.node_id,
                    {
                        "issue_status_text": "Detecting...",
                        "metadata": {
                            **(getattr(ambi_node, "metadata", {}) or {}),
                            "process_status": "running",
                            "pairwise_total": total_pairs,
                            "pairwise_finished": 0,
                        },
                    },
                )
            except Exception:
                logger.exception("Failed to mark AMBI_DETECT node as running")

        _detected_pairs: list[DetailRecordPairAmbiDetect] = []
        _pair_sem = __import__("threading").BoundedSemaphore(MAX_THREAD)

        def _process_pair(i: int, j: int, item_i: dict, item_j: dict) -> None:
            try:
                left_label = f"cluster_{i+1}"
                right_label = f"cluster_{j+1}"
                left_summary = self._build_enhanced_summary(item_i) if isinstance(item_i, dict) else str(item_i)
                right_summary = self._build_enhanced_summary(item_j) if isinstance(item_j, dict) else str(item_j)
                comparison_report = f"Left summary:\n{left_summary}\n\nRight summary:\n{right_summary}"
                # Call LLM pairwise ambiguity prompt
                prompt = build_pairwise_ambiguity_prompt(
                    left_summary=left_summary,
                    right_summary=right_summary,
                    user_question=(state.get_latest_user_question() or ""),
                    schema_text=schema_text,
                    preferences_text=preferences_text,
                )
                model = create_model(LLM_choice="Coder")
                raw = call_model_text(model, prompt, max_tokens=2048)
                parsed = parse_pairwise_ambiguity_output(raw)
                logger.info(f"Pairwise ambiguity detection for {left_label} vs {right_label} produced:\n{raw}\nParsed as:\n{parsed}")
                logger.info(parsed)

                det = DetailRecordPairAmbiDetect(
                    pair_id=f"{i+1}_vs_{j+1}",
                    left_cluster_label=left_label,
                    right_cluster_label=right_label,
                    comparison_report=comparison_report,
                    ambiguity_entries=parsed,
                )
                _detected_pairs.append(det)
                if ambi_node_id:
                    state.append_detail_record(ambi_node_id, det)
                    with pair_progress_lock:
                        pair_progress["finished"] += 1
                        finished_pairs = pair_progress["finished"]
                    state.update_node(
                        ambi_node_id,
                        {
                            "summary": f"Detected {finished_pairs}/{total_pairs} pair(s)",
                            "issue_status_text": f"Detecting {finished_pairs}/{total_pairs}",
                            "metadata": {
                                "process_status": "running",
                                "pairwise_total": total_pairs,
                                "pairwise_finished": finished_pairs,
                            },
                        },
                    )
                if step_callback:
                    step_callback({"type": "pair_complete", "pair_id": det.pair_id})
            except Exception as e:
                logger.error(f"Error occurred while processing pair {left_label} vs {right_label}: {e}")
                return
            finally:
                _pair_sem.release()

        threads = []
        for i in range(len(cluster_list)):
            for j in range(i + 1, len(cluster_list)):
                _pair_sem.acquire()
                t = __import__("threading").Thread(target=_process_pair, args=(i, j, cluster_list[i], cluster_list[j]), daemon=True)
                t.start()
                threads.append(t)

        # Wait for every pair thread to finish before returning.
        for t in threads:
            t.join()

        # Finalize AMBI_DETECT node summary
        if ambi_node_id and _detected_pairs:
            ctx_summaries = []
            for pd in _detected_pairs:
                num_opts = len(pd.ambiguity_entries) if pd.ambiguity_entries else 0
                ctx_summaries.append(f"{pd.pair_id} ({num_opts} opts)")
            ambi_summary = ", ".join(ctx_summaries)
            state.update_node(ambi_node_id, {"summary": ambi_summary or "Ambiguity detection complete"})
            try:
                existing_meta = getattr(state.get_node_snapshot(ambi_node_id), "metadata", {}) or {}
                state.update_node(
                    ambi_node_id,
                    {
                        "issue_status_text": "Complete",
                        "metadata": {
                            **existing_meta,
                            "process_status": "done",
                            "detected_pairs": len(_detected_pairs),
                            "pairwise_total": total_pairs,
                            "pairwise_finished": pair_progress["finished"],
                        },
                    },
                )
            except Exception:
                logger.exception("Failed to mark AMBI_DETECT node as done")
        elif ambi_node_id:
            state.update_node(ambi_node_id, {"summary": "No ambiguity detected"})
            try:
                existing_meta = getattr(state.get_node_snapshot(ambi_node_id), "metadata", {}) or {}
                state.update_node(
                    ambi_node_id,
                    {
                        "issue_status_text": "Complete",
                        "metadata": {
                            **existing_meta,
                            "process_status": "done",
                            "detected_pairs": 0,
                            "pairwise_total": total_pairs,
                            "pairwise_finished": pair_progress["finished"],
                        },
                    },
                )
            except Exception:
                logger.exception("Failed to mark AMBI_DETECT node as done (no pairs)")
        if ambi_node_id and step_callback:
            step_callback({"type": "ambi_detect_complete", "ambi_detect_node_id": ambi_node_id})

        return {"success": True, "error": None, "cand_gen_node_id": cand_node_id, "ambi_detect_node_id": ambi_node_id}


    def _retrieve_options(self, db_name: str, parsed: ParsedSql) -> dict[str, Any]:
        top_n = SETTINGS.detector_lsh_top_n
        columns: dict[str, list[dict[str, Any]]] = {}
        values: dict[str, list[dict[str, Any]]] = {}

        for col in parsed.columns[:12]:
            columns[col] = self.index_manager.query_keyword(
                db_name=db_name,
                keyword=col,
                top_n=top_n,
                kind="column",
            )

        for literal in parsed.literals[:12]:
            values[literal] = self.index_manager.query_keyword(
                db_name=db_name,
                keyword=literal,
                top_n=top_n,
                kind="value",
            )

        return {
            "columns": columns,
            "values": values,
            "functions": parsed.functions,
        }

    def _generate_sql_options(
        self,
        context: DetectorContext,
        sql_items: list[dict[str, Any]],
        ambiguity_focus: list[str] | None = None,
        taxonomy_guidance: str | None = None,
    ) -> list[dict[str, Any]]:
        # get schema
        current_db_path = get_db_file(SETTINGS.created_dbs_dir, context.db_name or "")
        schema_text = describe_sqlite_schema(current_db_path) if current_db_path else "No schema available"
        
        prompt = build_sql_options_prompt(
            user_question=context.user_question,
            sql_items=sql_items,
            reasoning=context.reasoning,
            previous_summary=context.previous_summary,
            schema_text=schema_text,
            preferences_text=context.preferences_text,
            taxonomy_guidance=taxonomy_guidance,
            ambiguity_focus=ambiguity_focus,
        )
        model = create_model(LLM_choice="Coder")
        logger.info("Generating SQL options for detector (items=%d)", len(sql_items))
        raw = call_model_text(model, prompt, max_tokens=49152)
        parsed = parse_sql_options_json(raw)
        logger.info("Generated SQL options\nParsed as:\n%s", parsed)

        # Ensure we always return one object per original SQL.
        if parsed:
            return parsed

        fallback: list[dict[str, Any]] = []
        for item in sql_items:
            fallback.append(
                {
                    "original_sql": str(item.get("original_sql") or ""),
                    "more_possible_sqls": [],
                }
            )
        return fallback

    def _generate_sql_options_diverse(
        self,
        context: DetectorContext,
        sql_items: list[dict[str, Any]],
        cand_node_id: str | None = None,
        state: Any | None = None,
    ) -> list[dict[str, Any]]:
        """Generate candidate SQLs by running multiple focused prompts in parallel."""
        if not sql_items:
            return []
        
        logger.info("Enter diverse SQL options generation...")

        original_sql = str(sql_items[0].get("original_sql") or "").strip()
        user_question = str(context.user_question or "").strip()

        focus_jobs: list[tuple[str, list[str]]] = []
        if self._has_grammar_trigger(user_question, original_sql):
            focus_jobs.append(("grammar", ["AmbiScope", "AmbiAttach"]))

        focus_jobs.append(("user_query", ["AmbiIntent"]))
        for ambi_type in ["AmbiColumn", "AmbiValue", "AmbiOp"]:
            focus_jobs.append((ambi_type, [ambi_type]))

        if not focus_jobs:
            return self._generate_sql_options(context, sql_items)

        total_jobs = len(focus_jobs)
        generated_batches: list[list[dict[str, Any]]] = []
        batches_lock = threading.Lock()
        progress_counter: dict[str, int] = {"done": 0}
        progress_lock = threading.Lock()
        _cand_sem = threading.BoundedSemaphore(MAX_THREAD)

        def _run_focus(focus_name: str, focus_types: list[str]) -> None:
            try:
                focused_taxonomy = build_taxonomy_guidance(focus_types)
                batch = self._generate_sql_options(
                    context,
                    sql_items,
                    ambiguity_focus=focus_types,
                    taxonomy_guidance=focused_taxonomy,
                )
            except Exception as exc:
                logger.warning("Focused candidate generation failed for %s: %s", focus_name, exc)
                batch = []
            finally:
                _cand_sem.release()
            with batches_lock:
                generated_batches.append(batch)
            # Progressive UI update
            with progress_lock:
                progress_counter["done"] += 1
                done = progress_counter["done"]
            if state is not None and cand_node_id is not None:
                try:
                    state.update_node(
                        cand_node_id,
                        {
                            "summary": f"Generating candidates: {done}/{total_jobs} focus types completed",
                            "metadata": {
                                "process_status": "running",
                                "focus_total": total_jobs,
                                "focus_finished": done,
                                "current_focus": focus_name,
                            },
                        },
                    )
                except Exception:
                    pass

        threads: list[threading.Thread] = []
        logger.info(f"Starting focused candidate generation with {total_jobs} focus types: {[f[0] for f in focus_jobs]}")
        for focus_name, focus_types in focus_jobs:
            _cand_sem.acquire()
            t = threading.Thread(target=_run_focus, args=(focus_name, focus_types), daemon=True)
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        # Current runtime path always has one target SQL item; aggregate all focused
        # outputs directly to avoid brittle exact-string matching on original_sql.
        if len(sql_items) == 1:
            aggregated_sqls: list[str] = []
            for batch in generated_batches:
                for item in batch or []:
                    aggregated_sqls.extend(
                        str(opt).strip()
                        for opt in (item.get("more_possible_sqls") or [])
                        if str(opt).strip()
                    )

            single_original = str(sql_items[0].get("original_sql") or "").strip()
            output: list[dict[str, Any]] = [
                {
                    "original_sql": single_original,
                    "more_possible_sqls": self._dedupe_sql_list(aggregated_sqls),
                }
            ]
        else:
            logger.warning(
                "Diverse generation received %d sql_items; using legacy per-original merge.",
                len(sql_items),
            )
            merged_by_original: dict[str, list[str]] = {}
            for item in sql_items:
                original = str(item.get("original_sql") or "").strip()
                if original:
                    merged_by_original[original] = []

            for batch in generated_batches:
                for item in batch or []:
                    original = str(item.get("original_sql") or "").strip()
                    if not original:
                        continue
                    merged_by_original.setdefault(original, [])
                    merged_by_original[original].extend(
                        str(opt).strip() for opt in (item.get("more_possible_sqls") or []) if str(opt).strip()
                    )

            output = []
            for item in sql_items:
                original = str(item.get("original_sql") or "").strip()
                output.append(
                    {
                        "original_sql": original,
                        "more_possible_sqls": self._dedupe_sql_list(merged_by_original.get(original, [])),
                    }
                )
        return output


