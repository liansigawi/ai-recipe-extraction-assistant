"""Checking Claude's answer before it becomes a draft (app/extraction/review.py).

The model's answers here are written by hand, to cover each check: these tests never call Claude.
"""

import pytest

from app.extraction.output import ExtractionOutput
from app.extraction.review import build_draft, first_line, manual_draft, normalize
from app.schemas import Category, Subcategory

LRM = "\N{LEFT-TO-RIGHT MARK}"

SOURCE = f"""{LRM}עוגת תפוזים 🍊
מתכון שכולם אוהבים! שמרו את הפוסט

10 פרוסות

לבצק:
• 200 גרם קמח
• 2 ביצים L
• מלח

אופן ההכנה:
1. מערבבים את כל
החומרים.
2. אופים 30-35 דקות ב-180 מעלות.

אפשר להקפיא.
#עוגה @someone"""

CATEGORIES = [
    Category(id=1, name="קינוחים", subcategories=[Subcategory(id=10, name="עוגות")]),
    Category(id=2, name="בישולים"),
    Category(id=3, name="ארוחות קלילות"),
]


def answer(**changes) -> ExtractionOutput:
    """A faithful answer for SOURCE; each test changes one thing."""
    data = {
        "is_recipe": True,
        "title": "עוגת תפוזים",
        "title_written_in_text": True,
        "servings": "10 פרוסות",
        "ingredient_groups": [
            {
                "name": "לבצק",
                "ingredients": [
                    {"text": "200 גרם קמח", "quantity": "200 גרם"},
                    {"text": "2 ביצים L", "quantity": "2"},
                    {"text": "מלח", "quantity": None},
                ],
            }
        ],
        "step_groups": [{"name": None, "steps": ["מערבבים את כל החומרים.", "אופים 30-35 דקות ב-180 מעלות."]}],
        "notes": ["אפשר להקפיא."],
        "issues": [],
        "classification": {"fit": "clear", "category_id": 1, "subcategory_id": 10, "candidate_category_ids": []},
    }
    data.update(changes)
    return ExtractionOutput.model_validate(data)


def kinds(draft) -> list[str]:
    return [issue.kind for issue in draft.issues]


def test_a_faithful_answer_becomes_a_draft_with_nothing_to_check():
    draft = build_draft(answer(), SOURCE, CATEGORIES)
    assert draft.status == "draft"
    assert draft.issues == []
    assert (draft.category_id, draft.subcategory_id) == (1, 10)
    assert draft.ingredient_groups[0].ingredients[2].quantity is None  # salt: no amount, none invented
    assert [source.kind for source in draft.sources] == ["text"]
    # A step that the text breaks over two lines still counts as written in the text.
    assert draft.step_groups[0].steps[0] == "מערבבים את כל החומרים."


def test_a_line_that_is_not_in_the_text_is_kept_but_flagged():
    groups = answer().model_dump()["ingredient_groups"]
    groups[0]["ingredients"].append({"text": "100 גרם סוכר", "quantity": "100 גרם"})  # invented
    draft = build_draft(answer(ingredient_groups=groups), SOURCE, CATEGORIES)
    assert kinds(draft) == ["not_found_in_source"]
    assert "100 גרם סוכר" in draft.issues[0].message


def test_a_reworded_step_is_flagged():
    steps = [{"name": None, "steps": ["מערבבים היטב את כל החומרים.", "אופים 30-35 דקות ב-180 מעלות."]}]
    draft = build_draft(answer(step_groups=steps), SOURCE, CATEGORIES)
    assert kinds(draft) == ["not_found_in_source"]


@pytest.mark.parametrize("quantity", ["200 ג׳", "2", "200 גרם קמח לבן"])
def test_a_quantity_not_written_in_its_line_is_removed_and_flagged(quantity):
    groups = answer().model_dump()["ingredient_groups"]
    groups[0]["ingredients"][0]["quantity"] = quantity
    draft = build_draft(answer(ingredient_groups=groups), SOURCE, CATEGORIES)
    assert draft.ingredient_groups[0].ingredients[0].quantity is None
    assert kinds(draft) == ["quantity_not_in_line"]


def test_a_composed_title_is_flagged():
    draft = build_draft(answer(title="עוגת תפוזים ביתית", title_written_in_text=False), SOURCE, CATEGORIES)
    assert draft.title == "עוגת תפוזים ביתית"
    assert kinds(draft) == ["missing_title"]


def test_an_empty_title_falls_back_to_the_first_line():
    draft = build_draft(answer(title="  "), SOURCE, CATEGORIES)
    assert draft.title == "עוגת תפוזים 🍊"  # the invisible mark at the start is dropped
    assert kinds(draft) == ["missing_title"]


# --- Classification ----------------------------------------------------------------------------


def classification(fit, category_id=None, subcategory_id=None, candidates=()):
    return {"fit": fit, "category_id": category_id, "subcategory_id": subcategory_id, "candidate_category_ids": list(candidates)}


def test_a_clear_choice_of_an_existing_category_classifies():
    draft = build_draft(answer(classification=classification("clear", 2)), SOURCE, CATEGORIES)
    assert (draft.category_id, draft.subcategory_id, draft.issues) == (2, None, [])


@pytest.mark.parametrize(
    "choice",
    [
        classification("clear", 99),  # no such category
        classification("ambiguous", None, None, [1, 3]),
        classification("ambiguous", 1, None, [1, 3]),  # an id together with "ambiguous" does not count
        classification("no_fit"),
        classification("clear", None),
    ],
)
def test_anything_but_a_clear_valid_choice_stays_unclassified_with_an_explanation(choice):
    draft = build_draft(answer(classification=choice), SOURCE, CATEGORIES)
    assert (draft.category_id, draft.subcategory_id) == (None, None)
    assert kinds(draft) == ["classification_unresolved"]


@pytest.mark.parametrize(
    ("choice", "kept"),
    [
        (classification("clear", 2, 10), 2),  # subcategory 10 belongs to category 1, not 2
        (classification("clear", 1, 77), 1),  # no such subcategory
    ],
)
def test_a_subcategory_that_is_not_the_categorys_own_is_dropped_and_the_category_kept(choice, kept):
    draft = build_draft(answer(classification=choice), SOURCE, CATEGORIES)
    assert (draft.category_id, draft.subcategory_id) == (kept, None)
    assert kinds(draft) == ["classification_unresolved"] and "נשמרה רק הקטגוריה" in draft.issues[0].message


def test_a_clear_choice_with_one_of_its_own_subcategories_keeps_both():
    draft = build_draft(answer(classification=classification("clear", 1, 10)), SOURCE, CATEGORIES)
    assert (draft.category_id, draft.subcategory_id, kinds(draft)) == (1, 10, [])


def test_an_ambiguous_choice_names_only_existing_categories():
    choice = classification("ambiguous", None, None, [1, 3, 42])
    message = build_draft(answer(classification=choice), SOURCE, CATEGORIES).issues[0].message
    assert '"קינוחים"' in message and '"ארוחות קלילות"' in message
    assert "42" not in message


def test_model_messages_about_categories_are_dropped_so_nothing_suggests_a_new_one():
    issues = [
        {"kind": "other", "message": "כדאי ליצור קטגוריה חדשה בשם חטיפים.", "quote": None},
        {"kind": "other", "message": "Consider a new 'Snacks' category.", "quote": None},
        {"kind": "missing_information", "message": "לא כתוב כמה זמן לצנן.", "quote": None},
    ]
    draft = build_draft(answer(issues=issues), SOURCE, CATEGORIES)
    assert [issue.message for issue in draft.issues] == ["לא כתוב כמה זמן לצנן."]


def test_a_quote_must_be_words_from_the_text():
    issues = [
        {"kind": "unclear_text", "message": "לא ברור איזה גודל.", "quote": "2 ביצים L"},
        {"kind": "unclear_text", "message": "לא ברור.", "quote": "3 ביצים XL"},
    ]
    draft = build_draft(answer(issues=issues), SOURCE, CATEGORIES)
    assert [issue.quote for issue in draft.issues] == ["2 ביצים L", None]


def test_empty_lines_and_groups_are_skipped_and_an_empty_recipe_is_flagged():
    draft = build_draft(
        answer(
            ingredient_groups=[{"name": "לציפוי", "ingredients": [{"text": " ", "quantity": None}]}],
            step_groups=[{"name": None, "steps": [""]}],
            notes=[" "],
        ),
        SOURCE,
        CATEGORIES,
    )
    assert draft.ingredient_groups == [] and draft.step_groups == [] and draft.notes == []
    assert "missing_information" in kinds(draft)


def test_comparison_ignores_spacing_and_invisible_marks_but_nothing_else():
    assert normalize(f" {LRM}2  כוסות\nקמח ") == "2 כוסות קמח"
    assert normalize("115 גר’") != normalize("115 גר'")  # a different apostrophe is a different text


# --- Saving without the model ----------------------------------------------------------------------


def test_a_manual_draft_takes_its_title_from_the_first_line_and_says_what_to_do():
    draft = manual_draft(f"\n\n  {LRM}חביתה של סבתא  \n2 ביצים\nמטגנים.")
    assert draft.title == "חביתה של סבתא"
    assert draft.ingredient_groups == [] and draft.step_groups == []
    assert kinds(draft) == ["not_extracted", "missing_title"]
    assert draft.status == "draft" and draft.category_id is None


def test_a_stand_in_title_is_cut_to_a_readable_length():
    assert len(first_line("א" * 500)) == 120
    assert first_line(" \n \n") == "מתכון ללא כותרת"


# --- Decoration that smaller models copy along -------------------------------------------------


def test_bullets_emoji_and_list_numbers_are_left_out_and_headings_lose_their_markers():
    groups = [
        {
            "name": "|לבצק:",
            "ingredients": [
                {"text": "• 200 גרם קמח", "quantity": "200 גרם"},
                {"text": "🥚 2 ביצים L", "quantity": "2"},
                {"text": "- מלח", "quantity": None},
            ],
        }
    ]
    steps = [{"name": "אופן ההכנה:", "steps": ["1. מערבבים את כל החומרים.", "2) אופים 30-35 דקות ב-180 מעלות."]}]
    draft = build_draft(answer(ingredient_groups=groups, step_groups=steps), SOURCE, CATEGORIES)
    assert draft.issues == []  # nothing invented: the clean lines are all in the text
    assert draft.ingredient_groups[0].name == "לבצק"
    assert [i.text for i in draft.ingredient_groups[0].ingredients] == ["200 גרם קמח", "2 ביצים L", "מלח"]
    assert draft.step_groups[0].name is None  # a single group titled like the section
    assert draft.step_groups[0].steps == ["מערבבים את כל החומרים.", "אופים 30-35 דקות ב-180 מעלות."]


def test_a_list_split_into_unnamed_pieces_is_put_back_together():
    steps = [
        {"name": None, "steps": ["מערבבים את כל החומרים."]},
        {"name": None, "steps": ["אופים 30-35 דקות ב-180 מעלות."]},
    ]
    draft = build_draft(answer(step_groups=steps), SOURCE, CATEGORIES)
    assert [g.steps for g in draft.step_groups] == [["מערבבים את כל החומרים.", "אופים 30-35 דקות ב-180 מעלות."]]


def test_a_section_title_is_not_a_group_name_so_the_pieces_of_one_list_join():
    steps = [
        {"name": "אופן ההכנה", "steps": ["מערבבים את כל החומרים."]},
        {"name": None, "steps": ["אופים 30-35 דקות ב-180 מעלות."]},
    ]
    draft = build_draft(answer(step_groups=steps), SOURCE.replace("אופן ההכנה:", "אופן ההכנה"), CATEGORIES)
    assert [(g.name, g.steps) for g in draft.step_groups] == [(None, ["מערבבים את כל החומרים.", "אופים 30-35 דקות ב-180 מעלות."])]


def test_repeated_notes_are_kept_once_and_promotion_is_flagged_not_deleted():
    draft = build_draft(answer(notes=["אפשר להקפיא.", "אפשר להקפיא.", "#עוגה @someone"]), SOURCE, CATEGORIES)
    assert draft.notes == ["אפשר להקפיא.", "#עוגה @someone"]
    assert kinds(draft) == ["other"]
    assert "#עוגה @someone" in draft.issues[0].message


def test_a_point_reported_twice_is_shown_once_in_its_first_place():
    twice = {"kind": "missing_information", "message": "לא כתוב כמה זמן לצנן.", "quote": None}
    other = {"kind": "unclear_text", "message": "לא ברור.", "quote": None}
    draft = build_draft(answer(issues=[twice, other, twice]), SOURCE, CATEGORIES)
    assert [issue.message for issue in draft.issues] == ["לא כתוב כמה זמן לצנן.", "לא ברור."]
