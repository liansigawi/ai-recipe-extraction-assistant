"""The extraction quality check's own logic, offline: its case files and its comparisons.

The quality check itself (evals/run_extraction.py) calls a model and is run by hand. These
tests only make sure that its expectations are written correctly and that it reports
what it should.
"""

import json
from pathlib import Path

import pytest

from app import schemas
from app.extraction.review import normalize
from app.schemas import Issue, RecipeInput
from evals.checks import AREAS, KNOWN_EXPECTATIONS, check, review_warnings
from evals.run_extraction import CASES_DIR, CATEGORIES
from evals.scoring import score_case, verdict

CASES = sorted(CASES_DIR.glob("*.json"))
WARNING_KINDS = {"ingredient_only_in_steps", "missing_information", "missing_title", "classification_unresolved",
                 "ambiguous_alternative", "unclear_text", "multiple_recipes"}


def test_there_are_cases_and_each_has_its_text():
    assert len(CASES) >= 15
    for case in CASES:
        assert case.with_suffix(".txt").is_file(), case.name


@pytest.mark.parametrize("case", CASES, ids=[case.stem for case in CASES])
def test_each_case_expects_only_what_its_text_says(case: Path):
    expect = json.loads(case.read_text(encoding="utf-8"))["expect"]
    text = normalize(case.with_suffix(".txt").read_text(encoding="utf-8"))
    assert set(expect) <= KNOWN_EXPECTATIONS, f"unknown expectation in {case.name}"
    if expect.get("is_recipe") is False:
        return
    assert ("title" in expect) != bool(expect.get("title_composed")), "a title, or title_composed"
    assert "category" in expect or "category_one_of" in expect
    assert expect["ingredient_groups"], "every recipe lists its ingredients"
    for group in expect["ingredient_groups"]:
        for line, quantity in group["items"]:
            assert normalize(line) in text, f"expected line not in the text: {line}"
            assert quantity is None or schemas.quoted_from(quantity, line), f"quantity not in its line: {quantity}"
    pieces = [*expect["preparation"], *expect.get("tips", []), *expect.get("facts", [])]  # excluded may be invented
    for piece in pieces:
        assert normalize(piece) in text, f"expected text not in the case's text: {piece}"
    for name in [expect.get("category"), *expect.get("category_one_of", [])]:
        assert name is None or name in {category.name for category in CATEGORIES}
    assert set(expect.get("warnings", [])) <= WARNING_KINDS


SOURCE = "עוגה\nסיפור קצר על העוגה.\n200 גרם קמח\nמלח\nאופים 30 דקות.\nאפשר להקפיא."
EXPECT = {
    "title": "עוגה",
    "category": "קינוחים",
    "ingredient_groups": [{"name": None, "items": [["200 גרם קמח", "200 גרם"], ["מלח", None]]}],
    "preparation": ["אופים 30 דקות."],
    "tips": ["אפשר להקפיא."],
    "excluded": ["סיפור קצר על העוגה."],
}


def draft(**changes) -> RecipeInput:
    data = {
        "title": "עוגה",
        "ingredient_groups": [{"name": None, "ingredients": [{"text": "200 גרם קמח", "quantity": "200 גרם"}, {"text": "מלח", "quantity": None}]}],
        "step_groups": [{"name": None, "steps": ["אופים 30 דקות."]}],
        "notes": ["אפשר להקפיא."],
        "category_id": 1,
        "status": "draft",
    }
    return RecipeInput.model_validate(data | changes)


def kinds(expect=EXPECT, source=SOURCE, **changes) -> list[str]:
    result = check(expect, draft=draft(**changes), error_code=None, categories=CATEGORIES, source=source)
    return [f.kind for f in result.findings]


def lines(*items) -> list[dict]:
    return [{"name": None, "ingredients": [{"text": t, "quantity": q} for t, q in items]}]


def test_a_faithful_draft_passes_every_check_and_says_what_was_checked():
    result = check(EXPECT, draft=draft(), error_code=None, categories=CATEGORIES, source=SOURCE)
    assert result.findings == [] and result.all_passed
    assert result.checked == {
        "wording": 5, "ingredient lines": 2, "quantities": 2, "groups": 1, "preparation": 1, "tips": 1,
        "not recipe content": 1, "title": 1, "category": 1,
    }
    assert set(result.checked) <= set(AREAS)


def test_a_wrong_or_missing_quantity_is_found_for_every_line():
    assert kinds(ingredient_groups=lines(("200 גרם קמח", "200"), ("מלח", None))) == ["wrong_quantity"]
    assert kinds(ingredient_groups=lines(("200 גרם קמח", None), ("מלח", "מלח"))) == ["wrong_quantity", "wrong_quantity"]


def test_a_missing_ingredient_is_one_problem_and_its_quantity_is_not_counted_as_checked():
    result = check(EXPECT, draft=draft(ingredient_groups=lines(("200 גרם קמח", "200 גרם"))), error_code=None,
                   categories=CATEGORIES, source=SOURCE)
    assert [f.kind for f in result.findings] == ["missing_ingredient"]
    assert result.checked["quantities"] == 1


def test_an_ingredient_kept_as_a_note_is_misplaced_not_missing():
    found = kinds(ingredient_groups=lines(("200 גרם קמח", "200 גרם")), notes=["אפשר להקפיא.", "מלח"])
    assert found == ["misplaced_ingredient", "extra_ingredient"] or found == ["misplaced_ingredient"]


def test_extra_and_reordered_ingredients_are_found():
    assert kinds(ingredient_groups=lines(("200 גרם קמח", "200 גרם"), ("מלח", None), ("עוגה", None))) == ["extra_ingredient"]
    assert kinds(ingredient_groups=lines(("מלח", None), ("200 גרם קמח", "200 גרם"))) == ["order"]


def test_text_that_is_not_recipe_content_counts_once_per_place_it_was_kept():
    expect = EXPECT | {"excluded": ["סיפור קצר על העוגה.", "סיפור"]}
    result = check(expect, draft=draft(notes=["אפשר להקפיא.", "סיפור קצר על העוגה."]), error_code=None,
                   categories=CATEGORIES, source=SOURCE)
    assert [f.kind for f in result.findings] == ["not_recipe_kept", "not_recipe_kept"]
    assert len(result.problems) == 1  # two phrases, one note


def test_preparation_tips_and_facts_must_be_kept():
    assert kinds(step_groups=[]) == ["missing_step"]
    assert kinds(step_groups=[], notes=["אפשר להקפיא.", "אופים 30 דקות."]) == ["misplaced_step"]
    assert kinds(notes=[]) == ["missing_tip"]
    expect = EXPECT | {"facts": ["מוכן ב-10 דקות"], "yield": {"text": "8 פרוסות", "number": "8"}}
    assert kinds(expect) == ["missing_fact", "missing_fact"]
    with_fact = SOURCE + "\nמוכן ב-10 דקות"
    assert kinds(expect, with_fact, servings="8", notes=["אפשר להקפיא.", "מוכן ב-10 דקות"]) == []


def test_groups_must_keep_their_names_and_stay_apart():
    expect = EXPECT | {"ingredient_groups": [
        {"name": "לבצק", "items": [["200 גרם קמח", "200 גרם"]]}, {"name": ["לציפוי", None], "items": [["מלח", None]]}]}
    two = [{"name": "לבצק", "ingredients": [{"text": "200 גרם קמח", "quantity": "200 גרם"}]},
           {"name": None, "ingredients": [{"text": "מלח", "quantity": None}]}]
    source = SOURCE.replace("200 גרם קמח", "לבצק:\n200 גרם קמח")
    assert kinds(expect, source, ingredient_groups=two) == []
    renamed = [two[0] | {"name": "בצק"}, two[1]]
    assert kinds(expect, source, ingredient_groups=renamed) == ["group"]
    merged = [{"name": "לבצק", "ingredients": [{"text": "200 גרם קמח", "quantity": "200 גרם"}, {"text": "מלח", "quantity": None}]}]
    assert kinds(expect, source, ingredient_groups=merged) == ["group"]


def test_a_wrong_category_is_an_error_an_unresolved_one_is_minor():
    assert kinds(category_id=2) == ["category_wrong"]
    result = check(EXPECT, draft=draft(category_id=None), error_code=None, categories=CATEGORIES, source=SOURCE)
    assert [f.kind for f in result.findings] == ["category_unresolved"] and result.all_passed


def test_a_finding_records_whether_the_app_showed_a_review_point_about_it():
    issue = Issue(kind="unused_text", message="המודל לא שיבץ את הקטע", quote="מלח")
    result = check(EXPECT, draft=draft(ingredient_groups=lines(("200 גרם קמח", "200 גרם")), issues=[issue]),
                   error_code=None, categories=CATEGORIES, source=SOURCE)
    assert [(f.kind, f.flagged_by_app) for f in result.findings] == [("missing_ingredient", True)]
    result = check(EXPECT, draft=draft(category_id=2), error_code=None, categories=CATEGORIES, source=SOURCE)
    assert [(f.kind, f.flagged_by_app) for f in result.findings] == [("category_wrong", False)]


def test_review_points_are_sorted_into_necessary_unnecessary_and_duplicates():
    issues = [
        Issue(kind="unused_text", message='לא שובץ "שמרו את הפוסט"', quote="שמרו את הפוסט"),  # not recipe: unnecessary
        Issue(kind="unused_text", message='לא שובץ "200 גרם קמח"', quote="200 גרם קמח"),  # recipe text left out: necessary
        Issue(kind="unclear_text", message="לא ברור"),  # a remark the case does not call for
        Issue(kind="not_found_in_source", message="שונה"),  # a real problem
        Issue(kind="other", message='ההערה "תייגו חברה" נראה כמו פנייה לעוקבים, תגית או אזכור'),  # the backend's flag
        Issue(kind="missing_information", message="אין טמפרטורה"),
        Issue(kind="missing_information", message="אין טמפרטורה"),  # the same point twice
    ]
    warnings = review_warnings(EXPECT | {"warnings": ["missing_information"]}, draft(issues=issues))
    assert [w.split(":")[0] for w in warnings.necessary] == [
        "unused_text", "not_found_in_source", "other", "missing_information", "missing_information"]
    assert [w.split(":")[0] for w in warnings.unnecessary] == ["unused_text", "unclear_text"]
    assert [w.split(":")[0] for w in warnings.duplicates] == ["missing_information"]


def test_a_missing_review_point_is_minor():
    assert kinds(EXPECT | {"warnings": ["ingredient_only_in_steps"]}) == ["missing_warning"]


def test_not_a_recipe_is_expected_or_reported():
    nothing = dict(draft=None, categories=CATEGORIES, source="")
    assert check({"is_recipe": False}, error_code="not_a_recipe", **nothing).findings == []
    [finding] = check({}, error_code="extraction_timeout", **nothing).findings
    assert finding.kind == "failed"


def test_the_verdict_says_how_many_checks_passed_never_more():
    passed = score_case(EXPECT, SOURCE, draft(), None, CATEGORIES)
    assert verdict(passed) == "all 15 checks passed"
    failed = score_case(EXPECT, SOURCE, draft(category_id=2, notes=[]), None, CATEGORIES)
    assert verdict(failed) == "2 of 14 checks failed (2 problems)"  # one note fewer to check for wording
