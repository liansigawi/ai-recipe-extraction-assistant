"""Comparing an extraction's draft with a case's expectations, written by hand. Pure functions:
tested offline in tests/test_eval_checks.py, so the evaluation's own logic is checked without a model.

A case's expectations, in <case>.json next to the text in <case>.txt. Every string is compared
after normalizing only spacing, Unicode form and invisible marks (review.normalize):

    "is_recipe": false                        the text is not a recipe: expect not_a_recipe
    "title": "...", "title_acceptable": [..]   the title, or one of these
    "title_composed": true                    the text has no title: any title, with a warning
    "category": "קינוחים" or null, or "category_one_of": ["ארוחות קלילות", null]
    "ingredient_groups": [{"name": "לבצק" | null | ["...", null], "items": [["2 כוסות קמח", "2 כוסות"], ["מלח", null]]}]
                                              EVERY ingredient line, in order, in its group, with its
                                              quantity (docs/quantity-conventions.md); null: none
    "preparation": ["..."]                    every preparation sentence: must be in the steps
    "tips": ["..."]                           every tip: in the notes or the steps
    "step_groups": ["בסיר לחץ"]               these step groups must exist
    "facts": ["Ready in 10 minutes"]          must be kept somewhere in the recipe
    "yield": {"text": "12 יחידות", "number": "12"}   in the servings, or the text anywhere in the recipe
    "excluded": ["..."]                       not recipe content: in no title, ingredient, step, note or heading
    "never_suggested": ["Snacks"]             nowhere at all, review points included (no new categories)
    "warnings": ["ingredient_only_in_steps"]  review points the app must show

Each check that fails is a Finding. Several checks can find the same underlying problem (an
introduction kept in a note contains two excluded phrases), so every finding names its problem,
and the report counts problems and failed checks separately. `checked` counts the checks per
area, so a report can say what was covered and what was not.
"""

from dataclasses import dataclass, field
from typing import Any

from app import schemas
from app.extraction.review import FIXED_MESSAGES, PROMOTION_FLAG, TIP_IN_LIST_FLAG, normalize

KNOWN_EXPECTATIONS = {
    "is_recipe", "title", "title_acceptable", "title_composed", "category", "category_one_of",
    "ingredient_groups", "preparation", "tips", "step_groups", "facts", "yield", "excluded",
    "never_suggested", "warnings",
}

# The areas a case can check, in report order.
AREAS = [
    "wording", "ingredient lines", "quantities", "groups", "preparation", "tips", "facts",
    "not recipe content", "title", "category", "warnings",
]
# Safe outcomes: worth a look, but the draft is not wrong (the person classifies; a review point is missing).
MINOR = {"category_unresolved", "missing_warning"}
# The app's own review points that point at real problems (not remarks the model made up).
PROBLEM_FLAGS = {"not_found_in_source", "quantity_not_in_line", "invalid_reference", "not_extracted"}


@dataclass(frozen=True)
class Finding:
    kind: str
    area: str
    message: str
    problem: str  # the underlying problem; several findings can share one
    flagged_by_app: bool = False  # the draft has a review point about it

    @property
    def minor(self) -> bool:
        return self.kind in MINOR


@dataclass
class Result:
    findings: list[Finding] = field(default_factory=list)
    checked: dict[str, int] = field(default_factory=dict)  # area -> checks made

    def count(self, area: str, number: int = 1) -> None:
        self.checked[area] = self.checked.get(area, 0) + number

    @property
    def problems(self) -> list[str]:
        """Each underlying problem once, in the order found."""
        return list(dict.fromkeys(f.problem for f in self.findings))

    @property
    def all_passed(self) -> bool:
        return not any(not f.minor for f in self.findings)


def check(
    expect: dict[str, Any],
    *,
    draft: schemas.RecipeInput | None,
    error_code: str | None,
    categories: list[schemas.Category],
    source: str,
) -> Result:
    result = Result()
    if not expect.get("is_recipe", True):
        result.count("category")
        if error_code != "not_a_recipe":
            result.findings.append(
                Finding("not_a_recipe_missed", "category", f"expected 'not a recipe', got {error_code or 'a draft'}", "not a recipe")
            )
        return result
    if error_code is not None or draft is None:
        result.findings.append(Finding("failed", "wording", f"the extraction failed: {error_code}", "failed"))
        return result

    original = normalize(source)
    lines = [(g.name, item.text, item.quantity) for g in draft.ingredient_groups for item in g.ingredients]
    steps = [step for g in draft.step_groups for step in g.steps]
    headings = [g.name for g in draft.ingredient_groups if g.name] + [g.name for g in draft.step_groups if g.name]
    found: list[Finding] = []

    def fail(kind: str, area: str, message: str, problem: str, *about: str) -> None:
        found.append(Finding(kind, area, message, problem, _flagged(kind, about, draft)))

    # Wording: every piece of the draft that is copied must be in the original as written.
    copied = [("ingredient", t) for _, t, _ in lines] + [("step", s) for s in steps] + [("note", n) for n in draft.notes]
    copied += [("group name", h) for h in headings]
    if not expect.get("title_composed"):
        copied.append(("title", draft.title))
    result.count("wording", len(copied))
    altered = [text for _, text in copied if normalize(text) not in original]
    for what, text in copied:
        if text in altered:
            fail("altered", "wording", f'{what} not in the original as written: "{text}"', f"wording:{text}", text)

    _check_ingredients(expect, lines, steps, draft.notes, result, fail)
    _check_text(expect, steps, draft, headings, result, fail)

    # Not recipe content: one problem per draft element that holds it, however many phrases match.
    elements = [draft.title, *(t for _, t, _ in lines), *steps, *draft.notes, *headings, draft.servings or ""]
    for piece in expect.get("excluded", []):
        result.count("not recipe content")
        for element in elements:
            if normalize(piece) and normalize(piece) in normalize(element):
                fail("not_recipe_kept", "not recipe content", f'"{piece}" kept in the recipe, in "{element}"', f"kept:{element}", element)
    everything = " | ".join([*elements, *(i.message for i in draft.issues), *(i.quote or "" for i in draft.issues)])
    for piece in expect.get("never_suggested", []):
        result.count("category")
        if normalize(piece).lower() in normalize(everything).lower():
            fail("suggested_category", "category", f'"{piece}" appears in the draft', f"suggested:{piece}")

    # Title.
    if "title" in expect:
        result.count("title")
        acceptable = [expect["title"], *expect.get("title_acceptable", [])]
        if not any(normalize(draft.title) == normalize(t) for t in acceptable):
            fail("title", "title", f'title "{draft.title}", expected "{expect["title"]}"', "title", draft.title)

    # Category.
    allowed = [expect["category"]] if "category" in expect else expect.get("category_one_of")
    if allowed is not None:
        result.count("category")
        names = {c.id: c.name for c in categories}
        actual = names.get(draft.category_id) if draft.category_id is not None else None
        if actual not in allowed:
            if actual is None:
                fail("category_unresolved", "category", f"left unclassified; a fitting category: {allowed}", "category")
            else:
                fail("category_wrong", "category", f"category {actual!r}, expected {allowed}", "category")

    # Review points the app must show.
    kinds = {issue.kind for issue in draft.issues}
    for kind in expect.get("warnings", []):
        result.count("warnings")
        if kind not in kinds:
            # A category chosen where none fits also hides the "unresolved" point: one problem, not two.
            problem = "category" if kind == "classification_unresolved" else f"warning:{kind}"
            fail("missing_warning", "warnings", f"expected a '{kind}' review point", problem)

    result.findings = found
    return result


def _check_ingredients(expect, lines, steps, notes, result: Result, fail) -> None:
    groups = expect.get("ingredient_groups")
    if groups is None:
        return
    expected = [(g.get("name"), text, quantity) for g in groups for text, quantity in g["items"]]
    drafted = [normalize(t) for _, t, _ in lines]
    elsewhere = normalize(" | ".join([*steps, *notes]))
    result.count("ingredient lines", len(expected))
    positions: list[int] = []
    for name, text, quantity in expected:
        if normalize(text) in drafted:
            index = drafted.index(normalize(text))
            positions.append(index)
            result.count("quantities")
            got = lines[index][2]
            if (got or None) != quantity:
                fail(
                    "wrong_quantity", "quantities", f'"{text}": quantity {got!r}, expected {quantity!r}', f"quantity:{text}", text
                )
        elif normalize(text) in elsewhere:
            fail("misplaced_ingredient", "ingredient lines", f'ingredient kept as a step or note: "{text}"', f"ingredient:{text}", text)
        else:
            fail("missing_ingredient", "ingredient lines", f'ingredient line missing: "{text}"', f"ingredient:{text}", text)
    wanted = {normalize(text) for _, text, _ in expected}
    for _, text, _ in lines:
        if normalize(text) not in wanted:
            result.count("ingredient lines")
            fail("extra_ingredient", "ingredient lines", f'not an expected ingredient line: "{text}"', f"extra:{text}", text)
    if positions != sorted(positions):
        result.count("ingredient lines")
        fail("order", "ingredient lines", "ingredient lines are not in the text's order", "order:ingredients")

    # Groups: each expected group's lines in one draft group, with an acceptable name, groups not merged.
    by_line = {normalize(t): name for name, t, _ in lines}
    used: dict[str | None, str] = {}
    for group in groups:
        names = [by_line[normalize(t)] for t, _ in group["items"] if normalize(t) in by_line]
        if not names:
            continue
        result.count("groups")
        acceptable = group.get("name")
        acceptable = acceptable if isinstance(acceptable, list) else [acceptable]
        label = acceptable[0] or "(no name)"
        if len(set(names)) > 1:
            fail("group", "groups", f'the lines of group "{label}" are split across groups {sorted(set(map(str, names)))}', f"group:{label}")
        elif not any((names[0] or None) == a or (names[0] and a and normalize(names[0]) == normalize(a)) for a in acceptable):
            fail("group", "groups", f'group named {names[0]!r}, expected {acceptable}', f"group:{label}")
        elif names[0] in used and used[names[0]] != label:
            fail("group", "groups", f'groups "{used[names[0]]}" and "{label}" were merged', f"group:{label}")
        used.setdefault(names[0], label)


def _check_text(expect, steps, draft, headings, result: Result, fail) -> None:
    step_text = normalize(" | ".join(steps))
    note_text = normalize(" | ".join(draft.notes))
    ingredient_text = normalize(" | ".join(i.text for g in draft.ingredient_groups for i in g.ingredients))
    all_text = normalize(" | ".join([draft.title, draft.servings or "", *headings, *steps, *draft.notes]))

    positions = []
    for piece in expect.get("preparation", []):
        result.count("preparation")
        target = normalize(piece)
        if target in step_text:
            positions.append(step_text.find(target))
        elif target in note_text or target in ingredient_text:
            fail("misplaced_step", "preparation", f'preparation kept as a note or ingredient: "{piece}"', f"preparation:{piece}", piece)
        else:
            fail("missing_step", "preparation", f'preparation missing: "{piece}"', f"preparation:{piece}", piece)
    if positions != sorted(positions):
        result.count("preparation")
        fail("order", "preparation", "the steps are not in the text's order", "order:steps")

    for piece in expect.get("tips", []):
        result.count("tips")
        target = normalize(piece)
        if target in step_text or target in note_text:
            continue
        if target in ingredient_text:
            fail("misplaced_tip", "tips", f'tip kept as an ingredient: "{piece}"', f"tip:{piece}", piece)
        else:
            fail("missing_tip", "tips", f'tip missing: "{piece}"', f"tip:{piece}", piece)

    step_groups = [normalize(g.name) for g in draft.step_groups if g.name]
    for name in expect.get("step_groups", []):
        result.count("groups")
        if normalize(name) not in step_groups:
            fail("group", "groups", f'no step group named "{name}"', f"step group:{name}")

    for piece in expect.get("facts", []):
        result.count("facts")
        if normalize(piece) not in all_text:
            fail("missing_fact", "facts", f'not kept anywhere in the recipe: "{piece}"', f"fact:{piece}", piece)
    if "yield" in expect:
        result.count("facts")
        wanted = expect["yield"]
        in_servings = draft.servings is not None and wanted["number"] in draft.servings
        if not in_servings and normalize(wanted["text"]) not in all_text:
            fail("missing_fact", "facts", f'the yield "{wanted["text"]}" is neither in the servings nor kept anywhere', "fact:yield")


def _flagged(kind: str, about: tuple[str, ...], draft: schemas.RecipeInput) -> bool:
    """Did the app show the person a review point about this problem?"""
    if kind == "category_unresolved":
        return any(issue.kind == "classification_unresolved" for issue in draft.issues)
    if kind == "title":
        return any(issue.kind in ("missing_title", "not_found_in_source") for issue in draft.issues)
    if kind in ("category_wrong", "missing_warning", "suggested_category", "order", "group") or not about:
        return False
    targets = [normalize(text) for text in about if text]
    for issue in draft.issues:
        said = normalize(f"{issue.message} {issue.quote or ''}")
        if any(t and (t in said or (issue.quote and normalize(issue.quote) in t)) for t in targets):
            return True
    return False


@dataclass
class Warnings:
    necessary: list[str] = field(default_factory=list)
    unnecessary: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)  # shown more than once (also counted above)


def review_warnings(expect: dict[str, Any], draft: schemas.RecipeInput | None) -> Warnings:
    """The draft's review points, sorted by what the case says.

    Necessary: the points the case expects, points about real problems (wording not in the
    original, an unusable quantity, an invalid reference, a line flagged as promotion, recipe
    text left out), a composed title, an unresolved category where none fits. Unnecessary:
    everything else, such as model remarks the case does not call for, or "not placed" points
    about text that is not part of the recipe. A point shown twice is also a duplicate.
    """
    warnings = Warnings()
    if draft is None:
        return warnings
    expected = set(expect.get("warnings", []))
    allowed = [expect["category"]] if "category" in expect else expect.get("category_one_of", ["-"])
    recipe = [t for g in expect.get("ingredient_groups", []) for t, _ in g["items"]]
    recipe += [*expect.get("preparation", []), *expect.get("tips", []), *expect.get("facts", [])]
    seen: set[tuple[str, str]] = set()
    for issue in draft.issues:
        label = f"{issue.kind}: {issue.message[:100]}"
        # A fixed message is about the passage it quotes: the same message on another passage is
        # another point. A model's own message is a claim: shown twice, it is a duplicate.
        fixed = issue.message in FIXED_MESSAGES or TIP_IN_LIST_FLAG in issue.message
        key = (issue.kind, normalize(issue.message), normalize(issue.quote or "") if fixed else "")
        if key in seen:
            warnings.duplicates.append(label)
        seen.add(key)
        quote = normalize(issue.quote or "")
        if issue.kind in expected or issue.kind in PROBLEM_FLAGS:
            necessary = True
        elif issue.kind == "other" and TIP_IN_LIST_FLAG in issue.message:  # "this tip may be an ingredient"
            necessary = any(quote and quote == normalize(t) for g in expect.get("ingredient_groups", []) for t, _ in g["items"])
        elif issue.kind == "other":
            necessary = PROMOTION_FLAG in issue.message
        elif issue.kind == "missing_title":
            necessary = bool(expect.get("title_composed"))
        elif issue.kind == "classification_unresolved":
            necessary = None in allowed
        elif issue.kind == "unused_text":
            necessary = any(quote and (quote in normalize(p) or normalize(p) in quote) for p in recipe)
        else:
            necessary = False
        (warnings.necessary if necessary else warnings.unnecessary).append(label)
    return warnings
