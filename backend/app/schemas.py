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

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

# Invisible characters that can sit at the edges of copied text: zero-width space,
# joiners and direction marks (U+200B-U+200F), the Arabic letter mark, bidi
# embeddings/overrides and isolates, and the byte-order mark. At the start of a title
# an LRM makes the browser lay a Hebrew title out left to right.
INVISIBLE_CHARACTERS = (
    "\N{ZERO WIDTH SPACE}-\N{RIGHT-TO-LEFT MARK}"
    "\N{ARABIC LETTER MARK}"
    "\N{LEFT-TO-RIGHT EMBEDDING}-\N{RIGHT-TO-LEFT OVERRIDE}"
    "\N{LEFT-TO-RIGHT ISOLATE}-\N{POP DIRECTIONAL ISOLATE}"
    "\N{ZERO WIDTH NO-BREAK SPACE}"
)
_EDGES = re.compile(rf"^[\s{INVISIBLE_CHARACTERS}]+|[\s{INVISIBLE_CHARACTERS}]+$")


def trim_edges(value: str) -> str:
    """Remove spaces and invisible marks at both ends; marks inside the text are kept."""
    return _EDGES.sub("", value)


# A reusable "text that is not empty" type: trimmed first, then checked (the order matters).
NonEmptyStr = Annotated[str, AfterValidator(trim_edges), Field(min_length=1)]


def quoted_from(quantity: str, text: str) -> bool:
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
        if self.quantity is not None and not quoted_from(self.quantity, self.text):
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

    The imported original text is kept apart from this, in `Recipe.original`, which editing
    never changes.
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


# --- Review: drafts, issues and the imported original --------------------------------------------

# "draft": imported and not reviewed yet. "saved": the person saved it as a recipe.
RecipeStatus = Literal["draft", "saved"]

# What an import can flag for review. The model may report the first group; the backend adds
# the second group from its own checks of the model's answer (app/extraction/review.py).
ModelIssueKind = Literal[
    "ingredient_only_in_steps",  # the steps use an ingredient the list does not name; it is NOT added
    "unclear_text",  # cut off, garbled, or wording that can be read two ways
    "missing_information",  # something a cook needs that the text does not give
    "ambiguous_alternative",  # an "or ..." whose scope is unclear
    "multiple_recipes",  # the text holds more than one recipe; only the main one was taken
    "other",
]
BackendIssueKind = Literal[
    "missing_title",  # the text has no title; one was composed from its words
    "quantity_not_in_line",  # the model's quantity is not written in its line; left empty
    "not_found_in_source",  # a line that does not appear in the original text: check it
    "classification_unresolved",  # no single existing category clearly fits; left unclassified
    "not_extracted",  # saved without the model: fill in the recipe from the original text
    "unused_text",  # a passage of the original the model neither used nor marked as not part of the recipe
    "invalid_reference",  # the model pointed at passages that do not exist, or used one twice
    "caption_incomplete",  # the caption came from a preview that may be cut off: compare with the post
]
IssueKind = ModelIssueKind | BackendIssueKind


class Issue(ContractModel):
    """Something the person should check before saving an imported draft."""

    kind: IssueKind
    message: NonEmptyStr  # for the person, in Hebrew
    quote: NonEmptyStr | None = None  # the exact words of the original text it is about, if any


ImportKind = Literal["text", "instagram"]  # websites and screenshots come later in milestone 5
# Which public page of the post supplied a caption read automatically (app/importers/instagram.py).
RetrievedFrom = Literal["post_page", "embed_view"]


class ImportedOriginal(ContractModel):
    """The text a recipe was imported from, exactly as pasted or read. Read-only: saving never changes it."""

    model_config = ConfigDict(str_strip_whitespace=False)  # returned exactly as stored, edges included

    kind: ImportKind  # "text": pasted by the person; "instagram": the caption, read from the post
    text: str
    model: NonEmptyStr | None  # the model that read it; None: saved without a model
    imported_at: AwareDatetime
    url: str | None = None  # the post it came from (also for a caption pasted after a failed read)
    retrieved_from: RetrievedFrom | None = None  # only for a caption read automatically


class Recipe(RecipeContent):
    """A stored recipe, as the API returns it."""

    id: int
    category: CategoryRef | None = None  # None: not classified yet
    subcategory: CategoryRef | None = None  # only together with a category
    is_sample: bool = False  # True for the built-in examples, which were invented for the project
    status: RecipeStatus = "saved"
    issues: list[Issue] = []  # what to check before saving a draft
    original: ImportedOriginal | None = None  # None: typed in by hand
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
    The server sets the id, the timestamps and is_sample itself. The imported original is
    not part of this model, so a save cannot change it.
    """

    category_id: int | None = None
    subcategory_id: int | None = None
    status: RecipeStatus = "saved"  # the review screen sends "draft" to keep reviewing later
    issues: list[Issue] = []  # the issues still open, when saving a draft

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


MAX_CATEGORY_NAME = 60
MAX_CATEGORY_DESCRIPTION = 600  # the model reads every description at each import: keep them short


def _blank_is_none(value: str | None) -> str | None:
    return value if value else None


OptionalDescription = Annotated[str | None, Field(max_length=MAX_CATEGORY_DESCRIPTION), AfterValidator(_blank_is_none)]


class CategoryUpdate(ContractModel):
    """PUT /api/categories/{id}: a category's new name and description. Its parent never changes: recipes
    point at the pair (category, subcategory), so moving a subcategory would break them."""

    name: Annotated[NonEmptyStr, Field(max_length=MAX_CATEGORY_NAME)]
    description: OptionalDescription = None  # what belongs in it: the model classifies by it


class CategoryInput(CategoryUpdate):
    """POST /api/categories: a new top-level category, or with parent_id a subcategory of one."""

    parent_id: int | None = None


class CategoryRow(ContractModel):
    """A category as created or changed: a subcategory has the id of its top-level category as parent_id."""

    id: int
    name: NonEmptyStr
    description: NonEmptyStr | None = None
    parent_id: int | None = None


# --- Importing ---------------------------------------------------------------------------------

MAX_IMPORT_CHARACTERS = 20_000  # a long recipe page is about 10,000; an Instagram caption at most 2,200


class InstagramImport(ContractModel):
    """POST /api/imports/instagram: the address of a public Instagram post or Reel."""

    url: str = Field(min_length=1, max_length=2000)
    use_model: bool = True  # False: save the caption as a draft to fill in by hand


class TextImport(ContractModel):
    """POST /api/imports/text: recipe text the person pasted."""

    # Kept exactly as pasted, spaces and line breaks included: no trimming here.
    model_config = ConfigDict(str_strip_whitespace=False)

    text: str = Field(min_length=1, max_length=MAX_IMPORT_CHARACTERS)
    use_model: bool = True  # False: save the text as a draft to fill in by hand, without Claude
    # The Instagram post the text was copied from, when reading the post itself failed: kept with
    # the original and as the recipe's source.
    url: str | None = Field(default=None, max_length=2000)
    # The text is a caption preview that may be cut off, sent unchanged: the draft says so.
    possibly_incomplete: bool = False

    @field_validator("text")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not trim_edges(value):
            raise ValueError("the text is empty")
        return value


class ExtractionInfo(ContractModel):
    """GET /api/extraction: can imports use a model right now, and which one?"""

    configured: bool  # ready: an API key is set (Claude), or Ollama runs and has the model (local)
    provider: Literal["claude", "ollama"]
    model: str
    local: bool  # True: the text stays on this computer
    # Why it is not ready, for the import screen.
    problem: Literal["no_api_key", "ollama_unreachable", "ollama_model_missing"] | None = None
