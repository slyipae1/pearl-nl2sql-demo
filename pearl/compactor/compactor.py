"""Compactor — summary-only conversation memory management."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from history.node_models import NodeRecord, NodeType
from history.system_state import SystemState
from utils.model_factory import create_model
from utils.logging_config import get_logger

logger = get_logger(__name__)


def _call_llm(model: Any, prompt: str, max_tokens: int = 49152) -> str:
    """Call the LLM and return the content string, with fallback for thinking mode."""
    messages = [{"role": "user", "content": prompt}]
    out = model(messages, max_tokens=max_tokens, extra_body={"enable_thinking": False})

    content = getattr(out, "content", None)
    if content is not None:
        return str(content).strip()

    raw = getattr(out, "raw", None)
    if raw is not None:
        try:
            msg = raw.choices[0].message
            if msg.content:
                return str(msg.content).strip()
            reasoning = getattr(msg, "reasoning", None)
            if reasoning:
                return str(reasoning).strip()
        except (IndexError, AttributeError):
            pass
    return ""


class Compactor:
    """Compacts conversation history into a manager-only summary."""

    def __init__(self, state: SystemState) -> None:
        self.state = state
        self.model = create_model(LLM_choice="Default")

    def perform_compaction(self, manager: Any) -> dict[str, Any]:
        """Summarize the conversation and reset manager memory with the summary."""
        rounds_md = self._render_conversation_markdown()
        if not rounds_md:
            return {"summary": ""}

        with ThreadPoolExecutor(max_workers=1) as pool:
            summary_future = pool.submit(self._summarize_conversation, rounds_md)
            new_summary = summary_future.result()

        full_summary = self._compact_nodes(new_summary)
        manager.reset_memory(initial_context=full_summary)
        return {"summary": full_summary}

    def _render_conversation_markdown(self) -> str:
        groups = self.state.get_round_groups_snapshot(mode="tech", include_archived=False)
        if not groups:
            return ""

        lines: list[str] = []
        for group in groups:
            rid = str(group.get("round_id") or "")
            label = group.get("round_label", "Round")
            attended = group.get("attended_when_enter") or []

            lines.append(f"## {label} ({rid})")
            if attended:
                lines.append(f"- This round started with attention on nodes: {attended}")

            nodes = group.get("nodes") or []
            for node in nodes:
                if getattr(node, "node_type", None) in [NodeType.COMPACT_SUMMARY, NodeType.FINAL_ANSWER, NodeType.GET_SCHEMA]:
                    continue
                payload = node.get_payload(mode="tech", details_level="prompt")
                node_id = payload.get("node_id", "")
                title = payload.get("title", "")
                details = payload.get("details", "")
                issue_text = payload.get("issue_status_text", "")

                lines.append(f"### Node: {node_id}")
                lines.append(f"Title: {title}")
                if details:
                    lines.append(details)
                if issue_text:
                    lines.append(f"Issue status: {issue_text}")
                lines.append("")

        return "\n".join(lines).strip()

    def _summarize_conversation(self, rounds_md: str) -> str:
        prompt = self._build_summarization_prompt(rounds_md)
        logger.info("Summarizing conversation via LLM (input chars=%d)", len(prompt))
        summary = _call_llm(self.model, prompt, max_tokens=49152)
        return summary.strip()

    def _build_summarization_prompt(self, rounds_md: str) -> str:
        return (
            "You are an NL2SQL conversation summarizer. Produce a compressed summary "
            "that will be injected as initial context for an agent after memory reset.\n\n"
            "Focus on:\n"
            "- Each user question that was answered\n"
            "- Any ambiguities or issues that were detected and resolved\n"
            "- The final correct SQL or answer for each question\n\n"
            "Ignore wrong attempts, failed SQL queries, and dead-end reasoning paths. "
            "Only keep the correct trajectory: question → issues resolved → correct answer.\n\n"
            "Format as:\n"
            "## Previous conversation summary\n"
            "### Round <idx>: <round_id>\n"
            "- Question: <user question>\n"
            "- Issues resolved: <ambiguities, schema clarifications>\n"
            "- Final answer: <correct SQL or result>\n\n"
            "Conversation history:\n"
            f"{rounds_md}\n\n"
            "IMPORTANT: DO NOT perform reasoning, directly start outputing ONLY the summary text starting with '## Previous conversation summary ...' without any additional commentary."
        )

    def _compact_nodes(self, new_summary: str) -> str:
        """Replace old non-current, non-compact nodes with one CompactSummary node."""
        current_round_id = self.state.current_round_id
        prev_summary_texts: list[str] = []

        with self.state.lock:
            for node in self.state.nodes:
                if node.node_type == NodeType.COMPACT_SUMMARY:
                    prev_summary_texts.append(node.details or node.summary)

            remove_ids = {
                n.node_id for n in self.state.nodes
                if n.round_id != current_round_id and n.node_type != NodeType.COMPACT_SUMMARY
            }

            self.state.archive_nodes.extend(n for n in self.state.nodes if n.node_id in remove_ids)
            self.state.nodes = [n for n in self.state.nodes if n.node_id not in remove_ids]

            node_summary = "Compacted Rounds: "
            all_rids = {n.round_id for n in self.state.archive_nodes if n.node_id in remove_ids}
            node_summary += ", ".join(sorted(all_rids)) if all_rids else "None"
            compact_node = NodeRecord(
                node_id=f"{current_round_id}.compact",
                round_id=current_round_id,
                step_index=-1,
                node_type=NodeType.COMPACT_SUMMARY,
                title="Compact Summary",
                summary=node_summary,
                details=new_summary.strip(),
                is_selectable=False,
            )

            insert_idx = 0
            for i, n in enumerate(self.state.nodes):
                if n.node_type == NodeType.COMPACT_SUMMARY:
                    insert_idx = i + 1
                else:
                    break
            self.state.nodes.insert(insert_idx, compact_node)
            self.state.version += 1

        all_parts = prev_summary_texts + [new_summary]
        return "\n\n".join(p.strip() for p in all_parts if p.strip())
