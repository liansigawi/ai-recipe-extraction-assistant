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
        "(e.g. '200 גרם' from '200 גרם קמח', 'כוס וחצי' from 'כוס וחצי סוכר'). "
        "null when the line gives no amount (e.g. 'מלח ופלפל', 'salt to taste'). Never invented."
    )


class ExtractedIngredientGroup(BaseModel):
    name: str | None = Field(
        description="The text's own heading for this group (e.g. 'לבצק', 'For the sauce'), without ':', '-', "
        "'|' or other decoration. null when the text does not group its ingredients."
    )
    ingredients: list[ExtractedIngredient]


class ExtractedStepGroup(BaseModel):
    name: str | None = Field(
        description="The text's own heading for these steps (e.g. 'בסיר לחץ', 'For the glaze'). "
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
        description="The recipe's title as written in the text. If the text has no title, a short title made "
        "from the text's own words."
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
    properties = schema["$defs"]["Classification"]["properties"]
    category_ids = [category.id for category in categories]
    subcategory_ids = [sub.id for category in categories for sub in category.subcategories]
    properties["category_id"] = _id_or_null(category_ids, properties["category_id"])
    properties["subcategory_id"] = _id_or_null(subcategory_ids, properties["subcategory_id"])
    if category_ids:
        properties["candidate_category_ids"]["items"] = {"type": "integer", "enum": category_ids}
    return transform_schema(schema)


def _id_or_null(ids: list[int], field: dict[str, Any]) -> dict[str, Any]:
    choices: list[dict[str, Any]] = [{"type": "integer", "enum": ids}] if ids else []
    return {"anyOf": [*choices, {"type": "null"}], "description": field["description"]}
