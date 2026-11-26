from __future__ import annotations

from pathlib import Path
import json
from copy import deepcopy
from typing import Any, List, Dict
from difflib import SequenceMatcher

from config import SETTINGS
from utils.logging_config import get_logger
from utils.model_factory import create_model
from utils.similarity import _similar
from detector.prompts import TAXONOMY_GRAMMAR_GUIDANCE, TAXONOMY_USERQUERY_GUIDANCE, TAXONOMY_DB_AMBICOLUMN, TAXONOMY_DB_AMBIVALUE, TAXONOMY_DB_AMBIVOP, TAXONOMY_ENDING, call_model_text

logger = get_logger(__name__)


BASE_DIR_NAME = "AmbiguityPreference"
BASE_FILE_NAME = "base.json"


def _current_preference_base_scope() -> str:
    scope = str(getattr(SETTINGS, "preference_base_scope", "within_DB") or "within_DB").strip()
    return scope or "within_DB"


def _normalize_source_db_names(value: Any) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = []

    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _merge_source_db_names(*values: Any) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in _normalize_source_db_names(value):
            if item not in seen:
                seen.add(item)
                merged.append(item)
    return merged


def _entry_matches_db_scope(entry: Dict[str, Any], db_name: str, scope_mode: str | None = None) -> bool:
    scope = str(scope_mode or _current_preference_base_scope() or "within_DB").strip().lower()
    if scope == "cross_db":
        return True
    source_dbs = _normalize_source_db_names((entry or {}).get("source_DBs"))
    if not source_dbs:
        return True
    return str(db_name or "").strip() in source_dbs


def _load_preference_base_raw(db_name: str) -> List[Dict[str, Any]]:
    """Load the raw preference base for `db_name` without scope filtering."""
    p = _base_path_for_db(db_name)
    try:
        if not p.exists():
            return []
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, list):
                return data
            return []
    except Exception:
        logger.exception("Failed to load preference base for db=%s", db_name)
        return []


def _base_path_for_db(db_name: str) -> Path:
    return Path(SETTINGS.created_dbs_dir) / db_name / BASE_DIR_NAME / BASE_FILE_NAME


def _load_preference_base(db_name: str, excluded_sink: List[Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
    """Load preference base entries usable for `db_name` under the configured scope.

    If `excluded_sink` is provided, entries filtered out by the current scope are appended to it.
    """
    raw_entries = _load_preference_base_raw(db_name)
    scope_mode = _current_preference_base_scope()
    usable: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for item in raw_entries:
        if not isinstance(item, dict):
            continue
        if _entry_matches_db_scope(item, db_name, scope_mode=scope_mode):
            usable.append(item)
        else:
            excluded.append(item)
    if excluded_sink is not None:
        excluded_sink.extend(excluded)
    return usable


def _normalize_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    ctx = str(entry.get("AmbiContext") or "").strip()
    raw_opts = list(entry.get("AmbiOpts") or [])
    opts: list[dict[str, Any]] = []
    for item in raw_opts:
        if isinstance(item, dict):
            # New format: {"snippet": str, "interpretation": str, "freq": int}
            snippet = str(item.get("snippet") or "").strip()
            interp = str(item.get("interpretation") or "").strip()
            try:
                freq = int(item.get("freq", 0))
            except (ValueError, TypeError):
                freq = 0
            if snippet:
                opts.append({"snippet": snippet, "interpretation": interp, "freq": max(0, freq)})
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            # Legacy format: [opt_str, freq]
            opt_str = str(item[0]).strip()
            if not opt_str:
                continue
            try:
                freq = int(item[1])
            except (ValueError, TypeError):
                try:
                    freq = 1 if float(item[1]) > 0 else 0
                except (ValueError, TypeError):
                    freq = 0
            opts.append({"snippet": opt_str, "interpretation": "", "freq": max(0, freq)})
    result: dict[str, Any] = {"AmbiContext": ctx, "AmbiOpts": opts}
    # Preserve extra top-level fields (source_detail_id, etc.) through normalization
    if isinstance(entry, dict):
        for k, v in entry.items():
            if k not in ("AmbiContext", "AmbiOpts") and k not in result:
                result[k] = v
    return result


def _normalize_choice_text(text: Any) -> str:
    """Normalize a displayed choice or snippet for comparison."""
    raw = str(text or "").strip()
    if not raw:
        return ""
    if " -- " in raw:
        raw = raw.split(" -- ", 1)[0].strip()
    raw = raw.strip().strip("`").strip().strip('"').strip("'")
    return " ".join(raw.split())


def _option_match_keys(opt: Any) -> set[str]:
    """Return normalized aliases for one option payload."""
    keys: set[str] = set()
    if isinstance(opt, dict):
        snippet = _normalize_choice_text(
            opt.get("snippet") or opt.get("SQL") or opt.get("sql") or opt.get("option") or opt.get("content") or ""
        )
        interp = _normalize_choice_text(opt.get("interpretation") or opt.get("description") or opt.get("note") or "")
        if snippet:
            keys.add(snippet)
        if snippet and interp:
            keys.add(_normalize_choice_text(f"{snippet} -- {interp}"))
    else:
        keys.add(_normalize_choice_text(opt))
    return {item for item in keys if item}


def _best_context_match(entries: List[Dict[str, Any]], query_ctx: str) -> tuple[int, float]:
    best_idx = -1
    best_score = -1.0
    q = str(query_ctx or "").strip()
    for idx, entry in enumerate(entries):
        ectx = str(entry.get("AmbiContext") or "").strip()
        score = _similar(ectx, q)
        if score > best_score:
            best_score = score
            best_idx = idx
    return best_idx, best_score


def _build_llm_merge_prompt(existing_entry: Dict[str, Any], new_entry: Dict[str, Any]) -> str:
    """Build LLM prompt to decide if two ambiguity entries are the same type.
    
    Returns a prompt asking the LLM to:
    1) Classify if both entries represent the same ambiguity type
    2) If SAME, provide a merged entry with combined options and updated freq counts
    3) Include taxonomy definitions for reference
    """
    existing_ctx = existing_entry.get("AmbiContext", "")
    existing_opts_str = json.dumps(existing_entry.get("AmbiOpts", []), ensure_ascii=False, indent=2)
    
    new_ctx = new_entry.get("AmbiContext", "")
    new_opts_str = json.dumps(new_entry.get("AmbiOpts", []), ensure_ascii=False, indent=2)
    
    prompt = f"""You are an expert in analyzing SQL query ambiguity entries to consolidate user preferences.

## Taxonomy of Ambiguity Types

{TAXONOMY_GRAMMAR_GUIDANCE}

{TAXONOMY_USERQUERY_GUIDANCE}

{TAXONOMY_DB_AMBICOLUMN}

{TAXONOMY_DB_AMBIVALUE}

{TAXONOMY_DB_AMBIVOP}

{TAXONOMY_ENDING}

---

## Task 1: Determine if Two Entries Represent the Same Ambiguity Type

Decision process:
1. **Classification**: Do both entries represent the SAME type of ambiguity (AmbiScope, AmbiAttach, AmbiIntent, AmbiColumn, AmbiValue, AmbiOp)?
2. **Decision**: decide either "SAME" or "NOT_SAME"

## if "SAME" -> Task 2: Merge the new and old into one entry

**If SAME**, provide a merged entry following this JSON format:
```json
{{
  "AmbiContext": "combined context (should reflect both entries)",
  "AmbiOpts": [
    {{"snippet": "...", "interpretation": "...", "freq": X}},
    ...
  ]
}}
```
Important: The snippet must be the MINIMAL SQL fragment that captures the ambiguity, not the whole SQL. The goal is to highlight the specific difference that leads to the execution difference. You will be seriously punished if you include more than needed


Merging rules and steps:
1. For each option in the new entry: if it existed in the new_entry with freq>0, consider as valid options to add
2. For each valid options, expect to increament freq by 1.
3. Merge into existing if applicable: for each new valid options, if an exisitng entry means the same, directly increment the freq by 1.
4. Add new options: for each remaining new valid options, create new option entry, if user select it, set freq=1, otherwise set freq=0

## Response Format

Return ONLY a JSON object:
```json
{{
  "decision": "SAME" | "NOT_SAME",
  "reasoning": "brief explanation of why they are/are not the same type",
  "merged_entry": {{...}} (only if decision is "SAME")
}}
```
---

## Current task:

### Existing Entry (in preference base):
AmbiContext: {existing_ctx}
AmbiOpts:
{existing_opts_str}

### New Entry (from current session):
AmbiContext: {new_ctx}
AmbiOpts:
{new_opts_str}

"""
    logger.info("Built LLM merge prompt for existing vs new entry with similarity=%.2f:\n%s", _similar(existing_ctx, new_ctx), prompt.split("## Current task:")[1].strip())
    return prompt


def _decide_entry_similarity_with_llm(existing_entry: Dict[str, Any], new_entry: Dict[str, Any]) -> Dict[str, Any]:
    """Call LLM to determine if two entries are the same ambiguity type.
    
    Returns dict with keys:
    - decision: "SAME" | "NOT_SAME"
    - reasoning: brief explanation
    - merged_entry: dict (only if SAME) with {"AmbiContext": str, "AmbiOpts": [...]}
    - success: bool
    - error: str (if success=False)
    """
    try:
        model = create_model(LLM_choice="Default")
        prompt = _build_llm_merge_prompt(existing_entry, new_entry)
        
        response_text = call_model_text(model, prompt, max_tokens=2048)
        logger.debug("LLM merge decision response:\n%s", response_text)
        
        # Try to parse JSON from response
        import re
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if not json_match:
            logger.warning("Could not find JSON in LLM response, treating as NOT_SAME")
            return {
                "decision": "NOT_SAME",
                "reasoning": "LLM response parsing failed",
                "success": False,
                "error": "No JSON found in response"
            }
        
        result = json.loads(json_match.group())
        decision = str(result.get("decision", "NOT_SAME")).strip().upper()
        
        if decision not in ("SAME", "NOT_SAME"):
            decision = "NOT_SAME"

        merged_entry = result.get("merged_entry") if decision == "SAME" else None
        if decision == "SAME" and isinstance(merged_entry, dict):
            merged_entry = _normalize_entry(merged_entry)
            merged_source_dbs = _merge_source_db_names(
                existing_entry.get("source_DBs"),
                new_entry.get("source_DBs"),
                merged_entry.get("source_DBs"),
            )
            if merged_source_dbs:
                merged_entry["source_DBs"] = merged_source_dbs
        
        return {
            "decision": decision,
            "reasoning": str(result.get("reasoning", "")),
            "merged_entry": merged_entry,
            "success": True,
            "error": ""
        }
    except Exception as exc:
        logger.exception("LLM merge decision failed: %s", exc)
        return {
            "decision": "NOT_SAME",
            "reasoning": "LLM call failed, defaulting to new entry",
            "success": False,
            "error": str(exc)
        }


def retrieve_preference_base(
    db_name: str,
    ambiguity_contexts: List[str] | None = None,
    similarity_threshold: float = 0.75,
) -> List[Dict[str, Any]]:
    """Retrieve preference base entries.

    - If `ambiguity_contexts` is omitted/empty, return full base entries.
    - If provided, return best matched entries above threshold for each context, as
      [{"query_context", "similarity", "entry"}, ...].
    """
    base = [_normalize_entry(item) for item in _load_preference_base(db_name)]
    if not ambiguity_contexts:
        return base

    matched: list[dict[str, Any]] = []
    for ctx in ambiguity_contexts:
        q = str(ctx or "").strip()
        if not q:
            continue
        best_score = -1.0
        best_entry: dict[str, Any] | None = None
        for entry in base:
            score = _similar(q, str(entry.get("AmbiContext") or ""))
            if score > best_score:
                best_score = score
                best_entry = entry
        if best_entry is not None and best_score >= similarity_threshold:
            matched.append(
                {
                    "query_context": q,
                    "similarity": float(best_score),
                    "entry": best_entry,
                }
            )
    return matched


def merge_preferences(existing: List[Dict[str, Any]], new_entries: List[Dict[str, Any]], similarity_threshold: float = 0.75, use_llm_for_merge: bool = True) -> List[Dict[str, Any]]:
    """Merge `new_entries` into `existing` in-memory and return merged list.

    Entry format expected: {"AmbiContext": str, "AmbiOpts": [{"snippet": str, "interpretation": str, "freq": int}, ...]}
    
    Merge strategy (hybrid):
    - If similarity >= 0.9: direct freq merge (high confidence)
    - If 0.7 <= similarity < 0.9 and use_llm_for_merge: call LLM to decide (medium confidence)
    - If similarity < threshold or LLM decides NOT_SAME: add as new entry
    - If LLM decides SAME: use merged_entry from LLM
    """
    merged = [_normalize_entry(e) for e in existing]
    llm_merge_count = 0
    
    for ne in new_entries:
        norm_ne = _normalize_entry(ne)
        nctx = str(norm_ne.get("AmbiContext") or "").strip()
        nopts = list(norm_ne.get("AmbiOpts") or [])
        matched = False
        
        # Find best matching existing entry by similarity
        best_score = -1.0
        best_idx = -1
        for idx, ex in enumerate(merged):
            ectx = str(ex.get("AmbiContext") or "").strip()
            score = _similar(ectx, nctx)
            if score > best_score:
                best_score = score
                best_idx = idx
        
        if best_idx >= 0 and best_score >= similarity_threshold:
            ex = merged[best_idx]
            
            # High similarity: direct merge
            if best_score >= 0.9:
                logger.info("Direct merge at similarity=%.2f for AmbiContext: %s", best_score, nctx)
                existing_opts: dict[str, dict[str, Any]] = {}
                for o in ex.get("AmbiOpts") or []:
                    if isinstance(o, dict):
                        snip = o.get("snippet", "")
                        existing_opts.setdefault(snip, {"snippet": snip, "interpretation": o.get("interpretation", ""), "freq": 0})
                        existing_opts[snip]["freq"] += o.get("freq", 0)
                for opt in nopts:
                    snip = opt.get("snippet", "")
                    if snip in existing_opts:
                        existing_opts[snip]["freq"] += opt.get("freq", 0)
                        if opt.get("interpretation") and not existing_opts[snip]["interpretation"]:
                            existing_opts[snip]["interpretation"] = opt["interpretation"]
                    else:
                        existing_opts[snip] = dict(opt)
                ex["AmbiOpts"] = list(existing_opts.values())
                merged_source_dbs = _merge_source_db_names(ex.get("source_DBs"), norm_ne.get("source_DBs"))
                if merged_source_dbs:
                    ex["source_DBs"] = merged_source_dbs
                matched = True

            # Medium similarity: use LLM to decide if same
            elif best_score >= 0.7 and use_llm_for_merge:
                logger.info("LLM merge decision at similarity=%.2f for AmbiContext: %s", best_score, nctx)
                llm_result = _decide_entry_similarity_with_llm(ex, norm_ne)

                if llm_result.get("success") and llm_result.get("decision") == "SAME" and llm_result.get("merged_entry"):
                    # LLM says SAME: use merged_entry
                    merged_entry = _normalize_entry(llm_result["merged_entry"])
                    ex["AmbiContext"] = merged_entry.get("AmbiContext", ex.get("AmbiContext"))
                    ex["AmbiOpts"] = merged_entry.get("AmbiOpts", [])
                    merged_source_dbs = _merge_source_db_names(ex.get("source_DBs"), norm_ne.get("source_DBs"), merged_entry.get("source_DBs"))
                    if merged_source_dbs:
                        ex["source_DBs"] = merged_source_dbs
                    llm_merge_count += 1
                    matched = True
                    logger.info("LLM merge successful: decision=SAME, reasoning=%s", llm_result.get("reasoning", ""))
                else:
                    # LLM says NOT_SAME or error: treat as new entry
                    logger.info("LLM merge decision=NOT_SAME or error, adding as new entry (reasoning=%s)", llm_result.get("reasoning", ""))
                    matched = False

            # Medium similarity but no LLM: direct merge as fallback
            elif best_score >= 0.7:
                logger.info("Direct merge (LLM disabled) at similarity=%.2f for AmbiContext: %s", best_score, nctx)
                existing_opts: dict[str, dict[str, Any]] = {}
                for o in ex.get("AmbiOpts") or []:
                    if isinstance(o, dict):
                        snip = o.get("snippet", "")
                        existing_opts.setdefault(snip, {"snippet": snip, "interpretation": o.get("interpretation", ""), "freq": 0})
                        existing_opts[snip]["freq"] += o.get("freq", 0)
                for opt in nopts:
                    snip = opt.get("snippet", "")
                    if snip in existing_opts:
                        existing_opts[snip]["freq"] += opt.get("freq", 0)
                        if opt.get("interpretation") and not existing_opts[snip]["interpretation"]:
                            existing_opts[snip]["interpretation"] = opt["interpretation"]
                    else:
                        existing_opts[snip] = dict(opt)
                ex["AmbiOpts"] = list(existing_opts.values())
                merged_source_dbs = _merge_source_db_names(ex.get("source_DBs"), norm_ne.get("source_DBs"))
                if merged_source_dbs:
                    ex["source_DBs"] = merged_source_dbs
                matched = True

        if not matched:
            merged.append(norm_ne)
            logger.debug("Added new preference entry for AmbiContext: %s", nctx)
    
    logger.info("merge_preferences completed: %d entries merged, %d LLM decisions used", len(merged), llm_merge_count)
    return merged


def save_preference_base(
    db_name: str,
    new_entries: List[Dict[str, Any]],
    similarity_threshold: float = 0.75,
    use_llm_for_merge: bool = True,
    excluded_entries: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Merge and persist preference base for db_name. Returns a summary dict.

    This function writes atomically (write to tmp then rename).
    If use_llm_for_merge=True, will call LLM for medium-similarity matches (0.7-0.9).
    """
    p = _base_path_for_db(db_name)
    p.parent.mkdir(parents=True, exist_ok=True)
    raw_existing = _load_preference_base_raw(db_name)
    existing = []
    raw_excluded: list[dict[str, Any]] = []
    scope_mode = _current_preference_base_scope()
    for item in raw_existing:
        if not isinstance(item, dict):
            continue
        if _entry_matches_db_scope(item, db_name, scope_mode=scope_mode):
            existing.append(_normalize_entry(item))
        else:
            raw_excluded.append(_normalize_entry(item))

    preserved_excluded = [
        _normalize_entry(item)
        for item in (excluded_entries if excluded_entries is not None else raw_excluded)
        if isinstance(item, dict)
    ]

    merged = merge_preferences(existing, new_entries, similarity_threshold=similarity_threshold, use_llm_for_merge=use_llm_for_merge)

    updated_entries: list[dict[str, Any]] = []
    seen_final_indexes: set[int] = set()
    for new_entry in new_entries or []:
        nctx = str(new_entry.get("AmbiContext") or "").strip()
        if not nctx:
            continue

        final_idx, final_score = _best_context_match(merged, nctx)
        if final_idx < 0 or final_idx in seen_final_indexes:
            continue
        seen_final_indexes.add(final_idx)

        old_idx, old_score = _best_context_match(existing, nctx)
        final_entry = merged[final_idx]
        old_entry = existing[old_idx] if old_idx >= 0 and old_score >= similarity_threshold else None

        old_opts_raw = list((old_entry or {}).get("AmbiOpts") or [])
        final_opts_raw = list(final_entry.get("AmbiOpts") or [])
        old_opt_map: dict[str, dict[str, Any]] = {}
        for opt in old_opts_raw:
            if not isinstance(opt, dict):
                continue
            key = _normalize_choice_text(opt.get("snippet") or "")
            if key:
                old_opt_map[key] = opt

        option_diffs: list[dict[str, Any]] = []
        for opt in final_opts_raw:
            if not isinstance(opt, dict):
                continue
            snippet = str(opt.get("snippet") or "").strip()
            interp = str(opt.get("interpretation") or "").strip()
            try:
                new_freq = int(opt.get("freq", 0))
            except Exception:
                new_freq = 0

            key = _normalize_choice_text(snippet)
            old_opt = old_opt_map.get(key)
            old_freq: int | None = None
            if old_opt is not None:
                try:
                    old_freq = int(old_opt.get("freq", 0))
                except Exception:
                    old_freq = 0

            if old_opt is None:
                status = "selected_new" if new_freq > 0 else "new"
            elif old_freq is not None and new_freq > old_freq:
                status = "incremented"
            elif old_freq is not None and new_freq == old_freq:
                status = "unchanged"
            else:
                status = "decremented"

            option_diffs.append(
                {
                    "snippet": snippet,
                    "interpretation": interp,
                    "old_freq": old_freq,
                    "new_freq": new_freq,
                    "delta": (new_freq - old_freq) if old_freq is not None else new_freq,
                    "status": status,
                }
            )

        inc_count = sum(1 for item in option_diffs if item.get("status") == "incremented")
        new_count = sum(1 for item in option_diffs if item.get("status") in {"new", "selected_new"})
        updated_entries.append(
            {
                "AmbiContext": final_entry.get("AmbiContext", nctx),
                "source_context": nctx,
                "decision": "new" if old_entry is None else "merged",
                "match_score": float(final_score),
                "previous_match_score": float(old_score) if old_entry is not None else None,
                "change_summary": f"{inc_count} option(s) incremented, {new_count} option(s) newly introduced",
                "option_diffs": option_diffs,
                "old_opts": old_opts_raw,
                "new_opts": final_opts_raw,
            }
        )

    final_entries: list[dict[str, Any]] = []
    for entry in merged:
        maybe = dict(entry)
        source_dbs = _merge_source_db_names(maybe.get("source_DBs"), db_name)
        if source_dbs:
            maybe["source_DBs"] = source_dbs
        final_entries.append(maybe)

    final_entries.extend(preserved_excluded)

    # compute summary
    added = len(final_entries) - len(raw_existing)
    try:
        tmp = p.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(final_entries, fh, ensure_ascii=False, indent=2)
        tmp.replace(p)
    except Exception as exc:
        logger.exception("Failed to save preference base for db=%s: %s", db_name, exc)
        return {"success": False, "error": str(exc)}
    return {"success": True, "added": added, "total": len(final_entries), "updated_entries": updated_entries, "merged_entries": merged}


def _fmt_opt(opt: Any) -> str:
    """Format a single preference option, handling both dict and list formats."""
    if isinstance(opt, dict):
        snippet = opt.get("snippet", "")
        interp = opt.get("interpretation", "")
        freq = opt.get("freq", 0)
        text = f"{snippet} -- {interp}" if interp else snippet
        return f"{text} (f={freq})"
    elif isinstance(opt, (list, tuple)) and len(opt) >= 2:
        return f"{opt[0]} (f={opt[1]})"
    return str(opt)


def _compute_merged_entry_from_options(
    selected_option_snippets: set[str],
    scored_entry_record: Dict[str, Any] | None = None,
    all_options_with_scores: List[Dict[str, Any]] | None = None,
    source_db_name: str | None = None,
) -> Dict[str, Any]:
    """Compute preference entry format for user selection.
    
    Rules for freq:
    - Selected options: freq = 1 (for new entries)
    - Unselected but score > 0: freq = 0 (for new entries, indicates valid alternative)
    - Preserve unselected scored options to show user considered all alternatives
    
    Returns dict with format:
    {
        "AmbiContext": "...",
        "AmbiOpts": [
            {"snippet": "...", "interpretation": "...", "freq": int (0 or 1 for new)},
            ...
        ]
    }
    """
    entry = {}
    selected_norm = {
        _normalize_choice_text(item)
        for item in (selected_option_snippets or set())
        if _normalize_choice_text(item)
    }
    
    # Extract AmbiContext from scored entry
    if scored_entry_record:
        entry["AmbiContext"] = str(scored_entry_record.get("AmbiContext", scored_entry_record.get("ambiguity_context", ""))).strip()
        source_dbs = _merge_source_db_names(scored_entry_record.get("source_DBs"), source_db_name)
        if source_dbs:
            entry["source_DBs"] = source_dbs
    elif source_db_name:
        entry["source_DBs"] = _merge_source_db_names(source_db_name)
    
    # Store source_detail_id for provenance tracking (enables cross-reference with specifying questions)
    if scored_entry_record:
        sid = str(scored_entry_record.get("detail_id") or scored_entry_record.get("id") or "").strip()
        if sid:
            entry["source_detail_id"] = sid

    # Build AmbiOpts with freq increments
    options = []
    if all_options_with_scores:
        for opt in all_options_with_scores:
            opt_snippet = str(opt.get("snippet", opt.get("SQL", opt.get("sql", "")))).strip()
            opt_interpretation = str(opt.get("interpretation", opt.get("description", ""))).strip()
            
            # Determine freq: 1 if selected, 0 otherwise (but still include in new entry)
            is_selected = bool(selected_norm.intersection(_option_match_keys(opt)))
            freq = 1 if is_selected else 0
            
            if opt_snippet:
                options.append({
                    "snippet": opt_snippet,
                    "interpretation": opt_interpretation,
                    "freq": freq
                })
    
    entry["AmbiOpts"] = options
    return entry


def save_preferences_from_scored_entries(
    db_name: str,
    scored_entries: List[Dict[str, Any]],
    selected_options_by_entry_id: Dict[str, set[str]],
    state: Any | None = None,
    similarity_threshold: float = 0.75,
    source_db_name: str | None = None,
    excluded_entries: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Save preferences from evaluated ambiguity entries with user selections.
    
    Args:
        db_name: database name
        scored_entries: list of DetailRecordScoredAmbiEntry as dicts
        selected_options_by_entry_id: dict mapping entry_id -> set of selected option snippets
        state: SystemState for node creation context
        similarity_threshold: for preference merge
    
    Returns:
        {
            "success": bool,
            "entries_saved": int,
            "entries_updated": int,
            "entries_new": int,
            "merged_with_llm": int,
            "error": str (if success=False)
        }
    """
    logger.info("save_preferences_from_scored_entries: processing %d entries", len(scored_entries or []))
    
    try:
        # Convert scored entries + selections to preference entries
        preference_entries = []
        for entry in scored_entries or []:
            entry_id = str(entry.get("detail_id", entry.get("id", ""))).strip()
            if not entry_id:
                logger.warning("Scored entry missing detail_id, skipping")
                continue
            
            selected_snippets = selected_options_by_entry_id.get(entry_id, set())
            if not selected_snippets:
                logger.debug("No selections for entry_id=%s, skipping", entry_id)
                continue
            
            # Extract all options from scored entry
            all_options = entry.get("Options", entry.get("options", entry.get("AmbiOpts", [])))
            
            # Compute merged preference entry with freq counts
            pref_entry = _compute_merged_entry_from_options(
                selected_option_snippets=selected_snippets,
                scored_entry_record=entry,
                all_options_with_scores=all_options,
                source_db_name=source_db_name or db_name,
            )
            
            if pref_entry.get("AmbiOpts"):
                preference_entries.append(pref_entry)
                logger.debug("Created preference entry: context=%s, options=%d", 
                           pref_entry.get("AmbiContext", "?"), len(pref_entry.get("AmbiOpts", [])))
        
        if not preference_entries:
            logger.info("No preference entries to save")
            return {"success": True, "entries_saved": 0, "entries_updated": 0, "entries_new": 0, "merged_with_llm": 0}

        # Save via the shared base-path merger so the worker and manager
        # follow the same merge/diff logic.
        save_result = save_preference_base(
            db_name,
            preference_entries,
            similarity_threshold=similarity_threshold,
            use_llm_for_merge=True,
            excluded_entries=excluded_entries,
        )
        if not save_result.get("success", False):
            return {
                "success": False,
                "entries_saved": 0,
                "entries_updated": 0,
                "entries_new": 0,
                "merged_with_llm": 0,
                "error": str(save_result.get("error", "save failed")),
            }

        entries_new = int(save_result.get("added", 0))
        entries_updated = max(0, len(preference_entries) - entries_new)

        # Sync in-memory state with saved preferences
        if state is not None and preference_entries:
            append_prefs = getattr(state, "append_current_round_preferences", None)
            if callable(append_prefs):
                append_prefs(preference_entries)
                logger.debug("Synced %d preference entries to currentRound_preferences in state", len(preference_entries))
        
        logger.info("Preferences saved: %d entries total, %d new, %d updated", int(save_result.get("total", 0)), entries_new, entries_updated)
        
        return {
            "success": True,
            "entries_saved": len(preference_entries),
            "entries_updated": entries_updated,
            "entries_new": entries_new,
            "merged_with_llm": 0,  # TODO: track from merge_preferences
            "updated_entries": list(save_result.get("updated_entries") or []),
            "merged_entries": list(save_result.get("merged_entries") or []),
            "error": ""
        }
    
    except Exception as exc:
        logger.exception("save_preferences_from_scored_entries failed: %s", exc)
        return {
            "success": False,
            "entries_saved": 0,
            "entries_updated": 0,
            "entries_new": 0,
            "merged_with_llm": 0,
            "error": str(exc)
        }


def prepare_user_preference_context(
    state: Any,
    db_name: str,
    ambiguity_contexts: List[str],
    similarity_threshold: float = 0.75,
) -> Dict[str, Any]:
    """Build prioritized user preference context for detector/evaluator.

    Query priorities:
    1) currentRound_preferences (highest) — user's ambiguity resolutions from the current round
    2) archive_preferences (medium) — user's resolutions from earlier rounds in this session, matched by context similarity
    3) Persistent base entries (lowest) — relevant historical decisions from previous sessions

    Returns dict with keys:
    - entries: list of formatted entries for all priorities
    - preferences_text: markdown-formatted string for inclusion in LLM prompts
    - sources: dict with counts for each priority level
    """
    contexts = [str(c or "").strip() for c in (ambiguity_contexts or []) if str(c or "").strip()]

    pri1: list[dict[str, Any]] = []  # Current round preferences
    pri2: list[dict[str, Any]] = []  # Archive preferences (previous rounds this session)
    pri3: list[dict[str, Any]] = []  # Persistent base entries

    # Build cross-reference lookup: detail_id -> specifying question info
    # Used to enrich formatting with question text and free_text
    q_lookup: dict[str, dict[str, Any]] = {}
    archived_qs = list(getattr(state, "archive_specifying_questions", []) or [])
    for q in archived_qs:
        did = str(q.get("detail_id") or "").strip()
        if did:
            q_lookup[did] = q

    # Priority 1: currentRound_preferences (always included)
    pri1 = list(getattr(state, "currentRound_preferences", []) or [])

    # Priority 2: archive_preferences, filtered by context similarity
    archive_prefs = list(getattr(state, "archive_preferences", []) or [])
    if contexts:
        for entry in archive_prefs:
            ctx = str(entry.get("AmbiContext") or "").strip()
            if ctx and any(_similar(ctx, ac) >= similarity_threshold for ac in contexts):
                pri2.append(entry)
    else:
        pri2 = list(archive_prefs)

    # Priority 3: Persistent base entries
    base_matched_raw = retrieve_preference_base(
        db_name=db_name,
        ambiguity_contexts=contexts,
        similarity_threshold=similarity_threshold,
    )
    for item in base_matched_raw or []:
        if isinstance(item, dict):
            entry = item.get("entry")
            if isinstance(entry, dict):
                pri3.append(entry)

    # Build markdown output
    md_parts: list[str] = []

    def _selected_and_not_selected_text(opts: list[dict[str, Any]]) -> tuple[str, str]:
        selected_opts = [_fmt_opt(o) for o in opts if o.get("freq", 0) > 0]
        selected_set = set(selected_opts)
        not_selected_opts = [_fmt_opt(o) for o in opts if _fmt_opt(o) not in selected_set]
        selected_text = ", ".join(selected_opts) if selected_opts else "(none)"
        not_selected_text = ", ".join(not_selected_opts) if not_selected_opts else "(none)"
        return selected_text, not_selected_text

    if pri1:
        md_parts.append("## User Specification from Current Round (1st Priority — Directly Addressing Current Ambiguity):\n")
        for e in pri1:
            ctx = e.get("AmbiContext", "")
            opts = e.get("AmbiOpts", [])
            selected_text, not_selected_text = _selected_and_not_selected_text(opts)

            # Cross-reference with specifying questions for richer display
            sid = str(e.get("source_detail_id") or "").strip()
            q_info = q_lookup.get(sid) if sid else None
            if q_info:
                q_text = str(q_info.get("question") or "").strip()
                free_text = str((q_info.get("answer") or {}).get("free_text") or "").strip()
                if q_text:
                    parts = [f"**Q:** {q_text}"]
                    parts.append(f"**Selected:** {selected_text}")
                    parts.append(f"**Not Selected:** {not_selected_text}")
                    if free_text:
                        parts.append(f"**Free text:** {free_text}")
                    md_parts.append("\n".join(parts))
                    continue

            # Fallback: entry-only format
            parts = [f"**Ambiguity Context:** {ctx}", f"**Selected:** {selected_text}", f"**Not Selected:** {not_selected_text}"]
            md_parts.append("\n".join(parts))

    if pri2:
        md_parts.append("## User Specifications from Previous Rounds in This Session (2nd Priority — Similar Ambiguities):\n")
        for e in pri2:
            ctx = e.get("AmbiContext", "")
            opts = e.get("AmbiOpts", [])
            selected_text, not_selected_text = _selected_and_not_selected_text(opts)

            # Cross-reference with specifying questions for richer display
            sid = str(e.get("source_detail_id") or "").strip()
            q_info = q_lookup.get(sid) if sid else None
            if q_info:
                q_text = str(q_info.get("question") or "").strip()
                free_text = str((q_info.get("answer") or {}).get("free_text") or "").strip()
                if q_text:
                    parts = [f"**Q:** {q_text}"]
                    parts.append(f"**Selected:** {selected_text}")
                    parts.append(f"**Not Selected:** {not_selected_text}")
                    if free_text:
                        parts.append(f"**Free text:** {free_text}")
                    md_parts.append("\n".join(parts))
                    continue

            # Fallback: entry-only format
            parts = [f"**Ambiguity Context:** {ctx}", f"**Selected:** {selected_text}", f"**Not Selected:** {not_selected_text}"]
            md_parts.append("\n".join(parts))

    if pri3:
        md_parts.append("## User Preference from Previous Conversations (3rd Priority — Historical Baseline):\n")
        md_parts.append("*Notes: `f=` means number of times the option has been specified as a preference. \n")
        for e in pri3:
            if not isinstance(e, dict):
                continue
            ctx = e.get("AmbiContext", "")
            opts = e.get("AmbiOpts", [])
            opts_text = "\n".join([_fmt_opt(o) for o in opts])
            md_parts.append(f"**AmbiContext:** {ctx}\n**AmbiOpts:** {opts_text}")

    all_entries = pri1 + pri2 + pri3
    preferences_text = "\n\n".join(md_parts).strip()

    logger.info("Prepared user preference context: %d entries (pri1=%d, pri2=%d, pri3=%d)", len(all_entries), len(pri1), len(pri2), len(pri3))
    logger.info("User preference context:\n%s", preferences_text)

    return {
        "entries": all_entries,
        "preferences_text": preferences_text,
        "sources": {
            "current_round_preferences": len(pri1),
            "archive_preferences": len(pri2),
            "base_matches": len(pri3),
        },
    }
