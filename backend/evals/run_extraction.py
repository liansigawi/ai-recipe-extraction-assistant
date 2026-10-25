"""Extraction quality check: real model requests on representative recipe texts.

Separate from the software tests: each case is one real request (paid, with Claude), and the
results depend on the model. Run it by hand, from backend/:

    uv run python -m evals.run_extraction                              every case in evals/cases/
    uv run python -m evals.run_extraction --case 04-english-quick-salad   one case (repeatable)
    uv run python -m evals.run_extraction --cases-dir ../data/evals/local-cases
                                       also your own cases, e.g. real captions (git-ignored)
    uv run python -m evals.run_extraction --extractor ollama --mode text
                                       a local model, with the text-copying approach

Bounded: at most MAX_CASES requests per run, one at a time, each with the backend's own
limits. Uses the same settings as the backend (RECIPES_EXTRACTOR, RECIPES_EXTRACTION_MODE,
ANTHROPIC_API_KEY, RECIPES_MODEL, RECIPES_OLLAMA_*); the options override them for one run.

Each case is <name>.txt (the text, exactly as pasted) and <name>.json (what to expect; see
evals/checks.py). The answer goes through the same checks as a real import
(app/extraction/review.py). Results in <data folder>/evals/extraction/<run>/: report.md, a
summary.json for evals/compare.py, and each case's raw answer, draft and findings as JSON.
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx2

from app import schemas
from app.config import load_settings
from app.errors import ApiError
from app.extraction.choose import extraction_info, make_extractor
from app.extraction.claude import Extractor
from app.extraction.review import is_recipe, make_draft
from app.sample_data import STARTER_CATEGORIES
from evals.scoring import score_case, totals, verdict

CASES_DIR = Path(__file__).parent / "cases"
MAX_CASES = 40  # bounded: with Claude each case is one paid request

# The categories of a new notebook, with the ids a new database gives them.
CATEGORIES = [
    schemas.Category(id=index, name=name, description=description)
    for index, (name, description) in enumerate(STARTER_CATEGORIES, start=1)
]


def load_cases(folders: list[Path], only: list[str]) -> list[tuple[str, str, dict]]:
    cases = []
    for folder in folders:
        for expect_file in sorted(folder.glob("*.json")):
            name = expect_file.stem
            if only and name not in only:
                continue
            text = expect_file.with_suffix(".txt").read_text(encoding="utf-8")
            cases.append((name, text, json.loads(expect_file.read_text(encoding="utf-8"))))
    return cases


def run_case(extractor: Extractor, text: str, expect: dict) -> dict:
    output = draft = error_code = None
    started = time.monotonic()
    try:
        output = extractor.extract(text, CATEGORIES)
        if not is_recipe(output):
            error_code = "not_a_recipe"
        else:
            draft = make_draft(output, text, CATEGORIES)
    except ApiError as error:
        error_code = error.code
    seconds = round(time.monotonic() - started, 1)
    return {
        "seconds": seconds,
        "usage": getattr(extractor, "last_usage", {}),
        "error": error_code,
        "raw": getattr(extractor, "last_raw", None),  # the model's answer exactly as received
        "answer": output.model_dump(mode="json") if output else None,
        "draft": draft.model_dump(mode="json") if draft else None,
    } | score_case(expect.get("expect", {}), text, draft, error_code, CATEGORIES)


def stay_awake() -> None:
    """Ask Windows not to sleep while this run lasts (a laptop that slept mid-run made one case
    take 26 minutes). The request ends with the process; no power setting is changed."""
    if sys.platform == "win32":
        import ctypes

        es_continuous, es_system_required = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(es_continuous | es_system_required)


def gpu_use(settings) -> dict | None:
    """How much of the local model is on the GPU, from Ollama's own report (GET /api/ps)."""
    if settings.extractor != "ollama":
        return None
    try:
        models = httpx2.get(settings.ollama_url + "/api/ps", timeout=5).json().get("models") or []
    except httpx2.HTTPError:
        return None
    for model in models:
        if model.get("name") == settings.ollama_model or model.get("model") == settings.ollama_model:
            size, vram = model.get("size", 0), model.get("size_vram", 0)
            return {
                "size_gb": round(size / 1e9, 2),
                "on_gpu_gb": round(vram / 1e9, 2),
                "on_gpu_percent": round(100 * vram / size) if size else None,
                "context": model.get("context_length"),
            }
    return None


def describe_draft(record: dict) -> list[str]:
    draft = record["draft"]
    if draft is None:
        return [f"- No draft: `{record['error']}`"]
    names = {category.id: category.name for category in CATEGORIES}
    lines = [
        f"- **Title:** {draft['title']}",
        f"- **Servings:** {draft['servings']}",
        f"- **Category:** {names.get(draft['category_id'], 'unresolved')}",
    ]
    for group in draft["ingredient_groups"]:
        lines.append(f"- **Ingredients{' – ' + group['name'] if group['name'] else ''}:**")
        lines += [f"  - {item['text']}  ·  quantity: `{item['quantity']}`" for item in group["ingredients"]]
    for group in draft["step_groups"]:
        lines.append(f"- **Steps{' – ' + group['name'] if group['name'] else ''}:**")
        lines += [f"  {number}. {step}" for number, step in enumerate(group["steps"], start=1)]
    if draft["notes"]:
        lines.append("- **Notes:**")
        lines += [f"  - {note}" for note in draft["notes"]]
    if draft["issues"]:
        lines.append("- **Flagged for review:**")
        lines += [
            f"  - `{issue['kind']}`: {issue['message']}" + (f" (quote: «{issue['quote']}»)" if issue["quote"] else "")
            for issue in draft["issues"]
        ]
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the extraction quality check (real model requests).")
    parser.add_argument("--case", action="append", default=[], help="run only this case (repeatable)")
    parser.add_argument("--cases-dir", action="append", type=Path, default=[], help="also load cases from this folder")
    parser.add_argument("--extractor", choices=["claude", "ollama"], help="override RECIPES_EXTRACTOR for this run")
    parser.add_argument("--mode", choices=["references", "text"], help="override RECIPES_EXTRACTION_MODE for this run")
    parser.add_argument("--model", help="override the model (RECIPES_MODEL or RECIPES_OLLAMA_MODEL) for this run")
    args = parser.parse_args()

    settings = load_settings()
    if args.extractor:
        settings = settings.model_copy(update={"extractor": args.extractor})
    if args.mode:
        settings = settings.model_copy(update={"extraction_mode": args.mode})
    if args.model:
        settings = settings.model_copy(update={"ollama_model" if settings.extractor == "ollama" else "model": args.model})
    info = extraction_info(settings)
    if not info.configured:
        print(
            {
                "no_api_key": "No ANTHROPIC_API_KEY is configured. See the README, section 'Connect the Claude API'.",
                "ollama_unreachable": f"Ollama is not running at {settings.ollama_url}. Start the Ollama app.",
                "ollama_model_missing": f"Ollama does not have {info.model}. Run: ollama pull {info.model}",
            }.get(info.problem or "", "The model is not ready.")
        )
        return 2
    cases = load_cases([CASES_DIR, *args.cases_dir], args.case)
    if not cases:
        print("No cases found.")
        return 2
    if len(cases) > MAX_CASES:
        print(f"{len(cases)} cases is more than the limit of {MAX_CASES} requests per run. Choose cases with --case.")
        return 2

    stay_awake()
    extractor = make_extractor(settings)
    mode = settings.extraction_mode
    label = f"{info.provider}/{info.model}, {mode}"
    run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{info.provider}-{info.model.replace(':', '-').replace('/', '-')}-{mode}"
    out_dir = settings.data_dir / "evals" / "extraction" / run_id
    out_dir.mkdir(parents=True)
    print(f"{len(cases)} cases with {label}: {len(cases)} requests, one at a time. Results: {out_dir}")

    report = [f"# Extraction quality check {run_id}", "", f"Model: `{label}`. Cases: {len(cases)}.", ""]
    summary: dict = {"model": info.model, "provider": info.provider, "mode": mode, "cases": {}}
    for name, text, expect in cases:
        print(f"- {name} ...", end=" ", flush=True)
        record = run_case(extractor, text, expect)
        (out_dir / f"{name}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        summary["cases"][name] = case_summary(record)
        usage = record["usage"]
        tokens = f", {usage['input_tokens']}+{usage['output_tokens']} tokens" if usage else ""
        print(f"{verdict(record)}, {record['seconds']} s{tokens}")
        tokens = f" Tokens: {usage['input_tokens']} in, {usage['output_tokens']} out." if usage else ""
        report += [f"## {name}", "", expect.get("about", ""), "", f"Time: {record['seconds']} s.{tokens} {verdict(record).capitalize()}.", ""]
        report += [
            f"- **{f['kind']}** ({f['area']}{', minor' if f['minor'] else ''}"
            f"{', flagged in the app' if f['flagged_by_app'] else ''}): {f['message']}"
            for f in record["findings"]
        ] or ["- Every check passed."]
        report += [f"- Unnecessary review point: {w}" for w in record["warnings"]["unnecessary"]]
        report += ["", "<details><summary>The draft</summary>", "", *describe_draft(record), "", "</details>", ""]

    summary["gpu"] = gpu_use(settings)
    summary["totals"] = totals(summary["cases"])
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = summary_lines(summary, len(cases))
    report[3:3] = [*lines, ""]
    (out_dir / "report.md").write_text("\n".join(report), encoding="utf-8")
    print("\n".join(lines) + f"\nReport: {out_dir / 'report.md'}")
    return 0


def case_summary(record: dict) -> dict:
    """What a run's summary.json keeps of one case."""
    keys = (
        "seconds", "usage", "error", "recipe_expected", "imported", "checked", "failed", "problems", "minor_problems",
        "all_checks_passed", "warnings",
    )
    return {key: record[key] for key in keys}


def summary_lines(summary: dict, case_count: int) -> list[str]:
    t = summary["totals"]
    coverage = ", ".join(f"{area} {n - t['failed'].get(area, 0)}/{n}" for area, n in t["checked"].items())
    refused = f" (refused: {', '.join(t['recipes_refused'])})" if t["recipes_refused"] else ""
    return [
        f"**Imports:** recipes imported {t['recipes_imported']} of {t['recipe_texts']}{refused}; texts that are not "
        f"recipes refused {t['non_recipes_refused']} of {t['non_recipe_texts']}.",
        f"**Checks passed within the drafts made, by area:** {coverage}.",
        f"**Problems:** {t['problems']} (and {t['minor_problems']} minor: a category left for you, a review point "
        f"missing, a source gap not pointed out, a fact or tip split over adjacent entries). "
        f"**Cases where every check passed (minor ones included):** {t['cases_all_passed']} of {case_count}.",
        f"**Review points shown:** {t['warnings_shown']}, of which unnecessary {t['unnecessary_warnings']}, duplicates "
        f"{t['duplicate_warnings']}. **Total time:** {t['seconds']:.0f} s.",
        f"**GPU:** {summary['gpu']}" if summary.get("gpu") else "**GPU:** not reported",
    ]


if __name__ == "__main__":
    sys.exit(main())
