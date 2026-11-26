from __future__ import annotations

import threading
import time
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from history.node_models import DetailRecord, DetailRecordScoredAmbiEntry, NodeRecord, NodeType, STANDARD_TITLES
from utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass

class SystemState:
    selected_db: str = ""
    current_round_id: str = ""
    round_counter: int = 0
    step_counter_in_round: int = 0
    version: int = 0
    nodes: list[NodeRecord] = field(default_factory=list)
    archive_nodes: list[NodeRecord] = field(default_factory=list) # for storing archived nodes that are removed from main nodes list, mainly for compaction
    selected_node_ids: list[str] = field(default_factory=list)
    selected_node_ids_by_round: dict[str, list[str]] = field(default_factory=dict) # storing the ids that are attended when enter the round, only modified when start a round or by Manager
    pending_summary_nodeid: dict[str, bool] = field(default_factory=dict)
    specifying_questions: list[dict[str, Any]] = field(default_factory=list)
    archive_specifying_questions: list[dict[str, Any]] = field(default_factory=list) # for storing archived specifying questions that are removed from main specifying_questions list, as session preference declerations
    currentRound_preferences: list[dict[str, Any]] = field(default_factory=list)
    archive_preferences: list[dict[str, Any]] = field(default_factory=list)
    specifying_question_counter: int = 0
    round_order: list[str] = field(default_factory=list)
    lock: threading.RLock = field(default_factory=threading.RLock)

    def start_new_round(self, log_path: str = "") -> str:
        with self.lock:

            # Finish the previous round
            if self.current_round_id:
                logger.info("Round %s ended.", self.current_round_id)
                if self.currentRound_preferences:
                    self.archive_preferences.extend(deepcopy(self.currentRound_preferences))
                    self.currentRound_preferences = []
                if not self.current_round_id in self.selected_node_ids_by_round:
                    self.selected_node_ids_by_round[self.current_round_id] = []
                    logger.warning("No attended nodes recorded for round %s, defaulting to empty.", self.current_round_id)

                # Log the completed round if a log path is configured
                if log_path:
                    from ui.logger import write_round_log
                    round_id = self.current_round_id
                    attended = list(self.selected_node_ids_by_round.get(round_id, []))
                    nodes_payload = []
                    for node in self.nodes:
                        if node.round_id == round_id:
                            payload = node.get_payload()
                            payload.pop("round_id", None)
                            nodes_payload.append(payload)
                    write_round_log(log_path, round_id, attended, nodes_payload)

            logger.info("Enter next round with attended nodes: %s", self.selected_node_ids)
            self.round_counter += 1
            self.step_counter_in_round = 0
            self.current_round_id = f"r{int(time.time())}_{self.round_counter}"
            
            if self.current_round_id not in self.round_order:
                self.round_order.append(self.current_round_id)
            
            if not self.current_round_id in self.selected_node_ids_by_round:
                self.selected_node_ids_by_round[self.current_round_id] = list(self.selected_node_ids)
            
            logger.info("Started new round: %s", self.current_round_id)
            self.version += 1

            # reset selection for new round
            for node in self.nodes:
                node.being_selected = False
            self.selected_node_ids = []
            self.pending_summary_nodeid = {}

            return self.current_round_id

    def _next_step_index(self) -> int:
        self.step_counter_in_round += 1
        return self.step_counter_in_round

    def create_node(
        self,
        node_type: NodeType,
        summary: str,
        details: str,
        reasoning: str = "",
        title: str = "",
        parents: list[str] | None = None,
        detail_records: list[Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> NodeRecord:
        with self.lock:
            if not self.current_round_id:
                self.start_new_round()
            step_index = self._next_step_index()
            node_id = f"{self.current_round_id}.s{step_index}"
            resolved_title = title or STANDARD_TITLES.get(node_type, node_type.value)

            node = NodeRecord(
                node_id=node_id,
                round_id=self.current_round_id,
                step_index=step_index,
                node_type=node_type,
                title=resolved_title,
                summary=summary,
                details=details,
                reasoning=reasoning,
                parents=self._sanitize_parent_ids(parents or [], child_node_id=node_id),
                detail_records=list(detail_records or []),
                metadata=dict(metadata or {}),
            )
            self.nodes.append(node)
            self.version += 1
            return node

    def update_node(self, node_id: str, updates: dict[str, Any]) -> None:
        with self.lock:
            for node in self.nodes:
                if node.node_id == node_id:
                    for key, value in updates.items():
                        if key == "parents":
                            value = self._sanitize_parent_ids(value or [], child_node_id=node_id)
                        setattr(node, key, value)
                    self.version += 1
                    return

    def _sanitize_parent_ids(self, parent_ids: list[str], child_node_id: str) -> list[str]:
        existing_ids = {n.node_id for n in self.nodes} | {n.node_id for n in self.archive_nodes}
        output: list[str] = []
        seen: set[str] = set()
        for raw_id in parent_ids:
            pid = str(raw_id or "").strip()
            if not pid or pid == child_node_id or pid in seen:
                continue
            if pid in existing_ids:
                output.append(pid)
                seen.add(pid)
        return output

    def set_node_parents(self, node_id: str, parent_ids: list[str]) -> bool:
        with self.lock:
            cleaned = self._sanitize_parent_ids(parent_ids, child_node_id=node_id)
            for node in self.nodes:
                if node.node_id == node_id:
                    node.parents = cleaned
                    self.version += 1
                    return True
            return False

    def append_detail_record(self, node_id: str, detail_record: DetailRecord) -> bool:
        with self.lock:
            for node in self.nodes:
                if node.node_id != node_id:
                    continue
                if any(existing.detail_id == detail_record.detail_id for existing in node.detail_records):
                    return False
                node.detail_records.append(detail_record)
                self.version += 1
                return True
            return False

    def get_detail_record(self, detail_id: str) -> DetailRecord | None:
        with self.lock:
            for node in self.archive_nodes + self.nodes:
                for record in node.detail_records:
                    if record.detail_id == detail_id:
                        return deepcopy(record)
            return None

    def mark_scored_entry_fixed(self, detail_id: str, fixed_by: str, round_id: str) -> bool:
        with self.lock:
            for node in self.nodes:
                for idx, record in enumerate(node.detail_records):
                    if record.detail_id != detail_id:
                        continue
                    if not isinstance(record, DetailRecordScoredAmbiEntry):
                        return False
                    updated = deepcopy(record)
                    updated.is_fixed = True
                    updated.fixed_by = str(fixed_by or "").strip()
                    updated.fixed_round_id = str(round_id or "").strip()
                    node.detail_records[idx] = updated
                    self.version += 1
                    return True
            return False

    def get_nodes_snapshot(self, include_archived: bool = True) -> list[NodeRecord]:
        with self.lock:
            # return both nodes and archived
            if include_archived:
                return [deepcopy(node) for node in self.archive_nodes] + [deepcopy(node) for node in self.nodes] # put archive at front
            else:
                return [deepcopy(node) for node in self.nodes]

    def get_node_snapshot(self, node_id: str) -> NodeRecord | None:
        with self.lock:
            for node in self.nodes:
                if node.node_id == node_id:
                    return deepcopy(node)
            for node in self.archive_nodes:
                if node.node_id == node_id:
                    return deepcopy(node)
            return None

    def get_round_nodes_snapshot(self, round_id: str) -> list[NodeRecord]:
        with self.lock:
            return [deepcopy(node) for node in self.archive_nodes if node.round_id == round_id] + [deepcopy(node) for node in self.nodes if node.round_id == round_id] # put archive at front

    def get_round_final_sql(self, round_id: str | None = None) -> tuple[str, str]:
        """Return the latest SQL_GEN node's SQL text and execution result text for a round.

        Args:
            round_id: Optional round identifier. If omitted, use the current round.

        Returns:
            A tuple of (sql_text, raw_result_text). Returns empty strings when no
            SQL generation node or SQL detail record is available.
        """
        with self.lock:
            target_round_id = str(round_id or self.current_round_id or "").strip()
            if not target_round_id:
                return "", ""

            round_nodes = [
                node
                for node in self.archive_nodes + self.nodes
                if node.round_id == target_round_id
            ]
            for node in reversed(round_nodes):
                if node.node_type != NodeType.SQL_GEN:
                    continue

                for record in reversed(node.detail_records):
                    if hasattr(record, "sql_text"):
                        sql_text = str(getattr(record, "sql_text", "") or "").strip()
                        raw_result_text = str(getattr(record, "raw_result_text", "") or "").strip()
                        return sql_text, raw_result_text

                return "", ""

            return "", ""

    def get_latest_user_question(self, round_id: str | None = None) -> str:
        with self.lock:
            for node in reversed(self.nodes):
                if round_id is not None and node.round_id != round_id:
                    continue
                if node.node_type == NodeType.USER_QUESTION:
                    return node.summary.strip() or node.details.strip()
            return ""

    def build_history_summary(self, max_nodes: int = 8, exclude_round_id: str | None = None) -> str:
        # return ""
        # later let maintainer call llm to create a compact summary
        with self.lock:
            filtered = [node for node in self.nodes if exclude_round_id is None or node.round_id != exclude_round_id]
            if not filtered:
                return ""
            selected = filtered[-max_nodes:]
            lines: list[str] = []
            for node in selected:
                summary = node.summary.strip() or node.display_title()
                lines.append(f"[{node.round_id}:{node.step_index}] {node.node_type.value}: {summary}")
            return "\n".join(lines)

    def find_last_node(self, node_type: NodeType, round_id: str | None = None) -> NodeRecord | None:
        with self.lock:
            for node in reversed(self.nodes):
                if node.node_type != node_type:
                    continue
                if round_id is not None and node.round_id != round_id:
                    continue
                return deepcopy(node)
            return None

    def set_selected_nodes(self, ordered_ids: list[str]) -> None:
        with self.lock:
            selected_set = set(ordered_ids)
            self.selected_node_ids = [node_id for node_id in ordered_ids]

            for node in self.nodes:
                node.being_selected = node.node_id in selected_set

            self.version += 1

    def clear_all(self) -> None:
        with self.lock:
            self.nodes.clear()
            self.archive_nodes.clear()
            self.selected_node_ids.clear()
            self.selected_node_ids_by_round.clear()
            self.pending_summary_nodeid.clear()
            self.specifying_questions.clear()
            self.archive_specifying_questions.clear()
            self.currentRound_preferences.clear()
            self.archive_preferences.clear()
            self.specifying_question_counter = 0
            self.round_order.clear()
            self.round_counter = 0
            self.step_counter_in_round = 0
            self.current_round_id = ""
            self.version += 1

    # ----------------- Preference memory management ----------------- #

    def append_current_round_preferences(self, entries: list[dict[str, Any]]) -> None:
        with self.lock:
            for entry in entries or []:
                if not isinstance(entry, dict):
                    continue
                self.currentRound_preferences.append(deepcopy(entry))
            self.version += 1

    def get_current_round_preferences(self) -> list[dict[str, Any]]:
        with self.lock:
            return [deepcopy(item) for item in self.currentRound_preferences]

    def get_archive_preferences(self) -> list[dict[str, Any]]:
        with self.lock:
            return [deepcopy(item) for item in self.archive_preferences]

    # ----------------- Specifying question management -----------------#
    
    def queue_specifying_question(
        self,
        question: str,
        detail_id: str = "",
        choices: list[str] | None = None,
        multi_selection: bool = False,
        question_format: str = "spec_multi_choices",
        hidden_rationale: str = "",
        preselect_option_idxs: list[int] | None = None,
        manager_rationale: str = "",
        evaluator_justification: str = "",
        source: str = "manager",
    ) -> str:
        with self.lock:
            self.specifying_question_counter += 1
            q_id = f"q{self.specifying_question_counter}"
            payload = {
                "question_id": q_id,
                "detail_id": str(detail_id or "").strip(),
                "question": str(question or "").strip(),
                "choices": [str(c).strip() for c in (choices or []) if str(c).strip()],
                "multi_selection": bool(multi_selection),
                "question_format": str(question_format or "spec_multi_choices").strip() or "spec_multi_choices",
                "hidden_rationale": str(hidden_rationale or "").strip(),
                "preselect_option_idxs": [int(idx) for idx in (preselect_option_idxs or [])],
                "manager_rationale": str(manager_rationale or "").strip(),
                "evaluator_justification": str(evaluator_justification or "").strip(),
                "source": source,
                "status": "pending",
                "answer": {},
                "round_id": self.current_round_id,
                "created_at": time.time(),
            }
            self.specifying_questions.append(payload)
            self.version += 1
            return q_id

    def get_specifying_questions(self, only_pending: bool = False) -> list[dict[str, Any]]:
        with self.lock:
            output = [deepcopy(item) for item in self.specifying_questions]
            if only_pending:
                output = [item for item in output if item.get("status") == "pending"]
            return output

    def get_specifying_question(self, question_id: str) -> dict[str, Any] | None:
        with self.lock:
            for item in self.specifying_questions:
                if item.get("question_id") == question_id:
                    return deepcopy(item)
            return None

    def save_specifying_answer(self, question_id: str, answer: dict[str, Any]) -> bool:
        with self.lock:
            for item in self.specifying_questions:
                if item.get("question_id") != question_id:
                    continue
                item["answer"] = dict(answer or {})
                has_any_answer = any(
                    bool(item["answer"].get(key))
                    for key in ["multi_choices", "free_text"]
                )
                item["status"] = "answered" if has_any_answer else "pending"
                item["answered_at"] = time.time() if has_any_answer else None
                self.version += 1
                return True
            return False

    def set_specifying_question_metadata(self, question_id: str, metadata: dict[str, Any]) -> bool:
        with self.lock:
            for item in self.specifying_questions:
                if item.get("question_id") != question_id:
                    continue
                for key, value in (metadata or {}).items():
                    if key in {"choices", "preselect_option_idxs"} and isinstance(value, list):
                        item[key] = list(value)
                    else:
                        item[key] = value
                self.version += 1
                return True
            return False

    def skip_specifying_question(self, question_id: str) -> bool:
        with self.lock:
            for item in self.specifying_questions:
                if item.get("question_id") != question_id:
                    continue
                item["answer"] = {}
                item["status"] = "skipped"
                item["answered_at"] = time.time()
                self.version += 1
                return True
            return False

    def count_pending_specifying_questions(self) -> int:
        with self.lock:
            return sum(1 for item in self.specifying_questions if item.get("status") == "pending")

    def consume_answered_specifying_questions(self) -> list[dict[str, Any]]:
        with self.lock:
            answered = [deepcopy(item) for item in self.specifying_questions if item.get("status") == "answered"]
            if not answered:
                return []
            self.specifying_questions = [item for item in self.specifying_questions if item.get("status") != "answered"]
            # add to archive
            self.archive_specifying_questions.extend(answered.copy())
            self.version += 1
            return answered

    def consume_decided_specifying_questions(self) -> list[dict[str, Any]]:
        with self.lock:
            decided = [deepcopy(item) for item in self.specifying_questions if item.get("status") in {"answered", "skipped"}]
            if not decided:
                return []
            self.specifying_questions = [item for item in self.specifying_questions if item.get("status") == "pending"]
            # add to archive
            self.archive_specifying_questions.extend(decided.copy())
            self.version += 1
            return decided

    def clear_specifying_questions(self) -> None:
        with self.lock:
            self.specifying_questions.clear()
            self.version += 1

    
    def get_selected_nodes(self) -> list[str]:
        with self.lock:
            return list(self.selected_node_ids)

    def get_selected_nodes_text(self) -> str:
        with self.lock:
            if not self.selected_node_ids:
                return "(none)"
            return "\n".join(self.selected_node_ids)

    def ends_with_final_answer(self) -> bool:
        with self.lock:
            if not self.nodes:
                return True
            return self.nodes[-1].node_type == NodeType.FINAL_ANSWER or self.nodes[-1].node_type == NodeType.MANAGER_SUMMARY

    def append_attended_nodes_for_current_round(self, node_ids: list[str]) -> list[str]:
        with self.lock:
            if not self.current_round_id:
                return []
            current = list(self.selected_node_ids_by_round.get(self.current_round_id, []))
            seen = set(current)
            for node_id in node_ids:
                cleaned = str(node_id).strip()
                if cleaned and cleaned not in seen:
                    current.append(cleaned)
                    seen.add(cleaned)
            self.selected_node_ids_by_round[self.current_round_id] = current
            self.version += 1
            return list(current)

    def register_pending_summary_node(self, node_id: str) -> None:
        with self.lock:
            if node_id:
                self.pending_summary_nodeid[node_id] = False
                self.version += 1

    def mark_pending_summary_node_done(self, node_id: str) -> None:
        with self.lock:
            if node_id in self.pending_summary_nodeid:
                self.pending_summary_nodeid[node_id] = True
                self.version += 1

    def all_pending_summary_nodes_done(self) -> bool:
        with self.lock:
            if not self.pending_summary_nodeid:
                return True
            return all(self.pending_summary_nodeid.values())

    def get_pending_summary_snapshot(self) -> dict[str, bool]:
        with self.lock:
            return dict(self.pending_summary_nodeid)

    def clear_pending_summary_nodes(self) -> None:
        with self.lock:
            self.pending_summary_nodeid.clear()
            self.version += 1

    def get_round_groups_snapshot(self, mode: str = "tech", include_archived: bool=True) -> list[dict[str, Any]]:
        with self.lock:
            nodes_snapshot = self.get_nodes_snapshot(include_archived=include_archived)
            if not nodes_snapshot:
                return []

            round_ids = list(self.round_order)
            if not round_ids:
                seen: set[str] = set()
                for node in nodes_snapshot:
                    if node.round_id not in seen:
                        seen.add(node.round_id)
                        round_ids.append(node.round_id)

            groups: list[dict[str, Any]] = []
            for round_index, round_id in enumerate(round_ids, start=1):
                round_nodes = [node for node in nodes_snapshot if node.round_id == round_id]
                if not round_nodes:
                    continue

                selected_ids = self.selected_node_ids_by_round.get(round_id, [])

                groups.append(
                    {
                        "round_id": round_id,
                        "round_label": f"Round {round_index}",
                        "is_current_round": round_id == self.current_round_id,
                        "is_open": round_id == self.current_round_id,
                        "attended_when_enter": selected_ids,
                        "selected_ids_text": ", ".join(selected_ids) if selected_ids else "(none)",
                        "selected_ids": selected_ids,
                        "nodes": round_nodes,
                    }
                )

            return groups
