"""Rebuild saved runs' drafts from their saved model answers with today's backend code, and score them.

    uv run python -m evals.rebuild <label> <run folder> [<run folder> ...]

No model calls: the model's answers stay exactly as they were, so the difference from the run's own
drafts is only what the backend does with them (for example how quantities are read). Writes
<run>/rebuilt-<label>.json in the shape of rescored.json; the run's own files are not changed.
Answers whose shape no longer fits today's code (fields that were removed since) are adapted:
a passage label written as {"role": ..., "quantity": ...} becomes its role.
"""

import json
import sys
from pathlib import Path

from app.config import load_settings
from app.extraction.output import ReferenceOutput
from app.extraction.review import make_draft
from evals.rescore import case_folders
from evals.run_extraction import CATEGORIES, case_summary, summary_lines
from evals.scoring import score_case, totals


def adapt(answer: dict) -> dict:
    passages = {key: value["role"] if isinstance(value, dict) else value for key, value in answer["passages"].items()}
    return answer | {"passages": passages}


def rebuild(run: Path, label: str) -> dict:
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    cases = {}
    for record_file in sorted(run.glob("*.json")):
        if record_file.name == "summary.json" or record_file.name.startswith(("rescored", "rebuilt")):
            continue
        name = record_file.stem
        folder = next((f for f in case_folders() if (f / f"{name}.json").exists()), None)
        if folder is None:
            continue
        record = json.loads(record_file.read_text(encoding="utf-8"))
        expect = json.loads((folder / f"{name}.json").read_text(encoding="utf-8")).get("expect", {})
        source = (folder / f"{name}.txt").read_text(encoding="utf-8")
        draft = None
        if record["answer"] is not None and record["error"] is None:
            draft = make_draft(ReferenceOutput.model_validate(adapt(record["answer"])), source, CATEGORIES)
        scored = record | {"draft": draft.model_dump(mode="json") if draft else None}
        scored |= score_case(expect, source, draft, record["error"], CATEGORIES)
        cases[name] = case_summary(scored) | {"findings": scored["findings"], "draft": scored["draft"]}
    result = {key: summary.get(key) for key in ("model", "provider", "mode", "gpu")} | {"cases": cases}
    result["totals"] = totals(cases)
    (run / f"rebuilt-{label}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    label = sys.argv[1]
    for arg in sys.argv[2:]:
        run = Path(arg)
        if not run.is_absolute() and not run.exists():
            run = load_settings().data_dir / "evals" / "extraction" / arg
        result = rebuild(run, label)
        print(f"{run.name} rebuilt ({label}, {len(result['cases'])} cases):")
        print("\n".join("  " + line for line in summary_lines(result, len(result["cases"]))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
