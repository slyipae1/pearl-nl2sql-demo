from __future__ import annotations

import json
from typing import Any
from utils.logging_config import get_logger

logger = get_logger(__name__)


TAXONOMY_GRAMMAR_GUIDANCE = r"""
### Grammar-Sourced (linguistic structure of the question)

**AmbiScope**
- **Contextual Trigger**: **Phrase** with quantifiers like "every", "all", "each" that introduce ambiguity between per-item and collective interpretation.
- **Interpretation Format**: Per-item reading (things associated with each individual member) vs. collective reading (things common to all members).

Example: "systems every specialist works with"
  → `SELECT specialist_name, system_id ... ORDER BY system_id`  -- per-item: each specialist's individually associated systems
  → `SELECT system_id ... WHERE system_id IN (
         SELECT system_id
         FROM specialists_system_usage
         GROUP BY system_id
         HAVING COUNT(DISTINCT specialist_id) = (SELECT COUNT(specialist_id) FROM specialists_system_usage)
     )`  -- collective: only systems that EVERY specialist works with (intersection)

 SQL impact: per-item returns individual assignments (n rows per specialist); collective returns only items common to all members (intersection, typically fewer rows).

**AmbiAttach**
- **Contextual Trigger**: **Phrase** with modifiers, conjunctions ("or", "and"), or prepositional phrases, whose attachment span is ambiguous.
- **Interpretation Format**: The modifier applies to the whole list (wide scope) vs. just the nearest item (narrow scope).

Example: "desktops or laptops with Linux?"
  → `WHERE (device_type = 'desktop' OR device_type = 'laptop') AND os = 'Linux'`  -- "with Linux" attaches to the either desktops or laptops
  → `WHERE (device_type = 'laptop' AND os = 'Linux') OR device_type = 'desktop'`  -- "with Linux" attaches only to "laptops"

  SQL impact: WHERE clause logic differs — the filter on os applies to the full OR scope or just one conjunct.
"""


TAXONOMY_USERQUERY_GUIDANCE = r"""
### UserIntent-Sourced (vague or under-defined user intent)

**AmbiIntent**
- **Contextual Trigger**: **Phrase** with under-defined qualitative or descriptive terms ("recent", "large", "relevant", "high-performing"), abstract concepts ("profile", "report", "analysis", "summary"), or fragmentary goals with missing operational context.
- **Interpretation Format**: Definition of the vague term, construction or operationalization of the vague goal, grounded in available DB columns, available data or conversational context.

  Example A (threshold definition): "Show recent projects"
  → `WHERE created_date > CURRENT_DATE - INTERVAL '3 months'`  -- recent = last 3 months (time-based threshold)
  → `WHERE status = 'In Progress' OR status = 'Ongoing'`       -- recent = active projects (status-based)
  → `WHERE created_date > (SELECT MAX(created_date) - INTERVAL '30 days' FROM projects)`  -- recent = latest 30 days (dynamic window)
  SQL impact: WHERE condition differs based on how the vague term is operationalized.

  Example B (abstract concept): "Give me a performance report"
  → `employee_id, AVG(rating) FROM reviews GROUP BY employee_id`  -- performance = team ratings (subjective evaluation)
  → `project_id, SUM(hours_spent) FROM time_logs GROUP BY project_id`  -- performance = project effort (time investment)
  → `department_id, COUNT(promotions) FROM promotions GROUP BY department_id`  -- performance = career advancement (promotion count)
  SQL impact: choice of table, aggregation, and output columns differs based on inferred intent.

  Example C (unclear metric): "Show productive teams"
  → `ORDER BY projects_completed DESC LIMIT 5`  -- productive = most projects completed (output quantity)
  → `WHERE avg_task_completion_time < 5`        -- productive = fast task turnaround (speed)
  → `WHERE team_satisfaction >= 4.0`            -- productive = high team morale (satisfaction)
  SQL impact: choice of metric and filtering logic differs based on how vague term is operationalized.
"""


TAXONOMY_DB_AMBICOLUMN = r"""
### DB-Sourced (schema and data grounding)

**AmbiColumn**
- **Contextual Trigger**: **Phrase or entity** that has multiple possible column references in the schema that could plausibly satisfy the same NL entity mention.
- **Interpretation Format**: List of possible `table.column` mappings, optionally combined with logical operation (using OR, AND, UNION, etc.) when the entity could span multiple columns.

Example (multi-column combination): "Find high schools by name containing 'High'"
  Schema: `Schools(school_name, ...)`, `SATScores(sname, school_id, ...)` — both store school names but in different tables.
  → `WHERE sname LIKE '%High%'`                                                   -- List: `SATScores.sname`
  → `WHERE school_name LIKE '%High%'`                                             -- List: `Schools.school_name`
  → `...WHERE s.school_name LIKE '%High%' OR sc.sname LIKE '%High%'`              -- List: `SATScores.sname`, `Schools.school_name`; OR: either column contains "High"
  → `...WHERE s.school_name LIKE '%High%' AND sc.sname LIKE '%High%'`             -- List: `SATScores.sname`, `Schools.school_name`; AND: both columns contains "High"
  
  Situation 1: `school_name` contains "Central High", "West High", etc.; `sname` stores abbreviated codes like "CHS", "WHS" with only 20% containing "High". `school_name` has 0% NULLs, `sname` has 10% NULLs.
    Scoring: use only `school_name` scored highest; all others scored low

  Situation 2: Both columns store full names, but both have NULLs, not all records with names appear in both columns (the rest are in one but not the other).
    Scoring: Neither single column alone achieves full recall. OR-ing both captures all matches (highest score), others scored low.
  
  SQL impact: When multiple columns could satisfy the same NL entity, interpretations may involve picking one, OR-ing conditions (at least one matches), AND-ing conditions (all match), or UNION-ing separate queries.
"""

TAXONOMY_DB_AMBIVALUE = r"""
### DB-Sourced (schema and data grounding)

**AmbiValue**
- **Contextual Trigger**: **Phrase or entity** with multiple possible mappings from a user-provided constant to stored cell values, differing in format (case, abbreviation, encoding) or matching strategy (exact, substring, normalization).
- **Interpretation Format**: List of possible `value in table.column`, optionally with the matching logic.
  Note: If a constant maps to conceptually DIFFERENT columns (e.g., "Texas" matching both `state` and `city`), that column-choice aspect is AmbiColumn. Once the column is determined, the value-format / matching-strategy aspect is AmbiValue. If a constant maps to conceptually SAME columns (e.g., "xx High School" matching both `xx high school` in `SATScores.sname`, `xx High School` in `Schools.school_name`), this is a mxiture ambigutiy with primary type being AmbiValue and hidden type AmbiColumn.

Example: "Show all fires caused by campfires in Texas"; The `state` column contains 'Texas', 'TEXAS', 'TX' that could plausibly match "Texas"
  → `WHERE state = 'Texas'`              -- List: `Texas` in `FireRecord.state`; Logic: exact match
  → `WHERE LOWER(state) = 'texas'`       -- List: `Texas` in `FireRecord.state`, `TEXAS` in `FireRecord.state`; Logic: case-insensitive
  → `WHERE state IN ('Texas', 'TEXAS', 'TX')` -- List: `Texas` in `FireRecord.state`, `TEXAS` in `FireRecord.state`, `TX` in `FireRecord.state`; Logic: case-insensitive & abbreviations

  Situation 1: The sample distribution shows the data has inconsistent casing and abbreviation usage, and it's possible that 'TX' uniquely maps to Texas in this domain.
  Scoring: LOWER match scores highest (captures most variants with near-zero false-positive risk). Multi-value scores medium and similar to LOWER match (captures more but 'TX' may overlap with other entities). Exact match scores lowest (too restrictive).

  Situation 2: The sample data suggests no abbreviation usage practice. The data is nearly clean except for occasional uppercase entries.
  Scoring: LOWER match scores highest (captures most variants with near-zero false-positive risk). Multi-value scores medium and large gap to LOWER match (captures more but 'TX' is more risky). Exact match scores lowest (too restrictive).

  SQL impact: the same ambiguity may require different matching strategies depending on the data distribution and schema context.
"""

TAXONOMY_DB_AMBIVOP = r"""
### DB-Sourced (schema and data grounding)

**AmbiOp**
- **Contextual Trigger**: (a) **Phrase** describing operations — joins, aggregation, ranking, deduplication, filtering strategy, calculations, data reformatting, casting; AND/OR (b) **DB-instance-sourced situations** with multiple valid handling strategies — NULL treatment, duplicate handling, precision/rounding, type casting, output formatting.
- **Interpretation Format**: Decision of how to handle the operation, with the specific SQL technique and its behavioral consequence.

Example A (NULL/zero handling): "Calculate average of something"
  
  Situation A1: calculate average of score; Table `StudentScores`, column `score`, rows have NULL `score`. There are tables about attendance records.
  → `AVG(score)`               -- NULLs excluded
  → `AVG(score) ... WHERE score != 0` -- Zeros excluded
  → `AVG(COALESCE(score, 0))`  -- NULLs treated as zero
  Scoring: `AVG(COALESCE(score, 0))` scores higher because absent students meaningfully scored zero. `AVG(score)` and zeros exclusion overstates class performance by excluding lower-performing absentees, COALESCE scores lower.

  Situation A2: calculate average of age; Table `People`, column `age`. rows have NULL `age`, and these NULLs are randomly distributed across otherwise complete records (consistent with data-entry omission).
  → `AVG(age)`               -- NULLs excluded
  → `AVG(age) ... WHERE age != 0`       -- Zeros excluded
  → `AVG(COALESCE(age, 0))`  -- NULLs treated as 0
  Scoring: `AVG(age) ... WHERE age != 0` if the database seems to use zeros to indicates missing values; `AVG(age)` scores higher if missing values recored as NULLs; `COALESCE` scored lowed because replacing missing data with zero introduces systematic bias (treats "unknown" as "zero years old").

  SQL impact: aggregate result differs when NULL values exist; scoring depends on whether NULL means "data missing" vs. "meaningful zero."


Example B (ranking): "Rank employees by salary"
  → `RANK() OVER (ORDER BY salary DESC)`         -- standard rank, with gaps
  → `DENSE_RANK() OVER (ORDER BY salary DESC)`   -- dense rank, ensure no gaps
  → `ROW_NUMBER() OVER (ORDER BY salary DESC)`   -- no ties, no gaps
  Scoring: When the results showing tie distribution, `RANK` or `DENSE_RANK` is more appropriate — they score higher. When others info such as user preference, conversation histry show a unique ordering is preferred, `ROW_NUMBER` scores higher.
  SQL impact: choices differ when there are ties and whether the user expects gaps, no gaps, or unique positions.

Example C (deduplication): "Count product categories"
  → `COUNT(category)`          -- all values
  → `COUNT(DISTINCT category)` -- distinct values
  → `COUNT(DISTINCT LOWER(category))` -- case-normalized
  Scoring: If the sample distribution shows the data has noisy formatting, LOWER match scores high; conversely, if the data seem clean and well-maintained, LOWER match might scored low with the risk of over-normalization.
  SQL impact: matching strategries differes based on whether duplicates or formatting inconsistencies exist.

Example D (join strategy): "List all students and their enrolled courses"
  → `Students s JOIN Enrollments e ON s.id = e.student_id`     -- inner join: exclude NULLs in Enrollments
  → `Students s LEFT JOIN Enrollments e ON s.id = e.student_id` -- left join: show NULLs in Enrollments
  Scoring: When the intent is a complete roster (e.g., for audit or administrative review), LEFT JOIN scores higher. When the intent is active enrollment analysis, INNER JOIN scores higher. But if there is no NULLs, probably not reported as an ambiguity situations.
  SQL impact: join type is determined by user preference and statistical situations like NULL appearance.
"""


TAXONOMY_ENDING = r"""
Important: Each type has its own expected output representation:
- `AmbiContext` = the shortest NL substring matching the Contextual Trigger for that types.
- `snippet` = minimal SQL fragment representing that interpretation, with `...` for unrelated parts.
- `interpretation` = text following the Interpretation Format for that types.

Execution-grounded evaluation principle: The level of being reasonable depends on the specific situation grounded in the data instance. Both semantic meaning & execution results (statistics of columns/values related to the ambiguous operation) are important for determining which option is most reasonable.
"""


TAXONOMY_SECTIONS: dict[str, str] = {
        "grammar": TAXONOMY_GRAMMAR_GUIDANCE,
        "user_query": TAXONOMY_USERQUERY_GUIDANCE,
        "db_AmbiColumn": TAXONOMY_DB_AMBICOLUMN,
        "db_AmbiValue": TAXONOMY_DB_AMBIVALUE,
        "db_AmbiOp": TAXONOMY_DB_AMBIVOP,
        "ending": TAXONOMY_ENDING,
}

TYPE_TO_TAXONOMY_SECTIONS: dict[str, tuple[str, ...]] = {
        "AmbiScope": ("grammar",),
        "AmbiAttach": ("grammar",),
        "AmbiIntent": ("user_query",),
        "AmbiColumn": ("db_AmbiColumn",),
        "AmbiValue": ("db_AmbiValue",),
        "AmbiOp": ("db_AmbiOp",),
}


def build_taxonomy_guidance(ambiguity_types: list[str] | None = None) -> str:
        """Compose the ambiguity taxonomy sections used by prompt builders."""
        if not ambiguity_types:
                return "\n\n".join(TAXONOMY_SECTIONS.values())

        ordered_sections: list[str] = []
        for ambi_type in ambiguity_types:
                for section_key in TYPE_TO_TAXONOMY_SECTIONS.get(str(ambi_type).strip(), ()):
                        if section_key not in ordered_sections:
                                ordered_sections.append(section_key)

        if not ordered_sections:
                return "\n\n".join(TAXONOMY_SECTIONS.values())

        guidance = "\n\n".join(TAXONOMY_SECTIONS[key] for key in ordered_sections if key in TAXONOMY_SECTIONS)

        ## always add ending
        guidance += "\n\n" + TAXONOMY_SECTIONS['ending']

        return guidance


TAXONOMY_GUIDANCE = build_taxonomy_guidance()


def _format_sql_items_markdown(
    user_question: str,
    reasoning: str,
    previous_summary: str,
    sql_items: list[dict[str, Any]],
    current_round_steps: str | None = None,
    generated_sql_options: list[dict[str, Any]] | None = None,
    preferences_text: str | None = None,
) -> str:
    """Format detector payload as LLM-friendly markdown."""

    parts: list[str] = []
    parts.append("## Input\n")
    parts.append("### Basic Info")
    parts.append(f"- **User Question**: {user_question}")
    if preferences_text:
        parts.append("- **User Preferences**: see section below")
    parts.append("")

    if preferences_text:
        pref = preferences_text[:5000]
        parts.append("### User Preference Context")
        parts.append(pref)
        parts.append("")

    parts.append("### SQL Items")
    parts.append("")

    for idx, item in enumerate(sql_items, start=1):
        original_sql = item.get("original_sql", "")
        parsed = item.get("parsed", {})
        retrieved = item.get("retrieved_options", {})

        # parts.append(f"#### SQL Item {idx}")
        # parts.append("")
        parts.append("**Original SQL:**")
        parts.append(f"```sql\n{original_sql}\n```")
        parts.append("")

        # Columns & Confusing Options
        columns = parsed.get("columns") or []
        column_options = retrieved.get("columns") or {}
        if columns:
            parts.append("**Columns & Confusing Options:**")
            for col in columns:
                matches = column_options.get(col) or []
                if matches:
                    formatted = [f"- COLUMN `{m['table']}.{m['column']}`" for m in matches]
                    parts.append(f"COLUMN `{col}` in original SQL might be confused with: \n{'\n'.join(formatted)}")
                else:
                    parts.append(f"- `{col}`")
            parts.append("")

        # Values & Confusing Appearances
        literals = parsed.get("literals") or []
        value_options = retrieved.get("values") or {}
        if literals:
            parts.append("**Values & Confusing Appearances:**")
            for lit in literals:
                matches = value_options.get(lit) or []
                if matches:
                    formatted = [f"- VALUE `{m['value']}` exists in COLUMN `{m['table']}.{m['column']}`" for m in matches]
                    parts.append(f"VALUE `{lit}` in original SQL might be confused with: \n{'\n'.join(formatted)}")
                else:
                    parts.append(f"- `'{lit}'`")
            parts.append("")

        # Functions & Confusing Appearances
        functions = parsed.get("functions") or []
        if functions:
            parts.append("**Functions**")
            parts.append("The following parts with functions can be focused to consider potential ambiguity issues (e.g. logically alternatives, different handling of duplications, missing values, operate on different columns, etc.): ")
            for func in functions:
                parts.append(f"- `{func}`")
            parts.append("")

        # Alternative SQL Options (only for issue detection)
        if generated_sql_options is not None:
            parts.append("**Alternative SQL Options with Execution:**")
            # only add the options for this index item
            options_for_item = next((opt for opt in generated_sql_options if opt.get("original_sql") == original_sql), None)
            if options_for_item is None and len(sql_items) == 1 and isinstance(generated_sql_options, list) and generated_sql_options:
                options_for_item = generated_sql_options[0]
            if options_for_item:
                more_sqls = options_for_item.get("more_possible_sqls") or []
                if more_sqls:
                    for opt_sql in more_sqls:
                        parts.append(f"- ```sql\n{opt_sql}\n```")
                else:
                    parts.append("- (no alternatives generated)")
            else:
                parts.append("- (no alternatives generated)")
            parts.append("")

    return "\n".join(parts)


REASONING_MULTI_TYPE = """\
## Step-by-step reasoning process
For each Ambguity Type:
0. **Review ambiguity type taxonomy**, ensure full userstanding and integrity of definitions and format of trigger context and interpretation. 
1. **Analyze the context**: NL question, original SQL, retrieved hints of confusing options.
2. **Systematically check each ambiguity type**: For each of the 6 types listed in the taxonomy below (AmbiScope, AmbiAttach, AmbiIntent, AmbiColumn, AmbiValue, AmbiOp):
   - **Recognize the trigger**: Does the NL question or SQL contain triggers matching this type?
   - **Reason about issues**: If a trigger is present, could the original SQL be ambiguous w.r.t. this type?
   - **Generate interpretations**: For each plausible interpretation, produce one alternative SQL. Filter out trivial paraphrases.
   - **Only include if execution differs**: An alternative is only worth including if it produces a meaningfully different execution result.
3. **Further Exploration**: After generating candidates from step 2, treat them as seed SQLs and repeat the process to discover higher-order ambiguities. Stop when no additional meaningful alternatives can be discovered.
"""

REASONING_SINGLE_TYPE = """
## Step-by-step reasoning process
0. **Review ambiguity type taxonomy**, ensure full userstanding and integrity of definitions and format of context and interpretation. 
1. **Analyze the context**: NL question, original SQL, retrieved hints of confusing options, and user preferences.
2. **Focus on the requested ambiguity type(s)**: Only generate alternatives directly relevant to the focused type(s).
3. **Systematically check the trigger**: Determine whether the NL question or SQL actually supports this ambiguity type.
4. **Generate interpretations only when reasonable**: For each plausible interpretation, produce one alternative SQL.
5. **Only include if execution differs**: Alternative must produce meaningfully different execution result.
6. **Further Exploration**: After generating candidates, treat them as seed SQLs and repeat the process to discover higher-order ambiguities. Stop when no additional meaningful alternatives can be discovered.
7. **Stop early when not applicable**: If the focused type clearly does not apply, return no alternatives.
"""


def build_sql_options_prompt(
    user_question: str,
    sql_items: list[dict[str, Any]],
    reasoning: str,
    previous_summary: str,
    schema_text: str,
    preferences_text: str = "",
    taxonomy_guidance: str | None = None,
    ambiguity_focus: list[str] | None = None,
) -> str:
    input_markdown = _format_sql_items_markdown(
        user_question=user_question,
        reasoning=reasoning,
        previous_summary=previous_summary,
        sql_items=sql_items,
        preferences_text=preferences_text,
    )
    logger.info("Built SQL options prompt:\n%s", input_markdown)
    focused_taxonomy = taxonomy_guidance or build_taxonomy_guidance(ambiguity_focus)
    focus_note = ""
    if ambiguity_focus:
        focus_list = ", ".join(str(item).strip() for item in ambiguity_focus if str(item).strip())
        if focus_list:
            focus_note = f"\nFocused ambiguity types for this prompt: {focus_list}.\n"
    # Select reasoning version based on focus breadth
    if ambiguity_focus is None or len(ambiguity_focus) >= 2:
        reasoning_section = REASONING_MULTI_TYPE
    else:
        reasoning_section = REASONING_SINGLE_TYPE

    emphases = (
        "- Be brave in designing alternative SQL structures — the original SQL may be incorrect or incomplete, so correct alternatives could look significantly different. Do not be constrained by the original SQL's structure or logic.\n"
        "- Learn from the taxonomy examples provided below and apply that reasoning logic to your own analysis. Transform the demonstrated pattern-recognition approach to discover ambiguities in this specific context.\n"
        "- You will be rewarded for finding SQL alternatives that reveal a comprehensive set of meaningful, non-trivial, and hard-to-recognize ambiguity problems. Prioritize quality and insight over quantity.\n"
    )
    # Illustrative example output to show exact JSON formatting expected from the model
    output_example = (
        "Example output (JSON):\n"
        "{\"items\": [\n"
        "  {\"original_sql\": \"SELECT COUNT(category) FROM products;\",\n"
        "   \"more_possible_sqls\": [\"SELECT COUNT(category) FROM products -- counts all rows including duplicates\",\n"
        "                           \"SELECT COUNT(DISTINCT LOWER(category)) FROM products -- counts with case\",\n"
        "                           \"SELECT COUNT(DISTINCT LOWER(category)) FROM products -- counts distinct normalized to lowercase\"]\n"
        "  },\n"
        "  {\"original_sql\": \"SELECT * FROM Schools WHERE school_name LIKE '%High%';\",\n"
        "   \"more_possible_sqls\": [\"SELECT * FROM SATScores WHERE sname LIKE '%High%' -- matches SATScores.sname\",\n"
        "                           \"SELECT * FROM Schools WHERE school_name LIKE '%High%' -- matches Schools.school_name\",\n"
        "                           \"SELECT * FROM Schools s JOIN SATScores sc ON s.school_id = sc.school_id WHERE s.school_name LIKE '%High%' OR sc.sname LIKE '%High%' -- OR: either column matches\",\n"
        "                           \"SELECT * FROM Schools s JOIN SATScores sc ON s.school_id = sc.school_id WHERE s.school_name LIKE '%High%' AND sc.sname LIKE '%High%' -- AND: both columns must match\"]\n"
        "  }\n"
        "]}"
    )

    return (
        "You are an expert in generating minimal diverse SQL alternatives for maximum ambiguity coverage from an execution-distinctions perspective.\n\n"
        "Task: For the given original SQL, generate alternative SQL interpretations that could also reasonably match the user's NL intent.\n"
        "Target to cover as many reasonable SQL options as possible while ensuring distinct execution results.\n"
        "Return ONLY valid JSON, no markdown fences, no explanatory text.\n\n"
        f"{emphases}\n"
        f"{reasoning_section}\n"
        "## Important constraints\n"
        "- Aim for maximal coverage of ambiguity issues: the ultimate goal of these SQL candidates is to help discover ambigutiy issues, so you are most helpful when you cover most. \n"
        "- Keep generated SQL syntactically valid for the target DB (SQLite).\n"
        "- Ordering: cluster related SQL variants together (neighbors have minimal SQL differences).\n"
        "- Each SQL should be followed with a comment `-- notes` to highlight its unique aspects.\n"
        "- The notes must be CONCISE, better within 25 words. \n"
        "- If user preferences or previous specifications resolve an ambiguity, do NOT generate alternatives that contradict them.\n\n"
        "- If the focused ambiguity type clearly does not yield any valid SQL alternative, return an empty `more_possible_sqls` list for that item.\n"
        f"{focus_note}"
        "Output format: {{\"items\": [{{\"original_sql\": str, \"more_possible_sqls\": [\"alternative_sql1 -- notes\", \"alternative_sql2 -- notes\", ...]}}]}}\n\n"
        f"{focused_taxonomy}\n"
        f"{input_markdown}\n"
        # f"{output_example}\n\n"
        f"Relevant schema: \n{schema_text}"
    )


def parse_sql_options_json(raw_text: str) -> list[dict[str, Any]]:
    text = (raw_text or "").strip()
    if not text:
        return []

    # Try direct parse.
    data: Any = None
    try:
        data = json.loads(text)
    except Exception as exc:
        logger.error("Failed to parse JSON directly: %s", exc)
        # Lightweight rescue if model wrapped output with text.
        left = text.find("{")
        right = text.rfind("}")
        if left >= 0 and right > left:
            try:
                data = json.loads(text[left : right + 1])
            except Exception as exc:
                logger.error("Failed to parse JSON from model output: %s", exc)
                return []
        else:
            return []

    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []

    output: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        original = str(item.get("original_sql") or "").strip()
        options_raw = item.get("more_possible_sqls") or []
        options = [str(opt).strip() for opt in options_raw if str(opt).strip()]
        if not original:
            continue
        output.append({"original_sql": original, "more_possible_sqls": options[:3]})
    return output



def build_pairwise_ambiguity_prompt(
    left_summary: str,
    right_summary: str,
    user_question: str = "",
    schema_text: str = "",
    preferences_text: str = "",
    taxonomy_guidance: str | None = None,
) -> str:
    """Build a prompt to detect ambiguity between two execution result summaries."""
    resolved_taxonomy = taxonomy_guidance or TAXONOMY_GUIDANCE
    output_example = (
        "Examples of output format using cases in taxonomy (JSON):\n"
        "MOST IMPORTANT: do NOT put the whole SQL in snippet only if needed, Use MINIMAL partial SQL.\n\n"
        "Example 1:\n"
        "\n```json\n"
        "[\n"
        "  {\n"
        '    "AmbiContext": "count product categories",\n'
        '    "AmbiType": "AmbiOp",\n'
        '    "Options": [\n'
        '      {"snippet": "COUNT(category)", "interpretation": "counts all including duplicate"},\n'
        '      {"snippet": "COUNT(category)", "interpretation": "counts with case-normalized"},\n'
        '      {"snippet": "COUNT(DISTINCT category)", "interpretation": "counts only unique categories"}\n'
        "    ]\n"
        "  }\n"
        "]\n"
        "Example 2:\n"
        "\n```\n"
        "\n```json\n"
        "[\n"
        "  {\n"
        '    "AmbiContext": "school names containing High",\n'
        '    "AmbiType": "AmbiColumn",\n'
        '    "Options": [\n'
        '      {"snippet": "school_name LIKE \'%High%\'", "interpretation": "Use `Schools.school_name` only"},\n'
        '      {"snippet": "sname LIKE \'%High%\'", "interpretation": "Use `SATScores.sname` only"},\n'
        '      {"snippet": "s.school_name LIKE \'%High%\' AND sc.sname LIKE \'%High%\'", "interpretation": "Use both `SATScores.sname`, `Schools.school_name`; AND: both columns contains `High`"},\n'
        '      {"snippet": "s.school_name LIKE \'%High%\' OR sc.sname LIKE \'%High%\'", "interpretation": "Use both `SATScores.sname`, `Schools.school_name`; OR: either column contains `High`"}\n'
        "    ]\n"
        "  }\n"
        "]\n"
        "\n```\n"
    )

    base = (
        "You are an expert execution-result-oriented SQL reviewer. Compare two SQL execution result summaries and identify the precise ambiguity contexts that caused the difference.\n"
        "Return ONLY valid JSON as a list of objects. No markdown fences, no explanatory text.\n\n"
        "## Step-by-step process\n"
        "0. Review ambiguity type taxonomy, ensure ful userstanding of definitions and format of context and interpretation. "
        "1. **Compare the execution summaries** — identify the difference (row count, column values, ordering, etc.).\n"
        "2. **Trace back to the SQL** — find the minimal SQL fragment(s) that, if changed, would produce that difference.\n"
        "3. **Map to the NL question** — find the shortest NL substring corresponding to the ambiguous choice.\n"
        "4. **Classify** — assign the primary AmbiType from the taxonomy: AmbiScope, AmbiAttach, AmbiIntent, AmbiColumn, AmbiValue, AmbiOp.\n"
        "5. **Format** — create exactly one JSON entry per distinct ambiguity context (do not duplicate contexts).\n\n"
        "## Output entry format (JSON array of objects)\n"
        "Each entry must have this exact structure:\n"
        "{\n"
        '  "AmbiContext": "shortest NL substring matching the Contextual Trigger of the identified type",\n'
        '  "AmbiType": "primary type, one of: AmbiScope, AmbiAttach, AmbiIntent, AmbiColumn, AmbiValue, AmbiOp",\n'
        '  "Options": [\n'
        '    {"snippet": "minimal SQL fragement for one interpretation (use ... for unrelated parts)", "interpretation": "description following the Interpretation Format in taxonomy"}\n'
        "  ]\n"
        "}\n"
        "Return ONLY the JSON array, no markdown or extra text.\n\n"
        f"{output_example}\n\n"
        "## Important rules\n"
        "- snippet must be the MINIMAL SQL fragment that captures the ambiguity, not the whole SQL. The goal is to highlight the specific difference that leads to the execution difference. You will be seriously punished if you include more than needed\n"
        "- Ensure full userstanding and integrity of definitions and format of context and interpretation. "
        "- Only include an entry when the execution results differ meaningfully.\n"
        "- If multiple ambiguity contexts or multiple types contribute to the difference, create a separate entry for each context.\n"
        "- Use the retrieved DB hints and user preferences as supporting evidence for classification.\n"
        "- Result cluster with more candidates does NOT guarantee to be more correct sometime even means the opposite, especially for situations with ambiguity since there will be more ambiguous options needed to check. Please judge by resonability of execution result and the SQL logic. \n "
        "- Match the AmbiType to the taxonomy definition (prioritize the primary type that most closely matches the issue).\n"
        "- If no meaningful issue is found, return an empty JSON array: []\n"
    )
    parts = [base]
    parts.append(f"{resolved_taxonomy}\n\n")
    if user_question:
        parts.append(f"User question: {user_question}\n")
    parts.append("Left execution summary:\n" + left_summary + "\n")
    parts.append("Right execution summary:\n" + right_summary + "\n")
    if preferences_text:
        parts.append("User preference context (higher priority):\n" + preferences_text + "\n")

    logger.info("Built pairwise ambiguity prompt (chars=%d)", len("\n".join(parts)))

    if schema_text:
        parts.append("Relevant schema:\n" + schema_text + "\n")
    return "\n".join(parts)


def parse_pairwise_ambiguity_output(raw_text: str) -> list[dict[str, Any]]:
    """Parse structured ambiguity entries returned by the pairwise detector."""
    text = (raw_text or "").strip()
    if not text:
        return []

    if text.startswith("```json"):
        text = text[7:].lstrip()
    elif text.startswith("```"):
        text = text[3:].lstrip()
    if text.endswith("```"):
        text = text[:-3].rstrip()

    try:
        payload: Any = json.loads(text)
    except Exception:
        left = text.find("[")
        right = text.rfind("]")
        if left >= 0 and right > left:
            try:
                payload = json.loads(text[left : right + 1])
            except Exception:
                return []
        else:
            return []

    if isinstance(payload, dict):
        if isinstance(payload.get("items"), list):
            payload = payload.get("items")
        elif isinstance(payload.get("ambiguity_entries"), list):
            payload = payload.get("ambiguity_entries")
        else:
            return []

    if not isinstance(payload, list):
        return []

    output: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        context = str(item.get("AmbiContext") or item.get("ambiguity_context") or item.get("context") or "").strip()
        descrip = str(item.get("AmbiContext_descrip") or item.get("AmbiContextDesc") or item.get("description") or "").strip()
        ambi_type = str(item.get("AmbiType") or item.get("ambiguity_type") or item.get("type") or "").strip()
        opts_raw = item.get("Options") or item.get("AmbiOpts") or item.get("options") or []
        opts: list[dict[str, str]] = []
        if isinstance(opts_raw, list):
            for opt in opts_raw:
                if isinstance(opt, dict):
                    snippet = str(opt.get("snippet") or opt.get("option_content") or opt.get("content") or "").strip()
                    interp = str(opt.get("interpretation") or opt.get("option_note") or opt.get("note") or "").strip()
                    if snippet or interp:
                        opts.append({"snippet": snippet, "interpretation": interp})
                elif isinstance(opt, (list, tuple)) and opt:
                    snippet = str(opt[0]).strip()
                    interp = str(opt[1]).strip() if len(opt) > 1 else ""
                    if snippet or interp:
                        opts.append({"snippet": snippet, "interpretation": interp})
                else:
                    snippet = str(opt).strip()
                    if snippet:
                        opts.append({"snippet": snippet, "interpretation": ""})

        if not context and not descrip and not ambi_type and not opts:
            continue
        output.append(
            {
                "AmbiContext": context,
                "AmbiContext_descrip": descrip,
                "AmbiType": ambi_type,
                "Options": opts,
            }
        )
    return output


def _extract_content(out: Any) -> str | None:
    """Extract content from a model response, handling thinking-mode fallback."""
    print(out)
    content = getattr(out, "content", None)
    if content is not None:
        return str(content).strip()

    # Try reasoning field inside raw ChatCompletion (vLLM Qwen3 thinking mode)
    raw = getattr(out, "raw", None)
    if raw is not None:
        try:
            msg = raw.choices[0].message
            if msg.content:
                return msg.content.strip()
            reasoning = getattr(msg, "reasoning", None)
            if reasoning:
                logger.warning("Extracting content from raw.message.reasoning fallback.")
                return reasoning.strip()
        except (IndexError, AttributeError):
            pass
    return None


# ======================================================================
# Structured Candidate Generation (for cand_gen_type="structured")
# ======================================================================

REASONING_STRUCTURED = """\
## Step-by-step reasoning process
1. **Analyze the context**: NL question, original SQL, schema, retrieved confusing options.
2. **Identify ambiguity triggers**: For each ambiguity type (AmbiScope, AmbiAttach, AmbiIntent, AmbiColumn, AmbiValue, AmbiOp), check if the NL question or SQL contains triggers.
3. **Generate interpretations per trigger**: For each distinct ambiguity context, produce at least 2 interpretation options with complete runnable full_sql.
4. **Only include if interpretations produce meaningfully different results**: If all interpretations yield the same execution result, the ambiguity is not meaningful.
- Learn from the taxonomy examples and apply pattern recognition to this specific context.
"""

STRUCTURED_CANDGEN_OUTPUT_EXAMPLE = """\
Example output (JSON array):
```json
[
  {
    "AmbiContext": "count product categories",
    "AmbiType": "AmbiOp",
    "InterpretationOpts": [
      {"snippet": "COUNT(category)", "interpretation": "Counts all rows including duplicates", "full_sql": "SELECT COUNT(category) FROM products"},
      {"snippet": "COUNT(DISTINCT category)", "interpretation": "Counts only unique category values", "full_sql": "SELECT COUNT(DISTINCT category) FROM products"},
      {"snippet": "COUNT(DISTINCT LOWER(category))", "interpretation": "Counts case-normalized unique values", "full_sql": "SELECT COUNT(DISTINCT LOWER(category)) FROM products"}
    ]
  },
  {
    "AmbiContext": "school names containing High",
    "AmbiType": "AmbiColumn",
    "InterpretationOpts": [
      {"snippet": "school_name LIKE '%High%'", "interpretation": "Match on Schools.school_name column", "full_sql": "SELECT school_name FROM Schools WHERE school_name LIKE '%High%'"},
      {"snippet": "sname LIKE '%High%'", "interpretation": "Match on SATScores.sname column", "full_sql": "SELECT sname FROM SATScores WHERE sname LIKE '%High%'"},
      {"snippet": "s.school_name LIKE '%High%' OR sc.sname LIKE '%High%'", "interpretation": "Either column can match (OR logic)", "full_sql": "SELECT s.school_name FROM Schools s JOIN SATScores sc ON s.school_id = sc.school_id WHERE s.school_name LIKE '%High%' OR sc.sname LIKE '%High%'"}
    ]
  }
]
```"""


def build_structured_candgen_prompt(
    user_question: str,
    sql_text: str,
    schema_text: str,
    retrieved_column_options: list[dict[str, Any]],
    retrieved_value_options: list[dict[str, Any]],
    preferences_text: str = "",
    fixing_history: str = "",
) -> str:
    """Build a prompt for structured candidate generation.

    The LLM outputs a JSON array of ambiguity entries directly, each with
    AmbiContext, AmbiType, and InterpretationOpts (snippet/interpretation/full_sql).
    """
    col_options_text = json.dumps(retrieved_column_options[:8], indent=2) if retrieved_column_options else "none"
    value_options_text = json.dumps(retrieved_value_options[:8], indent=2) if retrieved_value_options else "none"
    fixing_block = f"\n## Previously Fixed Issues\n{fixing_history}\n" if fixing_history else ""

    prompt = f"""## Task: Structured Ambiguity Detection & Candidate Generation

You are an expert in identifying SQL ambiguity from an execution-distinctions perspective.

### Output Instructions
Output exactly one of:
- "NO AMBIGUITY" if no meaningful ambiguity exists.
- A JSON array of ambiguity entries.

Each entry format:
{{
  "AmbiContext": "shortest NL substring with ambiguity",
  "AmbiType": "AmbiIntent|AmbiColumn|AmbiValue|AmbiOp|AmbiScope|AmbiAttach",
  "InterpretationOpts": [
    {{
      "snippet": "minimal SQL fragment highlighting the difference",
      "interpretation": "clear description of what this interpretation means",
      "full_sql": "complete runnable SQL query for this interpretation (can reuse non-ambiguous parts from original SQL)"
    }}
  ]
}}

**IMPORTANT**: Each entry MUST have at least 2 interpretation options. Single-option entries are NOT valid.

{STRUCTURED_CANDGEN_OUTPUT_EXAMPLE}

---
## Current Task

Analyze for all 6 ambiguity types:
1. **AmbiScope**: Quantifier scope (every/all/each — per-item vs. collective).
2. **AmbiAttach**: Modifier/conjunction attachment (wide vs. narrow scope).
3. **AmbiIntent**: Vague/under-defined terms (recent, large, profile, report, etc.).
4. **AmbiColumn**: Phrase matching multiple possible columns.
5. **AmbiValue**: Constant matching multiple stored values.
6. **AmbiOp**: Operational ambiguity (NULL handling, ranking, join types, etc.).

{REASONING_STRUCTURED}

## User Question
{user_question}

## Current Best SQL
{sql_text}

## Retieved DB Column Options (possible column ambiguities)
{col_options_text}

## Retrieved DB Value Options (possible value ambiguities)
{value_options_text}
{fixing_block}
## Database & Schema
{schema_text}
"""
    if preferences_text:
        prompt += f"\n## User Preferences\n{preferences_text}\n"
    return prompt


def parse_structured_candgen_output(raw_text: str) -> list[dict[str, Any]]:
    """Parse structured ambiguity entries from LLM output.

    Returns list of dicts with:
      - AmbiContext: str
      - AmbiType: str
      - InterpretationOpts: [{"snippet": str, "interpretation": str, "full_sql": str}, ...]
    """
    text = (raw_text or "").strip()
    if not text:
        return []

    # Strip markdown code fences
    if text.startswith("```json"):
        text = text[7:].lstrip()
    elif text.startswith("```"):
        text = text[3:].lstrip()
    if text.endswith("```"):
        text = text[:-3].rstrip()

    # Try direct JSON parse
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        # Fallback: extract JSON array
        left = text.find("[")
        right = text.rfind("]")
        if left >= 0 and right > left:
            try:
                payload = json.loads(text[left: right + 1])
            except json.JSONDecodeError:
                return []
        else:
            return []

    if isinstance(payload, dict):
        # Handle wrapper formats
        for key in ("items", "ambiguity_entries", "entries"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            return []

    if not isinstance(payload, list):
        return []

    output: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        context = str(item.get("AmbiContext") or item.get("ambiguity_context") or item.get("context") or "").strip()
        ambi_type = str(item.get("AmbiType") or item.get("ambiguity_type") or item.get("type") or "").strip()
        opts_raw = (
            item.get("InterpretationOpts")
            or item.get("interpretationOpts")
            or item.get("options")
            or item.get("Options")
            or []
        )
        if not isinstance(opts_raw, list):
            continue

        opts: list[dict[str, str]] = []
        for opt in opts_raw:
            if not isinstance(opt, dict):
                continue
            snippet = str(opt.get("snippet") or "").strip()
            interp = str(opt.get("interpretation") or "").strip()
            full_sql = str(opt.get("full_sql") or "").strip()
            if not snippet and not interp and not full_sql:
                continue
            opts.append({"snippet": snippet, "interpretation": interp, "full_sql": full_sql})

        if not context and not ambi_type and not opts:
            continue
        # Require at least 2 options
        if len(opts) < 2:
            continue
        output.append({
            "AmbiContext": context,
            "AmbiType": ambi_type,
            "InterpretationOpts": opts,
        })
    return output


def call_model_text(model: Any, prompt: str, max_tokens: int = 16384) -> str:
    messages = [{"role": "user", "content": prompt}]

    # First attempt — rely on higher max_tokens to let thinking finish.
    out = model(messages, max_tokens=max_tokens, extra_body={"streaming": False})
    # Debug output handled via logger
    content = _extract_content(out)
    if content is not None:
        return content

    # content is None — probably Qwen3 thinking mode consumed all tokens.
    # Retry once with thinking disabled.
    logger.warning("First call returned content=None (likely thinking mode). Retrying with thinking disabled...")
    out = model(messages, max_tokens=max_tokens, extra_body={"streaming": False, "enable_thinking": False})
    # Debug output handled via logger
    content = _extract_content(out)
    if content is not None:
        return content

    # Last resort: raw reasoning field (still useful for debugging).
    logger.warning("Retry also returned content=None. Falling back to raw reasoning field.")
    raw = getattr(out, "raw", None)
    if raw is not None:
        try:
            reasoning = getattr(raw.choices[0].message, "reasoning", None)
            if reasoning:
                return reasoning.strip()
        except (IndexError, AttributeError):
            pass
    return ""
