"""Score saved quality-check runs again with the current expectations and checks. No model calls.

    uv run python -m evals.rescore <run folder> [<run folder> ...]

Uses each case's saved draft exactly as that run produced it (so a run keeps showing what its own
code did), the case texts and the expectation files of today. Writes <run>/rescored.json, in the
same shape as a run's summary.json plus each case's findings; the run's own files are not changed.
"""

import json
import sys
from pathlib import Path

from app.config import load_settings
from evals.run_extraction import CASES_DIR, CATEGORIES, case_summary, summary_lines
from evals.scoring import score_case, totals


def case_folders() -> list[Path]:
    return [CASES_DIR, load_settings().data_dir / "evals" / "local-cases"]


def rescore(run: Path) -> dict:
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    cases = {}
    for record_file in sorted(run.glob("*.json")):
        if record_file.name in ("summary.json", "rescored.json"):
            continue
        name = record_file.stem
        folder = next((f for f in case_folders() if (f / f"{name}.json").exists()), None)
        if folder is None:
            continue  # a case that no longer exists
        record = json.loads(record_file.read_text(encoding="utf-8"))
        expect = json.loads((folder / f"{name}.json").read_text(encoding="utf-8")).get("expect", {})
        source = (folder / f"{name}.txt").read_text(encoding="utf-8")
        scored = record | score_case(expect, source, record["draft"], record["error"], CATEGORIES)
        cases[name] = case_summary(scored) | {"findings": scored["findings"]}
    result = {key: summary.get(key) for key in ("model", "provider", "mode", "gpu")} | {"cases": cases}
    result["totals"] = totals(cases)
    (run / "rescored.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    for arg in sys.argv[1:]:
        run = Path(arg)
        if not run.is_absolute() and not run.exists():
            run = load_settings().data_dir / "evals" / "extraction" / arg
        result = rescore(run)
        print(f"{run.name} ({len(result['cases'])} cases):")
        print("\n".join("  " + line for line in summary_lines(result, len(result["cases"]))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
