"""Ingredient lines that the app derives from the preparation, by a fixed rule, never by a model.

So far one kind: the oil a step clearly uses for frying or greasing when the ingredient list has none
for it ("מחממים מעט שמן במחבת" -> "מעט שמן לטיגון"; "משמנים את התבנית בשמן" -> "שמן לשימון התבנית").
Such a line is the app's wording, built only from the step's own words (its amount "מעט" or "קצת" if it
has one, the oil it names, what it is for) and it says so: Ingredient.derived_from holds the sentence it
comes from. It is not presented as a line of the source's list, and the original text is not changed.
It replaces the review point "המצרך שמן מופיע באופן ההכנה..." for that use, because nothing is left to
check. Oil that a step uses in any other way keeps the point: measured ("חצי כוס שמן"), optional
("אפשר לשמן"), or going into a batter, a dough, a sauce, a marinade or another component ("לבלילה").
A step that cooks without oil ("מטגנים ללא שמן") neither adds oil nor raises the point; frying with no
oil named adds nothing.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from app import schemas

LABEL_WORDS = ("שמן",)  # the review points about these words are this rule's to keep or replace

# "שמן" as a noun, with the prefix letters it takes ("בשמן", "והשמן"); not "לשמן" (to grease) or "שמנת".
_OIL = re.compile(r"(?<!\w)(?P<prefix>[ובהמכש]{0,3})שמן(?P<kind>\s+(?:זית|קנולה|קוקוס|צמחי|חמניות|חמנייה|שומשום|אבוקדו|תירס|בוטנים))?(?P<deep>\s+עמוק)?(?!\w)")
_AMOUNT = re.compile(r"(?:^|\s)[ובה]{0,2}(?P<amount>מעט|קצת)\s+$")  # "מעט שמן", "במעט שמן", "עם קצת שמן"
_MEASURED = re.compile(r"(?:\d|חצי|רבע|שליש|כף|כפות|כפית|כפיות|כוס|כוסות|ספל|מ\"ל|מ״ל|מל|ליטר|גרם)\S*\s+(?:של\s+)?$")
_NEGATED = re.compile(r"(?:ללא|בלי|בלא|אין\s+צורך|לא\s+צריך|לא\s+מוסיפים|לא\s+משתמשים)(?:\s+\S+){0,2}\s*$")
_OPTIONAL = re.compile(r"(?<!\w)(?:אפשר|ניתן|אם\s+רוצים|לפי\s+הטעם|לא\s+חובה|רשות|אופציונלי|אופציונאלי|במידת\s+הצורך|במידה\s+ו|אם\s+צריך)(?!\w)")
# A listed oil line, or its group, that names another component ("שמן זית לרוטב", "לבצק"): not the pan's oil.
_COMPONENT = re.compile(
    r"(?<!\w)[ולבהמש]{0,3}(?:בלילה|בצק|עיסה|רוטב|רטבים|מרינדה|תערובת|קרם|ויניגרט|סלט|פסטו|מטבל|ממרח|תבלינים|ציפוי)(?!\w)"
)
# Oil that goes into a component ("לבלילה", "לרוטב", "לתוך הבלילה"): part of the recipe, not the pan's.
_INTO = re.compile(
    r"(?<!\w)(?:ו?ל|(?:אל|לתוך)\s+ה?)(?:בלילה|בצק|עיסה|רוטב|מרינדה|תערובת|קרם|ויניגרט|סלט|פסטו|מטבל|ממרח|ציפוי)(?!\w)"
)
_FRYING = re.compile(r"(?<!\w)ו?(?:מטגנים|מטגנות|מטגן|מטגנת|לטגן|טגנו|תטגנו|מקפיצים|מקפיץ|להקפיץ|הקפיצו|מזהיבים|להזהיב|הזהיבו)(?!\w)")
_HEATING = re.compile(r"(?<!\w)ו?(?:מחממים|מחמם|מחממת|לחמם|חממו|תחממו)(?!\w)")
_PAN = re.compile(r"(?<!\w)[ובה]{0,3}(?:מחבת|סיר|ווק|קדרה)(?!\w)")
_GREASING = re.compile(r"(?<!\w)ו?(?:משמנים|משמן|משמנת|לשמן|שמנו|תשמנו|מרססים|לרסס|ריססו|מברישים|להבריש)(?!\w)")
_GREASED = re.compile(r"(?<!\w)(?:את\s+)?[ובה]{0,2}(?P<object>תבנית|תבניות|מחבת|מגש|מגשים|שקעים|צלחת|כלי)(?!\w)")
_SENTENCE = re.compile(r"[^.;!?\n]+[.;!?]?")
_GENERIC_GROUP = {"מצרכים", "המצרכים", "רכיבים", "מרכיבים", "ingredients"}
_PURPOSE = {"frying": re.compile(r"טיגון|לטגן"), "greasing": re.compile(r"שימון|לשמן|משמן|תבנית|ספריי")}


@dataclass
class OilUse:
    purpose: str  # "frying", "greasing" (clear: a line can be derived) or "other" (the review point stays)
    line: str | None  # the derived line, for a clear use
    amount: str | None
    sentence: str  # the step's sentence, as written
    step: str


def oil_uses(steps: list[str]) -> list[OilUse]:
    """Every mention of oil in the steps, in order, with what it is used for; mentions of cooking without
    oil are left out."""
    uses = []
    for step in steps:
        for sentence in (s.strip() for s in _SENTENCE.findall(step)):
            for match in _OIL.finditer(sentence):
                before = sentence[: match.start()]
                if _NEGATED.search(before + match.group("prefix")):
                    continue
                uses.append(_use(sentence, step, match, before))
    return uses


def _use(sentence: str, step: str, match: re.Match, before: str) -> OilUse:
    def other() -> OilUse:
        return OilUse("other", None, None, sentence, step)

    if _OPTIONAL.search(sentence) or _MEASURED.search(before) or _INTO.search(sentence):
        return other()
    amount_match = _AMOUNT.search(before) if not match.group("prefix") else None  # "במעט שמן": the ב is the amount's
    amount = amount_match.group("amount") if amount_match else None
    oil = "שמן" + (match.group("kind") or "")
    words = f"{amount} {oil}" if amount else oil
    greased = _GREASED.search(sentence)
    if _GREASING.search(sentence) and greased:
        return OilUse("greasing", f"{words} לשימון ה{greased.group('object')}", amount, sentence, step)
    if _FRYING.search(sentence) or (_HEATING.search(sentence) and _PAN.search(sentence)):
        return OilUse("frying", f"{words} לטיגון{' עמוק' if match.group('deep') else ''}", amount, sentence, step)
    return other()


def _oil_listed(groups: list[schemas.IngredientGroup], purpose: str) -> tuple[bool, bool]:
    """(the list has any oil, the list has oil that may be the oil for this purpose). Oil in the main
    list, unnamed or generic, may be; oil that a named group or the line itself gives to another
    component is not assumed to be."""
    any_oil = covers = False
    for group in groups:
        for item in group.ingredients:
            if not (_OIL.search(item.text) or "קנולה" in item.text):
                continue
            any_oil = True
            general = group.name is None or group.name.strip(" :") in _GENERIC_GROUP
            named_for = f"{group.name or ''} {item.text}"
            if (general and not _COMPONENT.search(item.text)) or _PURPOSE[purpose].search(named_for):
                covers = True
    return any_oil, covers


def _about_oil(issue: schemas.Issue) -> bool:
    if issue.kind != "ingredient_only_in_steps":
        return False
    named = re.findall(r'"([^"]+)"', issue.message)
    return bool(named) and any(word in named[0] for word in LABEL_WORDS)


def add_oil_from_steps(draft: schemas.RecipeInput, point: Callable[[str, str], schemas.Issue]) -> schemas.RecipeInput:
    """The draft with a derived oil line for each clear frying or greasing use that its list has no oil
    for, and the review point about oil (made by `point(words, step)`, the import's own) only where a
    use is not clear and the list has no oil at all. Applying it again changes nothing."""
    steps = [step for group in draft.step_groups for step in group.steps]
    uses = oil_uses(steps)
    if not uses and not any(_about_oil(issue) for issue in draft.issues):
        return draft
    any_oil = _oil_listed(draft.ingredient_groups, "frying")[0]
    derived: list[schemas.Ingredient] = []
    seen: set[str] = set()
    for use in uses:
        if use.purpose == "other" or use.purpose in seen or _oil_listed(draft.ingredient_groups, use.purpose)[1]:
            continue
        seen.add(use.purpose)
        derived.append(schemas.Ingredient(text=use.line, quantity=use.amount, derived_from=use.sentence[:500]))
    issues = [issue for issue in draft.issues if not _about_oil(issue)]
    unclear = next((use for use in uses if use.purpose == "other"), None)
    if unclear is not None and not any_oil:
        written = _OIL.search(unclear.sentence)
        issues.append(point(written.group(0)[len(written.group("prefix")) :].strip(), unclear.step))
    groups = list(draft.ingredient_groups)
    if derived:
        if len(groups) == 1 and groups[0].name is None:
            groups = [groups[0].model_copy(update={"ingredients": [*groups[0].ingredients, *derived]})]
        else:
            groups.append(schemas.IngredientGroup(name=None, ingredients=derived))
    return draft.model_copy(update={"ingredient_groups": groups, "issues": issues})

