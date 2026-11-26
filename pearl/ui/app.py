from __future__ import annotations

import html
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import gradio as gr
import pandas as pd

from nl2sql.nl2sql_worker import NL2SQLWorker
from compactor import Compactor
from config import SETTINGS
from database.inspector import execute_sql, get_db_file, list_db_names, list_tables, sample_table
from history.node_maintainer import spawn_maintainer_worker
from history.node_models import (
    DetailRecordFinalAnswer,
    DetailRecordUserQuestion,
    DetailRecordSQLGen,
    NodeType,
    STANDARD_TITLES,
)
from history.system_state import SystemState
from manager import Manager, ManagerProcessResult
from ui.components_introduction import INTRO_ARCHITECTURE_HTML, INTRO_HTML
from ui.components_node_chain import CSS_TEMPLATE, JS_ON_LOAD, render_allrounds_html, toggle_selection
from ui.components_spec_questions import (
    generate_specifying_questions_form_html,
    generate_spec_questions_js_control,
    CSS_SPEC_QUESTIONS,
    SPEC_QUESTIONS_JS_CODE,
)

from utils.logging_config import get_logger
from utils.profile import df_profile_markdown
import base64
logger = get_logger(__name__)

LAYOUT_CSS = """
#conv-layout-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.conv-toggle-btn {
  border: 1px solid #bfd0e6;
  background: linear-gradient(180deg, #ffffff 0%, #f4f8ff 100%);
  color: #1d3f6e;
  border-radius: 8px;
  padding: 7px 12px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.conv-toggle-btn:hover {
  border-color: #7fa5d9;
  background: linear-gradient(180deg, #ffffff 0%, #eaf2ff 100%);
}

.conv-layout-pill {
  border: 1px solid #d6e0ee;
  background: #f8fbff;
  color: #4a5f7d;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 600;
}

#conv-main-shell {
  align-items: stretch;
  gap: 12px;
}

#conv-chat-col,
#conv-panel-col {
  transition: all 180ms ease;
  min-width: 0;
}

#conv-main-shell.panel-visible #conv-chat-col {
  flex: 2 1 0% !important;
  max-width: 40% !important;
}

#conv-main-shell.panel-visible #conv-panel-col {
  flex: 3 1 0% !important;
  max-width: 60% !important;
  display: block !important;
}

#conv-main-shell.panel-hidden #conv-chat-col {
  flex: 1 1 100% !important;
  max-width: 100% !important;
}

#conv-main-shell.panel-hidden #conv-panel-col {
  display: none !important;
}

@media (max-width: 980px) {
  #conv-main-shell.panel-visible {
    flex-direction: column !important;
  }
  #conv-main-shell.panel-visible #conv-panel-col,
  #conv-main-shell.panel-visible #conv-chat-col {
    max-width: 100% !important;
    width: 100% !important;
    flex: 1 1 auto !important;
  }
  #conv-main-shell.panel-visible #conv-panel-col {
    order: 1;
  }
  #conv-main-shell.panel-visible #conv-chat-col {
    order: 2;
  }
}
"""

JS_LAYOUT_CONTROL = """
(function() {
  if (window.__ConvLayoutBound) return;
  window.__ConvLayoutBound = true;

  function qs(id) { return document.getElementById(id); }

  function setLayout(panelHidden) {
    var shell = qs('conv-main-shell');
    if (!shell) return;
    shell.classList.toggle('panel-hidden', panelHidden);
    shell.classList.toggle('panel-visible', !panelHidden);
    var btn = qs('conv-toggle-panel-btn');
    var pill = qs('conv-layout-mode-pill');
    if (btn) btn.textContent = panelHidden ? 'Show Right Panel' : 'Hide Right Panel';
    if (pill) pill.textContent = panelHidden ? 'Chat Full Width' : 'Split 2:3';
  }

  function bind() {
    var btn = qs('conv-toggle-panel-btn');
    if (!btn) return;
    btn.addEventListener('click', function() {
      var shell = qs('conv-main-shell');
      if (!shell) return;
      var hidden = shell.classList.contains('panel-hidden');
      setLayout(!hidden);
    });
  }

  function init() {
    setLayout(false);
    bind();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
"""


@dataclass
class UIState:
    chat_history: list[dict[str, str]] = field(default_factory=list)


class App:
    def __init__(self) -> None:
        self.state = SystemState()
        self.responder = NL2SQLWorker()
        self.responder.set_state(self.state)
        self.manager = Manager(state=self.state, responder=self.responder)
        self._last_rendered_version: int = 0
        self._last_rendered_html: str = ""
        self._current_mode: str = "tech"
        self._compact_decision_event: threading.Event | None = None
        self._compact_decision: bool | None = None
        self._compact_in_progress: bool = False
        self._spec_selected_question_id: str = ""
        self._spec_last_action_text: str = ""
        # (no flag needed — hide_spec_panel is passed as parameter)

    # ---------- Database selection ----------#
    def _refresh_db_choices(self):
        choices = [""] + list_db_names(SETTINGS.created_dbs_dir)
        return gr.Dropdown(choices=choices, value="")
    
    def _update_table_choices(self, db_name: str):
        tables = self._get_table_list(db_name) if db_name else []
        value = tables[0] if tables else None
        return gr.Dropdown(choices=tables, value=value, label="Table")
    
    def _on_select_database(self, db_name: str):
        if not db_name:
            self.state.selected_db = ""
            return "No database selected."

        db_file = get_db_file(SETTINGS.created_dbs_dir, db_name)
        if not db_file.exists():
            return f"Database file not found: {db_file}"

        self.state.selected_db = db_name
        self.responder.set_database(db_file)
        return f"Selected database: {db_name}"

    # ---------- Inspector Tab ----------#

    @staticmethod
    def _get_table_list(db_name: str) -> list[str]:
        db_file = SETTINGS.created_dbs_dir / db_name / f"{db_name}.sqlite"
        return list_tables(db_file)

    @staticmethod
    def _sample_table(db_name: str, table: str, n: int):
        db_file = SETTINGS.created_dbs_dir / db_name / f"{db_name}.sqlite"
        try:
            return sample_table(db_file, table, int(n))
        except Exception as exc:
            return [[f"_Error: {exc}_"]]

    @staticmethod
    def _execute_sql(db_name: str, sql: str):
        db_file = SETTINGS.created_dbs_dir / db_name / f"{db_name}.sqlite"
        try:
            return execute_sql(db_file, sql)
        except Exception as exc:
            return [[f"_Error: {exc}_"]]

    @staticmethod
    def _load_mermaid_and_stats(db_name: str):
        if not db_name:
            return "", ""
        db_dir = SETTINGS.created_dbs_dir / db_name
        mermaid_path = db_dir / "mermaid_raw.mmd"
        stats_path = db_dir / "db_table_column_stats.csv"
        mermaid_md = ""
        stats_md = ""

        if mermaid_path.exists():
            with open(mermaid_path, "r", encoding="utf-8") as file:
                code = file.read().strip()
            if code:
                mermaid_md = f"# Database Schema \n```mermaid\n{code}\n```"

        if stats_path.exists():
            df = pd.read_csv(stats_path)
            if not df.empty:
                grouped = df.groupby("table")
                stats_md = "# Database Statistics \n"
                max_cols = 10
                for table, subdf in grouped:
                    columns = list(subdf["column"])
                    total = int(subdf.iloc[0]["total"]) if not subdf.empty else 0
                    stats_md += f"\n### Table: {table} (Total: {total})\n"
                    for i in range(0, len(columns), max_cols):
                        chunk = columns[i : i + max_cols]
                        if i == 0:
                            stats_md += "| Metric | " + " | ".join(chunk) + " |\n"
                            stats_md += "|---" + ("|---" * len(chunk)) + "|\n"
                        else:
                            stats_md += "|---" + ("|---" * len(chunk)) + "|\n"
                            stats_md += "| **Metric** | **" + "** | **".join(chunk) + "** |\n"
                        unique_row = [str(subdf[subdf["column"] == col]["unique_non_null"].values[0]) for col in chunk]
                        empty_row = [str(subdf[subdf["column"] == col]["empty"].values[0]) for col in chunk]
                        stats_md += f"| **Unique** | {' | '.join(unique_row)} |\n"
                        stats_md += f"| **Empty** | {' | '.join(empty_row)} |\n"
        return mermaid_md, stats_md

    def _do_sample(self, db_name: str, table: str, n: int):
        if not db_name or not table:
            return ["[_Select database and table._]"]
        return self._sample_table(db_name, table, int(n))

    def _do_execute_sql(self, db_name: str, sql: str):
        if not db_name or not sql:
            return ["[_Select database and enter SQL._]"]
        return self._execute_sql(db_name, sql)

    # -------- Conversation tab: UI frontend handling ----------#
    
    def _build_main_output( # output format for UI front end for whole uistate update
        self,
        mode: str,
        ui_state: UIState,
        user_input_value: str = "",
        compact_btn_update: Any = None,
        compact_yes_update: Any = None,
        compact_no_update: Any = None,
        spec_status_message: str = "",
        hide_spec_panel: bool = False,
    ) -> tuple[Any, ...]:
        compact_btn_update = compact_btn_update if compact_btn_update is not None else gr.update(visible=True)
        compact_yes_update = compact_yes_update if compact_yes_update is not None else gr.update(visible=False)
        compact_no_update = compact_no_update if compact_no_update is not None else gr.update(visible=False)
        return (
            ui_state.chat_history,
            self._render_node_chain(mode),
            self._render_selected_nodes_text(),
            user_input_value,
            ui_state,
            compact_btn_update,
            compact_yes_update,
            compact_no_update,
            *self._compute_spec_panel_updates(spec_status_message, hide_spec_panel=hide_spec_panel),
        )

    def _on_mode_change(self, mode: str, ui_state: UIState):
        self._current_mode = mode
        self._last_rendered_version = self.state.version
        return (
            self._render_node_chain(mode),
            self._render_selected_nodes_text(),
            gr.update(visible=(mode == "tech")),
            gr.update(visible=(mode != "tech")),
        )

    def _on_timer_tick(self) -> str:
        """Called by gr.Timer every 0.5s. Re-renders node_html if state has changed."""
        current_version = self.state.version
        if current_version > self._last_rendered_version:
            self._last_rendered_version = current_version
            # logger.info(f"[INFO] Re-rendering node chain for mode={self._current_mode} with state version={current_version}")
            # print(self._render_node_chain(self._current_mode))
            return self._render_node_chain(self._current_mode)
        if not self._last_rendered_html:
            return self._render_node_chain(self._current_mode)
        return self._last_rendered_html

    def _on_compact_direct(self, db_name: str, mode: str, ui_state: UIState) -> tuple:
        """Direct compact button handler — runs Compactor immediately."""
        if self._compact_in_progress:
            ui_state.chat_history.append({"role": "assistant", "content": "Compaction is already in progress..."})
            return self._build_main_output(mode, ui_state, user_input_value="")
        self._compact_in_progress = True
        try:
            self.state.start_new_round(log_path=SETTINGS.log_path)
            compactor = Compactor(self.state)
            result = compactor.perform_compaction(self.manager)
            msg = f"Compaction complete. Summary generated ({len(result.get('summary', ''))} chars)."
            ui_state.chat_history.append({"role": "assistant", "content": msg})
        except Exception as exc:
            ui_state.chat_history.append({"role": "assistant", "content": f"Compaction failed: {exc}"})
        finally:
            self._compact_in_progress = False
        self._last_rendered_version = self.state.version
        return self._build_main_output(mode, ui_state, user_input_value="")

    def _reset_full_app(self) -> UIState:
        self.state.clear_all()
        self.manager.reset_all()
        self.responder.set_state(self.state)

        # hard-reset responder database binding
        self.responder.current_db_path = None
        setattr(self.responder, "agent", None)

        self._last_rendered_version = 0
        self._last_rendered_html = ""
        self._compact_decision_event = None
        self._compact_decision = None
        self._compact_in_progress = False
        self._spec_selected_question_id = ""

        return UIState()
    
    def _on_page_load(self, mode: str):
        fresh_ui = self._reset_full_app()
        choices = [""] + list_db_names(SETTINGS.created_dbs_dir)
        return (
            gr.update(choices=choices, value=""),      # db_dropdown
            "No database selected.",                   # db_status
            [],                                        # chatbot
            self._render_node_chain(mode),             # node_html
            "(none)",                                  # selected_nodes_text
            "",                                        # user_input
            fresh_ui,                                  # ui_state
            gr.update(visible=True),                   # compact_btn
            gr.update(visible=False),                  # compact_confirm_yes
            gr.update(visible=False),                  # compact_confirm_no
            *self._compute_spec_panel_updates(""),    # specification question panel
            "",                                        # mermaid_render
            "",                                        # stats_render
            gr.update(choices=[], value=None),         # sample_table_dropdown
        )
    
    def _on_clear(self, mode: str, ui_state: UIState) -> tuple:
        """Clear all state — resets App, Manager, Responder, SystemState, and UIState."""
        self.state.clear_all()
        self.manager.reset_all()

        # Reset App internal state
        self._last_rendered_version = 0
        self._last_rendered_html = ""
        self._compact_decision_event = None
        self._compact_decision = None
        self._compact_in_progress = False
        self._spec_selected_question_id = ""

        # Return fresh UI state
        fresh_ui = UIState()
        return (
            [],
            self._render_node_chain(mode),
            "(none)",
            "",
            fresh_ui,
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(visible=False),
            *self._compute_spec_panel_updates(""),
        )
    
    # --------- History Nodes panel ----------#
    
    def _create_step_node(self, event: dict[str, Any]) -> str | None:
        node_type_raw = str(event.get("node_type") or "").strip()
        if not node_type_raw:
            # Progress-only events (for example detector/evaluator callbacks)
            # are allowed to pass through this boundary without creating nodes.
            return None

        try:
            node_type = NodeType(node_type_raw)
        except Exception:
            return None
        title = event.get("title", "") or STANDARD_TITLES.get(node_type, node_type.value)
        summary = event.get("summary", "") or "Step completed."
        details = event.get("details", "") or summary
        reasoning = event.get("reasoning", "") or ""
        parents = event.get("parents") or event.get("parent_ids") or []

        node = self.state.create_node(
            node_type=node_type,
            title=title,
            summary=summary,
            details=details,
            reasoning=reasoning,
            detail_records=event.get("detail_records", []),
            metadata=event.get("metadata", {}),
            parents=list(parents),
        )

        # print("[DEBUG] ready to call maintainer worker for node_id=", node.node_id, flush=True)
        self.state.register_pending_summary_node(node.node_id)
        spawn_maintainer_worker(self.state, node.node_id, event)
        return node.node_id

    def _render_node_chain(self, mode: str):
        groups = self.state.get_round_groups_snapshot(mode)
        
        html = render_allrounds_html(groups, mode=mode)
        self._last_rendered_html = html
        return html

    def _render_selected_nodes_text(self) -> str:
        return self.state.get_selected_nodes_text()

    def _on_select_node(self, evt: gr.SelectData, mode: str, ui_state: UIState):
        selected_node_id = str(evt.value or "")
        ordered_node_ids = [node.node_id for node in self.state.get_nodes_snapshot()]
        selected_ids = toggle_selection(selected_node_id, ordered_node_ids, self.state.get_selected_nodes())
        self.state.set_selected_nodes(selected_ids)

        logger.info(f"Selected node ids: {selected_ids} | current round: {self.state.current_round_id}")
        self._last_rendered_version = self.state.version
        return self._render_node_chain(mode), self._render_selected_nodes_text(), ui_state
    
    # -------- Specifying Questions Panel ----------#
    
    def _render_specifying_questions_html(self) -> str:
        """Render ALL pending specification questions as an interactive HTML form.
        
        Generates a unified form with:
        - All questions displayed as interactive cards simultaneously
        - Checkboxes with green preselection hints (not pre-checked)
        - Free-text input areas for each question
        - Collapsible evidence sections
        - Per-question Save/Skip buttons
        - Custom JavaScript to wire form submission to hidden Gradio buttons
        
        Returns HTML form + embedded CSS + inline JavaScript.
        """
        questions = self.state.get_specifying_questions(only_pending=True)
        if not questions:
            return ""

        # Attempt to find latest SQL_GEN detail record for the current round
        sql_detail = None
        try:
            nodes = self.state.get_nodes_snapshot()
            for node in reversed(nodes):
                if node.node_type != NodeType.SQL_GEN:
                    continue
                for record in reversed(node.detail_records or []):
                    # pick the most recent detail that carries sql_text/raw_result
                    if hasattr(record, "sql_text"):
                        sql_detail = record
                        break
                if sql_detail:
                    break
        except Exception:
            sql_detail = None

        # Build a collapsed section showing current best final SQL, profile, result preview, and download link
        details_parts: list[str] = []
        details_parts.append(f"<style>\n{CSS_SPEC_QUESTIONS}\n.spec-final-section {{ margin-bottom: 10px; }} .spec-final-section .sql-block pre {{ background:#f6f8fb; padding:8px; border-radius:6px; overflow:auto; }}</style>")

        details_parts.append('<details class="spec-final-section">')
        details_parts.append('<summary style="font-weight:700;">Current Final SQL & Execution Result</summary>')

        if sql_detail is not None:
            # SQL text
            sql_text = str(getattr(sql_detail, "sql_text", "") or "").strip()
            if sql_text:
                details_parts.append("<div class='sql-block'><pre>" + html.escape(sql_text) + "</pre></div>")

            # Profile markdown for dataframe
            profile_md = ""
            try:
                raw_df = getattr(sql_detail, "raw_result", None)
                if raw_df is not None:
                    profile_md = df_profile_markdown(raw_df)
            except Exception:
                profile_md = ""

            if profile_md:
                details_parts.append("<div class='profile-block'><pre>" + html.escape(profile_md) + "</pre></div>")

            # Result preview: prefer trusted HTML produced by backend
            result_html = str(getattr(sql_detail, "raw_result_html", "") or "").strip()
            if result_html:
                details_parts.append("<div class='result-preview'><div class='detail-label'>Result Preview</div>" + result_html + "</div>")
            else:
                # Fallback: render small HTML table from DataFrame
                try:
                    if getattr(sql_detail, "raw_result", None) is not None:
                        limited = sql_detail.raw_result.head(20)
                        if not limited.empty:
                            small_html = limited.to_html(index=False, escape=False)
                            details_parts.append("<div class='result-preview'>" + small_html + "</div>")
                except Exception:
                    pass

            # CSV download link: create data URI when csv_text available
            csv_text = str(getattr(sql_detail, "csv_text", "") or "").strip()
            csv_file_path = str(getattr(sql_detail, "csv_file_path", "") or "").strip()
            if csv_text:
                try:
                    b64 = base64.b64encode(csv_text.encode("utf-8")).decode("ascii")
                    details_parts.append(
                        '<div style="margin-top:8px;">'
                        f'<a class="download-csv" href="data:text/csv;base64,{b64}" download="sql_result.csv">Download CSV</a>'
                        '</div>'
                    )
                except Exception:
                    pass
            elif csv_file_path:
                details_parts.append(f"<div style='margin-top:8px;'>CSV saved at: <code>{html.escape(csv_file_path)}</code></div>")
        else:
            details_parts.append("<div class='detail-text'>No SQL generation result available yet.</div>")

        details_parts.append('</details>')

        final_section_html = "".join(details_parts)

        # Generate the HTML form with all question cards
        form_html = generate_specifying_questions_form_html(questions)
        if not form_html:
            return final_section_html + generate_spec_questions_js_control()

        # Combine final section + form HTML + JS into single output
        complete_html = final_section_html + form_html

        return complete_html

    def _compute_spec_panel_updates(self, status_message: str = "", hide_spec_panel: bool = False) -> tuple[Any, ...]:
        """Compute updates for spec-questions panel.

        Now returns only:
        1. Panel title
        2. HTML form (with all questions + CSS + JS)
        3. Hidden data: full submission JSON (for form submission)
        4. Status message

        The HTML form's JavaScript will populate the hidden submission field before
        clicking the hidden Gradio submit button.
        """
        questions = self.state.get_specifying_questions(only_pending=True)
        if not hide_spec_panel:
            logger.info(
                "spec_panel: hide_spec_panel=False, found %d pending questions: %s",
                len(questions),
                [q.get("question_id", "?") for q in questions],
            )

        panel_title = "### Clarification / Specification Questions"

        # During manager processing, defer showing spec panel until worker completes
        if hide_spec_panel:
            return (
                gr.update(value=""),  # clear title (component stays in DOM)
                gr.update(value=""),  # clear HTML (component stays in DOM)
                gr.update(value="[]"),
                gr.update(visible=False, value=""),
            )

        status_update = gr.update(visible=bool(status_message), value=status_message)

        if not questions:
            # No questions pending
            return (
                gr.update(value=""),  # clear title (component stays in DOM)
                gr.update(value=""),  # clear HTML (component stays in DOM)
                gr.update(value="[]"),  # hidden submission payload
                status_update,
            )

        # Render the full form HTML with all questions
        form_html = self._render_specifying_questions_html()

        return (
            gr.update(value=panel_title),
            gr.update(value=form_html),
            gr.update(value="[]"),  # hidden submission payload (will be set by JS)
            status_update,
        )

    def _save_specifying_answer(
        self,
        selected_question_id: str,
        multi_choices: list[str] | None,
        free_text: str,
    ) -> tuple[str, str]:
        qid = str(selected_question_id or "").strip()
        if not qid:
            return "", ""
        question = self.state.get_specifying_question(qid)
        if not question:
            return "", ""

        payload = {
            "multi_choices": [str(v).strip() for v in (multi_choices or []) if str(v).strip()],
            "free_text": str(free_text or "").strip(),
        }
        saved = self.state.save_specifying_answer(qid, payload)
        if not saved:
            return "", ""

        has_any = any([payload["multi_choices"], payload["free_text"]])
        if not has_any:
            return f"Saved empty answer payload for {qid}.", ""

        summary_parts: list[str] = []
        if payload["multi_choices"]:
            summary_parts.append(f"[multi]={', '.join(payload['multi_choices'])}")
        if payload["free_text"]:
            summary_parts.append(f"[note]={payload['free_text']}")
        concise = "; ".join(summary_parts)
        qtext = question.get("question") or question
        return f"Saved answer for {qid}.", f"[{qid}] {qtext}  {concise}"

    def _skip_specifying_question(self, selected_question_id: str) -> tuple[str, str]:
        qid = str(selected_question_id or "").strip()
        if not qid:
            return "", ""
        question = self.state.get_specifying_question(qid)
        if not question:
            return "", ""
        skipped = self.state.skip_specifying_question(qid)
        if not skipped:
            return "", ""
        qtext = question.get("question") or question
        return f"Skipped question {qid}.", f"[{qid}] {qtext}  [skipped]"

    def _run_spec_submit_and_process(
        self,
        mode: str,
        ui_state: UIState,
        submission_json: str,
    ):
        """Submit all clarification cards at once.

        Cards with any checked choice or free-text are saved as answered.
        Blank cards are skipped.
        """
        import json

        try:
            raw = str(submission_json or "").strip()
            payload = json.loads(raw) if raw else []
        except Exception as exc:
            logger.warning("Failed to parse clarification submission JSON: %s", exc)
            payload = []

        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list):
            payload = []

        pending_questions = {
            str(item.get("question_id") or "").strip(): item
            for item in self.state.get_specifying_questions(only_pending=True)
            if str(item.get("question_id") or "").strip()
        }

        processed_ids: set[str] = set()
        answered_ids: list[str] = []
        skipped_ids: list[str] = []

        for item in payload:
            if not isinstance(item, dict):
                continue
            qid = str(item.get("question_id") or "").strip()
            if not qid or qid not in pending_questions:
                continue

            raw_choices = item.get("multi_choices") or []
            if not isinstance(raw_choices, list):
                raw_choices = []
            multi_choices = [str(v).strip() for v in raw_choices if str(v).strip()]
            free_text = str(item.get("free_text") or "").strip()

            if multi_choices or free_text:
                saved_msg, _ = self._save_specifying_answer(
                    selected_question_id=qid,
                    multi_choices=multi_choices,
                    free_text=free_text,
                )
                if saved_msg:
                    answered_ids.append(qid)
            else:
                skipped_msg, _ = self._skip_specifying_question(qid)
                if skipped_msg:
                    skipped_ids.append(qid)

            processed_ids.add(qid)

        for qid in pending_questions:
            if qid in processed_ids:
                continue
            skipped_msg, _ = self._skip_specifying_question(qid)
            if skipped_msg:
                skipped_ids.append(qid)

        summary_parts: list[str] = []
        if answered_ids:
            summary_parts.append(f"answered {len(answered_ids)}")
        if skipped_ids:
            summary_parts.append(f"skipped {len(skipped_ids)}")
        summary = (
            "Submitted clarification answers."
            if not summary_parts
            else "Submitted clarification answers: " + ", ".join(summary_parts) + "."
        )
        if answered_ids:
            summary += f" Answered: {', '.join(answered_ids)}."
        if skipped_ids:
            summary += f" Skipped: {', '.join(skipped_ids)}."

        logger.info(
            "Clarification submit processed: answered=%s skipped=%s summary=%s",
            answered_ids,
            skipped_ids,
            summary,
        )

        ui_state.chat_history.append({"role": "user", "content": summary})
        base_question = self.state.get_latest_user_question(self.state.current_round_id)
        yield from self._advance_spec_panel_or_process(
            mode=mode,
            ui_state=ui_state,
            user_text_for_processing=base_question,
            spec_status=summary,
        )

    def _on_spec_question_change(self, selected_question_id: str):
        """Handle selector change: update selected question ID and recompute all panel updates."""
        self._spec_selected_question_id = str(selected_question_id or "")
        return self._compute_spec_panel_updates("")

    def _run_spec_save_and_process(
        self,
        mode: str,
        ui_state: UIState,
        selected_question_id: str,
        multi_choices_json: str,
        free_text: str,
    ):
        """Save a clarification answer, advance to next pending question if any, otherwise continue.
        
        Args:
            mode: Current UI mode (tech/non-tech)
            ui_state: Current UI state
            selected_question_id: Question ID to save answer for
            multi_choices_json: JSON string array of selected choices
            free_text: Free-text response
        """
        # Parse JSON multi_choices
        multi_choices: list[str] = []
        try:
            if multi_choices_json and str(multi_choices_json).strip():
                import json
                multi_choices = json.loads(str(multi_choices_json))
                if not isinstance(multi_choices, list):
                    multi_choices = []
        except Exception as e:
            logger.warning(f"Failed to parse multi_choices JSON: {e}")
            multi_choices = []
        
        spec_status, _spec_echo = self._save_specifying_answer(
            selected_question_id=selected_question_id,
            multi_choices=multi_choices,
            free_text=free_text,
        )
        base_question = self.state.get_latest_user_question(self.state.current_round_id)
        yield from self._advance_spec_panel_or_process(
            mode=mode,
            ui_state=ui_state,
            user_text_for_processing=base_question,
            spec_status=spec_status,
        )

    def _run_spec_skip_and_process(
        self,
        mode: str,
        ui_state: UIState,
        selected_question_id: str,
    ):
        """Skip a clarification question, advance, and continue only when all are decided."""
        spec_status, _spec_echo = self._skip_specifying_question(selected_question_id)
        base_question = self.state.get_latest_user_question(self.state.current_round_id)
        yield from self._advance_spec_panel_or_process(
            mode=mode,
            ui_state=ui_state,
            user_text_for_processing=base_question,
            spec_status=spec_status,
        )

    def _advance_spec_panel_or_process( # connect to normal round after ALL sepcification question answered or skipped
        self,
        mode: str,
        ui_state: UIState,
        user_text_for_processing: str,
        spec_status: str,
    ):
        pending = self.state.count_pending_specifying_questions()
        if pending > 0:
            self._last_rendered_version = self.state.version
            yield self._build_main_output(mode, ui_state, user_input_value="", spec_status_message=spec_status)
            return

        if not user_text_for_processing:
            ui_state.chat_history.append({"role": "assistant", "content": "No active user question found to continue."})
            self._last_rendered_version = self.state.version
            yield self._build_main_output(mode, ui_state, user_input_value="", spec_status_message=spec_status)
            return

        self._last_rendered_version = self.state.version
        yield self._build_main_output(mode, ui_state, user_input_value="", spec_status_message=spec_status)
        # start a new round
        self.state.start_new_round()
        # Specification follow-up must continue current topic and enter manager enrich flow.
        self.manager.round_start_type = "Cont_Round"
        yield from self._run_normal_processing(user_text_for_processing, mode, ui_state)

    # -------- Main loop with user ----------#
    
    def _run_normal_processing(self, user_text: str, mode: str, ui_state: UIState): # connect to Manager.overall_workflow()
        """Normal round processing — used for Fresh_Round and Cont_Round."""
        result_holder: dict[str, Any] = {"answer": "", "summary": "", "summary_timed_out": False, "error": ""}

        def worker():
            try:
                manager_result: ManagerProcessResult = self.manager.overall_workflow(
                    user_text, self._create_step_node
                )
                if manager_result.error:
                    result_holder["error"] = manager_result.error
                    return
                result_holder["answer"] = manager_result.responder_answer
                result_holder["summary"] = manager_result.summary_text
                result_holder["summary_timed_out"] = manager_result.summary_timed_out
            except Exception as exc:
                result_holder["error"] = str(exc)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        waiting_message = {"role": "assistant", "content": "Waiting for agent to take actions ..."}
        ui_state.chat_history.append(waiting_message)
        self._last_rendered_version = self.state.version
        # Hide spec questions during manager processing via parameter
        yield self._build_main_output(mode, ui_state, user_input_value="", hide_spec_panel=True)
        yield from self._poll_worker(thread, waiting_message, mode, ui_state)

        if ui_state.chat_history and ui_state.chat_history[-1] == waiting_message:
            ui_state.chat_history.pop()

        if result_holder["error"]:
            answer_text = f"Execution error: {result_holder['error']}"
        else:
            answer_text = result_holder["summary"] if result_holder["summary"] else result_holder["answer"]

        if not self.state.ends_with_final_answer():
            self.state.create_node(
                node_type=NodeType.FINAL_ANSWER,
                title=STANDARD_TITLES[NodeType.FINAL_ANSWER],
                summary="Final answer generated.",
                details=answer_text,
                reasoning=answer_text,
                detail_records=[DetailRecordFinalAnswer(answer_text)],
            )

        ui_state.chat_history.append({"role": "assistant", "content": answer_text})
        self.state.consume_decided_specifying_questions()
        self._last_rendered_version = self.state.version
        yield self._build_main_output(mode, ui_state, user_input_value="")

    def _run_round_generator( # connect chatbot send with _run_normal_process
        self,
        user_text: str,
        mode: str,
        ui_state: UIState,
    ):
        """Generator for the send_btn.click event."""
        
        # not allowed when pending questions
        if self.state.count_pending_specifying_questions() > 0:
            ui_state.chat_history.append({"role": "assistant", "content": "Please submit the clarification question(s) above before sending a new question."})
            self._last_rendered_version = self.state.version
            yield self._build_main_output(mode, ui_state, user_input_value=user_text)
            return

        ui_state.chat_history.append({"role": "user", "content": user_text})

        if not self.state.selected_db:
            ui_state.chat_history.append({"role": "assistant", "content": "Select a database first."})
            self._last_rendered_version = self.state.version
            yield self._build_main_output(mode, ui_state, user_input_value="")
            return

        self.state.start_new_round(log_path=SETTINGS.log_path)
        self.state.create_node(
            node_type=NodeType.USER_QUESTION,
            title=STANDARD_TITLES[NodeType.USER_QUESTION],
            summary=user_text,
            details=user_text,
            detail_records=[DetailRecordUserQuestion(user_text)],
        )

        # --- Detect round start type ---
        start_type = self.manager.detect_and_set_round_start_type(user_text)

        if start_type == "New_Topic":
            # --- Phase 1: Show compact confirmation ---
            confirm_msg = "Detected new topic. Do you want to compact the conversation first?"
            ui_state.chat_history.append({"role": "assistant", "content": confirm_msg})

            self._compact_decision_event = threading.Event()
            self._compact_decision = None

            waiter = threading.Thread(target=self._compact_decision_event.wait, daemon=True)
            waiter.start()

            # Yield with confirm buttons visible
            self._last_rendered_version = self.state.version
            yield self._build_main_output(
                mode,
                ui_state,
                user_input_value="",
                compact_btn_update=gr.update(visible=False),
                compact_yes_update=gr.update(visible=True),
                compact_no_update=gr.update(visible=True),
            )

            while waiter.is_alive():
                time.sleep(0.35)
                yield self._build_main_output(
                    mode,
                    ui_state,
                    user_input_value="",
                    compact_btn_update=gr.update(visible=False),
                    compact_yes_update=gr.update(visible=True),
                    compact_no_update=gr.update(visible=True),
                )

            # --- Decision made: immediately hide buttons ---
            if ui_state.chat_history and ui_state.chat_history[-1] == {"role": "assistant", "content": confirm_msg}:
                ui_state.chat_history.pop()

            if self._compact_decision:
                # Show compacting message
                ui_state.chat_history.append({"role": "assistant", "content": "Compacting conversation ..."})
                yield self._build_main_output(mode, ui_state, user_input_value="")

                compactor = Compactor(self.state)
                compactor.perform_compaction(self.manager)

                # Remove the compacting message
                if ui_state.chat_history and ui_state.chat_history[-1]["content"] == "Compacting conversation ...":
                    ui_state.chat_history.pop()
            else:
                # Yield once to hide buttons immediately
                yield self._build_main_output(mode, ui_state, user_input_value="")

            # --- Phase 2: Process with cached question ---
            yield from self._run_processing_after_compact(mode, ui_state)
            return

        # --- Normal flow: Fresh_Round or Cont_Round ---

        yield from self._run_normal_processing(user_text, mode, ui_state)

    def _on_compact_yes(self) -> None:
        if self._compact_decision_event is not None and not self._compact_decision_event.is_set():
            self._compact_decision = True
            self._compact_decision_event.set()

    def _on_compact_no(self) -> None:
        if self._compact_decision_event is not None and not self._compact_decision_event.is_set():
            self._compact_decision = False
            self._compact_decision_event.set()

    def _run_processing_after_compact(self, mode: str, ui_state: UIState): # connect to Manager.continue_after_compact()
        """Processing after compact decision — uses manager.continue_after_compact()."""
        result_holder: dict[str, Any] = {"answer": "", "summary": "", "summary_timed_out": False, "error": ""}

        def worker():
            try:
                manager_result: ManagerProcessResult = self.manager.continue_after_compact(self._create_step_node)
                if manager_result.error:
                    result_holder["error"] = manager_result.error
                    return
                result_holder["answer"] = manager_result.responder_answer
                result_holder["summary"] = manager_result.summary_text
                result_holder["summary_timed_out"] = manager_result.summary_timed_out
            except Exception as exc:
                result_holder["error"] = str(exc)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        waiting_message = {"role": "assistant", "content": "Waiting for agent to take actions ..."}
        ui_state.chat_history.append(waiting_message)
        self._last_rendered_version = self.state.version
        # Hide spec questions during manager processing via parameter
        yield self._build_main_output(mode, ui_state, user_input_value="", hide_spec_panel=True)
        yield from self._poll_worker(thread, waiting_message, mode, ui_state)

        if ui_state.chat_history and ui_state.chat_history[-1] == waiting_message:
            ui_state.chat_history.pop()

        if result_holder["error"]:
            answer_text = f"Execution error: {result_holder['error']}"
        else:
            answer_text = result_holder["summary"] if result_holder["summary"] else result_holder["answer"]

        if not self.state.ends_with_final_answer():
            self.state.create_node(
                node_type=NodeType.FINAL_ANSWER,
                title=STANDARD_TITLES[NodeType.FINAL_ANSWER],
                summary="Final answer generated.",
                details=answer_text,
                reasoning=answer_text,
                detail_records=[DetailRecordFinalAnswer(answer_text)],
            )

        ui_state.chat_history.append({"role": "assistant", "content": answer_text})
        self._last_rendered_version = self.state.version
        yield self._build_main_output(mode, ui_state, user_input_value="")

    def _poll_worker(self, thread: threading.Thread, waiting_message: dict, # UI update helper when running manager
                     mode: str, ui_state: UIState):
        """Yield tuples while the worker thread is alive."""
        while thread.is_alive():
            time.sleep(0.35)
            yield self._build_main_output(mode, ui_state, user_input_value="", hide_spec_panel=True)

    # --------- Main UI layout ----------#
    def build(self) -> gr.Blocks:
        with gr.Blocks(title="NL2SQL Tech/Non-Tech History Demo", css=LAYOUT_CSS) as demo:
            ui_state = gr.State(UIState())
            gr.Markdown("# NL2SQL Demo")

            # --- DB selection and mode ---
            with gr.Row():
                with gr.Column(scale=2):
                    db_dropdown = gr.Dropdown(label="Database", choices=[""], value="")
                with gr.Column(scale=1):
                    mode_dropdown = gr.Dropdown(
                        label="Mode",
                        choices=["tech", "non-tech"],
                        value="tech",
                        visible=False # no longer need to switch to non-tech mode
                    )
            db_status = gr.Markdown("No database selected.")

            # --- conv and inspector tabs ---
            with gr.Tabs():
                with gr.Tab("Introduction"):
                    gr.HTML(value=INTRO_HTML)
                    gr.HTML(value=INTRO_ARCHITECTURE_HTML)

                with gr.Tab("Conversation"):
                    gr.HTML(
                        value=(
                            "<div id='conv-layout-toolbar'>"
                            "<button id='conv-toggle-panel-btn' class='conv-toggle-btn' "
                            "title='Toggle right panel visibility'>Hide Right Panel</button>"
                            "<span id='conv-layout-mode-pill' class='conv-layout-pill'>Split 2:3</span>"
                            "</div>"
                        ),
                        js_on_load=JS_LAYOUT_CONTROL,
                        apply_default_css=False,
                        label="",
                    )
                    with gr.Row(elem_id="conv-main-shell", equal_height=False):
                        with gr.Column(scale=2, elem_id="conv-chat-col"):
                            chatbot = gr.Chatbot(height=520, label="Conversation")
                            user_input = gr.Textbox(label="Ask a question", placeholder="e.g. What is total budget?")
                            send_btn = gr.Button("Send")
                            with gr.Row():
                                compact_btn = gr.Button("Compact Now", visible=True)
                                compact_confirm_yes = gr.Button("✓ Yes, compact", visible=False, variant="primary")
                                compact_confirm_no = gr.Button("✗ No, continue", visible=False)
                                clear_btn = gr.Button("Clear All", variant="stop")

                            spec_panel_title = gr.Markdown(
                                "### Clarification / Specification Questions",
                                visible=True,
                            )
                            spec_questions_html = gr.HTML(visible=True, js_on_load=SPEC_QUESTIONS_JS_CODE)
                            spec_status = gr.Markdown("", visible=False)
                            
                            # Hidden field for form data (populated by JS before button click)
                            spec_hidden_submission = gr.Textbox(value="[]", visible="hidden", elem_id="spec_hidden_submission")
                            spec_submit_btn = gr.Button("Submit Clarifications", visible="hidden", elem_id="spec_submit_btn")

                        with gr.Column(scale=3, elem_id="conv-panel-col"):
                            default_html = self._render_node_chain(self._current_mode)
                            node_html = gr.HTML(
                                value=default_html,
                                css_template=CSS_TEMPLATE,
                                js_on_load=JS_ON_LOAD,
                                apply_default_css=False,
                                label="Node Chain",
                            )
                            selected_nodes_text = gr.Textbox(
                                label="Currently Selected Node IDs",
                                value="(none)",
                                lines=4,
                                interactive=False,
                                visible=False
                            )

                with gr.Tab("DB Inspector"):
                    inspector_notice = gr.Markdown("Only available under tech-mode", visible=False)
                    with gr.Column(visible=True) as inspector_section:
                        with gr.Accordion("Database Diagram", open=False):
                            mermaid_render = gr.Markdown(visible=True)

                        with gr.Accordion("Column Statistics", open=False):
                            stats_render = gr.Markdown(visible=True)

                        with gr.Accordion("Random Sample Table Data", open=False):
                            sample_table_dropdown = gr.Dropdown(label="Table", choices=[], value=None)
                            sample_n = gr.Number(
                                label="Sample N Rows",
                                value=5,
                                precision=0,
                                minimum=1,
                                maximum=50,
                            )
                            sample_btn = gr.Button("Sample")
                            sample_result = gr.Dataframe(
                                wrap=True,
                                interactive=False,
                                label="Sampled Data",
                                max_height=800,
                            )

                        with gr.Accordion("Raw SQL Execution", open=False):
                            sql_input = gr.Textbox(
                                label="SQL Query",
                                lines=2,
                                placeholder="Enter SINGLE SQL: e.g. SELECT * FROM People LIMIT 5",
                            )
                            sql_btn = gr.Button("Execute")
                            sql_result = gr.Dataframe(
                                wrap=True,
                                interactive=False,
                                label="SQL Result",
                                max_height=800,
                            )

            demo.load(self._refresh_db_choices, outputs=[db_dropdown])

            db_dropdown.change(self._on_select_database, inputs=[db_dropdown], outputs=[db_status])
            db_dropdown.change(self._load_mermaid_and_stats, inputs=[db_dropdown], outputs=[mermaid_render, stats_render])
            db_dropdown.change(self._update_table_choices, inputs=[db_dropdown], outputs=[sample_table_dropdown])

            clear_btn.click(
                self._on_clear,
                inputs=[mode_dropdown, ui_state],
                outputs=[chatbot, node_html, selected_nodes_text, user_input, ui_state,
                         compact_btn, compact_confirm_yes, compact_confirm_no,
                         spec_panel_title, spec_questions_html, spec_hidden_submission, spec_status],
            )

            send_btn.click(
                self._run_round_generator,
                inputs=[user_input, mode_dropdown, ui_state],
                outputs=[chatbot, node_html, selected_nodes_text, user_input, ui_state,
                         compact_btn, compact_confirm_yes, compact_confirm_no,
                         spec_panel_title, spec_questions_html, spec_hidden_submission, spec_status],
            )

            compact_btn.click(
                self._on_compact_direct,
                inputs=[db_dropdown, mode_dropdown, ui_state],
                outputs=[chatbot, node_html, selected_nodes_text, user_input, ui_state,
                         compact_btn, compact_confirm_yes, compact_confirm_no,
                         spec_panel_title, spec_questions_html, spec_hidden_submission, spec_status],
            )

            compact_confirm_yes.click(
                self._on_compact_yes,
                inputs=[],
                outputs=[],
                queue=False,
            )

            compact_confirm_no.click(
                self._on_compact_no,
                inputs=[],
                outputs=[],
                queue=False,
            )

            spec_submit_btn.click(
                self._run_spec_submit_and_process,
                inputs=[mode_dropdown, ui_state, spec_hidden_submission],
                outputs=[
                    chatbot,
                    node_html,
                    selected_nodes_text,
                    user_input,
                    ui_state,
                    compact_btn,
                    compact_confirm_yes,
                    compact_confirm_no,
                    spec_panel_title,
                    spec_questions_html,
                    spec_hidden_submission,
                    spec_status,
                ],
                queue=True,
            )

            # disable user select node
            # node_html.select(
            #     self._on_select_node,
            #     inputs=[mode_dropdown, ui_state],
            #     outputs=[node_html, selected_nodes_text, ui_state],
            # )

            mode_dropdown.change(
                self._on_mode_change,
                inputs=[mode_dropdown, ui_state],
                outputs=[node_html, selected_nodes_text, inspector_section, inspector_notice],
            )

            sample_btn.click(
                self._do_sample,
                inputs=[db_dropdown, sample_table_dropdown, sample_n],
                outputs=[sample_result],
            )
            sql_btn.click(self._do_execute_sql, inputs=[db_dropdown, sql_input], outputs=[sql_result])

            # Auto-refresh timer: polls state.version and re-renders node_html on change
            timer = gr.Timer(value=0.5)
            timer.tick(self._on_timer_tick, outputs=[node_html])

            demo.load(
                self._on_page_load,
                inputs=[mode_dropdown],
                outputs=[
                    db_dropdown, db_status, chatbot, node_html, selected_nodes_text, user_input, ui_state,
                    compact_btn, compact_confirm_yes, compact_confirm_no,
                    spec_panel_title, spec_questions_html, spec_hidden_submission, spec_status,
                    mermaid_render, stats_render, sample_table_dropdown
                ],
            )
        
        return demo


def build_demo() -> gr.Blocks:
    app = App()
    return app.build()
