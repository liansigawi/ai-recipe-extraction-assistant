"""The extraction quality check's own logic, offline: its case files and its comparisons.

The quality check itself (evals/run_extraction.py) calls Claude and is run by hand. These
tests only make sure that its expectations are written correctly and that it reports
what it should.
"""

import json
from pathlib import Path

import pytest

from app import schemas
from app.extraction.review import build_draft, normalize
from evals.checks import KNOWN_EXPECTATIONS, check
from evals.run_extraction import CASES_DIR, CATEGORIES
from tests.test_extraction_review import answer

CASES = sorted(CASES_DIR.glob("*.json"))


def test_there_are_cases_and_each_has_its_text():
    assert len(CASES) >= 10
    for case in CASES:
        assert case.with_suffix(".txt").is_file(), case.name


@pytest.mark.parametrize("case", CASES, ids=[case.stem for case in CASES])
def test_each_case_expects_only_what_its_text_says(case: Path):
    expect = json.loads(case.read_text(encoding="utf-8"))["expect"]
    text = normalize(case.with_suffix(".txt").read_text(encoding="utf-8"))
    assert set(expect) <= KNOWN_EXPECTATIONS, f"unknown expectation in {case.name}"
    for line, *quantity in expect.get("ingredients", []):
        assert normalize(line) in text, f"expected line not in the text: {line}"
        if quantity and quantity[0] is not None:
            assert schemas.quoted_from(quantity[0], line), f"expected quantity not in its line: {quantity[0]}"
    for piece in expect.get("mentions", []):
        assert normalize(piece) in text, f"expected mention not in the text: {piece}"
    for name in [expect.get("category"), *expect.get("category_one_of", [])]:
        assert name is None or name in {category.name for category in CATEGORIES}


SOURCE = "עוגה\n200 גרם קמח\nמלח\nאופים 30 דקות."
GOOD = {
    "title": "עוגה",
    "ingredient_groups": [{"name": None, "ingredients": [{"text": "200 גרם קמח", "quantity": "200 גרם"}, {"text": "מלח", "quantity": None}]}],
    "step_groups": [{"name": None, "steps": ["אופים 30 דקות."]}],
    "notes": [],
    "servings": None,
    "classification": {"fit": "clear", "category_id": 1, "subcategory_id": None, "candidate_category_ids": []},
}
EXPECT = {
    "category": "קינוחים",
    "ingredient_count": 2,
    "ingredients": [["200 גרם קמח", "200 גרם"], ["מלח", None]],
    "mentions": ["30 דקות"],
}


def run(expect=EXPECT, **changes):
    output = answer(**(GOOD | changes))
    draft = build_draft(output, SOURCE, CATEGORIES)
    return [(f.kind, f.message) for f in check(expect, output=output, draft=draft, error_code=None, categories=CATEGORIES)]


def test_a_faithful_extraction_has_no_findings():
    assert run() == []


def test_omissions_additions_quantities_and_classification_are_reported():
    groups = [{"name": None, "ingredients": [{"text": "200 גרם קמח", "quantity": "200"}, {"text": "סוכר", "quantity": None}]}]
    steps = [{"name": None, "steps": ["אופים."]}]
    choice = {"fit": "no_fit", "category_id": None, "subcategory_id": None, "candidate_category_ids": []}
    kinds = sorted({kind for kind, _ in run(ingredient_groups=groups, step_groups=steps, classification=choice)})
    assert kinds == ["classification", "not_in_source", "omission", "wrong_quantity"]


def test_not_a_recipe_is_expected_or_reported():
    assert check({"is_recipe": False}, output=None, draft=None, error_code="not_a_recipe", categories=CATEGORIES) == []
    [finding] = check({}, output=None, draft=None, error_code="extraction_timeout", categories=CATEGORIES)
    assert finding.kind == "failed"
