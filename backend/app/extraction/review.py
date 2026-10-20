"""Turn Claude's answer into a draft for review, checking everything on the way.

Nothing the model says is taken on trust:
- every line (title, ingredients, steps, notes, group names) must appear in the original
  text; a line that does not is kept but flagged, so the person compares it with the source;
- every quantity must be written in its own ingredient line; one that is not is left empty
  and flagged, never kept as an invented amount;
- category ids must exist, and a subcategory must belong to the chosen category; otherwise
  the draft stays unclassified and an issue says why. Only an unambiguous answer classifies;
- the model's issue messages may not talk about categories (they are dropped), so nothing
  ever suggests a new category; classification messages are written here, from the
  database's own category names;
- quotes must be words from the original text; others are removed.
"""

import re
import unicodedata

from pydantic import ValidationError

from app import schemas
from app.errors import ApiError
from app.extraction.output import Classification, ExtractionOutput

MAX_MODEL_ISSUES = 20
MAX_MESSAGE_LENGTH = 400
MAX_TITLE_LENGTH = 120

_INVISIBLE = re.compile(f"[{schemas.INVISIBLE_CHARACTERS}]")
_SPACES = re.compile(r"\s+")
_MENTIONS_CATEGORIES = re.compile(r"קטגורי|categor", re.IGNORECASE)


def normalize(text: str) -> str:
    """For comparing with the original: same Unicode form, no invisible marks, single spaces.

    Nothing else is relaxed: a changed letter, digit, unit or apostrophe still counts as different.
    """
    text = unicodedata.normalize("NFC", text)
    text = _INVISIBLE.sub("", text)
    return _SPACES.sub(" ", text).strip()


class _Original:
    def __init__(self, text: str) -> None:
        self._normalized = normalize(text)

    def contains(self, piece: str) -> bool:
        return normalize(piece) in self._normalized


def build_draft(output: ExtractionOutput, source_text: str, categories: list[schemas.Category]) -> schemas.RecipeInput:
    """The model's answer as a draft recipe with its review issues. Raises ApiError if it is not usable."""
    original = _Original(source_text)
    issues: list[schemas.Issue] = []

    def check(piece: str, what: str) -> None:
        if not original.contains(piece):
            issues.append(
                schemas.Issue(
                    kind="not_found_in_source",
                    message=f'{what} "{piece}" לא מופיע כך בטקסט המקורי. השוו למקור ותקנו אם צריך.',
                )
            )

    category_id, subcategory_id, classification_issue = resolve_classification(output.classification, categories)
    if classification_issue is not None:
        issues.append(classification_issue)

    title = _clean(output.title)[:MAX_TITLE_LENGTH]
    if not title:
        title = first_line(source_text)
        issues.append(_missing_title(title))
    elif not output.title_written_in_text:
        issues.append(_missing_title(title))
    else:
        check(title, "הכותרת")

    issues.extend(_model_issues(output, original))

    servings = _clean(output.servings or "") or None
    if servings:
        check(servings, "כמות המנות")

    ingredient_groups = []
    for group in output.ingredient_groups:
        name = _clean(group.name or "") or None
        if name:
            check(name, "שם הקבוצה")
        ingredients = []
        for item in group.ingredients:
            text = _clean(item.text)
            if not text:
                continue
            check(text, "השורה")
            quantity = _clean(item.quantity or "") or None
            if quantity is not None and not schemas.quoted_from(quantity, text):
                issues.append(
                    schemas.Issue(
                        kind="quantity_not_in_line",
                        message=f'הכמות "{quantity}" לא כתובה בשורה "{text}", ולכן נשארה ריקה. השלימו מהמקור אם צריך.',
                    )
                )
                quantity = None
            ingredients.append({"text": text, "quantity": quantity})
        if ingredients:
            ingredient_groups.append({"name": name, "ingredients": ingredients})

    step_groups = []
    for group in output.step_groups:
        name = _clean(group.name or "") or None
        if name:
            check(name, "כותרת הקבוצה")
        steps = [step for step in (_clean(step) for step in group.steps) if step]
        for step in steps:
            check(step, "השלב")
        if steps:
            step_groups.append({"name": name, "steps": steps})

    notes = [note for note in (_clean(note) for note in output.notes) if note]
    for note in notes:
        check(note, "ההערה")

    if not ingredient_groups and not step_groups:
        issues.append(schemas.Issue(kind="missing_information", message="לא נמצאו בטקסט מצרכים או שלבי הכנה."))

    try:
        return schemas.RecipeInput(
            title=title,
            servings=servings,
            ingredient_groups=ingredient_groups,
            step_groups=step_groups,
            notes=notes,
            sources=[schemas.Source(kind="text")],
            category_id=category_id,
            subcategory_id=subcategory_id,
            status="draft",
            issues=issues,
        )
    except ValidationError:
        raise ApiError(502, "extraction_invalid_output", "Claude's answer could not be turned into a recipe.") from None


def resolve_classification(
    choice: Classification, categories: list[schemas.Category]
) -> tuple[int | None, int | None, schemas.Issue | None]:
    """(category_id, subcategory_id, issue): a category only for a clear, valid choice; never a new one."""
    by_id = {category.id: category for category in categories}

    def unresolved(message: str) -> tuple[None, None, schemas.Issue]:
        return None, None, schemas.Issue(kind="classification_unresolved", message=message)

    if choice.fit == "clear" and choice.category_id is not None:
        category = by_id.get(choice.category_id)
        if category is None:
            return unresolved("המודל ענה במספר קטגוריה שלא קיים, ולכן המתכון נשאר לא מסווג. בחרו קטגוריה קיימת או השאירו כך.")
        if choice.subcategory_id is None:
            return category.id, None, None
        if any(sub.id == choice.subcategory_id for sub in category.subcategories):
            return category.id, choice.subcategory_id, None
        return unresolved(
            f'המודל בחר ב"{category.name}" עם תת-קטגוריה שאינה שייכת אליה, ולכן המתכון נשאר לא מסווג. '
            "בחרו בעצמכם, או השאירו לא מסווג."
        )
    if choice.fit == "ambiguous":
        names = [by_id[i].name for i in dict.fromkeys(choice.candidate_category_ids) if i in by_id]
        if len(names) >= 2:
            listed = ", ".join(f'"{name}"' for name in names)
            return unresolved(f"לא ברור לאיזו קטגוריה המתכון שייך: {listed}. בחרו בעצמכם, או השאירו לא מסווג.")
        return unresolved("לא ברור לאיזו קטגוריה המתכון שייך. בחרו קטגוריה קיימת, או השאירו לא מסווג.")
    return unresolved("אף אחת מהקטגוריות הקיימות לא מתאימה בבירור. בחרו קטגוריה קיימת, או השאירו לא מסווג.")


def manual_draft(source_text: str) -> schemas.RecipeInput:
    """A draft for text saved without the model: the person fills it in from the original."""
    title = first_line(source_text)
    return schemas.RecipeInput(
        title=title,
        sources=[schemas.Source(kind="text")],
        status="draft",
        issues=[
            schemas.Issue(
                kind="not_extracted",
                message="הטקסט נשמר בלי עיבוד. העתיקו ממנו את המצרכים ואת שלבי ההכנה לטופס.",
            ),
            _missing_title(title),
        ],
    )


def first_line(text: str) -> str:
    """The first non-empty line, as a stand-in title."""
    for line in text.splitlines():
        cleaned = _clean(line)
        if cleaned:
            return cleaned[:MAX_TITLE_LENGTH]
    return "מתכון ללא כותרת"


def _missing_title(title: str) -> schemas.Issue:
    return schemas.Issue(
        kind="missing_title",
        message=f'בטקסט אין כותרת ברורה. הכותרת "{title}" נלקחה ממילים בטקסט; שנו אותה אם צריך.',
    )


def _model_issues(output: ExtractionOutput, original: _Original) -> list[schemas.Issue]:
    issues = []
    for issue in output.issues[:MAX_MODEL_ISSUES]:
        message = _clean(issue.message)[:MAX_MESSAGE_LENGTH]
        quote = _clean(issue.quote or "") or None
        if not message or _MENTIONS_CATEGORIES.search(message) or (quote and _MENTIONS_CATEGORIES.search(quote)):
            continue  # classification feedback comes only from resolve_classification
        if quote is not None and not original.contains(quote):
            quote = None
        issues.append(schemas.Issue(kind=issue.kind, message=message, quote=quote))
    return issues


def _clean(text: str) -> str:
    return schemas.trim_edges(text)
