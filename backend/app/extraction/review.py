"""Turn the model's answer into a draft for review, checking everything on the way.

Two kinds of answer (RECIPES_EXTRACTION_MODE):
- references (the default): the model labels each numbered passage of the original (an
  ingredient, a step, a heading, a note, not part of the recipe...) and the recipe's wording is
  copied from the original here, so it cannot be altered. build_draft_from_references.
- text: the model copies the wording itself; build_draft checks it against the original.

Nothing the model says is taken on trust:
- every passage must be labeled, and a passage that "continues" must have an item before it;
  otherwise a review issue quotes the passage, so nothing is left out silently;
- copied text (text mode, and the title) must appear in the original; a line that does not is
  kept but flagged, so the person compares it with the source;
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
from app.extraction.output import Classification, ExtractionOutput, ReferenceOutput
from app.extraction.quantity import find_quantity
from app.extraction.segments import Segment, ends_with_colon, passage_key, passage_text, segment_text

MAX_MODEL_ISSUES = 20
MAX_MESSAGE_LENGTH = 400
MAX_TITLE_LENGTH = 120

_INVISIBLE = re.compile(f"[{schemas.INVISIBLE_CHARACTERS}]")
_SPACES = re.compile(r"\s+")
_MENTIONS_CATEGORIES = re.compile(r"קטגורי|categor", re.IGNORECASE)

# Decoration that the contract leaves out, which smaller models tend to copy along:
# bullets and emoji at the start of a line, list numbers before a step, ":" "-" "|" around headings.
_BULLETS = set("-–—•·*▪►‣◦●○✓✔➤→")
_JOINERS = {"️", "‍"}  # parts of emoji such as 🌶️ and 🙋‍♀️
# "1." "2)" "(3)", or a keycap emoji "1️⃣" (a digit, an optional emoji selector, the keycap mark)
_LIST_NUMBER = re.compile(r"^(?:\(?\d{1,2}[.)]\s+|\d\N{VARIATION SELECTOR-16}?\N{COMBINING ENCLOSING KEYCAP}\s*)")
_HEADING_EDGES = " :：-–—|•*"
# Section titles that are not groups when a recipe has only one group of that kind.
_GENERIC_HEADINGS = {
    "מצרכים", "רכיבים", "מה צריך", "מה צריך?", "ingredients",
    "הכנה", "אופן הכנה", "אופן ההכנה", "מה עושים", "מה עושים?", "איך מכינים", "איך מכינים?",
    "method", "instructions", "directions", "preparation",
}
# Hashtags, @mentions and calls to action: not part of the recipe. Lines with them are flagged, never deleted.
PROMOTION_FLAG = "נראה כמו פנייה לעוקבים"  # in the review point that flags such a line
TIP_IN_LIST_FLAG = "נמצאת ברשימת המצרכים אבל נשמרה כהערה"  # in the review point about such a tip
# Baking and its details, for the missing-information points. "אפייה" alone is left out: it is
# mostly equipment ("נייר אפייה", "תבנית אפייה").
_BAKE = re.compile(r"אופים|לאפות|נאפה|נאפית|(?<!\w)bake(?!\w)|(?<!\w)bake for", re.IGNORECASE)
_OVEN = re.compile(r"תנור|(?<!\w)oven(?!\w)", re.IGNORECASE)
_TEMPERATURE = re.compile(r"\d+\s*(?:°|מעלות|degrees(?!\w))", re.IGNORECASE)
_TIME = re.compile(
    r"\d+(?:\s*[-–]\s*\d+)?\s*(?:דקות|דקה|דק׳|דק'|שעות|שעה|minutes?|mins?(?!\w)|hours?|hrs?(?!\w))"
    r"|חצי שעה|רבע שעה|שעה|שעתיים|an hour|half an hour",
    re.IGNORECASE,
)
_WATER = {"מים", "water"}  # rarely listed as an ingredient: no point about it
# The fixed message for each kind of passage the model points at.
# The review points whose message is fixed (the passage they quote is their evidence).
_POINT_MESSAGES = {
    "unclear_text": ("unclear_text", "הקטע הזה נראה חתוך, משובש או לא ברור. השוו למקור."),
    "ambiguous_alternative": ("ambiguous_alternative", 'בקטע הזה יש "או" שלא ברור על מה הוא חל.'),
    "multiple_recipes": ("multiple_recipes", "נראה שבטקסט יש יותר ממתכון אחד; נלקח העיקרי. בדקו שלא חסר דבר."),
}
_NO_TEMPERATURE = "הטקסט מזכיר אפייה בתנור, אבל לא באיזו טמפרטורה. השלימו אם אתם יודעים."
_NO_BAKING_TIME = "בשלב הזה לא כתוב כמה זמן לאפות. השלימו אם אתם יודעים."
FIXED_MESSAGES = {message for _, message in _POINT_MESSAGES.values()} | {_NO_TEMPERATURE, _NO_BAKING_TIME}
_PROMO = re.compile(r"(^|\s)[#@][\w.]+|תייג|את הפוסט|לייק|link in bio|save this post", re.IGNORECASE)
# A passage of only hashtags, mentions and symbols ("#עוגה #אפייה @baker 👇"): never recipe content.
_PROMO_ONLY = re.compile(r"(?:\s*(?:[#@][\w.]+|[^\w\s]))+\s*")


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

    title = _without_end_decoration(output.title)[:MAX_TITLE_LENGTH]
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
        name = _heading(group.name)
        if name:
            check(name, "שם הקבוצה")
        ingredients = []
        for item in group.ingredients:
            text = _line(item.text)
            if not text:
                continue
            check(text, "השורה")
            ingredients.append({"text": text, "quantity": _quantity(item.quantity, text, issues)})
        if ingredients:
            ingredient_groups.append({"name": name, "ingredients": ingredients})
    ingredient_groups = _tidy_groups(ingredient_groups, "ingredients")

    step_groups = []
    for group in output.step_groups:
        name = _heading(group.name)
        if name:
            check(name, "כותרת הקבוצה")
        steps = [step for step in (_line(step, numbered=True) for step in group.steps) if step]
        for step in steps:
            check(step, "השלב")
            _flag_promo(step, "השלב", issues)
        if steps:
            step_groups.append({"name": name, "steps": steps})
    step_groups = _tidy_groups(step_groups, "steps")

    notes: list[str] = []
    for note in (_line(note) for note in output.notes):
        if note and normalize(note) not in {normalize(kept) for kept in notes}:  # each note once
            notes.append(note)
            check(note, "ההערה")
            _flag_promo(note, "ההערה", issues)

    if not ingredient_groups and not step_groups:
        issues.append(schemas.Issue(kind="missing_information", message="לא נמצאו בטקסט מצרכים או שלבי הכנה."))
    # The same point reported twice is shown once, in its first place.
    seen: set[tuple[str, str, str | None]] = set()
    unique = []
    for issue in issues:
        if (issue.kind, issue.message, issue.quote) not in seen:
            seen.add((issue.kind, issue.message, issue.quote))
            unique.append(issue)
    issues = unique

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
        raise ApiError(502, "extraction_invalid_output", "The model's answer could not be turned into a recipe.") from None


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


def _line(text: str, numbered: bool = False) -> str:
    """A line without the decoration at its start: bullets, emoji used as bullets, a step's list number."""
    text = _clean(text)
    while text and (text[0] in _BULLETS or text[0] in _JOINERS or unicodedata.category(text[0]) == "So"):
        text = _clean(text[1:])
    if numbered:
        text = _clean(_LIST_NUMBER.sub("", text, count=1))
    return text


def _heading(name: str | None) -> str | None:
    """A group's name without heading markers around it ("|לבצק:" -> "לבצק")."""
    return _clean(_clean(name or "").strip(_HEADING_EDGES)) or None


def _tidy_groups(groups: list[dict], items: str) -> list[dict]:
    """Merge groups without a name that follow each other (one list split in pieces), and drop the
    name of a single group when it is only the section's title ("מצרכים", "אופן ההכנה")."""
    merged: list[dict] = []
    for group in groups:
        if merged and group["name"] is None and merged[-1]["name"] is None:
            merged[-1][items].extend(group[items])
        else:
            merged.append(group)
    if len(merged) == 1 and (merged[0]["name"] or "").lower() in _GENERIC_HEADINGS:
        merged[0]["name"] = None
    return merged


def _flag_promo(text: str, what: str, issues: list[schemas.Issue]) -> None:
    if _PROMO.search(text):
        issues.append(
            schemas.Issue(
                kind="other",
                message=f'{what} "{text}" {PROMOTION_FLAG}, תגית או אזכור, ולא כחלק מהמתכון. מחקו אם כך.',
            )
        )


# --- Drafts from passage labels ----------------------------------------------------------------


def is_recipe(output: ExtractionOutput | ReferenceOutput) -> bool:
    """Whether the answer found a recipe. With passage labels, the labels decide: a text with a
    passage labeled as an ingredient or a step is a recipe, whatever the answer's first field says
    (measured: the model once labeled five ingredients and a step, but had already written
    is_recipe = false before labeling them)."""
    if isinstance(output, ReferenceOutput):
        roles = set(output.passages.values())
        return output.is_recipe or bool(roles & {"ingredient", "step"})
    return output.is_recipe


def make_draft(
    output: ExtractionOutput | ReferenceOutput, source_text: str, categories: list[schemas.Category]
) -> schemas.RecipeInput:
    """The draft for either kind of answer."""
    if isinstance(output, ReferenceOutput):
        # The same text always gives the same passages, so these are the numbers the model saw.
        return build_draft_from_references(output, source_text, segment_text(source_text), categories)
    return build_draft(output, source_text, categories)


def build_draft_from_references(
    output: ReferenceOutput, source_text: str, segments: list[Segment], categories: list[schemas.Category]
) -> schemas.RecipeInput:
    """A draft whose ingredients, steps, headings and notes are copied from the original passages,
    by the role the answer gives each passage.

    - The passages are read in the text's order, so items and groups keep the text's order.
    - A passage the answer did not label, or one that "continues" nothing, is not guessed at: an
      issue quotes it, so nothing is left out silently.
    - A label ("איך מכינים:"), a line of only hashtags and mentions, and the title's own line are
      never the content of an ingredient, a step or a note.
    """
    original = _Original(source_text)
    issues: list[schemas.Issue] = []

    labels = _labels(output, source_text, segments)
    category_id, subcategory_id, classification_issue = resolve_classification(output.classification, categories)
    if classification_issue is not None:
        issues.append(classification_issue)
    title_line = next(
        (
            _without_end_decoration(_line(passage_text(source_text, segments, number, number)))[:MAX_TITLE_LENGTH]
            for number, role in sorted(labels.items())
            if role == "title"
        ),
        None,
    )
    title = _title(output.title, output.title_written_in_text, source_text, original, issues, title_line)
    issues.extend(_referenced_issues(output, source_text, segments, labels))
    servings = _clean(output.servings or "") or None
    if servings and not original.contains(servings):
        issues.append(_not_found("כמות המנות", servings))

    # The passage that is exactly the title the model gave (as on a title line): the title, never
    # an ingredient or a step, even if the answer labels it so.
    title_passage = next(
        (
            segment.id
            for segment in segments
            if output.title_written_in_text
            and normalize(_without_end_decoration(segment.text(source_text))) == normalize(title)
        ),
        None,
    )

    def is_label_or_title(number: int) -> bool:
        return number == title_passage or _not_content(source_text, segments[number - 1])

    ingredient_groups: list[dict] = []  # {"heading": passage number or None, "items": [[first, last]]}
    step_groups: list[dict] = []
    notes: list[list] = []
    info_starts: set[int] = set()  # the first passage of each note that is a yield or time line
    unlabeled: list[int] = []
    current: list | None = None  # [first, last]: the item that a "continues" passage extends
    previous: str | None = None  # the role of the passage before
    for segment in segments:
        role = labels.get(segment.id)
        if role == "continues":
            if current is not None:
                current[1] = segment.id
                continue
            if previous in ("title", "not_recipe"):  # the rest of an introduction or a call to action
                continue
            if previous == "ingredient_heading":  # the label's own list or text goes on here
                role = "ingredient"
            elif previous == "step_heading":
                role = "step"
            else:
                issues.append(_nothing_to_continue(segment.text(source_text)))
                current = previous = None
                continue
        current = None
        if role is None:
            unlabeled.append(segment.id)
            previous = None
            continue
        if segment.id == title_passage or role in ("title", "not_recipe") or _PROMO_ONLY.fullmatch(segment.text(source_text)):
            previous = "not_recipe"
            continue
        if role == "tip" and ingredient_groups and not step_groups:  # after the list started, before the steps
            issues.append(_tip_in_ingredient_list(segment.text(source_text)))
        if ends_with_colon(source_text, segment):  # a label: a heading, whatever the answer says
            role = {"ingredient": "ingredient_heading", "step": "step_heading"}.get(role, role)
        if role == "ingredient_heading":
            ingredient_groups.append({"heading": segment.id, "items": []})
        elif role == "step_heading":
            step_groups.append({"heading": segment.id, "items": []})
        elif role in ("ingredient", "step"):
            groups = ingredient_groups if role == "ingredient" else step_groups
            if not groups:
                groups.append({"heading": None, "items": []})
            current = [segment.id, segment.id]
            groups[-1]["items"].append(current)
        elif role in ("tip", "info"):  # a note
            current = [segment.id, segment.id]
            notes.append(current)
            if role == "info":
                info_starts.add(segment.id)
        previous = role

    def text_of(first: int, last: int, keep_labels: bool = False) -> str:
        """The item's text, without a label ("טיפ:"), the title line or hashtags at its ends. An info
        line keeps its label: in "זמן הכנה: 50 דקות" the label is what the time is for."""
        def left_out(number: int) -> bool:
            if keep_labels:
                return number == title_passage or bool(_PROMO_ONLY.fullmatch(segments[number - 1].text(source_text)))
            return is_label_or_title(number)

        while first <= last and left_out(first):
            first += 1
        while last >= first and left_out(last):
            last -= 1
        return passage_text(source_text, segments, first, last) if first <= last else ""

    ingredient_list = []
    for group in ingredient_groups:
        ingredients = []
        for first, last in group["items"]:
            text = _line(_without_final_period(text_of(first, last)))
            if text:
                ingredients.append({"text": text, "quantity": find_quantity(text)})
        if ingredients:
            ingredient_list.append({"name": _group_name(source_text, segments, group["heading"]), "ingredients": ingredients})

    step_list = []
    for group in step_groups:
        steps = []
        for first, last in group["items"]:
            text = _line(text_of(first, last), numbered=True)
            if text:
                steps.append(text)
                _flag_promo(text, "השלב", issues)
        if steps:
            step_list.append({"name": _group_name(source_text, segments, group["heading"]), "steps": steps})

    note_list: list[str] = []
    for first, last in notes:
        text = _line(text_of(first, last, keep_labels=first in info_starts))
        if text and normalize(text) not in {normalize(kept) for kept in note_list}:
            note_list.append(text)
            _flag_promo(text, "ההערה", issues)

    for run in _runs(unlabeled):
        text = passage_text(source_text, segments, run[0], run[-1])
        issues.append(
            schemas.Issue(
                kind="unused_text",
                message=f'המודל לא שיבץ את הקטע "{_short(text)}". אם הוא חלק מהמתכון, הוסיפו אותו.',
                quote=_short(text, 300),
            )
        )

    ingredient_list = _tidy_groups(ingredient_list, "ingredients")
    step_list = _tidy_groups(step_list, "steps")
    steps = [step for group in step_list for step in group["steps"]]
    lines = [item["text"] for group in ingredient_list for item in group["ingredients"]]
    issues.extend(_only_in_steps(output, source_text, segments, steps, lines))
    issues.extend(_missing_information(source_text, steps))
    if not ingredient_list and not step_list:
        issues.append(schemas.Issue(kind="missing_information", message="לא נמצאו בטקסט מצרכים או שלבי הכנה."))
    return _draft(title, servings, ingredient_list, step_list, note_list, category_id, subcategory_id, issues)


def _labels(output: ReferenceOutput, source_text: str, segments: list[Segment]) -> dict[int, str]:
    """Each passage's role, found by the passage's own key; a passage without one is left out."""
    labels = {}
    for segment in segments:
        role = output.passages.get(passage_key(source_text, segment))
        if role is not None:
            labels[segment.id] = role
    return labels


def _group_name(source_text: str, segments: list[Segment], heading: int | None) -> str | None:
    return _heading(passage_text(source_text, segments, heading, heading)) if heading is not None else None


def _quantity(quantity: str | None, text: str, issues: list[schemas.Issue]) -> str | None:
    """The model's quantity, if it is written in the line. The whole line is not a quantity
    ("מלח ופלפל" for "מלח ופלפל"): left empty, without a review point, since the line is complete."""
    quantity = _clean(quantity or "") or None
    if quantity is None or normalize(quantity) == normalize(text):
        return None
    if not schemas.quoted_from(quantity, text):
        issues.append(_quantity_not_in_line(quantity, text))
        return None
    return quantity


def _nothing_to_continue(text: str) -> schemas.Issue:
    return schemas.Issue(
        kind="invalid_reference",
        message=f'המודל סימן את הקטע "{_short(text)}" כהמשך של הקטע שלפניו, אבל אין לפניו מצרך, שלב או הערה '
        "להמשיך. אם הוא חלק מהמתכון, הוסיפו אותו.",
        quote=_short(text, 300),
    )


def _not_content(source_text: str, segment: Segment) -> bool:
    return ends_with_colon(source_text, segment) or bool(_PROMO_ONLY.fullmatch(segment.text(source_text)))


def _title(
    title: str,
    written: bool,
    source_text: str,
    original: _Original,
    issues: list[schemas.Issue],
    title_line: str | None = None,
) -> str:
    """The model writes the title itself (it may be composed); a title it says is written in the
    text must be found there. If it is not, but the answer labeled a passage as the title line,
    that passage's own words are the title: the label says which words are meant, so nothing is
    guessed. Decoration at its end (emoji) is left out, as at the start of lines."""
    title = _without_end_decoration(title)[:MAX_TITLE_LENGTH]
    if written and title and _starts_a_line(title, source_text):
        return title
    if written and title_line:
        return title_line
    if not title:
        title = first_line(source_text)
    if written and not original.contains(title):
        issues.append(_not_found("הכותרת", title))
    else:  # composed, or words from inside a sentence: the text has no title line with them
        issues.append(_missing_title(title))
    return title


def _starts_a_line(title: str, source_text: str) -> bool:
    """A title written in the text is a title line: some line starts with it."""
    wanted = normalize(title)
    return any(normalize(_line(line)).startswith(wanted) for line in source_text.splitlines() if line.strip())


def _without_end_decoration(text: str) -> str:
    """Without emoji and other symbols at the end ("שקשוקה ירוקה 💚" → "שקשוקה ירוקה")."""
    text = _clean(text)
    while text and (text[-1] in _JOINERS or unicodedata.category(text[-1]) == "So"):
        text = _clean(text[:-1])
    return text


def _referenced_issues(
    output: ReferenceOutput, source_text: str, segments: list[Segment], labels: dict[int, str]
) -> list[schemas.Issue]:
    """The passages the model pointed at, each with the fixed message for its kind and the passage
    quoted as the evidence. Not shown: a point that needs a passage and has none, and a point about a
    passage the model itself labeled as not part of the recipe (it is already left out)."""
    issues = []
    for issue in output.issues[:MAX_MODEL_ISSUES]:
        if labels.get(issue.passage) in ("not_recipe", "title"):
            continue
        kind, message = _POINT_MESSAGES[issue.kind]
        quote = None
        if issue.passage is not None and 1 <= issue.passage <= len(segments):
            quote = _short(passage_text(source_text, segments, issue.passage, issue.passage), 300) or None
        if quote is None and issue.kind != "multiple_recipes":
            continue
        issues.append(schemas.Issue(kind=kind, message=message, quote=quote))
    return issues


def _only_in_steps(
    output: ReferenceOutput, source_text: str, segments: list[Segment], steps: list[str], lines: list[str]
) -> list[schemas.Issue]:
    """An ingredient the model says only the steps use: shown if that step writes those words and
    no ingredient line has them (in any of their usual forms: "התותים", "בתותים", "תות")."""
    listed = normalize(" | ".join(lines)).lower()
    issues = []
    for item in output.only_in_steps[:MAX_MODEL_ISSUES]:
        words = _clean(item.words)
        if not words or len(words.split()) > 4 or not 1 <= item.passage <= len(segments):
            continue
        passage = passage_text(source_text, segments, item.passage, item.passage)
        if normalize(words).lower() not in normalize(passage).lower():
            continue  # not what that passage writes
        if not any(normalize(passage) in normalize(step) for step in steps):
            continue  # not a step
        if _listed(words, listed):
            continue
        issues.append(
            schemas.Issue(
                kind="ingredient_only_in_steps",
                message=f'המצרך "{words}" מופיע באופן ההכנה אבל לא ברשימת המצרכים. הוסיפו אותו אם צריך.',
                quote=_short(passage, 300),
            )
        )
    return issues


def _listed(words: str, listed: str) -> bool:
    """Is the ingredient in the list? Decided by its first word of three letters or more, in any of
    its forms (without a Hebrew prefix letter or two, singular or plural); water always counts."""
    for word in words.split():
        word = normalize(word).lower().strip(".,;:!?()\"'״׳")
        forms = {word, word[1:], word[2:]} | {f[:-2] for f in (word, word[1:], word[2:]) if f.endswith(("ים", "ות", "es"))}
        forms |= {word[:-1]} if word.endswith("s") else set()
        forms = {f for f in forms if len(f) >= 3}
        if not forms:
            continue
        return bool(forms & _WATER) or any(form in listed for form in forms)
    return True


def _missing_information(source_text: str, steps: list[str]) -> list[schemas.Issue]:
    """What a cook needs to bake and the text does not give: the oven's temperature, the baking time."""
    issues = []
    baking = [step for step in steps if _BAKE.search(step) or _OVEN.search(step)]
    if baking and not _TEMPERATURE.search(source_text):
        issues.append(
            schemas.Issue(
                kind="missing_information",
                message=_NO_TEMPERATURE,
                quote=_short(baking[0], 300),
            )
        )
    for step in steps:
        if _BAKE.search(step) and not _TIME.search(step):
            issues.append(
                schemas.Issue(
                    kind="missing_information",
                    message=_NO_BAKING_TIME,
                    quote=_short(step, 300),
                )
            )
            break
    return issues


def _tip_in_ingredient_list(text: str) -> schemas.Issue:
    return schemas.Issue(
        kind="other",
        message=f"השורה הזאת {TIP_IN_LIST_FLAG}. אם זה מצרך, העבירו אותה לרשימת המצרכים.",
        quote=_short(text, 300),
    )


def _draft(
    title: str,
    servings: str | None,
    ingredient_groups: list[dict],
    step_groups: list[dict],
    notes: list[str],
    category_id: int | None,
    subcategory_id: int | None,
    issues: list[schemas.Issue],
) -> schemas.RecipeInput:
    seen: set[tuple[str, str, str | None]] = set()
    unique = []
    for issue in issues:  # the same point reported twice is shown once, in its first place
        if (issue.kind, issue.message, issue.quote) not in seen:
            seen.add((issue.kind, issue.message, issue.quote))
            unique.append(issue)
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
            issues=unique,
        )
    except ValidationError:
        raise ApiError(502, "extraction_invalid_output", "The model's answer could not be turned into a recipe.") from None


def _not_found(what: str, piece: str) -> schemas.Issue:
    return schemas.Issue(
        kind="not_found_in_source", message=f'{what} "{piece}" לא מופיע כך בטקסט המקורי. השוו למקור ותקנו אם צריך.'
    )


def _quantity_not_in_line(quantity: str, text: str) -> schemas.Issue:
    return schemas.Issue(
        kind="quantity_not_in_line",
        message=f'הכמות "{quantity}" לא כתובה בשורה "{text}", ולכן נשארה ריקה. השלימו מהמקור אם צריך.',
    )


def _without_final_period(text: str) -> str:
    """An ingredient line without a sentence's final period ("מלח ופלפל שחור." at the end of a prose list)."""
    return text[:-1] if text.endswith(".") and not text.endswith("..") else text


def _short(text: str, limit: int = 80) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _runs(numbers: list[int]) -> list[list[int]]:
    """[3, 4, 5, 9] -> [[3, 4, 5], [9]]"""
    runs: list[list[int]] = []
    for number in numbers:
        if runs and number == runs[-1][-1] + 1:
            runs[-1].append(number)
        else:
            runs.append([number])
    return runs
