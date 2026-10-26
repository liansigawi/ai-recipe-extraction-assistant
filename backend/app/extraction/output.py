"""The shape of Claude's answer, sent to the API as a JSON schema.

With structured output, the API makes the model's answer follow this schema exactly: every
field present, with the right types. It is NOT the recipe contract (app/schemas.py): it is
deliberately lenient (plain strings, no rules), so one bad line does not throw away the
whole answer. app/extraction/review.py checks every field afterwards.

The field descriptions are part of the schema the model sees, so they double as instructions.
"""

from copy import deepcopy
from typing import Any, Literal

from anthropic import transform_schema
from pydantic import BaseModel, Field

from app import schemas


class ExtractedIngredient(BaseModel):
    text: str = Field(
        description="The ingredient line exactly as written in the text, without a leading bullet, dash, "
        "number or emoji. Never translated, converted or corrected."
    )
    quantity: str | None = Field(
        description="The amount with its unit, copied character for character from this same line "
        "(e.g. '350 גרם' from '350 גרם קמח', '1/4 כפית' from '1/4 כפית פפריקה'; the number alone when there is "
        "no unit word: '3' from '3 גזרים'). null when the line gives no amount (e.g. 'פלפל שחור גרוס', 'salt to "
        "taste'). Never invented, and never the ingredient's name."
    )


class ExtractedIngredientGroup(BaseModel):
    name: str | None = Field(
        description="The text's own heading for this group (e.g. 'לבלילה', 'For the sauce'), without ':', '-', "
        "'|' or other decoration. null when the text does not group its ingredients."
    )
    ingredients: list[ExtractedIngredient]


class ExtractedStepGroup(BaseModel):
    name: str | None = Field(
        description="The text's own heading for these steps (e.g. 'על הגריל', 'For the glaze'). "
        "null for a plain list of steps."
    )
    steps: list[str] = Field(description="The steps in order, each with its wording, times and temperatures as written.")


class ModelIssue(BaseModel):
    kind: schemas.ModelIssueKind
    message: str = Field(description="A short explanation for the cook, in Hebrew. Never about categories.")
    quote: str | None = Field(description="The exact words from the text this is about, copied exactly; or null.")


class Classification(BaseModel):
    fit: Literal["clear", "ambiguous", "no_fit"] = Field(
        description="'clear': exactly one listed category clearly fits. 'ambiguous': two or more could fit. "
        "'no_fit': none of the listed categories fits."
    )
    category_id: int | None = Field(description="With fit='clear': the id of that category. Otherwise null.")
    subcategory_id: int | None = Field(
        description="With fit='clear': the id of one of THAT category's subcategories, only if one clearly fits. "
        "Otherwise null."
    )
    candidate_category_ids: list[int] = Field(
        description="With fit='ambiguous': the ids of the categories that could fit. Otherwise empty."
    )


class ExtractionOutput(BaseModel):
    is_recipe: bool = Field(description="false if the text does not contain a recipe; then leave the lists empty.")
    title: str = Field(
        description="The recipe's title as written in the text. If the text has no title, a short name of the "
        "dish itself (what it is, its main ingredients) in the text's own words, never the occasion or the praise."
    )
    title_written_in_text: bool = Field(description="true if the title is written in the text; false if you composed it.")
    servings: str | None = Field(description="The yield as written (e.g. '12 פרוסות', 'serves 4'), or null.")
    ingredient_groups: list[ExtractedIngredientGroup]
    step_groups: list[ExtractedStepGroup]
    notes: list[str] = Field(
        description="Tips the text gives (substitutions, storage, equipment, pan size, serving), as written."
    )
    issues: list[ModelIssue]
    classification: Classification


def output_schema(categories: list[schemas.Category]) -> dict[str, Any]:
    """The JSON schema for the API, with category ids limited to the categories that exist.

    So the model cannot even write the id of a category that is not in the database. (The
    backend still checks the ids, and that the subcategory belongs to the category.)
    """
    schema = deepcopy(ExtractionOutput.model_json_schema())
    _limit_categories(schema, categories)
    return transform_schema(schema)


def _limit_categories(schema: dict[str, Any], categories: list[schemas.Category]) -> None:
    properties = schema["$defs"]["Classification"]["properties"]
    category_ids = [category.id for category in categories]
    subcategory_ids = [sub.id for category in categories for sub in category.subcategories]
    properties["category_id"] = _id_or_null(category_ids, properties["category_id"])
    properties["subcategory_id"] = _id_or_null(subcategory_ids, properties["subcategory_id"])
    if category_ids:
        properties["candidate_category_ids"]["items"] = {"type": "integer", "enum": category_ids}


def _id_or_null(ids: list[int], field: dict[str, Any]) -> dict[str, Any]:
    choices: list[dict[str, Any]] = [{"type": "integer", "enum": ids}] if ids else []
    return {"anyOf": [*choices, {"type": "null"}], "description": field["description"]}


# --- The reference answer: a role for each passage instead of copied text -------------------------
#
# Used with RECIPES_EXTRACTION_MODE=references (the default). The text is cut into numbered
# passages (app/extraction/segments.py); the answer gives each passage a role, and the backend
# copies the passages' exact text and reads each ingredient's quantity from it (quantity.py). The
# model still writes the title, the servings, review points and the classification; the backend
# checks those as before.

PassageRole = Literal[
    "title", "ingredient_heading", "ingredient", "step_heading", "step", "continues", "tip", "info", "not_recipe"
]


class ReferencedIssue(BaseModel):
    kind: Literal["unclear_text", "ambiguous_alternative", "multiple_recipes"] = Field(
        description="What the person should check in that passage."
    )
    passage: int | None = Field(description="The number of the passage it is about (null only for multiple_recipes).")


class OnlyInSteps(BaseModel):
    passage: int = Field(description="The number of the step's passage.")
    words: str = Field(description="The ingredient's words, exactly as that step writes them.")


class ReferenceLabels(BaseModel):
    """What the text holds: a role for each passage, and whether it is a recipe at all. The local
    model's first request asks only this, with no categories in view (prompt.REFERENCE_LABELING_PROMPT)."""

    is_recipe: bool = Field(
        description="true if the text says what to use and how to make a food or a drink, whatever kind of dish "
        "it is; false if it contains no recipe (then label every passage 'not_recipe')."
    )
    title: str = Field(
        description="The recipe's title as written in the text. If the text has no title, a short name of the "
        "dish itself (what it is, its main ingredients) in the text's own words, never the occasion or the praise."
    )
    title_written_in_text: bool = Field(description="true if the title is written in the text; false if you composed it.")
    servings: str | None = Field(description="The yield as written (e.g. '12 פרוסות', 'serves 4'), or null.")
    passages: dict[str, PassageRole] = Field(
        description="Every passage, in order, named by its number and opening words: its role in the recipe."
    )
    only_in_steps: list[OnlyInSteps] = Field(
        description="Each ingredient that a step uses but the ingredient list does not mention."
    )
    issues: list[ReferencedIssue] = Field(description="Passages the person should check. The notebook writes the messages.")


class ReferenceOutput(ReferenceLabels):
    """The labels with a category (one request with Claude; with the local model, the category comes
    from a second request about the finished draft)."""

    # Not used by the backend: a moment to sum up the recipe before choosing a category (measured:
    # without it, labeling every passage left the model with no summary of the dish, and it chose
    # main dishes for muffins and a tart).
    dish: str = Field(
        description="In a few words, what kind of dish this is: sweet or savory, and what it is (a cake, a main "
        "course, a salad, a snack, a drink, a sauce...)."
    )
    classification: Classification


def reference_schema(categories: list[schemas.Category], keys: list[str], classify: bool = True) -> dict[str, Any]:
    """The JSON schema for the reference answer: one required role per passage, in the text's
    order, each under its key (segments.passage_key); passage numbers limited to the passages that
    exist, and category ids limited to the categories that exist. Without `classify`, the labels
    alone (ReferenceLabels): no dish, no category."""
    schema = deepcopy((ReferenceOutput if classify else ReferenceLabels).model_json_schema())
    roles = schema["properties"]["passages"]["additionalProperties"]
    schema["$defs"]["PassageRole"] = {"type": "string", "enum": roles["enum"]}
    schema["properties"]["passages"] = {
        "type": "object",
        "description": schema["properties"]["passages"]["description"],
        "properties": {key: {"$ref": "#/$defs/PassageRole"} for key in keys},
        "required": keys,
        "additionalProperties": False,
    }
    numbers = list(range(1, len(keys) + 1)) or [1]
    issue_passage = schema["$defs"]["ReferencedIssue"]["properties"]["passage"]
    schema["$defs"]["ReferencedIssue"]["properties"]["passage"] = {
        "anyOf": [{"type": "integer", "enum": numbers}, {"type": "null"}], "description": issue_passage["description"]
    }
    step_passage = schema["$defs"]["OnlyInSteps"]["properties"]["passage"]
    schema["$defs"]["OnlyInSteps"]["properties"]["passage"] = {
        "type": "integer", "enum": numbers, "description": step_passage["description"]
    }
    if classify:
        _limit_categories(schema, categories)
    return transform_schema(schema)


NO_CATEGORY = Classification(fit="no_fit", category_id=None, subcategory_id=None, candidate_category_ids=[])


class ClassificationAnswer(BaseModel):
    """The answer to the separate classification request (prompt.build_classification_request)."""

    dish: str = Field(
        description="In a few words, what kind of dish this is: sweet or savory, what it is, and what it is mainly "
        "made of (meat, poultry, fish, eggs, dairy, vegetables, grains...)."
    )
    classification: Classification


def classification_schema(categories: list[schemas.Category]) -> dict[str, Any]:
    """The JSON schema for the classification answer, with category ids limited to the existing ones."""
    schema = deepcopy(ClassificationAnswer.model_json_schema())
    _limit_categories(schema, categories)
    return transform_schema(schema)
