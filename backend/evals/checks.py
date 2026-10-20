"""Comparing an extraction with a case's expectations. Pure functions: tested offline in
tests/test_eval_checks.py, so the evaluation's own logic is checked without calling Claude.

A case's expectations (all optional) in <case>.json, next to the text in <case>.txt:

    "is_recipe": false                      the text is not a recipe: expect not_a_recipe
    "title": "...", "title_written_in_text": true
    "servings": "..."
    "category": "קינוחים" or null           null: must stay unresolved
    "category_one_of": ["קינוחים", null]     when more than one answer is reasonable
    "ingredients": [["200 גרם קמח", "200 גרם"], ["מלח", null], ["בצל אחד גדול"]]
                                            each line must be there, exactly; with a second item,
                                            its quantity must be exactly that (null: none)
    "ingredient_count": 15                  exactly this many lines (more: something was added)
    "ingredient_groups": ["לבצק", "לקרם"]    the group names, in order
    "ingredient_groups_include": ["לבצק"]  at least these groups (when the rest may vary)
    "step_groups_include": ["בסיר לחץ"]      these step groups must exist
    "mentions": ["180 מעלות", "30-35 דקות"]  must appear in a step or a note (times, temperatures)
    "not_ingredients": ["תות"]               no ingredient line may contain these
    "content_excludes": ["#", "@name"]      must not appear in the title, ingredients, steps or notes
    "issue_kinds": ["ingredient_only_in_steps"]   these must be flagged
"""

from dataclasses import dataclass
from typing import Any

from app import schemas
from app.extraction.output import ExtractionOutput
from app.extraction.review import normalize


KNOWN_EXPECTATIONS = {
    "is_recipe", "title", "title_written_in_text", "servings", "category", "category_one_of", "ingredients",
    "ingredient_count", "ingredient_groups", "ingredient_groups_include", "step_groups_include", "mentions",
    "not_ingredients", "content_excludes", "issue_kinds",
}


@dataclass(frozen=True)
class Finding:
    kind: str  # omission, wrong_quantity, addition, not_in_source, classification, missing_flag, ...
    message: str


def check(
    expect: dict[str, Any],
    *,
    output: ExtractionOutput | None,
    draft: schemas.RecipeInput | None,
    error_code: str | None,
    categories: list[schemas.Category],
) -> list[Finding]:
    if not expect.get("is_recipe", True):
        if error_code == "not_a_recipe":
            return []
        return [Finding("not_a_recipe_missed", f"expected 'not a recipe', got {error_code or 'a draft'}")]
    if error_code is not None or draft is None or output is None:
        return [Finding("failed", f"the extraction failed: {error_code}")]

    findings: list[Finding] = []
    lines = [(item.text, item.quantity) for group in draft.ingredient_groups for item in group.ingredients]
    steps = [step for group in draft.step_groups for step in group.steps]
    content = [draft.title, *(text for text, _ in lines), *steps, *draft.notes]
    same = lambda a, b: normalize(a) == normalize(b)  # noqa: E731

    for expected in expect.get("ingredients", []):
        text = expected[0]
        found = [quantity for line, quantity in lines if same(line, text)]
        if not found:
            findings.append(Finding("omission", f'ingredient line missing or changed: "{text}"'))
        elif len(expected) > 1 and found[0] != expected[1]:
            findings.append(Finding("wrong_quantity", f'"{text}": quantity {found[0]!r}, expected {expected[1]!r}'))

    if "ingredient_count" in expect and len(lines) != expect["ingredient_count"]:
        kind = "addition" if len(lines) > expect["ingredient_count"] else "omission"
        findings.append(Finding(kind, f"{len(lines)} ingredient lines, expected {expect['ingredient_count']}"))

    names = [group.name for group in draft.ingredient_groups]
    if "ingredient_groups" in expect:
        if [normalize(n) if n else None for n in names] != [normalize(n) if n else None for n in expect["ingredient_groups"]]:
            findings.append(Finding("structure", f"ingredient groups {names}, expected {expect['ingredient_groups']}"))
    for name in expect.get("ingredient_groups_include", []):
        if normalize(name) not in [normalize(n) for n in names if n]:
            findings.append(Finding("structure", f'no ingredient group named "{name}" (got {names})'))

    step_group_names = [normalize(group.name) for group in draft.step_groups if group.name]
    for name in expect.get("step_groups_include", []):
        if normalize(name) not in step_group_names:
            findings.append(Finding("structure", f'no step group named "{name}" (got {step_group_names})'))

    steps_and_notes = normalize(" | ".join([*steps, *draft.notes]))
    for piece in expect.get("mentions", []):
        if normalize(piece) not in steps_and_notes:
            findings.append(Finding("omission", f'"{piece}" is not in any step or note'))

    for piece in expect.get("not_ingredients", []):
        for line, _ in lines:
            if piece in line:
                findings.append(Finding("addition", f'ingredient line "{line}" should not exist (contains "{piece}")'))

    for piece in expect.get("content_excludes", []):
        for text in content:
            if piece in text:
                findings.append(Finding("unwanted_text", f'"{piece}" appears in "{text}"'))

    kinds = {issue.kind for issue in draft.issues}
    for kind in expect.get("issue_kinds", []):
        if kind not in kinds:
            findings.append(Finding("missing_flag", f"expected a '{kind}' issue"))

    names = {category.id: category.name for category in categories}
    actual = names.get(draft.category_id) if draft.category_id is not None else None
    if "category" in expect and actual != expect["category"]:
        findings.append(Finding("classification", f"category {actual!r}, expected {expect['category']!r}"))
    if "category_one_of" in expect and actual not in expect["category_one_of"]:
        findings.append(Finding("classification", f"category {actual!r}, expected one of {expect['category_one_of']}"))

    if "title" in expect and not same(draft.title, expect["title"]):
        findings.append(Finding("title", f'title "{draft.title}", expected "{expect["title"]}"'))
    if "title_written_in_text" in expect and output.title_written_in_text != expect["title_written_in_text"]:
        findings.append(
            Finding("title", f"title_written_in_text {output.title_written_in_text}, expected {expect['title_written_in_text']}")
        )
    if "servings" in expect and (draft.servings or None) != expect["servings"]:
        findings.append(Finding("omission", f"servings {draft.servings!r}, expected {expect['servings']!r}"))

    # The backend's own checks, whatever the case expects: lines not in the text, quantities not in their line.
    for issue in draft.issues:
        if issue.kind == "not_found_in_source":
            findings.append(Finding("not_in_source", issue.message))
        if issue.kind == "quantity_not_in_line":
            findings.append(Finding("wrong_quantity", issue.message))
    return findings
