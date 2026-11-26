from __future__ import annotations

import json
import threading
import time
from copy import deepcopy
from pathlib import Path
from queue import Queue, Empty
from typing import Any, Dict, List

from config import SETTINGS
from preference_learner import learner
from preference_learner.learner import (
    _base_path_for_db,
    _load_preference_base,
    _merge_source_db_names,
    merge_preferences,
    _similar,
    _normalize_choice_text,
    save_preferences_from_scored_entries,
)
from utils.logging_config import get_logger

logger = get_logger(__name__)


class PreferenceLearner:
    """Worker-class for preference persistence and retrieval.

    Responsibilities:
    - Convert evaluator detail records into canonical preference entries
    - Merge and persist the base JSON (with provenance augmentation)
    - Provide retrieval by detail_id or by context similarity
    - Optional background queue for asynchronous saves
    """

    def __init__(self, use_llm_for_merge: bool = False, similarity_threshold: float = 0.75) -> None:
        self.use_llm_for_merge = use_llm_for_merge
        self.similarity_threshold = float(similarity_threshold)
        self._queue: "Queue[dict]" = Queue()
        self._thread: threading.Thread | None = None
        self._stop_flag = threading.Event()
        self._excluded_entries_cache: Dict[str, List[Dict[str, Any]]] = {}

    def _set_excluded_entries(self, db_name: str, entries: List[Dict[str, Any]] | None) -> None:
        self._excluded_entries_cache[str(db_name or "").strip()] = [deepcopy(item) for item in (entries or []) if isinstance(item, dict)]

    def _get_excluded_entries(self, db_name: str) -> List[Dict[str, Any]]:
        return [deepcopy(item) for item in self._excluded_entries_cache.get(str(db_name or "").strip(), [])]

    def clear_excluded_cache(self, db_name: str | None = None) -> None:
        if db_name is None:
            self._excluded_entries_cache.clear()
        else:
            self._excluded_entries_cache.pop(str(db_name or "").strip(), None)

    # ------------------------- Conversion helpers -------------------------
    def prepare_from_detail_records(
        self,
        detail_records: List[Dict[str, Any]],
        source_db_name: str | None = None,
    ) -> List[Dict[str, Any]]:
        """Convert evaluator `DetailRecord` dicts into canonical preference entries.

        Expected flexible input keys on each `detail_record`:
        - detail_id (preferred)
        - ambiguity_context or ambiguity_context_text
        - options: list of option strings OR list of [opt, freq]
        - selected_options: optional set/list of chosen option strings (freq increment)
        - node_id: optional parent node id
        """
        out: List[Dict[str, Any]] = []
        for dr in detail_records or []:
            detail_id = str(dr.get("detail_id") or dr.get("id") or "").strip() or None
            node_id = str(dr.get("node_id") or "").strip() or None
            ctx = str(dr.get("ambiguity_context") or dr.get("ambiguity_context_text") or dr.get("AmbiContext") or "").strip()
            if not ctx:
                continue

            raw_opts = dr.get("options") or dr.get("AmbiOpts") or []
            opts: List[Dict[str, Any]] = []
            # options may be list[dict], list[str], or list[list]
            for item in raw_opts:
                if isinstance(item, dict):
                    # New format: {"snippet": str, "interpretation": str, ...}
                    snippet = str(item.get("snippet") or "").strip()
                    interp = str(item.get("interpretation") or "").strip()
                    if snippet:
                        opts.append({"snippet": snippet, "interpretation": interp, "freq": 0})
                elif isinstance(item, (list, tuple)) and len(item) >= 1:
                    # Legacy format: [opt_str, freq]
                    opt_str = str(item[0]).strip()
                    freq = int(item[1]) if len(item) >= 2 and isinstance(item[1], int) else 0
                    if opt_str:
                        opts.append({"snippet": opt_str, "interpretation": "", "freq": max(0, freq)})
                else:
                    # Legacy format: bare string
                    opt_str = str(item).strip()
                    if opt_str:
                        opts.append({"snippet": opt_str, "interpretation": "", "freq": 0})

            # If selected options supplied, bump their freq field to 1 (they represent user choice)
            selected = dr.get("selected_options") or dr.get("selected") or []
            selected_set = {str(s).strip() for s in selected or []}
            if selected_set:
                for opt in opts:
                    if opt["snippet"] in selected_set:
                        opt["freq"] += 1

            entry: Dict[str, Any] = {"AmbiContext": ctx, "AmbiOpts": opts}
            source_dbs = _merge_source_db_names(dr.get("source_DBs"), source_db_name)
            if source_dbs:
                entry["source_DBs"] = source_dbs
            if detail_id:
                entry["source_detail_id"] = detail_id
            if node_id:
                entry["source_node_id"] = node_id
            occ = dr.get("example_occurrences")
            if occ:
                entry["example_occurrences"] = occ
            else:
                entry.setdefault("example_occurrences", [])
            out.append(entry)
        return out

    # ------------------------- Persistence -------------------------
    def save_from_detail_records(self, db_name: str, detail_records: List[Dict[str, Any]], similarity_threshold: float | None = None) -> Dict[str, Any]:
        """Merge and persist preference entries derived from `detail_records`.

        This writes atomically to the base path returned by `_base_path_for_db`.
        The persisted entries will include optional provenance fields when available.
        """
        similarity_threshold = float(similarity_threshold or self.similarity_threshold)
        logger.info("PreferenceLearner.save_from_detail_records called for db=%s, entries=%d", db_name, len(detail_records or []))
        new_entries = self.prepare_from_detail_records(detail_records, source_db_name=db_name)
        if not new_entries:
            return {"success": False, "error": "no entries", "added": 0}

        # Load existing base (may contain arbitrary keys)
        excluded_entries: List[Dict[str, Any]] = []
        existing = _load_preference_base(db_name, excluded_sink=excluded_entries) or []
        self._set_excluded_entries(db_name, excluded_entries)

        # Use existing merge helper to compute merged canonical counts
        merged = merge_preferences(existing, new_entries, similarity_threshold)

        # Augment merged entries with provenance collected from existing/new entries where similar
        augmented: List[Dict[str, Any]] = []
        for m in merged:
            mctx = str(m.get("AmbiContext") or "").strip()
            prov_detail_ids = set()
            prov_node_ids = set()
            example_occ = []

            # collect from new_entries
            for ne in new_entries:
                if _similar(mctx, str(ne.get("AmbiContext") or "")) >= similarity_threshold:
                    if ne.get("source_detail_id"):
                        prov_detail_ids.add(str(ne.get("source_detail_id")))
                    if ne.get("source_node_id"):
                        prov_node_ids.add(str(ne.get("source_node_id")))
                    occ = ne.get("example_occurrences")
                    if isinstance(occ, list):
                        example_occ.extend(occ)

            # collect from existing preserved provenance if available
            for ex in existing:
                if _similar(mctx, str(ex.get("AmbiContext") or "")) >= similarity_threshold:
                    if ex.get("source_detail_id"):
                        prov_detail_ids.add(str(ex.get("source_detail_id")))
                    if ex.get("source_node_id"):
                        prov_node_ids.add(str(ex.get("source_node_id")))
                    occ = ex.get("example_occurrences")
                    if isinstance(occ, list):
                        example_occ.extend(occ)

            # attach provenance when present
            maybe = dict(m)
            if prov_detail_ids:
                maybe["source_detail_id"] = list(sorted(prov_detail_ids))
            if prov_node_ids:
                maybe["source_node_id"] = list(sorted(prov_node_ids))
            if example_occ:
                maybe["example_occurrences"] = example_occ
            augmented.append(maybe)

        final_entries = augmented + self._get_excluded_entries(db_name)

        # Write atomically
        p = _base_path_for_db(db_name)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            tmp = p.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(final_entries, fh, ensure_ascii=False, indent=2)
            tmp.replace(p)
        except Exception as exc:
            logger.exception("Failed to write preference base for db=%s: %s", db_name, exc)
            return {"success": False, "error": str(exc)}

        return {"success": True, "added": max(0, len(final_entries) - (len(existing) + len(excluded_entries))), "total": len(final_entries)}

    def save_from_answered_specifying_questions(self, db_name: str, state: Any) -> Dict[str, Any]:
        """Extract preferences from answered specifying questions and save to base.
        
        Workflow:
        1. Collect answered specifying questions from state.archive_specifying_questions (marked as answered)
        2. For each question, find corresponding DetailRecordScoredAmbiEntry in node history
        3. Extract selected choices from question answer
        4. Call save_preferences_from_scored_entries with selections
        
        Returns dict with save statistics.
        """
        logger.info("PreferenceLearner.save_from_answered_specifying_questions called for db=%s", db_name)
        
        try:
            # Collect answered questions from archive (questions marked as answered)
            archived_qs = list(getattr(state, "archive_specifying_questions", []) or [])
            answered_qs = [q for q in archived_qs if q.get("status") == "answered" and q.get("answer")]
            
            if not answered_qs:
                logger.info("No answered specifying questions found")
                return {"success": True, "entries_saved": 0, "entries_updated": 0, "entries_new": 0, "error": ""}
            
            # Build mapping of question detail_id -> selected choices
            selected_options_by_entry_id: Dict[str, set[str]] = {}
            scored_entries_with_detail: List[Dict[str, Any]] = []
            
            for q in answered_qs:
                detail_id = str(q.get("detail_id", "")).strip()
                if not detail_id:
                    logger.debug("Question missing detail_id: %s", q.get("question_id", "?"))
                    continue
                
                # Extract selected choices from answer
                answer = q.get("answer") or {}
                selected_choices = set()
                
                # Handle multi-choice selections
                multi_choices = answer.get("multi_choices") or []
                for c in multi_choices:
                    raw_choice = str(c or "").strip()
                    if not raw_choice:
                        continue
                    selected_choices.add(_normalize_choice_text(raw_choice))
                
                # Handle free text answer (if present, treat as additional selection context)
                free_text = str(answer.get("free_text", "")).strip()
                if free_text:
                    logger.debug("Question %s has free text answer: %s (not yet mapped to option)", 
                               detail_id, free_text)
                    # TODO: optionally call LLM to map free_text to an option snippet
                
                if selected_choices:
                    selected_options_by_entry_id[detail_id] = selected_choices
                    logger.debug("Mapped question %s to selections: %s", detail_id, selected_choices)
            
            if not selected_options_by_entry_id:
                logger.info("No selections mapped from answered questions")
                return {"success": True, "entries_saved": 0, "entries_updated": 0, "entries_new": 0, "error": ""}
            
            # Find corresponding scored entry nodes in history for each detail_id
            all_nodes = getattr(state, "nodes", [])
            for node in all_nodes or []:
                detail_records = getattr(node, "detail_records", []) or []
                for dr in detail_records:
                    # Check if this is a ScoredAmbiEntry with matching detail_id
                    dr_id = str(dr.get("detail_id", dr.get("id", ""))).strip()
                    if dr_id in selected_options_by_entry_id:
                        # Extract options from scored entry (AmbiType, Options/Options fields)
                        scored_entries_with_detail.append(dr)
            
            if not scored_entries_with_detail:
                logger.info("No scored ambi entries found for answered questions")
                return {"success": True, "entries_saved": 0, "entries_updated": 0, "entries_new": 0, "error": ""}
            
            # Call save_preferences_from_scored_entries with the scored entries and selections
            result = save_preferences_from_scored_entries(
                db_name=db_name,
                scored_entries=scored_entries_with_detail,
                selected_options_by_entry_id=selected_options_by_entry_id,
                state=state,
                similarity_threshold=self.similarity_threshold,
                source_db_name=db_name,
                excluded_entries=self._get_excluded_entries(db_name),
            )
            
            logger.info("save_from_answered_specifying_questions result: %s", result)
            return result
        
        except Exception as exc:
            logger.exception("save_from_answered_specifying_questions failed: %s", exc)
            return {
                "success": False,
                "entries_saved": 0,
                "entries_updated": 0,
                "entries_new": 0,
                "error": str(exc)
            }

    # ------------------------- Retrieval -------------------------
    def retrieve_by_detail_or_context(self, db_name: str, detail_record: Dict[str, Any] | None = None, contexts: List[str] | None = None, similarity_threshold: float | None = None) -> List[Dict[str, Any]]:
        """Retrieve matching preference entries.

        Priority:
          1) Exact match by `source_detail_id` when detail_record contains `detail_id`.
          2) Similarity match on `AmbiContext` for provided contexts.
        Returns list of matched entries (possibly empty).
        """
        similarity_threshold = float(similarity_threshold or self.similarity_threshold)
        excluded_entries: List[Dict[str, Any]] = []
        base = _load_preference_base(db_name, excluded_sink=excluded_entries) or []
        self._set_excluded_entries(db_name, excluded_entries)
        results: List[Dict[str, Any]] = []

        # 1) detail_id exact match
        if detail_record:
            did = str(detail_record.get("detail_id") or detail_record.get("id") or "").strip()
            if did:
                for e in base:
                    s = e.get("source_detail_id")
                    if not s:
                        continue
                    # stored provenance could be list or single
                    if (isinstance(s, list) and did in s) or (isinstance(s, str) and s == did):
                        results.append({"match_type": "detail_id", "entry": e, "score": 1.0})
                if results:
                    return results

        # 2) similarity search over contexts
        queries = [c for c in (contexts or []) if str(c).strip()]
        for q in queries:
            best_score = -1.0
            best_entry = None
            for e in base:
                score = _similar(str(e.get("AmbiContext") or ""), q)
                if score > best_score:
                    best_score = score
                    best_entry = e
            if best_entry is not None and best_score >= similarity_threshold:
                results.append({"match_type": "similarity", "entry": best_entry, "score": float(best_score)})

        return results

    # ------------------------- Background queue -------------------------
    def start_background_saver(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop_background_saver(self, wait: bool = True) -> None:
        self._stop_flag.set()
        if wait and self._thread:
            self._thread.join(timeout=5.0)

    def enqueue_save(self, db_name: str, detail_records: List[Dict[str, Any]], similarity_threshold: float | None = None) -> None:
        self._queue.put({"db_name": db_name, "detail_records": detail_records, "similarity_threshold": similarity_threshold})

    def _run_loop(self) -> None:
        while not self._stop_flag.is_set():
            try:
                job = self._queue.get(timeout=0.5)
            except Empty:
                continue
            try:
                db_name = job.get("db_name")
                detail_records = job.get("detail_records")
                similarity_threshold = job.get("similarity_threshold")
                if db_name and detail_records:
                    self.save_from_detail_records(db_name, detail_records, similarity_threshold)
            except Exception:
                logger.exception("PreferenceLearner background save failed")
            finally:
                self._queue.task_done()


__all__ = ["PreferenceLearner"]
