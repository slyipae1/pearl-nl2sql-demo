"""Generate a fully synthetic SQLite fixture for the PEARL demo.

The generator creates eight tables with fabricated values only:

  * people: ``Person-001`` ... ``Person-055``
  * projects: ``Synthetic Project NN`` with ``SYN-REF-*`` / ``SYN-PID-*`` /
    ``SYN-FIN-*`` identifiers
  * funding sources: ``SYN-FUND-*``
  * free text: ``Synthetic note NN``
  * amounts and dates: sampled from broad artificial ranges

Generic category labels such as ``PhD Student``, ``Postdoc`` and ``Current``
are used by the demo questions.

Usage:
    python3 examples/make_demo_db.py
    python3 examples/make_demo_db.py --output /path/to/demo.sqlite
"""

from __future__ import annotations

import argparse
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DEFAULT_OUTPUT = Path(__file__).resolve().parent / "synthetic_demo.sqlite"
SEED = 20261126

# ---------------------------------------------------------------------------
# Synthetic value pools used to generate the fixture.
# ---------------------------------------------------------------------------
SYNTHETIC_NAMES = [f"Person-{i:03d}" for i in range(1, 56)]
SYNTHETIC_ROLES = [
    "PhD Student",
    "Masters Student",
    "Postdoc",
    "Research Assistant",
    "Admin",
    "Visitor",
]
SYNTHETIC_POSITIONS = [
    "PhD Student",
    "Postdoc",
    "Research Assistant",
    "Admin",
]
SYNTHETIC_TITLES = [f"Synthetic Project {i:02d}" for i in range(1, 35)]
SYNTHETIC_REFS = [f"SYN-REF-{i:03d}" for i in range(1, 36)]
SYNTHETIC_PIDS = [f"SYN-PID-{i:03d}" for i in range(1, 36)]
SYNTHETIC_FIN_IDS = [f"SYN-FIN-{i:03d}" for i in range(1, 36)]
SYNTHETIC_SPONSORS = [f"Synthetic Sponsor {i:02d}" for i in range(1, 17)]
SYNTHETIC_FUND_CODES = [f"SYN-FUND-{i:03d}" for i in range(1, 14)]
SYNTHETIC_NOTES = [f"Synthetic note {i:03d}" for i in range(1, 51)]
# Artificial years for the synthetic fixture.
SYNTHETIC_YEARS = ["2027", "2028", "2029", "2030"]
SYNTHETIC_STATUSES = ["Current", "Closed", "Under Planning", "Synthetic Status"]
SYNTHETIC_CATEGORIES = ["PI", "Co-PI", "Co-I", "Director", "Synthetic Category"]
SYNTHETIC_SOURCES = ["Industry", "Government", "Internal", "Synthetic Source"]
SYNTHETIC_NATURE = ["full-time", "part-time"]
SYNTHETIC_BUDGET_LABELS = [
    "Synthetic budget line A",
    "Synthetic budget line B",
    "Synthetic budget line C",
]

BUDGET_COLUMNS = [
    f"{group}_{suffix}"
    for group in ("Salaries", "Travel", "Conference", "Equipment", "Other")
    for suffix in ("Expected", "Spent", "Committed", "Available")
]

FUNDING_COLUMNS = ["ID", "Short_Title", "Year", "Total", *BUDGET_COLUMNS, "Notes"]
PROJECT_COLUMNS = [
    "Reference_No", "Title", "Source", "Category", "Status",
    "Date_Start", "Date_End", "Date_Final_Close", "Financial_ID",
    "Funding_Total", "Funding_Received", "Funding_Committed", "Funding_Available",
    "Team_members", "Deliverables_Papers", "Deliverables_Patents",
    "Deliverables_Other", "Progress_Papers", "Progress_Patents",
    "Progress_Other", "Link", "Notes",
]

TABLES: dict[str, dict] = {
    "Funding_Details": {
        "rows": 11,
        "columns": FUNDING_COLUMNS,
        "types": {c: "TEXT" for c in ("ID", "Short_Title", "Notes")}
        | {"Year": "INTEGER"}
        | {c: "REAL" for c in ("Total", *BUDGET_COLUMNS)},
        "null": {"Salaries_Expected": .73, "Salaries_Spent": .73,
                 "Salaries_Committed": .82, "Salaries_Available": .73,
                 **{c: 1.0 for c in BUDGET_COLUMNS[4:]}, "Notes": 1.0},
    },
    "Funding_Summary": {
        "rows": 10,
        "columns": FUNDING_COLUMNS,
        "types": {c: "TEXT" for c in ("ID", "Short_Title", "Year", "Notes")}
        | {"Total": "REAL"} | {c: "REAL" for c in BUDGET_COLUMNS},
        "null": {"Year": .1, "Salaries_Expected": .4, "Salaries_Spent": .4,
                 "Salaries_Committed": .4, "Salaries_Available": .4,
                 "Travel_Expected": .8, "Travel_Spent": .8,
                 "Travel_Committed": .8, "Travel_Available": .8,
                 "Conference_Expected": .9, "Conference_Spent": 1.0,
                 "Conference_Committed": 1.0, "Conference_Available": 1.0,
                 "Equipment_Expected": .8, "Equipment_Spent": .7,
                 "Equipment_Committed": 1.0, "Equipment_Available": .8,
                 "Other_Expected": .6, "Other_Spent": .6,
                 "Other_Committed": 1.0, "Other_Available": .6, "Notes": 1.0},
    },
    "People": {
        "rows": 104,
        "columns": ["Name", "Category", "Date_Start", "Date_End", "Cost_Year",
                    "Cost_Cost", "Cost_Funding_Source", "Notes"],
        "types": {"Name": "TEXT", "Category": "TEXT", "Date_Start": "DATE",
                  "Date_End": "DATE", "Cost_Year": "TEXT", "Cost_Cost": "REAL",
                  "Cost_Funding_Source": "TEXT", "Notes": "TEXT"},
        "null": {"Category": .15, "Date_Start": .01, "Date_End": .63,
                 "Cost_Year": .32, "Cost_Cost": .58,
                 "Cost_Funding_Source": .62, "Notes": .93},
        "pk": ("Name", "Cost_Year"),
    },
    "Project_TRS_format": {
        "rows": 25,
        "columns": ["Reference_No", "Title", "Status", "Category", "Source",
                    "Date_Start", "Date_End"],
        "types": {c: "TEXT" for c in ("Reference_No", "Title", "Status", "Category", "Source")}
        | {"Date_Start": "DATE", "Date_End": "DATE"},
        "null": {"Reference_No": .24, "Status": .04, "Category": .28,
                 "Source": .04, "Date_Start": .2, "Date_End": .2},
        "pk": ("Reference_No", "Title"),
    },
    "Projects": {
        "rows": 23,
        "columns": PROJECT_COLUMNS,
        "types": {c: "TEXT" for c in PROJECT_COLUMNS if not c.startswith(("Funding_", "Date_"))}
        | {"Date_Start": "DATE", "Date_End": "DATE", "Date_Final_Close": "DATE"}
        | {c: "REAL" for c in PROJECT_COLUMNS if c.startswith("Funding_")},
        "null": {"Reference_No": .26, "Source": .09, "Category": .35,
                 "Date_Start": .22, "Date_End": .22, "Date_Final_Close": 1.0,
                 "Financial_ID": .48, "Funding_Total": .43,
                 "Funding_Received": .65, "Funding_Committed": .65,
                 "Funding_Available": .65, "Team_members": .65,
                 "Deliverables_Papers": .83, "Deliverables_Patents": .91,
                 "Deliverables_Other": .74, "Progress_Papers": .65,
                 "Progress_Patents": 1.0, "Progress_Other": .96,
                 "Link": 1.0, "Notes": .91},
        "pk": ("Reference_No", "Title"),
    },
    "Projects_deliverables": {
        "rows": 24,
        "columns": PROJECT_COLUMNS,
        "types": {c: "TEXT" for c in PROJECT_COLUMNS if not c.startswith(("Funding_", "Date_"))}
        | {"Date_Start": "DATE", "Date_End": "DATE", "Date_Final_Close": "DATE"}
        | {c: "REAL" for c in PROJECT_COLUMNS if c.startswith("Funding_")},
        "null": {"Reference_No": .25, "Source": .88, "Category": .08,
                 "Status": .33, "Date_End": .21, "Date_Final_Close": .21,
                 "Financial_ID": 1.0, "Funding_Total": .46,
                 "Funding_Received": .42, "Funding_Committed": .62,
                 "Funding_Available": .62, "Team_members": .62,
                 "Deliverables_Papers": .67, "Deliverables_Patents": .83,
                 "Deliverables_Other": .92, "Progress_Papers": .75,
                 "Progress_Patents": .67, "Progress_Other": 1.0,
                 "Link": .96, "Notes": 1.0},
        "pk": ("Reference_No", "Title"),
    },
    "工资管理": {
        "rows": 22,
        "columns": ["姓名", "职位", "成本", "百分比", "开始时间", "结束时间",
                    "实时成本", "性质", "资金来源", "明细"],
        "types": {"姓名": "TEXT", "职位": "TEXT", "成本": "REAL",
                  "百分比": "REAL", "开始时间": "DATE", "结束时间": "DATE",
                  "实时成本": "REAL", "性质": "TEXT", "资金来源": "TEXT",
                  "明细": "TEXT"},
        "null": {"职位": .14, "百分比": .64, "开始时间": .55,
                 "结束时间": .55, "性质": .82, "资金来源": .86, "明细": .86},
        "pk": ("姓名", "开始时间", "明细"),
    },
    "项目经费总表": {
        "rows": 34,
        "columns": ["Project_No", "Project_ID", "Project_title", "Sponsor",
                    "项目状态", "项目开始时间", "项目结束时间", "项目结余",
                    "可供花销类目", "项目总资金_收入", "承诺支出_Committed",
                    "支出_Expense", "计划支出_Plan", "项目负责人", "备注",
                    "经费明细表_记录时间", "项目成员", "明细", "人员管理",
                    "人员管理_副本"],
        "types": {c: "REAL" for c in ("项目结余", "项目总资金_收入",
                                       "承诺支出_Committed", "支出_Expense",
                                       "计划支出_Plan")}
        | {c: "DATE" for c in ("项目开始时间", "项目结束时间")}
        | {c: "TEXT" for c in ("Project_No", "Project_ID", "Project_title",
                               "Sponsor", "项目状态", "可供花销类目",
                               "项目负责人", "备注", "经费明细表_记录时间",
                               "项目成员", "明细", "人员管理", "人员管理_副本")},
        "null": {"Project_ID": .09, "Project_title": .09, "Sponsor": .29,
                 "项目状态": .09, "项目开始时间": .09, "项目结束时间": .09,
                 "可供花销类目": .15, "项目总资金_收入": .03,
                 "承诺支出_Committed": .62, "支出_Expense": .5,
                 "计划支出_Plan": .97, "项目负责人": .71, "备注": .74,
                 "经费明细表_记录时间": .88, "项目成员": 1.0, "明细": .68,
                 "人员管理": .91, "人员管理_副本": .91},
        "pk": ("Project_No", "Project_ID", "明细"),
    },
}


def _date(rng: random.Random) -> str:
    d = date(2016, 1, 1) + timedelta(days=rng.randint(0, 729))
    return f"{d.isoformat()} 00:00:00"


def _money(rng: random.Random) -> float:
    return round(rng.uniform(500, 2_500_000), 2)


def _value(rng: random.Random, table: str, col: str, i: int):
    """Return a fabricated value for one cell."""
    if col in ("ID", "Project_No", "Reference_No"):
        return SYNTHETIC_REFS[i % len(SYNTHETIC_REFS)]
    if col in ("Project_ID",):
        return SYNTHETIC_PIDS[i % len(SYNTHETIC_PIDS)]
    if col in ("Financial_ID",):
        return SYNTHETIC_FIN_IDS[i % len(SYNTHETIC_FIN_IDS)]
    if col in ("Short_Title", "Title", "Project_title"):
        return SYNTHETIC_TITLES[i % len(SYNTHETIC_TITLES)]
    if col in ("Name", "姓名", "Team_members", "项目负责人", "项目成员",
               "人员管理", "人员管理_副本"):
        return SYNTHETIC_NAMES[i % len(SYNTHETIC_NAMES)]
    if col in ("Category", "职位"):
        # Keep PhD Student dominant in People but rare in payroll so that the
        # two interpretations in Case 1 produce different counts.
        if table == "工资管理":
            return SYNTHETIC_POSITIONS[0] if i % 4 == 0 else rng.choice(SYNTHETIC_POSITIONS[1:])
        return SYNTHETIC_ROLES[0] if i % 2 == 0 else rng.choice(SYNTHETIC_ROLES[1:])
    if col in ("Cost_Funding_Source", "资金来源"):
        return rng.choice(SYNTHETIC_FUND_CODES)
    if col == "Sponsor":
        return rng.choice(SYNTHETIC_SPONSORS)
    if col == "Status" or col == "项目状态":
        return rng.choice(SYNTHETIC_STATUSES)
    if col in ("Source",):
        return rng.choice(SYNTHETIC_SOURCES)
    if col == "性质":
        return rng.choice(SYNTHETIC_NATURE)
    if col == "可供花销类目":
        return ", ".join(rng.sample(SYNTHETIC_BUDGET_LABELS, rng.randint(1, 3)))
    if col in ("Notes", "备注", "明细", "Link", "Deliverables_Papers",
               "Deliverables_Patents", "Deliverables_Other", "Progress_Papers",
               "Progress_Patents", "Progress_Other", "经费明细表_记录时间"):
        return SYNTHETIC_NOTES[i % len(SYNTHETIC_NOTES)]
    if col in ("Year", "Cost_Year"):
        return rng.choice(SYNTHETIC_YEARS)
    if col in ("Date_Start", "Date_End", "Date_Final_Close",
               "开始时间", "结束时间", "项目开始时间", "项目结束时间"):
        return _date(rng)
    if col in ("百分比",):
        return round(rng.uniform(0, 100), 2)
    if col in ("成本", "实时成本"):
        return round(rng.uniform(0, 450_000), 2)
    if col in ("项目结余", "项目总资金_收入", "承诺支出_Committed",
               "支出_Expense", "计划支出_Plan", "Total", "Cost_Cost"):
        return _money(rng)
    if col.startswith("Funding_") or col in BUDGET_COLUMNS:
        return _money(rng)
    raise ValueError(f"No synthetic generator for column {table}.{col}")


def build(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    conn = sqlite3.connect(output)
    cur = conn.cursor()
    rng = random.Random(SEED)

    for table, spec in TABLES.items():
        defs = []
        for col in spec["columns"]:
            typ = spec["types"].get(col, "TEXT")
            defs.append(f'"{col}" {typ}')
        if spec.get("pk"):
            pk = ", ".join(f'"{c}"' for c in spec["pk"])
            defs.append(f"PRIMARY KEY ({pk})")
        cur.execute(f'CREATE TABLE "{table}" ({", ".join(defs)})')

        nulls = spec.get("null", {})
        cols_sql = ", ".join(chr(34) + c + chr(34) for c in spec["columns"])
        placeholders = ", ".join("?" for _ in spec["columns"])
        for i in range(spec["rows"]):
            # Retry on synthetic PK collisions (small fabricated pools).
            for _ in range(100):
                row = []
                for col in spec["columns"]:
                    if rng.random() < nulls.get(col, 0.0):
                        row.append(None)
                    else:
                        row.append(_value(rng, table, col, i))
                try:
                    cur.execute(
                        f'INSERT INTO "{table}" ({cols_sql}) VALUES ({placeholders})',
                        row,
                    )
                    break
                except sqlite3.IntegrityError:
                    continue
            else:
                raise RuntimeError(f"Could not generate unique row {i} for {table}")
    conn.commit()
    conn.close()
    print(f"Wrote synthetic demo database to {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    build(args.output)


if __name__ == "__main__":
    main()
