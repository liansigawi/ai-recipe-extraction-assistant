"""Two quality-check runs side by side, case by case.

    uv run python -m evals.compare <run folder A> <run folder B>

The folders are under <data folder>/evals/extraction/. Each has the summary.json written by
evals/run_extraction.py; a rescored.json (evals/rescore.py) is used instead when there is one, so
older runs are compared under today's checks. Prints a Markdown table: for every case, the checks
passed, the problems (and minor ones), the unnecessary or duplicate review points, and the time.
"""

import json
import sys
from pathlib import Path

from app.config import load_settings


def load(arg: str) -> dict:
    folder = Path(arg)
    if not folder.is_absolute() and not folder.exists():
        folder = load_settings().data_dir / "evals" / "extraction" / arg
    for name in ("rescored.json", "summary.json"):
        if (folder / name).exists():
            return json.loads((folder / name).read_text(encoding="utf-8")) | {"name": folder.name, "file": name}
    raise FileNotFoundError(folder)


def cell(case: dict | None) -> str:
    if case is None:
        return "–"
    checks = sum(case["checked"].values())
    failed = sum(case["failed"].values()) - case["minor_problems"]
    warnings = case["warnings"]
    extra = len(warnings["unnecessary"]) + len(warnings["duplicates"])
    return f"{checks - failed}/{checks}, {case['problems']} problems{f', {extra} needless points' if extra else ''}, {case.get('seconds', 0):.0f} s"


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    a, b = load(sys.argv[1]), load(sys.argv[2])
    print(f"A: {a['name']} ({a['file']}) · B: {b['name']} ({b['file']})\n")
    print("| case | A | B |\n|---|---|---|")
    for name in sorted(set(a["cases"]) | set(b["cases"])):
        print(f"| {name} | {cell(a['cases'].get(name))} | {cell(b['cases'].get(name))} |")
    for run, label in ((a, "A"), (b, "B")):
        t = run["totals"]
        passed = ", ".join(f"{area} {n - t['failed'].get(area, 0)}/{n}" for area, n in t["checked"].items())
        print(f"\n{label}: {passed}. Problems {t['problems']} (minor {t['minor_problems']}); every check passed in "
              f"{t['cases_all_passed']} of {len(run['cases'])}; review points {t['warnings_shown']} "
              f"(unnecessary {t['unnecessary_warnings']}, duplicates {t['duplicate_warnings']}); {t['seconds']:.0f} s.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
