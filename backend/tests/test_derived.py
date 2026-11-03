"""Oil that a step clearly fries or greases with, added as a line the app derived from the preparation
(app/extraction/derived.py), instead of a review point; every other use of oil keeps the point."""

import pytest

from app import schemas
from app.extraction.derived import add_oil_from_steps
from app.extraction.review import make_draft, only_in_step_point
from app.extraction.segments import segment_text
from app.extraction.structured import structured_draft
from app.importers.website import StructuredRecipe
from tests.test_extraction_references import answer

FRY = "מחממים מעט שמן במחבת."
GREASE = "משמנים את התבנית בשמן."


def draft(steps: list[str], lines: list[str] | None = None, groups: list[tuple[str | None, list[str]]] | None = None) -> schemas.RecipeInput:
    """The draft of a page's recipe data with these lines and steps, as an import makes it."""
    recipe = StructuredRecipe(
        title="מתכון", ingredient_groups=groups if groups is not None else [(None, lines or ["2 בצלים"])],
        step_groups=[(None, steps)], servings=None, times={}, authors=[], image=None, description=None, found_in="json_ld", raw={},
    )
    return structured_draft(recipe, "", [], None)


def derived(result: schemas.RecipeInput) -> list[tuple[str, str | None, str]]:
    return [(i.text, i.quantity, i.derived_from) for g in result.ingredient_groups for i in g.ingredients if i.derived_from]


def points(result: schemas.RecipeInput) -> list[tuple[str, str | None]]:
    return [(i.message.split('"')[1], i.quote) for i in result.issues if i.kind == "ingredient_only_in_steps"]


def words_of(step: str) -> str:
    """The oil as the step names it ("שמן", "שמן זית")."""
    return "שמן זית" if "שמן זית" in step else "שמן"


def test_clear_frying_adds_a_little_oil_for_frying_with_its_sentence_instead_of_a_review_point():
    result = draft([f"{FRY} מוסיפים את הבצל ומטגנים 5 דקות."])
    assert derived(result) == [("מעט שמן לטיגון", "מעט", FRY)]
    assert points(result) == []  # nothing to check: no "טופל" needed
    assert [i.text for i in result.ingredient_groups[0].ingredients] == ["2 בצלים", "מעט שמן לטיגון"]


def test_greasing_the_pan_adds_oil_for_greasing_it_without_an_amount():
    assert derived(draft([GREASE, "אופים 30 דקות ב-180 מעלות."])) == [("שמן לשימון התבנית", None, GREASE)]


@pytest.mark.parametrize(
    ("step", "line"),
    [
        ("מחממים ווק עם מעט שמן. מקפיצים את הפטריות והבצל 3-4 דקות.", "מעט שמן לטיגון"),  # the Foody noodles
        ("מטגנים את הלביבות בשמן עמוק עד הזהבה.", "שמן לטיגון עמוק"),
        ("משמנים תבנית במעט שמן זית.", "מעט שמן זית לשימון התבנית"),  # the oil the step names, never another
        ("מטגנים את הקציצות בקצת שמן משני הצדדים.", "קצת שמן לטיגון"),
        ("מערבבים את הבלילה ומטגנים בשמן חם.", "שמן לטיגון"),  # the batter is fried: the oil does not go into it
    ],
)
def test_the_line_uses_only_the_step_s_own_words(step, line):
    assert [text for text, _, _ in derived(draft([step]))] == [line]


@pytest.mark.parametrize(
    "step",
    [
        "מוסיפים חצי כוס שמן לבלילה ומערבבים.",  # a measured ingredient of the batter
        "מחממים 2 כפות שמן במחבת.",  # measured: not "a little"
        "מערבבים שמן זית, מיץ לימון ומלח לרוטב.",  # a sauce
        "אפשר לשמן את התבנית בשמן.",  # optional
        "מוסיפים שמן ומערבבים היטב.",  # not frying or greasing
    ],
)
def test_oil_that_is_part_of_the_recipe_or_not_clearly_used_keeps_the_normal_review_point(step):
    result = draft([step])
    assert derived(result) == []
    assert [(words, quote) for words, quote in points(result) if "שמן" in words] == [(words_of(step), step)]


@pytest.mark.parametrize("step", ["מטגנים את הבצל ללא שמן עד שהוא מזהיב.", "אין צורך בשמן: המחבת מונעת הדבקה.", "מטגנים את הבצל עד הזהבה."])
def test_cooking_without_oil_or_frying_with_no_oil_named_adds_nothing_and_warns_about_nothing(step):
    result = draft([step])
    assert derived(result) == [] and points(result) == []


@pytest.mark.parametrize("listed", ["2 כפות שמן", "שמן זית", "שמן קנולה לטיגון", "מעט שמן"])
def test_oil_already_in_the_list_is_not_added_again(listed):
    result = draft([FRY, GREASE], lines=["2 בצלים", listed])
    assert derived(result) == [] and points(result) == []


def test_oil_the_list_gives_to_another_component_is_not_assumed_to_be_the_frying_oil():
    result = draft([FRY], groups=[("לרוטב", ["2 כפות שמן זית", "מיץ מלימון"]), ("למוקפץ", ["2 בצלים"])])
    assert derived(result) == [("מעט שמן לטיגון", "מעט", FRY)]
    assert result.ingredient_groups[-1].name is None  # its own group: not put into the sauce's or another's
    assert points(result) == []


def test_a_clear_use_adds_its_line_and_an_unclear_one_still_gets_the_point():
    batter = "מוסיפים חצי כוס שמן לבלילה ומערבבים."
    result = draft([batter, FRY])
    assert derived(result) == [("מעט שמן לטיגון", "מעט", FRY)]
    assert points(result) == [("שמן", batter)]


def test_frying_and_greasing_each_add_one_line_and_doing_it_again_adds_nothing():
    first = draft([FRY, "מטגנים את הבצל במעט שמן.", GREASE])
    assert [text for text, _, _ in derived(first)] == ["מעט שמן לטיגון", "שמן לשימון התבנית"]
    again = add_oil_from_steps(first, only_in_step_point)
    assert again == first


def test_other_ingredients_the_list_leaves_out_still_get_their_review_points():
    result = draft([FRY, "מוסיפים את השמנת ומבשלים.", "מקשטים בתותים."])
    assert [words for words, _ in points(result)] == ["שמנת", "תותים"]  # named without the prefix letter
    assert derived(result) == [("מעט שמן לטיגון", "מעט", FRY)]


def test_an_import_s_page_text_draft_gets_the_line_too():
    source = "שקשוקה\n4 ביצים\n2 עגבניות\nמחממים מעט שמן במחבת ומטגנים את העגבניות.\nשוברים פנימה את הביצים."
    roles = ["title", "ingredient", "ingredient", "step", "step"]
    assert len(segment_text(source)) == len(roles)
    result = make_draft(answer(source, roles), source, [])
    assert derived(result) == [("מעט שמן לטיגון", "מעט", "מחממים מעט שמן במחבת ומטגנים את העגבניות.")]
    assert points(result) == []


def test_a_derived_line_must_say_where_it_comes_from_and_its_amount_is_from_its_line():
    with pytest.raises(ValueError):
        schemas.Ingredient(text="שמן לטיגון", quantity="מעט", derived_from=FRY)
    with pytest.raises(ValueError):
        schemas.Ingredient(text="שמן לטיגון", quantity=None, derived_from="")
