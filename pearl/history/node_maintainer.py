from __future__ import annotations

import threading
from typing import Any

from history.node_models import DetailRecordSQLGen, NodeType, STANDARD_TITLES
from history.system_state import SystemState
from preference_learner.learner import prepare_user_preference_context
from utils.logging_config import get_logger

logger = get_logger(__name__)


class NodeHisMaintainer:
    def __init__(self, state: SystemState, node_id: str, event: dict[str, Any]) -> None:
        self.state = state
        self.node_id = node_id
        self.event = event

    def run(self) -> None:
        try:
            node_type = str(self.event.get("node_type") or "")
            reasoning = (self.event.get("reasoning") or "").strip()
            title = (self.event.get("title") or "").strip()
            summary = (self.event.get("summary") or "").strip()

            try:
                node_enum = NodeType(node_type)
            except Exception:
                node_enum = None
            if node_enum is not None:
                title = STANDARD_TITLES.get(node_enum, node_type)

            self.state.update_node(
                self.node_id,
                {   
                    "summary": summary,
                    "title": title,
                    "issue_status_text": (self.event.get("issue_status_text") or "").strip(),
                    "metadata": {**(self.event.get("metadata") or {})},
                },
            )

        finally:
            self.state.mark_pending_summary_node_done(self.node_id)
        


    @staticmethod
    def _summarize_sql_title() -> str:
        return "SQL Generation"
        # later should call LLM to summerized a title

    def _has_exec_sql_detail_records(self) -> bool:
        detail_records = self.event.get("detail_records") or []
        if not detail_records:
            return False
        return any(isinstance(record, (DetailRecordSQLGen)) for record in detail_records)

    def _build_detector_context(self) -> dict[str, str]:
        node = self.state.get_node_snapshot(self.node_id)
        round_id = node.round_id if node is not None else self.state.current_round_id
        round_nodes = self.state.get_round_nodes_snapshot(round_id)
        user_question = self.state.get_latest_user_question(round_id=round_id)

        round_step_lines: list[str] = []
        for item in round_nodes:
            if node is not None and item.step_index > node.step_index:
                continue
            summary = item.summary.strip() or item.display_title()
            round_step_lines.append(f"[{item.step_index}] {item.node_type.value}: {summary}")

        pref_ctx = prepare_user_preference_context(
            state=self.state,
            db_name=str(self.state.selected_db or ""),
            ambiguity_contexts=[user_question],
            similarity_threshold=0.75,
        )

        return {
            "db_name": self.state.selected_db,
            "user_question": user_question,
            "current_round_steps": "\n".join(round_step_lines),
            "previous_summary": self.state.build_history_summary(exclude_round_id=round_id),
            "reasoning": (self.event.get("reasoning") or "").strip(),
            "preferences_text": str(pref_ctx.get("preferences_text") or ""),
        }

    def _attach_detector_data_to_records(self, detector_result: dict[str, Any]) -> list[Any]:
        original_records = list(self.event.get("detail_records") or [])
        per_sql = detector_result.get("per_sql") or []
        generated = detector_result.get("generated_sql_options") or []

        sql_to_retrieved: dict[str, Any] = {}
        for item in per_sql:
            sql = str(item.get("original_sql") or "").strip()
            if not sql:
                continue
            sql_to_retrieved[sql] = item.get("retrieved_options") or {}

        sql_to_generated: dict[str, list[str]] = {}
        for item in generated:
            sql = str(item.get("original_sql") or "").strip()
            options = item.get("more_possible_sqls") or []
            if sql:
                sql_to_generated[sql] = [str(opt).strip() for opt in options if str(opt).strip()]

        updated: list[Any] = []
        for record in original_records:
            if isinstance(record, (DetailRecordSQLGen)):
                sql_key = (record.sql_text or "").strip()
            updated.append(record)
        return updated


def spawn_maintainer_worker(state: SystemState, node_id: str, event: dict[str, Any]) -> threading.Thread:
    worker = NodeHisMaintainer(state=state, node_id=node_id, event=event)
    thread = threading.Thread(target=worker.run, daemon=True)
    thread.start()
    return thread
