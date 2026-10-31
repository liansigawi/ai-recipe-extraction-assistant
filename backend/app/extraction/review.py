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
- quotes must be words from the original text; others are removed;
- servings need evidence: a passage that says it is the yield. A passage the model rejected as
  not part of the recipe (an instruction inside the text) never supplies a value;
- an ingredient that the text (or a screenshot's line wrapping) breaks over two lines is joined
  only on a clear sign: a number whose unit starts the next line, a "+" or an open bracket, a
  remark in brackets, a name cut after "גבינת" or "חמאת", a line ending in "ללא" or "עם". A line
  that only might go on the one before ("מופשר") stays as written and is flagged (_wrapped).
"""

import re
import unicodedata

from pydantic import ValidationError

from app import schemas
from app.errors import ApiError
from app.extraction import ingredient_words
from app.extraction.output import Classification, ExtractionOutput, ReferenceLabels, ReferenceOutput
from app.extraction.ingredient_words import HEBREW as INGREDIENT_WORDS
from app.extraction.ingredient_words import mentions_ingredient
from app.extraction.quantity import ends_with_unit, find_quantity, quantity_unclear, starts_with_amount, starts_with_unit
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
# Section titles, never group names.
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
# A label that says what a time is for ("זמן הכנה:", "Prep time:", "Cook:"): with a duration after it on its
# line, the line is a time for the whole recipe, kept as a note with its label.
_TIME_LABEL = re.compile(r"זמן|(?<!\w)(?:time|prep|cook|cooking|bake|baking|ready|total)(?!\w)", re.IGNORECASE)
_WATER = {"מים", "water"}  # rarely listed as an ingredient: no point about it
# A line that says what an ingredient is for, or that it is optional: "לציפוי - מלח מאלדון", "קרח להגשה",
# "אופציונאלי: שוקולד צ׳יפס", "To garnish: basil", "Lemon wedges, for serving". At the end of an ingredient
# list the model labeled such lines as tips (measured: the same line in the middle of the list, or without
# its purpose word, was an ingredient), and it labels the label alone as a tip ("אופציונאלי:" was lost).
_PURPOSES = "לציפוי|לקישוט|להגשה|לפיזור|לזילוף|למריחה|לגלגול|לבזיקה|לטבילה|לצד|לליווי|אופציונלי|אופציונאלי|לא חובה"
_PURPOSES_EN = (
    r"for (?:the )?(?:serving|garnish(?:ing)?|topping|decoration|decorating|sprinkling|dusting|dipping|drizzling)"
    r"|to (?:serve|garnish|top|decorate|sprinkle|dust)|optional"
)
_PURPOSE_LINE = re.compile(
    rf"^\W*(?:{_PURPOSES}|{_PURPOSES_EN})(?![\w])[^.!?]{{0,40}}[-–—:]\s*\S"  # the purpose first
    rf"|^[^.!?:]{{1,60}}\s(?:{_PURPOSES})(?:\s[^\s.!?]+)?[\s\W]*$"  # the purpose last
    rf"|^[^.!?:]{{1,60}},?\s(?:{_PURPOSES_EN})[\s\W]*$",
    re.IGNORECASE,
)
_PURPOSE_LABEL = re.compile(rf"^\W*(?:{_PURPOSES}|{_PURPOSES_EN})(?:\s\S+)?\s*:\s*$", re.IGNORECASE)  # "להגשה:"
# A note's label that says nothing more than "a note" ("טיפ:"): left out. Other labels say what the note is
# ("אופציה טבעונית:", "אחסון:", "Make ahead:") and stay with it.
_GENERIC_NOTE_LABEL = re.compile(r"^\W*(?:טיפ|טיפים|הערה|הערות|שימו לב|tips?|notes?)\W*$", re.IGNORECASE)
# A wish, a sign-off or a call to followers ("תהנו ❤️", "בתיאבון!", "וזהו😍 נכון קל?", "תייגו חברה", "Enjoy!").
# The prompt calls these not part of the recipe, but the model still labeled some as tips (measured: 5 cases).
_SOCIAL = re.compile(
    # "וזהו" and a line-ending "זהו" are "that's it"; "זהו הטריק" ("this is the trick") is not social.
    r"(?<!\w)ו?(?:בתיאבון|תהנו|תיהנו|בהצלחה|(?<=ו)זהו|זהו זה|זהו(?=\W*$)|נכון קל|קל נכון|מחכה לשמוע|ספרו לי|תספרו לי"
    r"|תייג\w*|תתייג\w*|שתפו|תשתפו|תשלח\w* את הפוסט|שלחו את הפוסט|עקבו אחרי(?:י|נו)|ת?שמרו את ה?(?:מתכון|פוסט))(?!\w)"
    r"|(?<!\w)(?:enjoy|bon app[eé]tit|happy (?:baking|cooking)|let me know|tag (?:a friend|me|someone)"
    r"|share (?:this|it|with)|save (?:this|the) (?:recipe|post)|follow (?:me|for))(?!\w)",
    re.IGNORECASE,
)
# What makes a short line useful whatever else it says: keeping, serving (and at what temperature), heating,
# swapping.
_NOTE_CONTENT = re.compile(
    r"מקרר|מקפיא|להגיש|מגישים|לחמם|מחממים|להחליף|להמיר|אפשר|ניתן|(?<!\w)(?:חם|חמים|חמה|קר|קרה|קרים|צונן)(?!\w)"
    r"|fridge|freez|serve|reheat|swap|substitut|instead|warm|cold|chilled|hot(?!\w)",
    re.IGNORECASE,
)
# Words that say a line is the recipe's yield.
_YIELD = re.compile(
    r"מנות|מנה|יחידות|יחידה|סועדים|אנשים|יוצא|יוצאת|יוצאות|יוצאים|מספיק"
    r"|(?<!\w)(?:serves?|servings?|makes|yields?|portions?)(?!\w)",
    re.IGNORECASE,
)
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
        # The category is clear; only the subcategory is not one of its own: keep the category.
        return category.id, None, schemas.Issue(
            kind="classification_unresolved",
            message=f'המודל בחר ב"{category.name}" עם תת-קטגוריה שאינה שייכת אליה, ולכן נשמרה רק הקטגוריה. '
            "בחרו תת-קטגוריה בעצמכם אם צריך.",
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


def _missing_title(title: str, from_text: bool = True) -> schemas.Issue:
    """A composed title: from the text's own words, or (as the model sometimes does) with words that
    are not in the text, which the message then says."""
    where = "נלקחה ממילים בטקסט" if from_text else "הוצעה על ידי המודל, ולא כל המילים בה מופיעות בטקסט"
    return schemas.Issue(kind="missing_title", message=f'בטקסט אין כותרת ברורה. הכותרת "{title}" {where}; שנו אותה אם צריך.')


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
    """Drop a group's name when it is only the section's title ("מצרכים", "Ingredients", "אופן
    ההכנה"), with one group or several, then merge groups without a name that follow each other
    (one list split in pieces)."""
    merged: list[dict] = []
    for group in groups:
        if (group["name"] or "").lower() in _GENERIC_HEADINGS:
            group["name"] = None
        if merged and group["name"] is None and merged[-1]["name"] is None:
            merged[-1][items].extend(group[items])
        else:
            merged.append(group)
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


def is_recipe(output: ExtractionOutput | ReferenceLabels) -> bool:
    """Whether the answer found a recipe. With passage labels, the labels can overrule the answer's
    first field: a text with passages labeled as ingredients and as steps is a recipe even if the
    model wrote is_recipe = false (measured: it once labeled five ingredients and a step after
    writing false). Ingredients alone do not overrule it: a shopping list is not a recipe."""
    if isinstance(output, ReferenceLabels):
        roles = set(output.passages.values())
        return output.is_recipe or {"ingredient", "step"} <= roles
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
    title_number = next((number for number, role in sorted(labels.items()) if role == "title"), None)
    title_line, title_is_label = None, False
    if title_number is not None:
        last = _title_line_end(source_text, segments, labels, title_number)
        title_is_label = last != title_number
        title_line = _without_end_decoration(_line(passage_text(source_text, segments, title_number, last)))[:MAX_TITLE_LENGTH]
    # Passages the model rejected as not part of the recipe (introductions, calls to action, and
    # instructions inside the text): they can never supply a value to the recipe.
    rejected = {normalize(s.text(source_text)) for s in segments if labels.get(s.id) == "not_recipe"}
    if title_is_label:  # "ארוחת בוקר של שישי:" alone is a framing, not the dish: its line as written is the title
        title = title_line or ""
    else:
        title = _title(output.title, output.title_written_in_text, source_text, issues, title_line, rejected)
    issues.extend(_referenced_issues(output, source_text, segments, labels))
    servings = _servings(output.servings, labels, source_text, segments)

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
    labeled_notes: set[int] = set()  # notes that start with a label saying what they are ("אופציה טבעונית:")
    skip_through = 0  # passages up to this one were already copied into the item before them
    last_note: list | None = None  # the note that the passage before belongs to
    purpose_items: set[int] = set()  # ingredients that start with their purpose label ("להגשה: גלידה")
    joined: int | None = None  # a passage already copied as the rest of the item before it
    unlabeled: list[int] = []
    current: list | None = None  # [first, last]: the item that a "continues" passage extends
    previous: str | None = None  # the role of the passage before
    # Lines that hold the recipe's own ingredient list, for telling a list inside an introduction apart.
    ingredient_lines = {s.line for s in segments if labels.get(s.id) in ("ingredient", "ingredient_heading")}
    for segment in segments:
        if segment.id == joined or segment.id <= skip_through:
            continue
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
        if role in ("ingredient", "step") and _in_rejected_list(source_text, segments, labels, segment, ingredient_lines):
            role = "not_recipe"  # "...the secret is simple: salt, garlic": the introduction's words, not its list
        if role in ("tip", "info", "step") and _is_social(source_text, segments, segment, role):
            role = "not_recipe"  # "תהנו ❤️": a sign-off, not a note
        if segment.id == title_passage or role in ("title", "not_recipe") or _PROMO_ONLY.fullmatch(segment.text(source_text)):
            previous = "not_recipe"
            continue
        list_started = any(group["items"] for group in ingredient_groups)
        introduces = _introduction(source_text, segments, labels, segment, role, list_started)
        if introduces is not None:
            # "אז מה צריך לכל הטוב הזה?" before the ingredients: it starts that list, and its words stay in
            # the original only (not a step, an ingredient or a note)
            groups = ingredient_groups if introduces == "ingredient" else step_groups
            if not groups or groups[-1]["items"]:
                groups.append({"heading": None, "items": []})
            previous, last_note = f"{introduces}_heading", None
            continue
        if role in ("ingredient_heading", "step_heading") and _is_sentence(source_text, segment):
            # A sentence is never a heading: what it heads says what it is. Before ingredients, an
            # ingredient written as a sentence; otherwise an instruction ("מחממים תנור מראש." is a step).
            heads = _next_section(segments, labels, segment)
            role = "ingredient" if heads == "ingredient" or (heads is None and role == "ingredient_heading") else "step"
        in_list = bool(ingredient_groups) and not step_groups  # after the list started, before the steps
        rest = _rest_of_line(source_text, segments, segment)
        if (
            rest is not None
            and labels.get(rest.id) not in (None, "title", "not_recipe")
            and _TIME_LABEL.search(segment.text(source_text))
            and _TIME.match(rest.text(source_text).strip())
        ):
            # "זמן הכנה: 25 דקות": a time for the whole recipe, whatever the labels say (not a step heading)
            current = [segment.id, rest.id]
            notes.append(current)
            info_starts.add(segment.id)
            joined, previous, last_note = rest.id, "info", current
            continue
        line_rest = _rest_of_its_line(source_text, segments, labels, segment) if role == "tip" and not in_list else []
        for piece in line_rest:
            labels[piece.id] = "tip"  # a tip label's line is the tip, whatever its pieces were labeled
        if line_rest and not _GENERIC_NOTE_LABEL.match(segment.text(source_text)):
            # "*אופציה טבעונית: כף פשתן טחון+3 כפות מים=לערבב... זה תחליף לביצה": the label says what the whole
            # line is, so it is one note with its label (an alternative, not one more ingredient). After a
            # plain "טיפ:" each sentence stays a note of its own.
            current = [segment.id, line_rest[-1].id]
            notes.append(current)
            labeled_notes.add(segment.id)
            skip_through, previous, last_note = line_rest[-1].id, role, current
            continue
        if (
            rest is not None
            and labels.get(rest.id) not in (None, "title", "not_recipe")
            and not step_groups
            and (in_list or role == "ingredient_heading")
            and _PURPOSE_LABEL.match(segment.text(source_text))
        ):
            # "להגשה: גלידת וניל", "To garnish: fresh basil": one line, one ingredient, its purpose kept
            if not ingredient_groups:
                ingredient_groups.append({"heading": None, "items": []})
            current = [segment.id, rest.id]
            ingredient_groups[-1]["items"].append(current)
            purpose_items.add(segment.id)
            joined, previous, last_note = rest.id, "ingredient", None
            continue
        if role in ("tip", "info") and in_list:
            text = segment.text(source_text)
            after_heading = previous == "ingredient_heading" and segments[segment.id - 2].line == segment.line
            heading = ingredient_groups[-1]["heading"]
            for_purpose = heading is not None and bool(_PURPOSE_LABEL.match(segments[heading - 1].text(source_text)))
            short = len(text.split()) <= 8 and not re.search(r"[.!?]", text)  # not a sentence
            if ends_with_colon(source_text, segment) and _PURPOSE_LABEL.match(text):
                role = "ingredient_heading"  # "להגשה:" before its ingredients
            elif role == "tip" and (after_heading or short and (for_purpose or _PURPOSE_LINE.match(text))):
                role = "ingredient"  # "לציפוי - מלח מאלדון", or under "להגשה:": an ingredient, as written
        if role == "tip" and in_list:
            issues.append(_tip_in_ingredient_list(segment.text(source_text)))
        if ends_with_colon(source_text, segment):  # a label: a heading, whatever the answer says
            role = {"ingredient": "ingredient_heading", "step": "step_heading"}.get(role, role)
        if role in ("ingredient_heading", "step_heading"):
            role = _heading_of_what_follows(role, segments, labels, segment)  # "הגרסה שלי:" before ingredients
        if role == "ingredient_heading":
            ingredient_groups.append({"heading": segment.id, "items": []})
        elif role == "step_heading":
            step_groups.append({"heading": segment.id, "items": []})
        elif role in ("ingredient", "step"):
            groups = ingredient_groups if role == "ingredient" else step_groups
            if not groups:
                groups.append({"heading": None, "items": []})
            before = groups[-1]["items"][-1] if role == "ingredient" and previous == "ingredient" and groups[-1]["items"] else None
            next_line = before is not None and before[1] == segment.id - 1 and segment.line == segments[before[1] - 1].line + 1
            line_before = passage_text(source_text, segments, before[0], before[1]) if next_line else ""
            if next_line and _wrapped(line_before, segment.text(source_text)):
                before[1] = segment.id  # one ingredient that the screen (or the text) broke over two lines
                current = before
            else:
                current = [segment.id, segment.id]
                groups[-1]["items"].append(current)
                if next_line and _maybe_continues(segment.text(source_text)):
                    issues.append(_maybe_continued(line_before, segment.text(source_text)))
        elif role in ("tip", "info"):  # a note
            if last_note is not None and last_note[1] == segment.id - 1 and _note_goes_on(source_text, segments, segment):
                last_note[1] = segment.id  # "זמן הכנה:" and "50 דקות", or a tip that goes on to the next line
                current = last_note
                if role == "info":
                    info_starts.add(last_note[0])  # the label says what the time or yield is for
            else:
                current = [segment.id, segment.id]
                notes.append(current)
                if role == "info":
                    info_starts.add(segment.id)
        last_note = current if role in ("tip", "info") else None
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
            text = _line(_without_final_period(text_of(first, last, keep_labels=first in purpose_items)))
            if text:
                ingredients.append({"text": text, "quantity": find_quantity(text)})
                if quantity_unclear(text):
                    issues.append(_unclear_amount(text))
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
        text = _line(text_of(first, last, keep_labels=first in info_starts or first in labeled_notes))
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


def _introduction(
    source_text: str, segments: list[Segment], labels: dict[int, str], segment: Segment, role: str | None,
    list_started: bool,
) -> str | None:
    """The list this passage only introduces ("ingredient" or "step"), or None. An introduction says what
    comes next instead of being part of it:
    - a question alone on its line, right before the ingredients ("אז מה צריך לכל הטוב הזה?", "What do you
      need?"), or labeled a heading before either list ("איך מכינים?");
    - a sentence labeled a heading before the ingredient list has started, with no amount in it ("הנה
      מה שצריך."): not an ingredient.
    A question before a step can be part of it ("רוצים פריך יותר?" then "אופים עוד 5 דקות"), so a
    question labeled a step or a tip introduces only an ingredient list."""
    if role in (None, "title", "not_recipe", "continues", "ingredient") or ends_with_colon(source_text, segment):
        return None
    heads = _next_section(segments, labels, segment)
    if heads is None:
        return None
    text = _without_end_decoration(segment.text(source_text)).rstrip()
    heading = role in ("ingredient_heading", "step_heading")
    if text.endswith("?") and _alone_on_line(segments, segment):
        return heads if heading or heads == "ingredient" else None
    if heading and heads == "ingredient" and not list_started and _is_sentence(source_text, segment) and find_quantity(text) is None:
        return "ingredient"
    return None


def _next_section(segments: list[Segment], labels: dict[int, str], segment: Segment) -> str | None:
    """The list that starts right after this passage, on a later line ("ingredient" or "step"); None
    when its own line goes on, or a note or nothing comes next."""
    for after in segments[segment.id :]:
        label = labels.get(after.id)
        if label in (None, "not_recipe"):
            continue
        if after.line == segment.line:
            return None
        return {"ingredient": "ingredient", "ingredient_heading": "ingredient", "step": "step", "step_heading": "step"}.get(label)
    return None


def _alone_on_line(segments: list[Segment], segment: Segment) -> bool:
    before = segments[segment.id - 2] if segment.id > 1 else None
    after = segments[segment.id] if segment.id < len(segments) else None
    return all(other is None or other.line != segment.line for other in (before, after))


def _rest_of_its_line(source_text: str, segments: list[Segment], labels: dict[int, str], segment: Segment) -> list[Segment]:
    """For a label ("אופציה טבעונית:"), the passages after it on its line, up to anything that is not part
    of the recipe (hashtags, a passage the model rejected)."""
    if not ends_with_colon(source_text, segment):
        return []
    rest = []
    for after in segments[segment.id :]:
        if (
            after.line != segment.line
            or labels.get(after.id) in (None, "title", "not_recipe")
            or _PROMO_ONLY.fullmatch(after.text(source_text))
        ):
            break
        rest.append(after)
    return rest


def _is_social(source_text: str, segments: list[Segment], segment: Segment, role: str) -> bool:
    """A wish, a sign-off or a call to followers, and nothing else: short, no number, no ingredient, nothing
    about keeping, serving or swapping. A step only when it is all of its line."""
    text = segment.text(source_text)
    if role == "step" and not _alone_on_line(segments, segment):
        return False
    return (
        len(text.split()) <= 12
        and bool(_SOCIAL.search(text))
        and not re.search(r"\d", text)
        and not _NOTE_CONTENT.search(text)
        and not ingredient_words.mentions_ingredient(text)
    )


def _heading_of_what_follows(role: str, segments: list[Segment], labels: dict[int, str], segment: Segment) -> str:
    """A heading heads the section that follows it: labeled a step heading but followed by ingredients
    ("הגרסה שלי:" before the list), it is the ingredients' heading, and the other way round."""
    for after in segments[segment.id :]:
        following = labels.get(after.id)
        if following in (None, "continues", "not_recipe"):
            continue
        if role == "step_heading" and following == "ingredient":
            return "ingredient_heading"
        if role == "ingredient_heading" and following == "step":
            return "step_heading"
        return role
    return role


def _title_line_end(source_text: str, segments: list[Segment], labels: dict[int, str], number: int) -> int:
    """The last passage of the title: the labeled one, or, when it is only a label ("ארוחת בוקר של
    שישי:"), the rest of its line too, unless that is an ingredient list or a step."""
    segment = segments[number - 1]
    if not ends_with_colon(source_text, segment):
        return number
    rest = [s for s in segments[number:] if s.line == segment.line]
    if not rest or any(labels.get(s.id) in ("ingredient", "ingredient_heading", "step", "step_heading") for s in rest):
        return number
    return rest[-1].id


def _in_rejected_list(
    source_text: str, segments: list[Segment], labels: dict[int, str], segment: Segment, ingredient_lines: set[int]
) -> bool:
    """Is this an item of a list that a rejected passage introduces on the same line ("הסוד: X, Y"
    after an introduction), while the recipe's own ingredients are on other lines?"""
    before = [s for s in segments[: segment.id - 1] if s.line == segment.line]
    label = next((s for s in reversed(before) if ends_with_colon(source_text, s)), None)
    if label is None or labels.get(label.id) not in ("not_recipe", "title"):
        return False
    return bool(ingredient_lines - {segment.line})


def _is_sentence(source_text: str, segment: Segment) -> bool:
    """A passage that ends a sentence ("מחממים תנור מראש."), not a label: never a heading."""
    if ends_with_colon(source_text, segment):
        return False
    return bool(re.search(r"[.!?]\W*$", _without_end_decoration(segment.text(source_text))))


def _rest_of_line(source_text: str, segments: list[Segment], segment: Segment) -> Segment | None:
    """For a label ("להגשה:"), the one passage after it on its line, if that is all the line holds."""
    if not ends_with_colon(source_text, segment) or segment.id >= len(segments):
        return None
    rest = segments[segment.id]  # passages are numbered from 1: this is the next one
    if rest.line != segment.line or (rest.id < len(segments) and segments[rest.id].line == segment.line):
        return None
    return rest


def _note_goes_on(source_text: str, segments: list[Segment], segment: Segment) -> bool:
    """Does this passage continue the note before it? On the same line, unless a sentence ended
    between them: after a label ("זמן הכנה:" then "50 דקות"), or where a tip after "טיפ:" was cut at
    its comma like a list. On the next line, after a line that ends in the middle of a sentence."""
    before = segments[segment.id - 2]
    if before.line == segment.line:
        return not source_text[before.start:segment.start].rstrip().endswith((".", "!", "?"))
    return before.text(source_text).rstrip().endswith((",", "-", "–", "—"))


def _servings(value: str | None, labels: dict[int, str], source_text: str, segments: list[Segment]) -> str | None:
    """The servings the model gave, only with evidence: written in a passage that says it is a yield
    ("12 יחידות", "Serves 2", "מצרכים (4 מנות):") and that the model did not reject as not part of
    the recipe. Appearing somewhere in the text is not enough ("100 גרם" from an instruction in the
    text, a pan size, an ingredient line): without evidence the field stays empty."""
    wanted = normalize(_clean(value or ""))
    if not wanted:
        return None
    for segment in segments:
        text = segment.text(source_text)
        if labels.get(segment.id) not in (None, "not_recipe") and wanted in normalize(text) and _YIELD.search(text):
            return _clean(value or "")
    return None


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


# Words that only begin an ingredient's name ("גבינת" in "גבינת שמנת", "חמאת" in "חמאת בוטנים", "אגוזי" in "אגוזי
# מלך"): Hebrew's construct forms, ending in ת (not the plural ות) or in י. A line that ends with one is cut off.
# Not a unit ("גרם" in "גרם מסאלה"), not a word that is an ingredient by itself ("שמנת").
_NAME_STARTS = frozenset(
    name.split()[0]
    for name in INGREDIENT_WORDS
    if " " in name
    and name.split()[0] not in INGREDIENT_WORDS
    and not starts_with_unit(name.split()[0])
    and re.search(r"(?<!ו)ת$|י$", name.split()[0])
)
# Words that cannot end a line of an ingredient: what they join or qualify is on the next line.
_JOINING_WORDS = frozenset({"ללא", "בלי", "עם", "של", "או", "וגם", "גם", "כמו", "לפי", "בתוספת", "and", "or", "with", "of", "without", "plus"})
_LAST_NUMBER = re.compile(r"(?:^|[\s+])\d+(?:[.,/]\d+)?\s*$")
_REMARK_ONLY = re.compile(r"^\s*\([^()]*\)\s*[.,;]?\s*$")


def _wrapped(before: str, line: str) -> bool:
    """Is this line the rest of the ingredient line before it? Only on a clear sign; never by closeness alone."""
    before, line = before.rstrip(), line.strip()
    last_word = re.sub(r"[^\w'\"׳״]+$", "", before).split()[-1:] or [""]
    if _LAST_NUMBER.search(before) and starts_with_unit(line) and (starts_with_amount(before) or "+" in before.split()[-1]):
        return True  # "15 ביסקוויטים טחונים+100" / "גרם חמאה מומסת": the number's unit is on the next line
    if re.search(r"\+\s*$", before) or (re.search(r"\+\s*\S+\s*$", before) and ends_with_unit(before)):
        return True  # "כוס סוכר+כוס" / "מים"
    if _REMARK_ONLY.match(line) or before.count("(") > before.count(")"):
        return True  # "80 גרם פודינג וניל" / "(קופסה אחת)"
    if last_word[0] in _NAME_STARTS and not starts_with_amount(line):
        return True  # "1 מיכל גבינת" / "שמנת (200 גרם)"
    return last_word[0].lower() in _JOINING_WORDS  # "קוביית שוקולד מריר ללא" / "סוכר"


def _maybe_continues(line: str) -> bool:
    """One word, no amount, no known ingredient ("מופשר"): perhaps the end of the line before, perhaps not."""
    words = re.sub(r"[^\w\s'\"׳״-]", " ", line).split()
    return len(words) == 1 and find_quantity(line) is None and not mentions_ingredient(line) and not line.strip().endswith(":")


def _maybe_continued(before: str, line: str) -> schemas.Issue:
    return schemas.Issue(
        kind="unclear_text",
        message=f'ייתכן שהשורה "{_short(line)}" היא המשך של "{_short(before)}" (שורה ששבירת השורות פיצלה). השוו למקור.',
        quote=_short(line, 300),
    )


def _unclear_amount(text: str) -> schemas.Issue:
    return schemas.Issue(
        kind="unclear_text",
        message=f'לא ברור איזה מהמספרים בשורה "{_short(text)}" הוא הכמות, ולכן הכמות נשארה ריקה. השלימו מהמקור.',
        quote=_short(text, 300),
    )


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
    issues: list[schemas.Issue],
    title_line: str | None = None,
    rejected: set[str] | None = None,
) -> str:
    """The model writes the title itself (it may be composed); a title it says is written in the
    text must be found there. If it is not, but the answer labeled a passage as the title line,
    that passage's own words are the title: the label says which words are meant, so nothing is
    guessed. Decoration at its end (emoji) is left out, as at the start of lines."""
    title = _without_end_decoration(title)[:MAX_TITLE_LENGTH]
    if rejected and normalize(title) in rejected:
        title, written = title_line or "", bool(title_line)  # never a passage rejected as not part of the recipe
    if written and title and _starts_a_line(title, source_text):
        return title
    if written and title_line:
        return title_line
    if not title:
        title = first_line(source_text)
    # No title line holds it, so it is composed, whatever the answer says ("written" composed titles
    # were measured): the point says whether its words come from the text.
    issues.append(_missing_title(title, from_text=_words_in_text(title, source_text)))
    return title


def _words_in_text(title: str, source_text: str) -> bool:
    """Is every word of the title written somewhere in the text (a title composed from the text's own
    words, as the model was asked), even if not in that order?"""
    text = normalize(source_text).lower()
    words = [w for w in re.findall(r"\w+", normalize(title).lower()) if len(w) > 1]
    return bool(words) and all(w in text for w in words)


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


def _only_in_step_point(words: str, step: str) -> schemas.Issue:
    return schemas.Issue(
        kind="ingredient_only_in_steps",
        message=f'המצרך "{words}" מופיע באופן ההכנה אבל לא ברשימת המצרכים. ייתכן שהמתכון המקורי לא מפרט אותו; '
        "הוא לא נוסף לרשימה ולא נקבעה לו כמות. הוסיפו אותו אם צריך.",
        quote=_short(step, 300),
    )


def _only_in_steps(
    output: ReferenceOutput, source_text: str, segments: list[Segment], steps: list[str], lines: list[str]
) -> list[schemas.Issue]:
    """Ingredients that a step uses and no ingredient line has: a recipe whose source leaves one out of
    its list ("מקשטים בתותים", no strawberries listed) is kept as written, with this review point.
    Found by the notebook itself (common ingredient words, app/extraction/ingredient_words.py), and
    from the model's claims, each shown only if that step writes those words and no ingredient line
    has them (in any of their usual forms: "התותים", "בתותים", "תות"). One point per ingredient."""
    listed = normalize(" | ".join(lines)).lower()
    found = ingredient_words.only_in_steps(lines, steps)
    issues = [_only_in_step_point(words, step) for words, step in found]
    shown = normalize(" | ".join(words for words, _ in found)).lower()
    for item in output.only_in_steps[:MAX_MODEL_ISSUES]:
        words = _clean(item.words)
        if not words or len(words.split()) > 4 or not 1 <= item.passage <= len(segments):
            continue
        passage = passage_text(source_text, segments, item.passage, item.passage)
        if normalize(words).lower() not in normalize(passage).lower():
            continue  # not what that passage writes
        if not any(normalize(passage) in normalize(step) for step in steps):
            continue  # not a step
        if _listed(words, listed) or shown and _listed(words, shown):
            continue  # in the list, or already pointed out
        issues.append(_only_in_step_point(words, passage))
        shown = f"{shown} | {normalize(words).lower()}"
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


def content_points(lines: list[str], steps: list[str], source_text: str) -> list[schemas.Issue]:
    """The checks that need no model, for a draft built without one (a page's own recipe data):
    ingredients only the steps mention, and what baking needs that the text does not give."""
    return [_only_in_step_point(words, step) for words, step in ingredient_words.only_in_steps(lines, steps)] + _missing_information(
        source_text, steps
    )


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
