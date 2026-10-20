"""The recipe data contract: the JSON shape exchanged between the API and the React app.

Pydantic validates it on the backend; frontend/src/types.ts mirrors it in TypeScript.
Field names are snake_case on both sides, so the JSON needs no renaming layer.

Fidelity rules this shape encodes (docs/brief.md, section 6):
- Text is kept as written. An ingredient line keeps its quantity, unit and state
  ("150 גרם חמאה מומסת" vs "30 גרם חמאה רכה"); steps keep their wording. Only
  spaces and invisible direction marks at the very start and end are trimmed.
- `quantity` is the amount exactly as written, or None when the recipe gives none.
  It must be quoted from its own ingredient line, and not cut out of a longer number
  ("2" from "200 גרם"). Whether it is the right part of the line, and whether the
  line matches the source, is checked in review (milestone 4).
- Groups follow the source. Ingredients are grouped per component (dough, filling...).
  Step groups follow the source's own headings; when the source gives alternative
  methods as separate passages (pressure cooker / regular pot), they become separate
  step groups named with the source's words. Alternatives inside one sentence stay
  one step: the sentence already keeps their times apart. Never invent a heading or
  a sentence.
- An unclassified recipe has category None. Category names are never free text
  here: the API returns the stored category's id and name.
"""

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, model_validator

# Invisible characters that can sit at the edges of copied text: zero-width space,
# joiners and direction marks (U+200B-U+200F), the Arabic letter mark, bidi
# embeddings/overrides and isolates, and the byte-order mark. At the start of a title
# an LRM makes the browser lay a Hebrew title out left to right.
_INVISIBLE = (
    "\N{ZERO WIDTH SPACE}-\N{RIGHT-TO-LEFT MARK}"
    "\N{ARABIC LETTER MARK}"
    "\N{LEFT-TO-RIGHT EMBEDDING}-\N{RIGHT-TO-LEFT OVERRIDE}"
    "\N{LEFT-TO-RIGHT ISOLATE}-\N{POP DIRECTIONAL ISOLATE}"
    "\N{ZERO WIDTH NO-BREAK SPACE}"
)
_EDGES = re.compile(rf"^[\s{_INVISIBLE}]+|[\s{_INVISIBLE}]+$")


def _trim_edges(value: str) -> str:
    """Remove spaces and invisible marks at both ends; marks inside the text are kept."""
    return _EDGES.sub("", value)


# A reusable "text that is not empty" type: trimmed first, then checked (the order matters).
NonEmptyStr = Annotated[str, AfterValidator(_trim_edges), Field(min_length=1)]


def _quoted_from(quantity: str, text: str) -> bool:
    """True when `quantity` appears in `text` without being cut out of a longer number."""
    before = r"(?<![\d.,/])" if quantity[0].isdigit() else ""  # not the "00" of "200"
    after = r"(?![\d]|[.,/]\d)" if quantity[-1].isdigit() else ""  # not the "2" of "2.5" or "200"
    return re.search(before + re.escape(quantity) + after, text) is not None


class ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",  # reject unknown fields: a typo or an invented field is an error, not ignored
        str_strip_whitespace=True,
        # The API always sends every field (null when empty), so /docs lists all of them as required.
        json_schema_serialization_defaults_required=True,
    )


class CategoryRef(ContractModel):
    """A category as shown on a recipe: its id plus the name to display."""

    id: int
    name: NonEmptyStr


class Ingredient(ContractModel):
    text: NonEmptyStr  # the line exactly as written, e.g. "2 כוסות אורז בסמטי"
    quantity: NonEmptyStr | None = None  # the amount exactly as written ("2 כוסות"), or None when none is given

    @model_validator(mode="after")
    def _quantity_is_quoted_from_text(self) -> "Ingredient":
        if self.quantity is not None and not _quoted_from(self.quantity, self.text):
            raise ValueError(f"quantity {self.quantity!r} must be quoted exactly as written in {self.text!r}")
        return self


class IngredientGroup(ContractModel):
    name: NonEmptyStr | None = None  # "לבצק", "למלית"; None when the recipe does not group its ingredients
    ingredients: list[Ingredient] = Field(min_length=1)


class StepGroup(ContractModel):
    name: NonEmptyStr | None = None  # the source's own heading, e.g. "בסיר לחץ"; None for a plain list
    steps: list[NonEmptyStr] = Field(min_length=1)  # in order, each as written; numbered when displayed


SourceKind = Literal["instagram", "website", "screenshot", "text", "manual"]


class Source(ContractModel):
    """Where the recipe came from: editable attribution, part of the recipe.

    The imported original (caption, page text, screenshots) will be stored apart from this, in
    its own table that editing never rewrites (milestone 4).
    """

    kind: SourceKind  # how the recipe got here; "manual": typed in the editor
    # The post or page address, when there is one. Only web links: no "javascript:" or "file:" addresses.
    url: Annotated[NonEmptyStr, Field(pattern=r"^https?://\S+$")] | None = None
    creators: list[NonEmptyStr] = []  # attribution as given by the source; the first is the main author


class RecipeContent(ContractModel):
    """The recipe itself: what the editor changes. Shared by the read and write models below."""

    title: NonEmptyStr
    servings: NonEmptyStr | None = None  # as written, e.g. "12 פרוסות"
    ingredient_groups: list[IngredientGroup] = []
    step_groups: list[StepGroup] = []
    notes: list[NonEmptyStr] = []  # substitutions, storage, equipment, serving tips: only what the recipe says
    sources: list[Source] = []


class Recipe(RecipeContent):
    """A stored recipe, as the API returns it."""

    id: int
    category: CategoryRef | None = None  # None: not classified yet
    subcategory: CategoryRef | None = None  # only together with a category
    is_sample: bool = False  # True for the built-in examples, which were invented for the project
    # With a time zone, so the browser shows the right local time. Sent as e.g. "2026-10-19T08:00:00Z".
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def _subcategory_needs_category(self) -> "Recipe":
        if self.subcategory is not None and self.category is None:
            raise ValueError("a subcategory requires a category")
        return self


class RecipeInput(RecipeContent):
    """What the page sends to create or save a recipe.

    Categories are referred to by id only. Whether those ids exist, and whether the
    subcategory belongs to the category, is checked against the database (app/crud.py).
    The server sets the id, the timestamps and is_sample itself.
    """

    category_id: int | None = None
    subcategory_id: int | None = None

    @model_validator(mode="after")
    def _subcategory_needs_category(self) -> "RecipeInput":
        if self.subcategory_id is not None and self.category_id is None:
            raise ValueError("a subcategory requires a category")
        return self


class Subcategory(ContractModel):
    id: int
    name: NonEmptyStr
    description: NonEmptyStr | None = None


class Category(ContractModel):
    """A top-level category with its subcategories, for the category picker."""

    id: int
    name: NonEmptyStr
    description: NonEmptyStr | None = None
    subcategories: list[Subcategory] = []
