"""Extraction quality check: real Claude requests on representative recipe texts.

Separate from the software tests: each case is one paid request, and the results depend
on the model. Run it by hand, from backend/:

    uv run python -m evals.run_extraction                              every case in evals/cases/
    uv run python -m evals.run_extraction --case english-quick-salad   one case (repeatable)
    uv run python -m evals.run_extraction --cases-dir ../data/evals/local-cases
                                       also your own cases, e.g. real captions (git-ignored)

Bounded: at most MAX_CASES requests per run, one at a time, each with the backend's own
answer-length limit. Uses the same settings as the backend (ANTHROPIC_API_KEY, RECIPES_MODEL).

Each case is <name>.txt (the text, exactly as pasted) and <name>.json (what to expect; see
evals/checks.py). The answer goes through the same checks as a real import
(app/extraction/review.py). Results: <data folder>/evals/extraction/<run>/report.md, plus
each case's raw answer and draft as JSON.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from app import schemas
from app.config import load_settings
from app.errors import ApiError
from app.extraction.claude import ClaudeExtractor
from app.extraction.review import build_draft
from app.sample_data import STARTER_CATEGORIES
from evals.checks import Finding, check

CASES_DIR = Path(__file__).parent / "cases"
MAX_CASES = 15

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


def run_case(extractor: ClaudeExtractor, text: str, expect: dict) -> tuple[dict, list[Finding]]:
    output = draft = error_code = None
    try:
        output = extractor.extract(text, CATEGORIES)
        if not output.is_recipe:
            error_code = "not_a_recipe"
        else:
            draft = build_draft(output, text, CATEGORIES)
    except ApiError as error:
        error_code = error.code
    findings = check(expect.get("expect", {}), output=output, draft=draft, error_code=error_code, categories=CATEGORIES)
    record = {
        "error": error_code,
        "answer": output.model_dump(mode="json") if output else None,
        "draft": draft.model_dump(mode="json") if draft else None,
        "findings": [finding.__dict__ for finding in findings],
    }
    return record, findings


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
    parser = argparse.ArgumentParser(description="Run the extraction quality check (paid Claude requests).")
    parser.add_argument("--case", action="append", default=[], help="run only this case (repeatable)")
    parser.add_argument("--cases-dir", action="append", type=Path, default=[], help="also load cases from this folder")
    parser.add_argument("--model", help="override RECIPES_MODEL for this run")
    args = parser.parse_args()

    settings = load_settings()
    if not settings.extraction_configured or settings.anthropic_api_key is None:
        print("No ANTHROPIC_API_KEY is configured. See the README, section 'Connect the Claude API'.")
        return 2
    cases = load_cases([CASES_DIR, *args.cases_dir], args.case)
    if not cases:
        print("No cases found.")
        return 2
    if len(cases) > MAX_CASES:
        print(f"{len(cases)} cases is more than the limit of {MAX_CASES} requests per run. Choose cases with --case.")
        return 2

    model = args.model or settings.model
    extractor = ClaudeExtractor(
        api_key=settings.anthropic_api_key.get_secret_value(), model=model, timeout=settings.model_timeout_seconds
    )
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = settings.data_dir / "evals" / "extraction" / run_id
    out_dir.mkdir(parents=True)
    print(f"{len(cases)} cases with {model}: {len(cases)} requests, one at a time. Results: {out_dir}")

    report = [f"# Extraction quality check {run_id}", "", f"Model: `{model}`. Cases: {len(cases)}.", ""]
    totals: dict[str, int] = {}
    for name, text, expect in cases:
        print(f"- {name} ...", end=" ", flush=True)
        record, findings = run_case(extractor, text, expect)
        (out_dir / f"{name}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        print("ok" if not findings else f"{len(findings)} finding(s)")
        for finding in findings:
            totals[finding.kind] = totals.get(finding.kind, 0) + 1
        report += [f"## {name}", "", expect.get("about", ""), ""]
        report += [f"- **{f.kind}**: {f.message}" for f in findings] or ["- No findings."]
        report += ["", "<details><summary>The draft</summary>", "", *describe_draft(record), "", "</details>", ""]

    summary = ", ".join(f"{kind}: {count}" for kind, count in sorted(totals.items())) or "no findings"
    report[3:3] = [f"**Findings:** {summary}", ""]
    (out_dir / "report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Findings: {summary}\nReport: {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
