"""Scoring one case and summing a run, the same way for a live run (evals/run_extraction.py) and
for re-scoring saved drafts (evals/rescore.py)."""

from dataclasses import asdict
from typing import Any

from app import schemas
from evals.checks import AREAS, check, review_warnings


def score_case(
    expect: dict[str, Any],
    source: str,
    draft: schemas.RecipeInput | dict | None,
    error_code: str | None,
    categories: list[schemas.Category],
) -> dict[str, Any]:
    if isinstance(draft, dict):
        draft = schemas.RecipeInput.model_validate(draft)
    result = check(expect, draft=draft, error_code=error_code, categories=categories, source=source)
    warnings = review_warnings(expect, draft)
    failed: dict[str, int] = {}
    for finding in result.findings:
        failed[finding.area] = failed.get(finding.area, 0) + 1
    major = [f for f in result.findings if not f.minor]
    return {
        # Import success, apart from accuracy within the draft: was a recipe expected, was a draft made?
        "recipe_expected": expect.get("is_recipe", True),
        "imported": draft is not None,
        "findings": [asdict(f) | {"minor": f.minor} for f in result.findings],
        "checked": result.checked,
        "failed": failed,
        "problems": len(dict.fromkeys(f.problem for f in major)),
        "minor_problems": len(dict.fromkeys(f.problem for f in result.findings if f.minor)),
        "all_checks_passed": result.all_passed,
        "warnings": {
            "shown": len(draft.issues) if draft else 0,
            "necessary": warnings.necessary,
            "unnecessary": warnings.unnecessary,
            "duplicates": warnings.duplicates,
        },
    }


def verdict(scored: dict[str, Any]) -> str:
    """What was checked and how it went, in words that do not claim more than the checks cover.
    "All checks passed" only when no check failed, minor ones included."""
    checks = sum(scored["checked"].values())
    failed = len(scored["findings"])
    if checks == 0 and failed:
        return "no draft: " + "; ".join(f["message"] for f in scored["findings"])
    if failed == 0:
        return f"all {checks} checks passed"
    problems, minor = scored["problems"], scored["minor_problems"]
    parts = [f"{problems} problem{'s' if problems != 1 else ''}"] if problems else []
    parts += [f"{minor} minor"] if minor else []
    return f"{failed} of {checks} checks failed ({', '.join(parts)})"


def totals(cases: dict[str, dict[str, Any]]) -> dict[str, Any]:
    checked: dict[str, int] = {}
    failed: dict[str, int] = {}
    for case in cases.values():
        for area, n in case["checked"].items():
            checked[area] = checked.get(area, 0) + n
        for area, n in case["failed"].items():
            failed[area] = failed.get(area, 0) + n
    order = {area: i for i, area in enumerate(AREAS)}
    recipes = {name: c for name, c in cases.items() if c.get("recipe_expected", True)}
    others = {name: c for name, c in cases.items() if not c.get("recipe_expected", True)}
    return {
        "recipes_imported": sum(bool(c.get("imported", not c.get("error"))) for c in recipes.values()),
        "recipe_texts": len(recipes),
        "recipes_refused": sorted(name for name, c in recipes.items() if not c.get("imported", not c.get("error"))),
        "non_recipes_refused": sum(not c.get("imported", not c.get("error")) for c in others.values()),
        "non_recipe_texts": len(others),
        "checked": dict(sorted(checked.items(), key=lambda kv: order.get(kv[0], 99))),
        "failed": dict(sorted(failed.items(), key=lambda kv: order.get(kv[0], 99))),
        "problems": sum(c["problems"] for c in cases.values()),
        "minor_problems": sum(c["minor_problems"] for c in cases.values()),
        "cases_all_passed": sum(c["all_checks_passed"] for c in cases.values()),
        "warnings_shown": sum(c["warnings"]["shown"] for c in cases.values()),
        "unnecessary_warnings": sum(len(c["warnings"]["unnecessary"]) for c in cases.values()),
        "duplicate_warnings": sum(len(c["warnings"]["duplicates"]) for c in cases.values()),
        "seconds": round(sum(c.get("seconds", 0) for c in cases.values()), 1),
    }
