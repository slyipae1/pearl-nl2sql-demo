from __future__ import annotations

import json
import math
import re
import uuid
from typing import Any

from utils.model_factory import create_model
from detector.prompts import TAXONOMY_GUIDANCE, call_model_text
from detector.issue_detector import IssueDetector
from history.node_models import (
    DetailRecordCandGeneration,
    DetailRecordPairAmbiDetect,
    DetailRecordScoredAmbiEntry,
    NodeType,
    STANDARD_TITLES,
)
from preference_learner.learner import prepare_user_preference_context
from utils.logging_config import get_logger

logger = get_logger(__name__)


class Evaluator:
    """Evaluator worker: score ambiguity options and create AMBI_EVAL node.

    This implementation calls the configured LLM to request numeric scores
    for each option in every ambiguity context. If the model output cannot
    be parsed, it falls back to equal scoring.
    """

    def __init__(self, model_choice: str = "Default") -> None:
        self.model_choice = model_choice

    @staticmethod
    def _context_key(context: str, ambi_type: str = "") -> str:
        compact = re.sub(r"\s+", " ", str(context or "").strip().lower())
        compact = re.sub(r"[^a-z0-9\s_]", "", compact)
        type_part = re.sub(r"\s+", "", str(ambi_type or "").strip().lower())
        return f"{type_part}::{compact}" if compact or type_part else ""

    @staticmethod
    def _normalize_option_dict(opt: Any) -> dict[str, Any]:
        if isinstance(opt, dict):
            snippet = str(
                opt.get("snippet")
                or opt.get("option_content")
                or opt.get("content")
                or opt.get("option")
                or ""
            ).strip()
            interp = str(
                opt.get("interpretation")
                or opt.get("option_note")
                or opt.get("note")
                or opt.get("description")
                or ""
            ).strip()
            just = str(opt.get("justification") or "").strip()
            score_raw = opt.get("score", 0.0)
            try:
                score = float(score_raw)
            except Exception:
                score = 0.0
            return {
                "snippet": snippet,
                "interpretation": interp,
                "justification": just,
                "score": score,
            }

        text = str(opt or "").strip()
        return {
            "snippet": text,
            "interpretation": "",
            "justification": "",
            "score": 0.0,
        }

    @staticmethod
    def _option_key(opt: dict[str, Any]) -> str:
        snippet = str(opt.get("snippet") or "").strip().lower()
        interp = str(opt.get("interpretation") or "").strip().lower()
        return f"{snippet}::{interp}"

    def _normalize_ambiguity_entry(self, amb: Any) -> dict[str, Any]:
        """Normalize legacy and canonical ambiguity schemas into context, options, type, and description."""
        if not isinstance(amb, dict):
            return {
                "AmbiContext": "",
                "AmbiType": "",
                "Options": [],
            }

        context = str(
            amb.get("ambiguity_context")
            or amb.get("AmbiContext")
            or amb.get("context")
            or ""
        ).strip()

        ambi_type = str(
            amb.get("AmbiType")
            or amb.get("ambiguity_type")
            or amb.get("type")
            or ""
        ).strip()

        raw_opts = (
            amb.get("Options")
            or amb.get("options")
            or amb.get("AmbiOpts")
            or amb.get("ambiguity_options")
            or amb.get("opts")
            or []
        )

        options: list[dict[str, Any]] = []
        for opt in raw_opts:
            if isinstance(opt, (list, tuple)) and opt:
                if len(opt) == 1:
                    options.append({"snippet": opt[0]})
                else:
                    options.append({"snippet": opt[0], "interpretation": opt[1]})
            else:
                options.append(self._normalize_option_dict(opt))

        cleaned_opts = []
        seen_opt = set()
        for opt in options:
            key = self._option_key(opt)
            if not key or key in seen_opt:
                continue
            seen_opt.add(key)
            cleaned_opts.append(opt)

        return {
            "AmbiContext": context,
            "AmbiType": ambi_type,
            "Options": cleaned_opts,
        }

    def _merge_pairwise_entries(self, pair_records: list[DetailRecordPairAmbiDetect]) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for pair in pair_records:
            pair_id = str(pair.pair_id or "").strip()
            pair_report = str(pair.comparison_report or "").strip()
            for amb in pair.ambiguity_entries:
                norm = self._normalize_ambiguity_entry(amb)
                context = str(norm.get("AmbiContext") or "").strip()
                if not context:
                    continue
                ambi_type = str(norm.get("AmbiType") or "").strip()
                key = self._context_key(context, ambi_type)
                if not key:
                    continue
                if key not in merged:
                    merged[key] = {
                        "AmbiContext": context,
                        "AmbiType": ambi_type,
                        "Options": [],
                        "source_pair_ids": [],
                        "comparison_reports": [],
                    }
                bucket = merged[key]
                if pair_id and pair_id not in bucket["source_pair_ids"]:
                    bucket["source_pair_ids"].append(pair_id)
                if pair_report and pair_report not in bucket["comparison_reports"]:
                    bucket["comparison_reports"].append(pair_report)

                existing_keys = {self._option_key(item) for item in bucket["Options"]}
                for opt in norm.get("Options") or []:
                    ok = self._option_key(opt)
                    if not ok or ok in existing_keys:
                        continue
                    bucket["Options"].append(opt)
                    existing_keys.add(ok)
        return list(merged.values())

    def _extract_majority_vote_evidence(self, state: Any, ambi_node: Any) -> dict[str, Any]:
        evidence: dict[str, Any] = {"clusters": [], "candidate_count": 0}
        parent_ids = list(getattr(ambi_node, "parents", []) or [])
        for pid in parent_ids:
            pnode = state.get_node_snapshot(str(pid))
            if pnode is None or getattr(pnode, "node_type", None) != NodeType.CAND_GEN:
                continue
            for record in getattr(pnode, "detail_records", []) or []:
                if not isinstance(record, DetailRecordCandGeneration):
                    continue
                mv = record.majority_vote_result or {}
                clusters = mv.get("clusters") if isinstance(mv, dict) else []
                safe_clusters: list[dict[str, Any]] = []
                if isinstance(clusters, list):
                    for idx, cluster in enumerate(clusters, 1):
                        if not isinstance(cluster, dict):
                            continue
                        sqls = cluster.get("SQLs")
                        if not isinstance(sqls, list):
                            sqls = []
                        # Use enhanced summary (includes df_profile_markdown output)
                        enhanced_summary = IssueDetector._build_enhanced_summary(cluster)
                        safe_clusters.append(
                            {
                                # "rnk": cluster.get("rnk", idx),
                                "SQLs": [str(item).strip() for item in sqls if str(item).strip()],
                                "shared_result_summary": enhanced_summary,
                            }
                        )
                evidence["clusters"] = safe_clusters
                candidates = record.candidates or []
                evidence["candidate_count"] = len(candidates) if isinstance(candidates, list) else 0
                return evidence
        return evidence

    def _build_prompt(
        self,
        user_question: str,
        merged_entries: list[dict[str, Any]],
        majority_vote_evidence: dict[str, Any],
        preferences_text: str = "",
    ) -> str:
        entries_payload = json.dumps(merged_entries, ensure_ascii=False, indent=2)
        vote_payload = json.dumps(majority_vote_evidence, ensure_ascii=False, indent=2)

        # Illustrative example of the desired AMBI_EVAL JSON output (scored entries)
        output_example = (
            "Example evaluator output (JSON array):\n"
            "[\n"
            "  {\n"
            "    \"AmbiContext\": \"high schools by name containing 'High'\",\n"
            "    \"AmbiType\": \"AmbiColumn\",\n"
            "    \"Options\": [\n"
            "      {\"snippet\": \"WHERE sc.sname LIKE '%High%'\", \"interpretation\": \"Match SATScores.sname\", \"score\": 0.10},\n"
            "      {\"snippet\": \"WHERE s.school_name LIKE '%High%'\", \"interpretation\": \"Match Schools.school_name\", \"score\": 0.65},\n"
            "      {\"snippet\": \"WHERE s.school_name LIKE '%High%' OR sc.sname LIKE '%High%'\", \"interpretation\": \"Either column matches (maximize recall)\", \"score\": 0.25}\n"
            "    ],\n"
            "    \"justification\": \"school_name appears more complete in samples; OR increases recall but risks duplicates.\",\n"
            "    \"source_pair_ids\": [\"p_example_1\"]\n"
            "  }\n"
            "]"
        )

        return (
            "You are an execution-result-oriented evaluator in an NL2SQL ambiguity resolution pipeline.\n"
            "Your job is to evaluate ambiguity contexts and score their options using execution-grounded evidence.\n"
            "Think step by step internally, but output ONLY valid JSON — no explanation text.\n\n"
            "## Inputs\n"
            "- Ambiguity entries: output from pairwise detection; may have overlaps and incompleteness.\n"
            "- Clustered results: execution evidence from candidate generation (majority-vote clusters).\n"
            "- Preferences: explicit user preference constraints (high priority).\n\n"
            "## Process\n"
            "0. **Review ambiguity type taxonomy**, ensure full userstanding and integrity of definitions and format of context and interpretation. "
            "1. **Normalize and merge**: Combine entries with the same or very similar NL context (use similarity matching).\n"
            "2. **Validate context**: Discard entire entries whose context is unreasonable for the question or unsupported by execution evidence.\n"
            "3. **Validate options**: Within retained entries, discard options that are unreasonable or contradict evidence.\n"
            "4. **Score options**: For each retained option, assign a score in [0,1] based on execution evidence. Scores must sum to 1.0 per context.\n"
            "5. **Classify type**: Assign each entry its primary AmbiType from: AmbiScope, AmbiAttach, AmbiIntent, AmbiColumn, AmbiValue, AmbiOp.\n\n"
            "## Output format\n"
            "Return a JSON array. Each object must have this structure:\n"
            "{\n"
            '  "AmbiContext": "shortest NL substring that triggered the issue (better follow format in taxonomy)",\n'
            '  "AmbiType": "primary type from: AmbiScope, AmbiAttach, AmbiIntent, AmbiColumn, AmbiValue, AmbiOp",\n'
            '  "Options": [\n'
            '    {"snippet": "minimal SQL snippet", "interpretation": "clear description following Interpretation Format in taxonomy", "score": 0.0}\n'
            "  ],\n"
            '  "justification": "short contextual explanation of scoring for the set of options",\n'
            '  "source_pair_ids": ["list of pair IDs that detected this entry"]\n'
            "}\n"
            "Return [] if no valid ambiguity remains.\n\n"
            "## Important Rules:\n"
            "- Without special specification, the options with **more robust, more comprehensive, higher variance/noise tolerance, safer (e.g. duplication, NULLs handling), and more aligned with expectations in general scenario** is preferred, since user has little knowledge about DB so ask questions with noisy terms, and the values stored in DB might also be noisy. "
            "- Result cluster with more candidates does NOT guarantee to be more correct sometime even means the opposite, especially for situations with ambiguity since there will be more ambiguous options needed to check. Please judge by resonability of execution result and the SQL logic. \n"
            "- The snippet must be the MINIMAL SQL fragment that captures the ambiguity, not the whole SQL. The goal is to highlight the specific difference that leads to the execution difference. You will be seriously punished if you include more than needed\n"
            "- Scoring Criteria: 1) For ture issues needed to be fixed, assign score higher than 0.8 to the correct action; 2) for ambiguity, if the correct option is clear, assign it a acore higher than 0.8, if the current SQL is already using the correct choice, assign 1 to the correct and 0 to all others; 3) For ambiguous cases tha require user intervention, assign score based on likelihood of correctness but with top score lower than 0.8.\n"
            f"{TAXONOMY_GUIDANCE}\n\n"
            f"User question:\n{user_question}\n\n"
            f"{preferences_text+'\n\n' or ''}"
            f"Clustered results:\n{vote_payload}\n\n"
            # f"{output_example}\n\n"
            f"Ambiguity entries:\n{entries_payload}\n"
        )

    @staticmethod
    def _clip_scores(scores: list[float]) -> list[float]:
        clipped = [min(1.0, max(0.0, float(s))) for s in scores]
        return clipped

    def _normalize_option_scores(self, options: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not options:
            return []
        scores: list[float] = []
        for item in options:
            raw = item.get("score", 0.0)
            try:
                scores.append(float(raw))
            except Exception:
                scores.append(0.0)

        scores = self._clip_scores(scores)
        total = sum(scores)
        if total <= 0:
            equal = 1.0 / float(len(options))
            scores = [equal] * len(options)
        else:
            scores = [s / total for s in scores]

        for idx, item in enumerate(options):
            item["score"] = float(scores[idx])
        return options

    def _parse_model_output(self, raw: str) -> list[dict[str, Any]]:
        payload: Any = None
        try:
            payload = json.loads(raw)
        except Exception:
            return []

        if isinstance(payload, dict):
            if isinstance(payload.get("items"), list):
                payload = payload.get("items")
            else:
                payload = [payload]

        if not isinstance(payload, list):
            return []

        output: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            context = str(item.get("AmbiContext") or item.get("ambiguity_context") or "").strip()
            if not context:
                continue
            descrip = str(item.get("AmbiContext_descrip") or item.get("description") or "").strip()
            ambi_type = str(item.get("AmbiType") or item.get("ambiguity_type") or "").strip()
            raw_opts = item.get("Options") or item.get("options") or []
            if not isinstance(raw_opts, list) or not raw_opts:
                continue

            opts = [self._normalize_option_dict(opt) for opt in raw_opts]
            opts = [opt for opt in opts if self._option_key(opt)]
            if not opts:
                continue

            opts = self._normalize_option_scores(opts)
            pair_ids = item.get("source_pair_ids") or item.get("source_pairs") or []
            if not isinstance(pair_ids, list):
                pair_ids = []
            parsed_item = {
                "AmbiContext": context,
                "AmbiContext_descrip": descrip,
                "AmbiType": ambi_type,
                "Options": opts,
                "justification": str(item.get("justification") or "").strip(),
                "evaluator_justification": str(item.get("justification") or "").strip(),
                "source_pair_ids": [str(pid).strip() for pid in pair_ids if str(pid).strip()],
            }
            output.append(parsed_item)

        return output

    def _normalize(self, scores: list[float]) -> list[float]:
        if not scores:
            return []
        total = sum(scores)
        if total <= 0:
            # equal distribution
            n = len(scores)
            return [1.0 / n] * n
        return [float(s) / float(total) for s in scores]

    def _entropy(self, probs: list[float]) -> float:
        e = 0.0
        for p in probs:
            if p > 0:
                e -= p * math.log2(p)
        return e

    def evaluate(self, ambi_detect_node_id: str, state: Any, step_callback: Any | None = None) -> dict[str, Any]:
        logger.info("Evaluator.evaluate() started for ambi_detect_node_id=%s", ambi_detect_node_id)
        if not ambi_detect_node_id:
            return {"success": False, "error": "No ambi_detect_node_id provided"}

        node = state.get_node_snapshot(ambi_detect_node_id)
        if node is None:
            return {"success": False, "error": f"AMBI_DETECT node {ambi_detect_node_id} not found"}


        pair_records = [r for r in node.detail_records if isinstance(r, DetailRecordPairAmbiDetect)]
        if not pair_records:
            return {"success": True, "ambi_eval_node_id": None, "scored_entries": []}

        model = create_model(LLM_choice=self.model_choice)

        merged_entries = self._merge_pairwise_entries(pair_records)
        if not merged_entries:
            return {"success": True, "ambi_eval_node_id": None, "scored_entries": []}

        # Create AMBI_EVAL node early with placeholder summary (progressive updates)
        parents = list(node.parents or [])
        eval_node = state.create_node(
            node_type=NodeType.AMBI_EVAL,
            title=STANDARD_TITLES.get(NodeType.AMBI_EVAL, "Ambiguity Option Evaluation"),
            summary="Evaluating ambiguity options...",
            details="Ambiguity option scoring",
            parents=parents,
            detail_records=[],
        )
        eval_node_id = eval_node.node_id

        all_contexts = [str(item.get("AmbiContext") or "").strip() for item in merged_entries if str(item.get("AmbiContext") or "").strip()]
        pref_ctx = prepare_user_preference_context(
            state=state,
            db_name=str(getattr(state, "selected_db", "") or ""),
            ambiguity_contexts=all_contexts,
            similarity_threshold=0.75,
        )
        preferences_text = str(pref_ctx.get("preferences_text") or "")

        majority_vote_evidence = self._extract_majority_vote_evidence(state, node)
        user_question = str(state.get_latest_user_question() or "")
        prompt = self._build_prompt(
            user_question=user_question,
            merged_entries=merged_entries,
            majority_vote_evidence=majority_vote_evidence,
            preferences_text=preferences_text,
        )
        logger.info(f"Built evaluator prompt with length={len(prompt)}")
        logger.info(prompt.split("User question:")[-1].strip() if "User question:" in prompt else prompt)

        raw_out = call_model_text(model, prompt, max_tokens=8192)
        parsed_entries = self._parse_model_output(raw_out)
        logger.info(f"Raw evaluator output length={len(str(raw_out))}")
        logger.info(parsed_entries)

        # Robust fallback: keep merged entries and assign equal scores if parsing fails.
        if not parsed_entries:
            logger.warning("Evaluator model output parsing failed or produced no valid entries. Falling back to equal scoring for merged entries.")
            parsed_entries = []
            for item in merged_entries:
                opts = [self._normalize_option_dict(opt) for opt in (item.get("Options") or [])]
                if not opts:
                    continue
                opts = self._normalize_option_scores(opts)
                parsed_entries.append(
                    {
                        "AmbiContext": str(item.get("AmbiContext") or "").strip(),
                        "AmbiContext_descrip": str(item.get("AmbiContext_descrip") or "").strip(),
                        "AmbiType": str(item.get("AmbiType") or "").strip(),
                        "Options": opts,
                        "justification": "",
                        "evaluator_justification": "",
                        "source_pair_ids": list(item.get("source_pair_ids") or []),
                    }
                )

        scored_entries: list[DetailRecordScoredAmbiEntry] = []
        for item in parsed_entries:
            options = list(item.get("Options") or [])
            if not options:
                continue
            options = self._normalize_option_scores(options)
            scores = [float(opt.get("score", 0.0)) for opt in options]
            norm = self._normalize(scores)
            for idx, opt in enumerate(options):
                opt["score"] = norm[idx] if idx < len(norm) else 0.0

            ent = self._entropy(norm)
            sorted_probs = sorted(norm, reverse=True)
            gap = (sorted_probs[0] - sorted_probs[1]) if len(sorted_probs) > 1 else sorted_probs[0]

            detail_id = f"s_{uuid.uuid4().hex[:10]}"
            preselect = [] if not norm or max(norm) < 0.8 else [int(norm.index(max(norm)))]

            scored = DetailRecordScoredAmbiEntry(
                ambiguity_context=str(item.get("AmbiContext") or "").strip(),
                ambiguity_context_descrip=str(item.get("AmbiContext_descrip") or "").strip(),
                ambi_type=str(item.get("AmbiType") or "").strip(),
                options=options,
                scores=norm,
                justification=str(item.get("justification") or "").strip(),
                manager_rationale="",
                evaluator_justification=str(item.get("evaluator_justification") or "").strip(),
                question_format="spec_multi_choices",
                preselect_option_idxs=preselect,
                source_pair_ids=[str(pid).strip() for pid in (item.get("source_pair_ids") or []) if str(pid).strip()],
                entropy=ent,
                score_gap=gap,
                is_fixed=False,
                fixed_by="",
                fixed_round_id="",
                raw_action_step={
                    "merged": True,
                    "majority_vote_evidence": majority_vote_evidence,
                },
                detail_id=detail_id,
            )
            scored_entries.append(scored)
            state.append_detail_record(eval_node_id, scored)
            state.update_node(eval_node_id, {"summary": f"Evaluated {len(scored_entries)} of {len(parsed_entries)} entries"})
            if step_callback:
                step_callback({"type": "evaluator_entry", "detail_id": detail_id, "ambiguity_context": scored.ambiguity_context})

        # Finalize AMBI_EVAL node summary
        summary_lines = []
        for se in scored_entries:
            top = max(se.scores) if se.scores else 0.0
            summary_lines.append(f"{se.ambiguity_context[:60]}...: top={top:.2f}")
        summary = "; ".join(summary_lines) if summary_lines else "Ambiguity evaluation results"
        state.update_node(eval_node_id, {"summary": summary})

        logger.info("Evaluator complete: eval_node=%s with %d scored entries", eval_node_id, len(scored_entries))
        if step_callback:
            step_callback({"type": "evaluator_complete", "ambi_eval_node_id": eval_node_id})

        return {"success": True, "ambi_eval_node_id": eval_node_id, "scored_entries": scored_entries}

    def evaluate_structured(
        self,
        cand_gen_node_id: str,
        state: Any,
        step_callback: Any | None = None,
    ) -> dict[str, Any]:
        """Evaluate structured ambiguity entries (cand_gen_type='structured' path).

        Reads ambiguity_entries and per_entry_results from a CAND_GEN node's
        DetailRecordCandGeneration, scores options via LLM, and creates
        the AMBI_EVAL node with DetailRecordScoredAmbiEntry records.
        """
        logger.info("Evaluator.evaluate_structured() started for cand_gen_node_id=%s", cand_gen_node_id)
        if not cand_gen_node_id:
            return {"success": False, "error": "No cand_gen_node_id provided"}

        node = state.get_node_snapshot(cand_gen_node_id)
        if node is None:
            return {"success": False, "error": f"CAND_GEN node {cand_gen_node_id} not found"}

        # Find the DetailRecordCandGeneration
        cand_record: DetailRecordCandGeneration | None = None
        for dr in node.detail_records:
            if isinstance(dr, DetailRecordCandGeneration):
                cand_record = dr
                break

        if cand_record is None:
            return {"success": False, "error": "No DetailRecordCandGeneration found in node"}

        entries = cand_record.ambiguity_entries
        per_entry_results = cand_record.per_entry_results

        if not entries:
            return {"success": True, "ambi_eval_node_id": None, "scored_entries": []}

        model = create_model(LLM_choice=self.model_choice)

        # Convert structured entries to the format expected by _build_prompt
        # Each entry: {AmbiContext, AmbiType, Options: [{snippet, interpretation, score: 0.0}]}
        merged_entries: list[dict[str, Any]] = []
        for idx, entry in enumerate(entries):
            opts = entry.get("InterpretationOpts", [])
            mapped_opts = [
                {"snippet": o.get("snippet", ""), "interpretation": o.get("interpretation", "")}
                for o in opts
            ]
            merged_entries.append({
                "AmbiContext": entry.get("AmbiContext", ""),
                "AmbiType": entry.get("AmbiType", ""),
                "Options": mapped_opts,
                "source_pair_ids": [f"structured_{idx + 1}"],
            })

        # Build evidence from per_entry_results
        execution_evidence: dict[str, Any] = {"entries": []}
        for result in per_entry_results:
            opts = result.get("options", [])
            opt_summaries = [
                {
                    "snippet": o.get("snippet", ""),
                    "exec_status": o.get("exec_status", ""),
                    "row_count": o.get("row_count", 0),
                    "profile": o.get("profile_text", "")[:300],
                }
                for o in opts
            ]
            execution_evidence["entries"].append({
                "AmbiContext": result.get("AmbiContext", ""),
                "refinement_log": result.get("refinement_log", ""),
                "all_removed": result.get("all_removed", False),
                "all_equivalent": result.get("all_equivalent", False),
                "options": opt_summaries,
            })

        # Create AMBI_EVAL node
        parents = list(node.parents or []) + [cand_gen_node_id]
        eval_node = state.create_node(
            node_type=NodeType.AMBI_EVAL,
            title=STANDARD_TITLES.get(NodeType.AMBI_EVAL, "Ambiguity Option Evaluation"),
            summary="Evaluating ambiguity options...",
            details="Structured ambiguity evaluation",
            parents=parents,
            detail_records=[],
        )
        eval_node_id = eval_node.node_id

        all_contexts = [e.get("AmbiContext", "") for e in entries if e.get("AmbiContext", "")]
        pref_ctx = prepare_user_preference_context(
            state=state,
            db_name=str(getattr(state, "selected_db", "") or ""),
            ambiguity_contexts=all_contexts,
            similarity_threshold=0.75,
        )
        preferences_text = str(pref_ctx.get("preferences_text") or "")

        user_question = str(state.get_latest_user_question() or "")
        prompt = self._build_prompt(
            user_question=user_question,
            merged_entries=merged_entries,
            majority_vote_evidence=execution_evidence,
            preferences_text=preferences_text,
        )
        logger.info("Built structured evaluator prompt with length=%d", len(prompt))

        raw_out = call_model_text(model, prompt, max_tokens=8192)
        parsed_entries = self._parse_model_output(raw_out)

        # Fallback: equal scoring
        if not parsed_entries:
            logger.warning("Structured evaluator parsing failed. Falling back to equal scoring.")
            parsed_entries = []
            for item in merged_entries:
                opts = [self._normalize_option_dict(opt) for opt in (item.get("Options") or [])]
                if not opts:
                    continue
                opts = self._normalize_option_scores(opts)
                parsed_entries.append({
                    "AmbiContext": item.get("AmbiContext", ""),
                    "AmbiContext_descrip": "",
                    "AmbiType": item.get("AmbiType", ""),
                    "Options": opts,
                    "justification": "",
                    "evaluator_justification": "",
                    "source_pair_ids": item.get("source_pair_ids", []),
                })

        # Build DetailRecordScoredAmbiEntry (same logic as evaluate())
        scored_entries: list[DetailRecordScoredAmbiEntry] = []
        for item in parsed_entries:
            options = list(item.get("Options") or [])
            if not options:
                continue
            options = self._normalize_option_scores(options)
            scores = [float(opt.get("score", 0.0)) for opt in options]
            norm = self._normalize(scores)
            for idx, opt in enumerate(options):
                opt["score"] = norm[idx] if idx < len(norm) else 0.0

            ent = self._entropy(norm)
            sorted_probs = sorted(norm, reverse=True)
            gap = (sorted_probs[0] - sorted_probs[1]) if len(sorted_probs) > 1 else sorted_probs[0]

            detail_id = f"s_{uuid.uuid4().hex[:10]}"
            preselect = [] if not norm or max(norm) < 0.8 else [int(norm.index(max(norm)))]

            scored = DetailRecordScoredAmbiEntry(
                ambiguity_context=str(item.get("AmbiContext") or "").strip(),
                ambiguity_context_descrip=str(item.get("AmbiContext_descrip") or "").strip(),
                ambi_type=str(item.get("AmbiType") or "").strip(),
                options=options,
                scores=norm,
                justification=str(item.get("justification") or "").strip(),
                manager_rationale="",
                evaluator_justification=str(item.get("evaluator_justification") or "").strip(),
                question_format="spec_multi_choices",
                preselect_option_idxs=preselect,
                source_pair_ids=[str(pid).strip() for pid in (item.get("source_pair_ids") or []) if str(pid).strip()],
                entropy=ent,
                score_gap=gap,
                is_fixed=False,
                fixed_by="",
                fixed_round_id="",
                raw_action_step={
                    "structured": True,
                    "execution_evidence": execution_evidence,
                },
                detail_id=detail_id,
            )
            scored_entries.append(scored)
            state.append_detail_record(eval_node_id, scored)
            state.update_node(eval_node_id, {"summary": f"Evaluated {len(scored_entries)} of {len(parsed_entries)} entries"})
            if step_callback:
                step_callback({"type": "evaluator_entry", "detail_id": detail_id, "ambiguity_context": scored.ambiguity_context})

        # Finalize summary
        summary_lines = []
        for se in scored_entries:
            top = max(se.scores) if se.scores else 0.0
            summary_lines.append(f"{se.ambiguity_context[:60]}...: top={top:.2f}")
        summary = "; ".join(summary_lines) if summary_lines else "Structured ambiguity evaluation results"
        state.update_node(eval_node_id, {"summary": summary})

        logger.info("Evaluator.evaluate_structured() complete: eval_node=%s with %d scored entries", eval_node_id, len(scored_entries))
        if step_callback:
            step_callback({"type": "evaluator_complete", "ambi_eval_node_id": eval_node_id})

        return {"success": True, "ambi_eval_node_id": eval_node_id, "scored_entries": scored_entries}
