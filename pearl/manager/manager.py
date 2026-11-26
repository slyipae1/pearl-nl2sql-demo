from __future__ import annotations

import difflib
import html
import json
import time
import ast
from dataclasses import dataclass
from typing import Any, Callable, List

from smolagents import ToolCallingAgent, tool
from smolagents.memory import ActionStep

from config import SETTINGS
from history.node_models import (
    DetailRecordManagerStep,
    DetailRecordManagerAutoFix,
    DetailRecordSQLGen,
    DetailRecordPairAmbiDetect,
    DetailRecordScoredAmbiEntry,
    DetailRecordPreferenceSave,
    NodeType,
    STANDARD_TITLES,
)
import threading
from preference_learner.learner import save_preference_base, _compute_merged_entry_from_options
from database.inspector import describe_sqlite_schema
from detector.issue_detector import IssueDetector
from history.system_state import SystemState
from utils.model_factory import create_model
from utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ManagerProcessResult:
    responder_answer: str
    summary_text: str
    summary_timed_out: bool = False
    error: str = ""

"""
APIs called by app:
- overall_workflow()
- continue_after_compact()
- detect_and_set_round_start_type()
- reset_all()
"""


class Manager:
    def __init__(self, state: SystemState, responder: Any) -> None:
        self.state = state
        self.responder = responder
        self.model = create_model(LLM_choice="ToolCall")

        self._active_mode: str = ""
        self._trace_tool_calls: list[dict[str, Any]] = []
        self._trace_read_round_ids: list[str] = []
        self._trace_read_node_ids: list[str] = []
        self._trace_set_attended_ids: list[str] = []
        self._trace_prepared_questions: list[dict[str, Any]] = []

        self.prompt_to_nl2sql: str = ""

        self.round_start_type: str = ""          # "Fresh_Round" | "Cont_Round" | "New_Topic"
        self.cached_question: str = ""            # holds user question when awaiting compact decision
        self._initial_context: str = ""           # compressed memory from Compactor

        self.manager_agent = ToolCallingAgent(
            model=self.model,
            tools=[
                self._tool_read_roundids(),
                self._tool_read_nodeids(),
                self._tool_prepare_specifying_question(),
            ],
            step_callbacks={ActionStep: self._on_manager_step},
            max_steps=10,
        )
        ## can we have a system prompt for manager?

    # -----------------  Manager agent ----------------- #

    @staticmethod
    def _parse_ids(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        if not text:
            return []

        parsed: Any = None
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except Exception:
                try:
                    parsed = ast.literal_eval(text)
                except Exception:
                    parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]

        parts = [part.strip() for part in text.replace("\n", ",").split(",")]
        return [part for part in parts if part]

    @staticmethod
    def _dedup_extend(target: list[str], new_values: list[str]) -> None:
        seen = set(target)
        for value in new_values:
            if value and value not in seen:
                target.append(value)
                seen.add(value)
 
    def _tool_read_roundids(self):
        @tool
        def read_roundids(round_ids: str) -> str:
            """Read detailed markdown snapshots for the specified round IDs.

            Args:
                round_ids: JSON list string or comma-separated round IDs.
            """
            ids = self._parse_ids(round_ids)
            self._dedup_extend(self._trace_read_round_ids, ids)
            return self._render_rounds_snapshot_markdown(ids, include_archived=True)

        return read_roundids

    def _tool_read_nodeids(self):
        @tool
        def read_nodeids(node_ids: str) -> str:
            """Read detailed markdown snapshots for the specified node IDs.

            Args:
                node_ids: JSON list string or comma-separated node IDs.
            """
            ids = self._parse_ids(node_ids)
            self._dedup_extend(self._trace_read_node_ids, ids)
            return self._render_nodes_snapshot_markdown(ids)

        return read_nodeids

    def _tool_set_attended_nodeids(self):
        @tool
        def set_attended_nodeids(node_ids: str) -> str:
            """Append node IDs to attended list of current round with deduplication.

            Args:
                node_ids: JSON list string or comma-separated node IDs.
            """
            ids = self._parse_ids(node_ids)
            self._dedup_extend(self._trace_set_attended_ids, ids)
            updated = self.state.append_attended_nodes_for_current_round(ids)
            return f"Updated attended node IDs for {self.state.current_round_id}: {updated}"

        return set_attended_nodeids

    def _tool_prepare_specifying_question(self):
        @tool
        def prepare_specifying_question(
            detail_id: str,
            question: str,
            choices: list[str] | None = None,
            multi_selection: bool = False,
            preselect_option_idxs: list[int] | None = None,
            manager_rationale: str = "",
        ) -> str:
            """Queue an explicit follow-up question for the UI specification panel.

            Args:
                detail_id: Source detail record ID for the ambiguity entry.
                question: The follow-up question to ask the user.
                choices: list of options, should one-to-one mapped with ambiguity options.
                multi_selection: Whether multiple options can be selected.
                preselect_option_idxs: Optional option indexes to preselect in the UI.
                manager_rationale: Additional rationale from the manager. (optional)
            """
            cleaned_detail_id = str(detail_id or "").strip()
            cleaned_question = str(question or "").strip()
            source_record = self.state.get_detail_record(cleaned_detail_id) if cleaned_detail_id else None
            if source_record is None:
                logger.warning(
                    "prepare_specifying_question: detail record %r not found, "
                    "queueing question without evaluator context",
                    cleaned_detail_id,
                )

            cleaned_choices = [str(item).strip() for item in (choices or []) if str(item).strip()]
            if not cleaned_choices and isinstance(source_record, DetailRecordScoredAmbiEntry):
                cleaned_choices = []
                for item in (source_record.options or []):
                    text = self._option_to_display_text(item)
                    if text:
                        cleaned_choices.append(text)

            if not cleaned_question:
                return "Skipped: empty question."

            merged_hidden_rationale = self._merge_question_rationales(
                evaluator_justification=str(getattr(source_record, "evaluator_justification", "") or ""),
                manager_rationale=manager_rationale,
            )

            question_id = self.state.queue_specifying_question(
                question=cleaned_question,
                detail_id=cleaned_detail_id,
                choices=cleaned_choices,
                multi_selection=bool(multi_selection),
                question_format="spec_multi_choices",
                hidden_rationale=merged_hidden_rationale,
                preselect_option_idxs=[int(idx) for idx in (preselect_option_idxs or [])],
                manager_rationale=str(manager_rationale or "").strip(),
                evaluator_justification=str(getattr(source_record, "evaluator_justification", "") or ""),
                source=self._active_mode or "manager",
            )
            self._trace_prepared_questions.append(
                {
                    "question_id": question_id,
                    "detail_id": cleaned_detail_id,
                    "question": cleaned_question,
                    "choices": cleaned_choices,
                    "multi_selection": bool(multi_selection),
                    "hidden_rationale": merged_hidden_rationale,
                    "manager_rationale": str(manager_rationale or "").strip(),
                    "preselect_option_idxs": [int(idx) for idx in (preselect_option_idxs or [])],
                }
            )
            logger.info("Queued specifying question: %s — %s", question_id, cleaned_question[:80])
            return f"Queued specifying question: {question_id}"

        return prepare_specifying_question

    @staticmethod
    def _merge_question_rationales(
        evaluator_justification: str,
        manager_rationale: str,
    ) -> str:
        parts: list[str] = []
        evaluator = str(evaluator_justification or "").strip()
        manager = str(manager_rationale or "").strip()
        if evaluator:
            parts.append(f"Evaluator justification: {evaluator}")
        if manager:
            parts.append(f"Manager rationale: {manager}")
        return "\n".join(parts).strip()

    @staticmethod
    def _option_to_display_text(option: Any) -> str:
        if isinstance(option, dict):
            snippet = str(option.get("snippet") or option.get("sql") or option.get("option_content") or option.get("option") or "").strip()
            interp = str(option.get("interpretation") or option.get("description") or option.get("note") or "").strip()
            if snippet and interp:
                return f"{snippet} -- {interp}"
            return snippet or interp
        return str(option or "").strip()

    def _on_manager_step(self, step: ActionStep, agent: Any) -> None:
        tool_calls = getattr(step, "tool_calls", None) or []
        observations = (getattr(step, "observations", "") or "").strip()
        for tc in tool_calls:
            name = str(getattr(tc, "name", "") or "").strip()
            args = getattr(tc, "arguments", {})
            self._trace_tool_calls.append(
                {
                    "mode": self._active_mode,
                    "step_number": getattr(step, "step_number", None),
                    "name": name,
                    "arguments": args,
                    "observations_preview": observations[:500],
                }
            )

    def _run_manager_agent(self, prompt: str, mode: str) -> str:
        self._active_mode = mode
        self._trace_tool_calls = []
        self._trace_read_round_ids = []
        self._trace_read_node_ids = []
        self._trace_set_attended_ids = []
        self._trace_prepared_questions = []
        output = self.manager_agent.run(prompt, reset=True)
        return str(output).strip()
    
    # ----------------------------------------------------------------
    # Round start type detection -> topic switch & compact
    # ----------------------------------------------------------------

    def detect_and_set_round_start_type(self, user_question: str) -> str:
        """Determine the round_start_type before the main process_question flow.

        Returns one of:
          "Fresh_Round"  — first round, proceed directly
          "Cont_Round"   — continuation (has attended IDs or manager says continue)
          "New_Topic"    — detected new topic, caller should show confirmation
        """
        is_first_round = self.state.round_counter <= 1
        current_round = self.state.current_round_id
        attended_ids = list(self.state.selected_node_ids_by_round.get(current_round, [])) if current_round else []

        if is_first_round:
            self.round_start_type = "Fresh_Round"
            return "Fresh_Round"

        if attended_ids:
            self.round_start_type = "Cont_Round"
            return "Cont_Round"

        # No selected IDs and not first round → ask LLM to judge topic switch
        topic = self._detect_topic_switch(user_question)
        if topic == "New_Topic":
            self.cached_question = user_question
            self.round_start_type = "New_Topic"
            return "New_Topic"

        self.round_start_type = "Cont_Round"
        return "Cont_Round"

    def _detect_topic_switch(self, user_question: str) -> str:
        """Short LLM call to decide if this is a new topic or continuation."""
        recent_rounds = self.state.round_order[-3:] if len(self.state.round_order) >= 3 else self.state.round_order[:]
        context = self._render_rounds_snapshot_markdown(recent_rounds) if recent_rounds else "(No previous rounds)"

        prompt = (
            "You are a conversation topic detector for an NL2SQL system.\n\n"
            "Given the conversation context below and the new user question, decide if the user is "
            "continuing the existing topic or starting a completely new topic.\n"
            "Reply with ONLY one word: New_Topic or Continue\n\n"
            "Do NOT perform reasoing on this task, should be straightforward enough to directly answer. \n"
            "## Conversation context\n"
            f"{context}\n\n"
            "## New user question\n"
            f"{user_question}\n"
        )
        # debug: topic detection prompt prepared

        messages = [{"role": "user", "content": prompt}]
        try:
            logger.info("Detecting new topic for prompt (chars=%d)", len(prompt))
            out = self.model(messages, max_tokens=16384)
            logger.info("Topic detection raw output available")
            content = self._extract_llm_content(out)
            if not content:
                out = self.model(messages, max_tokens=3200, extra_body={"enable_thinking": False})
                content = self._extract_llm_content(out)
            result = (content or "").strip().lower()
            if "new_topic" in result:
                return "New_Topic"
        except Exception as exc:
            logger.exception("Topic detection LLM call failed: %s", exc)

        return "Continue"

    def continue_after_compact(self, step_callback: Callable[[dict[str, Any]], Any]) -> "ManagerProcessResult":
        """Called after compaction decision is made. Processes the cached question."""
        q = self.cached_question
        self.cached_question = ""
        self.round_start_type = "Cont_Round"
        return self.overall_workflow(q, step_callback)

    def reset_memory(self, initial_context: str = "") -> None:
        """Reset the manager's agent memory, optionally injecting compressed context."""
        self._initial_context = initial_context

    # ----------------------------------------------------------------
    # Normal Workflow: enrich -> orchestrate -> post-process -> prepare specifying questions -> summarize
    # ----------------------------------------------------------------

    def overall_workflow(
        self,
        user_input: str,
        step_callback: Callable[[dict[str, Any]], Any],# app._create_step_node()
    ) -> "ManagerProcessResult":
        """Public orchestration entrypoint used by the app.

        Implements the manager-first workflow exactly as specified:
          1) identify DetailRecord of scored ambiguity disagree with current SQL
          2) enrich prompt if needed (consume specifying answers appropriately)
          3) decide which orchestrator to run via manager agent
          4) call the chosen orchestrator
          5) post-orchestration: optional NL2SQL retry on near-one-hot ambi entries
          6) prepare specifying questions for remaining unfixed ambiguity entries
          7) summarize the round (summary prompt excludes question preparation)
        """
        current_round = self.state.current_round_id
        if not current_round:
            raise RuntimeError("No active round. Start a round before manager processing.")
        
        logger.info("Manager round_start_type=%s", self.round_start_type)
        if self.round_start_type == "Fresh_Round":
            self.prompt_to_nl2sql = user_input
            result = self._orchestrate_default(self.prompt_to_nl2sql, step_callback)
        else:
            # 1) collect specification answers depending on input kind
            specification_answers = self.state.consume_answered_specifying_questions()
            specification_answers_text_html = self._format_specification_answers_html(specification_answers)
            attended_ids = list(self.state.selected_node_ids_by_round.get(current_round, [])) if current_round else []

            # if specification answers exist, record a user specification node for traceability (using HTML for UI)
            if specification_answers:
                self.state.create_node(
                    node_type=NodeType.USER_SPECIFICATION,
                    title=STANDARD_TITLES[NodeType.USER_SPECIFICATION],
                    summary="User answered specifying questions.",
                    details=specification_answers_text_html,
                    metadata={"question_ids": [item.get("question_id") for item in specification_answers]},
                )

                # Spawn background thread to persist preferences from answered specifying questions
                def _bg_save_prefs(specs: list[dict[str, Any]]):
                    try:
                        db_name = str(self.state.selected_db or "")
                        if not db_name:
                            return
                        entries: list[dict[str, Any]] = []
                        for item in specs:
                            detail_id = str(item.get("detail_id") or "").strip()
                            if not detail_id:
                                continue

                            # Retrieve the original DetailRecordScoredAmbiEntry by detail_id
                            source_record = self.state.get_detail_record(detail_id)
                            if source_record is None or not isinstance(source_record, DetailRecordScoredAmbiEntry):
                                continue

                            ambiguity_context = str(source_record.ambiguity_context or "").strip()
                            if not ambiguity_context:
                                continue

                            ans = item.get("answer") or {}
                            selected_choice_texts = set(
                                str(c).strip() for c in (ans.get("multi_choices") or [])
                                if str(c).strip()
                            )

                            # Map by choice index: choices are 1:1 ordered with scored entry options.
                            # Cannot rely on text parsing because choices may be NL (LLM-generated)
                            # rather than "snippet -- interpretation" format.
                            choices_list = list(item.get("choices") or [])
                            selected_option_snippets: set[str] = set()
                            for choice_idx, choice_text in enumerate(choices_list):
                                if str(choice_text).strip() in selected_choice_texts:
                                    if choice_idx < len(source_record.options):
                                        snippet = str(source_record.options[choice_idx].get("snippet", "")).strip()
                                        if snippet:
                                            selected_option_snippets.add(snippet)

                            # Build dictified scored entry record for _compute_merged_entry_from_options
                            scored_dict: dict[str, Any] = {
                                "detail_id": source_record.detail_id,
                                "ambiguity_context": source_record.ambiguity_context,
                                "options": source_record.options,
                            }

                            pref_entry = _compute_merged_entry_from_options(
                                selected_option_snippets=selected_option_snippets,
                                scored_entry_record=scored_dict,
                                all_options_with_scores=source_record.options,
                            )

                            if pref_entry.get("AmbiOpts"):
                                entries.append(pref_entry)

                            # Handle free-text answer as auxiliary entry
                            free_text = str(ans.get("free_text") or "").strip()
                            if free_text:
                                free_text_entry: dict[str, Any] = {
                                    "AmbiContext": ambiguity_context,
                                    "AmbiOpts": [{"snippet": free_text, "interpretation": "user free text input", "freq": 1}],
                                }
                                entries.append(free_text_entry)

                        if entries:
                            self.state.append_current_round_preferences(entries)
                            res = save_preference_base(db_name, entries)
                            # create a manager node to record the save result
                            summary = f"Preference save result: {res.get('success', False)}; added={res.get('added', 0)}; total={res.get('total', 0)}"
                            updated_entries = list(res.get("updated_entries") or [])
                            pref_save_record = DetailRecordPreferenceSave(
                                updated_entries=updated_entries,
                                summary=summary,
                            )
                            self.state.create_node(
                                node_type=NodeType.PREFERENCE_SAVE,
                                title=STANDARD_TITLES.get(NodeType.PREFERENCE_SAVE, "Preference Save"),
                                summary=summary,
                                details=summary,
                                detail_records=[pref_save_record],
                            )
                    except Exception:
                        return

                threading.Thread(target=_bg_save_prefs, args=(specification_answers,), daemon=True).start()

            # 2b) build enrichment prompt (using markdown-formatted spec answers for LLM)
            previous_round_id = self._get_previous_round_id()
            specification_answers_text_markdown = self._format_specification_answers_markdown(specification_answers)
            enrich_prompt = self._build_enrich_prompt(
                user_question=user_input,
                last_round_id=previous_round_id,
                specification_answers_text=specification_answers_text_markdown,
            )
            self.prompt_to_nl2sql = self._run_manager_agent(enrich_prompt, mode="enrich")
            self._register_manager_node(mode="enrich", content=self.prompt_to_nl2sql)

            schema_text = describe_sqlite_schema(self.responder.current_db_path)

            # 3) decide which orchestrator to run using an LLM-driven decision prompt
            if specification_answers:
                cur_final_sql, _ = self.state.get_round_final_sql(self.state.current_round_id)
                decision_prompt = (
                    "You are the manager of an agentic NL2SQL system.\n"
                    "Your task is to choose the most appropriate orchestrator workflow for the current request.\n\n"
                    "## Background:\n"
                    "The user asked an NL2SQL question. The system detected ambiguity and asked clarifying questions. "
                    "The user's answers are now available. Decide whether the remaining ambiguity risk is low or high, "
                    "and whether the current SQL needs a minor or significant revision.\n\n"
                    "## Available workflows:\n"
                    "- disamb_newCand: High risk with a significant change to the current SQL. Run the NL2SQL worker, "
                    "then generate new ambiguity candidates, then run the ambiguity evaluator.\n"
                    "- disamb_reuseCand: High risk with only a minor change to the current SQL. Run the NL2SQL worker, "
                    "then reuse the previous candidates in the detector, then run the ambiguity evaluator.\n"
                    "- disamb_none: Low risk. Run only the NL2SQL worker and skip the detector and evaluator.\n\n"
                    "Return exactly one token from {disamb_newCand, disamb_reuseCand, disamb_none}.\n\n"
                    "## Context:\n"
                    f"- User question: {user_input}\n"
                    f"- Current SQL: {cur_final_sql}\n"
                    f"- Specification answers summary:\n{specification_answers_text_markdown}\n"
                    f"- Schema:\n{schema_text}\n"
                )
                raw_decision = self._run_manager_agent(decision_prompt, mode="decide_workflow").strip().lower()
                if "disamb_reuse" in raw_decision:
                    chosen = "disamb_reuseCand"
                elif "disamb_new" in raw_decision:
                    chosen = "disamb_newCand"
                elif "disamb_none" in raw_decision:
                    chosen = "disamb_none"
                else:
                    chosen = "default"
            else: 
                chosen = "default"

            # 4) call orchestrator
            if chosen == "default":
                result = self._orchestrate_default(self.prompt_to_nl2sql, step_callback)
            elif chosen == "disamb_newCand":
                result = self._orchestrate_default(self.prompt_to_nl2sql, step_callback)
            elif chosen == "disamb_reuseCand":
                result = self._orchestrate_default(self.prompt_to_nl2sql, step_callback, detector_mode="reuseCand")
            elif chosen == "disamb_none":
                result = self._orchestrate_disamb_none(self.prompt_to_nl2sql, step_callback)
            else:
                result = self._orchestrate_default(self.prompt_to_nl2sql, step_callback)

        # 5) post-orchestration: optional auto-fix and NL2SQL retry
        rerun_needed = False
        thre_onehot = 0.8
        current_nodes = self.state.get_round_nodes_snapshot(current_round)
        unfixed_entries: list[DetailRecordScoredAmbiEntry] = []
        for node in current_nodes:
            for dr in node.detail_records:
                if isinstance(dr, DetailRecordScoredAmbiEntry) and not dr.is_fixed:
                    unfixed_entries.append(dr)

        # auto-fix near-one-hot entries
        auto_fixed_entries: list[DetailRecordScoredAmbiEntry] = []
        for entry in unfixed_entries:
            if not entry.scores:
                continue
            top = max(entry.scores)
            if top >=1:
                # already correct, set fixed directly and skip auto-fix as well
                self.state.mark_scored_entry_fixed(entry.detail_id, fixed_by="auto", round_id=current_round)
                continue
            if top >= thre_onehot:
                self.state.mark_scored_entry_fixed(entry.detail_id, fixed_by="auto", round_id=current_round)
                auto_fixed_entries.append(entry)
                rerun_needed = True

        if auto_fixed_entries:
            auto_fix_entries = [
                {
                    "ambiguity_context": e.ambiguity_context,
                    "top_score": max(e.scores) if e.scores else 0,
                    "selected_option_index": e.top_option_index() if e.options else None,
                    "selected_option": e.options[e.top_option_index()] if e.options else None,
                    "all_scores": list(e.scores),
                    "entropy": e.entropy,
                    "score_gap": e.score_gap,
                }
                for e in auto_fixed_entries
            ]
            auto_fix_record = DetailRecordManagerAutoFix(
                fixed_entries=auto_fix_entries,
                summary=f"Auto-fixed {len(auto_fixed_entries)} ambiguity option(s) with high confidence.",
                threshold=thre_onehot,
            )
            self.state.create_node(
                node_type=NodeType.MANAGER_AUTO_FIX,
                title=STANDARD_TITLES[NodeType.MANAGER_AUTO_FIX],
                summary=f"Auto-fixed {len(auto_fixed_entries)} ambiguity option(s) with high confidence.",
                details=auto_fix_record.format_details(),
                detail_records=[auto_fix_record],
            )

        if rerun_needed:
            # perform single NL2SQL retry with the fixed decisions included
            self.prompt_to_nl2sql = self._build_retry_prompt(
                                    user_question=self.prompt_to_nl2sql,
                                    non_ambi_drs=auto_fixed_entries,
                                )
            self._register_manager_node(mode="enrich_retry", content=self.prompt_to_nl2sql)
            responder_answer = self.responder.run_question(self.prompt_to_nl2sql, step_callback)
            result.responder_answer = str(responder_answer)

        # 6) prepare specifying questions for remaining unfixed entries
        remaining_unfixed: list[DetailRecordScoredAmbiEntry] = []
        current_nodes = self.state.get_round_nodes_snapshot(current_round)
        for node in current_nodes:
            for dr in node.detail_records:
                if isinstance(dr, DetailRecordScoredAmbiEntry) and not dr.is_fixed:
                    remaining_unfixed.append(dr)

        if remaining_unfixed:
            prep_prompt = self._build_prepareQ_prompt(remaining_unfixed)
            prep_out = self._run_manager_agent(prep_prompt, mode="prepare_questions")
            print(f"[DEBUG] Prepare questions output:\n{prep_out}\n", flush=True)

        # 7) summary phase
        current_round_snapshot = self._render_rounds_snapshot_markdown([current_round])
        summary_prompt = self._build_summary_prompt(current_round_snapshot)
        summary_text = self._run_manager_agent(summary_prompt, mode="summary")
        self._register_manager_node(mode="summary", content=summary_text)

        return ManagerProcessResult(
            responder_answer=str(result.responder_answer),
            summary_text=summary_text,
            summary_timed_out=False,
            error="",
        )


    def _orchestrate_default(self, enrich_prompt: str, step_callback: Callable[[dict[str, Any]], Any], detector_mode: str = "newCand") -> "ManagerProcessResult":
        """Default orchestration: NL2SQL worker -> detector(generate new candidates + pairwise) -> evaluator."""
        result = ManagerProcessResult(responder_answer="", summary_text="")
        
        try:
            # 1) NL2SQL worker
            responder_answer = self.responder.run_question(enrich_prompt, step_callback)
            result.responder_answer = str(responder_answer)

            # 2) Detector: find the latest SQL_GEN node in this round and call detector
            detector = IssueDetector()
            current_round = self.state.current_round_id
            sql_gen_node = self.state.find_last_node(NodeType.SQL_GEN, round_id=current_round)
            det_out = {"decision": "NO ISSUES", "detector_note": "No detector run", "generated_sql_options": []}
            if sql_gen_node is not None:
                try:
                    det_out = detector.detect_from_node(sql_gen_node.node_id, detector_mode, self.state, step_callback)
                except Exception as exc:
                    print(f"[WARN] Detector failed: {exc}", flush=True)
                    det_out = {"success": False, "decision": "NO ISSUES", "detector_note": f"detector failed: {exc}", "generated_sql_options": []}
            else:
                # no SQL_GEN found; nothing to detect
                det_out = {"success": True, "decision": "NO ISSUES", "detector_note": "No SQL_GEN node found", "generated_sql_options": []}

            # 3) Evaluator: synthesize scored ambiguity entries from detector output if present
            from evaluator.evaluator import Evaluator

            ambi_eval_node_id = None
            scored_entries: list[DetailRecordScoredAmbiEntry] = []
            try:
                evaluator = Evaluator()

                # Check if structured path was used (no AMBI_DETECT, structured entries in CAND_GEN)
                cand_gen_node = self.state.find_last_node(NodeType.CAND_GEN, round_id=current_round)
                cand_gen_meta = getattr(cand_gen_node, "metadata", {}) or {}
                is_structured = cand_gen_meta.get("cand_gen_type") == "structured"

                if is_structured and cand_gen_node is not None:
                    # Use evaluate_structured for the structured path
                    eval_out = evaluator.evaluate_structured(cand_gen_node.node_id, self.state, step_callback)
                    if eval_out.get("success"):
                        ambi_eval_node_id = eval_out.get("ambi_eval_node_id")
                        scored_entries = eval_out.get("scored_entries") or []
                else:
                    # Existing path: find the AMBI_DETECT node
                    ambi_detect_node = self.state.find_last_node(NodeType.AMBI_DETECT, round_id=current_round)
                    if ambi_detect_node is not None:
                        eval_out = evaluator.evaluate(ambi_detect_node.node_id, self.state, step_callback)
                        if eval_out.get("success"):
                            ambi_eval_node_id = eval_out.get("ambi_eval_node_id")
                            scored_entries = eval_out.get("scored_entries") or []
            except Exception as exc:
                print(f"[WARN] Evaluator failed: {exc}", flush=True)
                # evaluator failure should not crash manager; record a manager step
                mgr_step = DetailRecordManagerStep(manager_mode="evaluator", content=f"evaluator failed: {exc}")
                self.state.create_node(
                    node_type=NodeType.MANAGER_ENRICH_PROMPT,
                    title=STANDARD_TITLES.get(NodeType.MANAGER_ENRICH_PROMPT, "Manager"),
                    summary="Evaluator error",
                    details=str(exc),
                    detail_records=[mgr_step],
                )

            return result
        except Exception as exc:
            return ManagerProcessResult(responder_answer="", summary_text="", summary_timed_out=False, error=str(exc))
        
    def _orchestrate_disamb_none(self, user_question: str, step_callback: Callable[[dict[str, Any]], Any]) -> "ManagerProcessResult":
        """Explicit path when ambiguity handling is disabled: behave like default."""
        # Only call NL2SQL worker and skip detector/evaluator
        try:
            responder_answer = self.responder.run_question(user_question, step_callback)
            return ManagerProcessResult(responder_answer=str(responder_answer), summary_text="", summary_timed_out=False, error="")
        except Exception as exc:
            return ManagerProcessResult(responder_answer="", summary_text="", summary_timed_out=False, error=str(exc))
        
    # ----------------- Prompts Definitions ----------------- #
    # ---- helpers ---- #

    @staticmethod
    def _format_specification_answers_html(items: list[dict[str, Any]]) -> str:
        """Format specification answers as HTML for UI node rendering."""
        if not items:
            return ""
        cards: list[str] = []
        for item in items:
            qid = html.escape(str(item.get("question_id") or ""))
            question = html.escape(str(item.get("question") or ""))
            manager_rationale = str(item.get("manager_rationale") or "").strip()
            choices = item.get("choices") or []
            answer = item.get("answer") or {}
            multi_choices = [str(v).strip() for v in (answer.get("multi_choices") or []) if str(v).strip()]
            free_text = str(answer.get("free_text") or "").strip()

            # Build choices display: each choice with selected indicator
            choices_html = ""
            for c in choices:
                c_text = str(c).strip()
                if not c_text:
                    continue
                c_escaped = html.escape(c_text)
                if c_text in multi_choices:
                    choices_html += f'<div class="spec-answer-choice selected">✓ {c_escaped}</div>'
                else:
                    choices_html += f'<div class="spec-answer-choice">· {c_escaped}</div>'

            # Free text note
            free_text_html = ""
            if free_text:
                ft_escaped = html.escape(free_text)
                free_text_html = f'<div class="spec-answer-note"><span class="spec-answer-label">Note:</span> {ft_escaped}</div>'

            # Manager rationale collapsible
            rationale_html = ""
            if manager_rationale:
                rationale_escaped = html.escape(manager_rationale)
                rationale_html = (
                    f'<details class="spec-answer-rationale">'
                    f'<summary>Manager Rationale</summary>'
                    f'<div class="spec-answer-rationale-text">{rationale_escaped}</div>'
                    f'</details>'
                )

            card = (
                f'<div class="spec-answer-card">'
                f'<div class="spec-answer-qid">{qid}</div>'
                f'<div class="spec-answer-question"><strong>Question:</strong> {question}</div>'
                f'<div class="spec-answer-choices">{choices_html}</div>'
                f'{free_text_html}'
                f'{rationale_html}'
                f'</div>'
            )
            cards.append(card)

        return f'<div class="spec-summary-container">{"".join(cards)}</div>'

    @staticmethod
    def _format_specification_answers_markdown(items: list[dict[str, Any]]) -> str:
        """Format specification answers as clean Markdown for LLM prompts."""
        if not items:
            return ""
        lines: list[str] = []
        lines.append("## Specification Answers from User:\n")
        
        for item in items:
            qid = str(item.get("question_id") or "")
            question = str(item.get("question") or "")
            manager_rationale = str(item.get("manager_rationale") or "").strip()
            choices = item.get("choices") or []
            answer = item.get("answer") or {}
            multi_choices = [str(v).strip() for v in (answer.get("multi_choices") or []) if str(v).strip()]
            free_text = str(answer.get("free_text") or "").strip()
            
            lines.append(f"### Q{qid}: {question}")
            
            # Selected options
            if multi_choices:
                lines.append(f"**Selected Options:**")
                for choice in multi_choices:
                    lines.append(f"- {choice}")
            else:
                lines.append(f"**Selected Options:** (none)")
            
            # Free text if present
            if free_text:
                lines.append(f"**User Notes:** {free_text}")
            
            # Manager rationale if present
            if manager_rationale:
                lines.append(f"**Manager Rationale:** {manager_rationale}")
            
            lines.append("")  # Add blank line between entries
        
        return "\n".join(lines).strip()
    
    def _render_rounds_snapshot_markdown(self, round_ids: list[str], attended_ids: List=[], include_archived: bool=False) -> str:
        groups = self.state.get_round_groups_snapshot(mode="tech", include_archived=include_archived)
        group_by_id = {str(group.get("round_id") or ""): group for group in groups}
        lines: list[str] = []

        for rid in round_ids:
            group = group_by_id.get(rid)
            if not group:
                lines.append(f"## Round: {rid}\n(Not found)")
                continue

            lines.append(f"## {group.get('round_label', 'Round')} ({rid})")
            lines.append(f"- Attend to nodes when entered: {group.get('attended_when_enter', [])}")
            nodes = group.get("nodes") or []
            for node in nodes:
                payload = node.get_payload(mode="tech", details_level="prompt")
                lines.append(f"### Node: {payload.get('node_id')}")
                lines.append("About: " + payload.get("title", "") + "\n")
                lines.append(payload.get("details", "") + "\n\n")
                if payload.get('node_id') in attended_ids:
                    lines.append("*This node was selected to be paied attention to.*\n\n")

        return "\n".join(lines).strip() or "(No round snapshots available)"

    def _render_nodes_snapshot_markdown(self, node_ids: list[str]) -> str:
        all_nodes = {node.node_id: node for node in self.state.get_nodes_snapshot()}
        lines: list[str] = []
        for node_id in node_ids:
            node = all_nodes.get(node_id)
            if not node:
                lines.append(f"## Node: {node_id}\n(Not found)")
                continue
            payload = node.get_payload(mode="tech", details_level="prompt")
            lines.append(f"## Node: {node_id}")
            lines.append(f"In round: {payload.get('round_id', '')}")
            lines.append("About: " + payload.get("title", "") + "\n")
            lines.append(payload.get("details", "") + "\n\n")

        return "\n".join(lines).strip() or "(No node snapshots available)"

    # ---- Enrich Prompt to NL2SQL Worker --- #
    def _build_enrich_prompt(
        self,
        user_question: str,
        last_round_id: str,
        specification_answers_text: str,
    ) -> str:
        prompt = ''
        if self._initial_context:
            prompt += f"[Conversation History Summary]\n{self._initial_context.strip()}\n\n"
            self._initial_context = ""
        prompt += f"""
You are a manager agent for an agnetic NL2SQL system.
Your current task is to prepare an enriched query for the NL2SQL worker agent who is stateless (i.e. without memory of historical conversation).
Suggested steps:
1) Decide whether this should continue from previous question or a fresh new question.
2) Call read_roundids/read_nodeids only when more detail is needed.
3) Prepare an enriched prompt to call a NL2SQL worker. 

# Requirements:
1) NL2SQL worker agent is stateless, so MUST include **MINIMAL** and **SUFFICIENT** history info suh as: describe any terms that appear previously, if it is contining question, echo previous question(s). 
2) If user has response to specifying questions asked by the system, must clearly describe user decision, including what is the ambiguity or issue, what user decide to choose and what decide nto to chooce. 

# Info
## User Question:
{user_question}

## Last Round ID: {last_round_id or '(none)'}
"""
        if specification_answers_text:
            prompt += f"""
## Specification answers summary:
{specification_answers_text}
"""
        return prompt

    # ---- enrich prompt for RETRY NL2SQL Worker --- #
    def _build_retry_prompt(
        self,
        user_question: str,
        non_ambi_drs: List)->str:
        cur_final_sql, cur_result_text = self.state.get_round_final_sql(self.state.current_round_id)

        def _pick_top_option(entry: DetailRecordScoredAmbiEntry) -> str:
            if not entry.options:
                return "(no available option)"
            if not entry.scores:
                return self._option_to_display_text(entry.options[0]) or "(empty option)"
            best_idx = entry.top_option_index()
            return self._option_to_display_text(entry.options[best_idx]) or f"option {best_idx}"

        def _format_other_options(entry: DetailRecordScoredAmbiEntry, top_idx: int) -> str:
            others: list[str] = []
            for idx, option in enumerate(entry.options):
                if idx == top_idx:
                    continue
                opt_text = self._option_to_display_text(option)
                if opt_text:
                    others.append(opt_text)
            return ", ".join(others)

        lines: list[str] = [str(user_question or "").strip()]
        if cur_final_sql:
            lines.append("\nCurrent final SQL:\n" + cur_final_sql)
        if cur_result_text:
            lines.append("\nCurrent execution result:\n" + cur_result_text)

        issue_lines: list[str] = []
        for dr in non_ambi_drs or []:
            if not isinstance(dr, DetailRecordScoredAmbiEntry):
                continue
            context = str(dr.ambiguity_context or "").strip() or "(empty context)"
            top_idx = 0
            if dr.scores and dr.options:
                top_idx = dr.top_option_index()
            use_text = _pick_top_option(dr)
            not_use_text = _format_other_options(dr, top_idx)
            if not_use_text:
                issue_lines.append(f"for {context}, should use {use_text} and not use {not_use_text}")
            else:
                issue_lines.append(f"for {context}, should use {use_text}")

        if issue_lines:
            lines.append("\nDetected Issues:")
            lines.extend(f"- {line}" for line in issue_lines)

        return "\n".join(part for part in lines if part).strip()

    # ---- Prepare Specifying Questions ---- #
    @staticmethod
    def _entropy_hint(entropy: float | None) -> str:
        if entropy is None:
            return "unknown"
        if entropy >= 0.85:
            return "high"
        if entropy >= 0.45:
            return "medium"
        return "low"

    def _format_prepare_entry_block(self, entry: DetailRecordScoredAmbiEntry) -> str:
        lines: list[str] = []
        detail_id = str(entry.detail_id or "").strip() or "(missing detail_id)"
        lines.append(f"DetailRecord ID: {detail_id}")
        lines.append(f"Ambiguity context: {entry.ambiguity_context.strip() or '(empty)'}")
        if getattr(entry, "ambiguity_context_descrip", ""):
            lines.append(f"Context detail: {str(entry.ambiguity_context_descrip).strip()}")
        if getattr(entry, "ambi_type", ""):
            lines.append(f"Ambiguity type: {str(entry.ambi_type).strip()}")
        lines.append(f"Entropy: {entry.entropy if entry.entropy is not None else 'unknown'} ({self._entropy_hint(entry.entropy)})")
        if entry.score_gap is not None:
            lines.append(f"Score gap: {entry.score_gap:.4f}")
        lines.append("Options:")
        if entry.options:
            for idx, opt in enumerate(entry.options):
                score = entry.scores[idx] if idx < len(entry.scores) else None
                score_text = f"{score:.4f}" if isinstance(score, (float, int)) else "unknown"
                lines.append(f"  [{idx}] option={self._option_to_display_text(opt)} | score={score_text}")
        else:
            lines.append("  (no options available)")
        if entry.evaluator_justification.strip():
            lines.append(f"Evaluator justification: {entry.evaluator_justification.strip()}")
        if entry.preselect_option_idxs:
            lines.append(f"Current preselect hints: {entry.preselect_option_idxs}")
        return "\n".join(lines)

    def _build_prepareQ_prompt(self, remaining_unfixed: list[DetailRecordScoredAmbiEntry]) -> str:
        parts: list[str] = []
        cur_final_sql, _ = self.state.get_round_final_sql(self.state.current_round_id)
        parts.extend([
            "You are the manager of an NL2SQL system. You current task is to provide a one-to-one mapping question for user based on the identified issues. \n"
            "Review ambiguity entries and call `prepare_specifying_question` for each one that needs user clarification.\n\n"
            "## Input\n"
            "- Current final SQL: " + (cur_final_sql or "(no current SQL)") + "\n"
            "- Each entry below includes: ambiguity context, options (SQL snippet + interpretation + score), evaluator justification, and metadata.\n"
            "- The `[idx]` is the stable choice identifier.\n\n"
            "## Process (apply to each entry)\n"
            "1. **Decide** — Skip if already answered, invalid, or no longer applicable.\n"
            "2. **Question** — Write one clear, human-friendly question referencing the ambiguity context. One question per entry.\n"
            "3. **Choices** — Convert each SQL `snippet` into NL describing what it does. Use exact DB identifiers (table.column) when referenced; describe operations (functions, clauses, joins) in NL, not SQL syntax. Pair each choice with its `interpretation` internally, but do not expose raw internal metadata in the user-facing wording.\n"
            "4. **Rationale** — Describe the execution result in NL, highlighting what distinguishes this choice from others. Use this as evidence to suggest which option to pick.\n\n"
            "## Quality guidelines\n"
            "- **Conciseness**: Keep questions, choices, and rationale brief.\n"
            "- **Self-contained**: User should understand without inspecting the database. Briefly describe obscure column or table names.\n"
            "- **Preselection**: High entropy → may guess user decision and specify in preselection. Low entropy → usually without preselection leaving for user to decide.\n\n"
            "## Important Rules:\n"
            "- Without special specification, the options with **more robust, comprehensive, variance tolerant, safer, and more aligned with general user** is preferred, since user has little knowledge about DB so ask questions with noisy terms, and the values stored in DB might also be noisy. "
            "- Result cluster with more candidates does NOT guarantee to be more correct sometime even means the opposite, especially for situations with ambiguity since there will be more ambiguous options needed to check. Please judge by resonability of execution result and the SQL logic. \n"
            
        ])
        for entry in remaining_unfixed:
            parts.append(self._format_prepare_entry_block(entry))
            parts.append("\n---\n")
        parts.append(
            "Call prepare_specifying_question only for entries that truly need clarification.\n"
            "Choices must exactly match the entry's options in order and content.\n"
        )
        return "".join(parts)

    
    # ---- Summary of current round ---- #
    def _build_summary_prompt(self, current_round_snapshot: str) -> str:
        parts = []
        cur_final_sql, exec_res = self.state.get_round_final_sql(self.state.current_round_id)
        parts.extend([
            "You are the manager of an NL2SQL system.\n"
            "Your task is to summarize the round for the user. Only aggregate and reorganize existing information for readability; do not add any new information.\n\n"
            "## Requirements\n"
            "1) **Process Summary**: Provide a short, useful summary of what the system did.\n"
            "2) **Answer Interpretation**: Present the answer according to the round's final result.\n"
            "3) **Risk statement** (conditioned): declare the risk of current answer based on detected issues and whether auto-fixing or clarification questions were prepared. \n"
            "   - If **auto-fixing has been done**, mention that clearly with rationale of why it is done and declare any risk of this auto-fix.\n"
            "   - If **clarification questions were prepared**, mention that they may appear below the chatbot, but do not create any new questions here.\n"
            "4) Return ONLY the final user-facing summary via final_answer.\n\n"
            "## Current Round Snapshot\n"
            f"{current_round_snapshot}\n\n"
            "## Current Final Result\n"
            f"- Current final SQL: {cur_final_sql or '(no current SQL)'}\n"
            f"- Current execution result: {exec_res or '(no execution result)'}\n"
        ])
        return "".join(parts)


    # ----------------------------------------------------------------
    # Others: helpers
    # ----------------------------------------------------------------

    def reset_all(self) -> None:
        """Reset ALL internal state to initial defaults."""
        self._active_mode = ""
        self._trace_tool_calls = []
        self._trace_read_round_ids = []
        self._trace_read_node_ids = []
        self._trace_set_attended_ids = []
        self._trace_prepared_questions = []
        self.prompt_to_nl2sql = ""
        self.round_start_type = ""
        self.cached_question = ""
        self._initial_context = ""
        self.responder.reset_memory()

    @staticmethod
    def _extract_llm_content(out: Any) -> str | None:
        content = getattr(out, "content", None)
        if content is not None:
            return str(content).strip()
        raw = getattr(out, "raw", None)
        if raw is not None:
            try:
                msg = raw.choices[0].message
                if msg.content:
                    return msg.content.strip()
                reasoning = getattr(msg, "reasoning", None)
                if reasoning:
                    return reasoning.strip()
            except (IndexError, AttributeError):
                pass
        return None

    def _register_manager_node(self, mode: str, content: str) -> None:
        if mode == "enrich":
            node_type = NodeType.MANAGER_ENRICH_PROMPT
            title = STANDARD_TITLES[NodeType.MANAGER_ENRICH_PROMPT]
            summary = "Manager prepared enriched prompt."
        elif mode == "enrich_retry":
            node_type = NodeType.MANAGER_ENRICH_PROMPT
            title = STANDARD_TITLES[NodeType.MANAGER_ENRICH_PROMPT]
            summary = "Manager prepared enriched retry prompt."
        else:
            node_type = NodeType.MANAGER_SUMMARY
            title = STANDARD_TITLES[NodeType.MANAGER_SUMMARY]
            summary = "Manager summarized the round."

        detail = DetailRecordManagerStep(
            manager_mode=mode,
            content=content,
            set_attended_node_ids=list(self._trace_set_attended_ids),
            read_round_ids=list(self._trace_read_round_ids),
            read_node_ids=list(self._trace_read_node_ids),
            raw_action_step={"tool_calls": list(self._trace_tool_calls)},
        )
        self.state.create_node(
            node_type=node_type,
            title=title,
            summary=summary,
            details=content,
            detail_records=[detail],
            metadata={
                "manager_mode": mode,
                "tool_calls": list(self._trace_tool_calls),
                "prepared_specifying_questions": list(self._trace_prepared_questions),
            },
        )

    def _get_previous_round_id(self) -> str:
        if len(self.state.round_order) < 2:
            return ""
        return self.state.round_order[-2]

    
