# Synthetic Demo Scenarios

The bundled `synthetic_demo.sqlite` is fully synthetic. Regenerate it with:

```bash
python3 examples/make_demo_db.py
```

The generator uses a fixed seed (`SEED = 20261126`), so the counts below are stable.

Names (`Person-001` …), project titles (`Synthetic Project NN`), reference IDs (`SYN-REF-*`), funding codes (`SYN-FUND-*`) and notes are all fabricated.

## Case 1 — Execution-grounded guidance

Question: “How many PhD students in total?”

| Interpretation | SQL | Count |
|---|---|---|
| People roster | `SELECT COUNT(*) FROM People WHERE Category = 'PhD Student'` | 48 |
| Payroll roster | `SELECT COUNT(*) FROM 工资管理 WHERE 职位 = 'PhD Student'` | 4 |

The differing execution results are the evidence surfaced to the user, who picks the intended source.

## Case 2 — Preference reuse

Follow-up question: “List names of all PhD students.”

If the `People` source was selected in Case 1, the preference base supplies that context on the follow-up, reducing repeated clarification. Preferences are stored per database as JSON.

## Same-result check

```sql
SELECT COUNT(*) FROM People WHERE Category = 'PhD Student';
SELECT COUNT(*) FROM People WHERE Category LIKE 'PhD%';
```

Both return the same count; syntactically different SQL with identical results should not trigger a clarification.
