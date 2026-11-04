"""Bring saved recipes up to the importer's current rules: a report first, nothing changed until you approve
(docs/maintenance.md). From the project root:

    .\\maintain-recipes.cmd audit                                   read-only: proposals, a report, snapshots
    .\\maintain-recipes.cmd apply <batch folder> [--exclude ID ...] [--only ID ...] --yes
    .\\maintain-recipes.cmd undo <batch folder> --yes
    .\\maintain-recipes.cmd propose-from-page <recipe id> <page address> [--reviewed FILE]   read-only

The audit opens the notebook read-only and proposes, per recipe, separate changes with their own ids:
- "<id>-steps", "<id>-ingredients": for a recipe imported from a page's recipe data (JSON-LD or microdata),
  what the importer makes today of the recipe data saved with the import (app/importers/website.py), checked
  against the page's own lists. The page is read again only for that check (the saved data does not hold the
  page's lists), and any difference between the saved data and the page as it is now is reported.
- "<id>-oil": the line that the oil rule (app/extraction/derived.py) adds to a new import with these steps.
- "<id>-type": for a dessert without a type, the type the local classifier chooses in two requests that agree;
  otherwise none (unresolved). The main category and the healthy style are never changed.
propose-from-page makes a batch for one recipe from a page that holds its recipe: "<id>-ingredients", "-steps"
and "-notes" as the website importer reads them from the page (on a temporary copy of the notebook), or a reviewed
version of that draft holding only the page's own lines; "<id>-source" adds the page after the sources it has.

Applying a batch: a verified backup of the notebook first; then each recipe is changed in place, only in the
fields of its approved changes, and only if its content is still what the report saw, or that plus changes of
this batch already applied (else it is skipped and named: your newer work wins). A change already applied is
not applied again. Its id, status, media and cover, credits, cooked mark and imported original are never touched;
a source is only ever added, after the ones it has. Undo puts back what the batch wrote, only where it still
holds what the batch wrote.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import itertools
import json
import sqlite3
import sys
import tempfile
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.config import load_settings
from app.db import make_engine, utc_now
from app.errors import ApiError
from app.extraction.derived import add_oil_from_steps
from app.extraction.output import Classification
from app.extraction.review import only_in_step_point, resolve_classification
from app.extraction.structured import structured_draft
from app.importers import website
from app.migrate import backup_database
from scripts.export_public import open_read_only

KINDS = ["steps", "ingredients", "notes", "source", "oil", "type"]  # the order they are applied in
CONTENT = ["title", "servings", "ingredient_groups", "step_groups", "notes", "sources", "category_id", "subcategory_id", "healthy", "status", "issues"]
TYPE_RUNS = 2  # the classifier's requests per dessert; a type is proposed only when they all agree
Classifier = Callable[[schemas.RecipeInput, list[schemas.Category]], Classification]


class MaintenanceError(Exception):
    """Why the batch cannot be applied or undone, for the person running the script."""


# --- Recipes as content ----------------------------------------------------------------------------------


def content_of(recipe: schemas.Recipe) -> schemas.RecipeInput:
    """The recipe's own content, as a save sends it: what the batch may change, and what it compares."""
    return schemas.RecipeInput(
        title=recipe.title, servings=recipe.servings, ingredient_groups=recipe.ingredient_groups, step_groups=recipe.step_groups,
        notes=recipe.notes, sources=recipe.sources, category_id=recipe.category.id if recipe.category else None,
        subcategory_id=recipe.subcategory.id if recipe.subcategory else None, healthy=recipe.healthy, status=recipe.status,
        issues=recipe.issues,
    )


def fingerprint(content: schemas.RecipeInput) -> str:
    data = content.model_dump(mode="json", include=set(CONTENT))
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def apply_changes(content: schemas.RecipeInput, changes: list[dict]) -> schemas.RecipeInput:
    """The content with these changes, in KINDS order (the oil rule sees the repaired steps and groups)."""
    for change in sorted(changes, key=lambda c: KINDS.index(c["kind"])):
        if change["kind"] == "steps":
            content = content.model_copy(update={"step_groups": [schemas.StepGroup.model_validate(g) for g in change["after"]]})
        elif change["kind"] == "ingredients":
            content = content.model_copy(update={"ingredient_groups": [schemas.IngredientGroup.model_validate(g) for g in change["after"]]})
        elif change["kind"] == "notes":
            content = content.model_copy(update={"notes": list(change["after"])})
        elif change["kind"] == "source":
            content = content.model_copy(update={"sources": [schemas.Source.model_validate(s) for s in change["after"]]})
        elif change["kind"] == "oil":
            content = add_oil_from_steps(content, only_in_step_point)  # the rule itself: never twice the same line
        elif change["kind"] == "type":
            content = content.model_copy(update={"subcategory_id": change["after"]["id"]})
    return content


def _derived(content: schemas.RecipeInput) -> list[dict]:
    return [i.model_dump() for g in content.ingredient_groups for i in g.ingredients if i.derived_from is not None]


# --- The audit ----------------------------------------------------------------------------------------------


def audit(
    database_path: Path, reader: website.WebReader | None, classifier: Classifier | None, out: Callable[[str], None] = print
) -> dict:
    """Every proposal for the notebook (read-only): the batch as a dict, with its snapshots."""
    engine = open_read_only(database_path)
    try:
        with Session(engine) as session:
            categories = crud.list_categories(session)
            recipes = crud.list_recipes(session)
            imports = {row.recipe_id: row for row in session.query(models.RecipeImport).all()}
            batch: dict[str, Any] = {
                "label": "proposed changes of this maintenance update",
                "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "notebook": str(database_path),
                "recipes": [], "no_change": [], "unresolved": [], "skipped_samples": [],
            }
            before: list[dict] = []
            after: list[dict] = []
            for recipe in sorted(recipes, key=lambda r: r.id):
                if recipe.is_sample:
                    batch["skipped_samples"].append({"id": recipe.id, "title": recipe.title})
                    continue
                current = content_of(recipe)
                changes, unresolved = [], []
                record = imports.get(recipe.id)
                if record is not None and record.kind == "website" and record.retrieved_from in ("json_ld", "microdata"):
                    out(f"  {recipe.id}: the page's recipe data, checked against the page…")
                    repairs, problem = _website_repairs(recipe, record, current, categories, reader)
                    changes += repairs
                    if problem:
                        unresolved.append({"what": "steps and ingredients", "why": problem})
                repaired = apply_changes(current, [c for c in changes if c["kind"] in ("steps", "ingredients")])
                oil = _oil_change(recipe, repaired)
                if oil is not None:
                    changes.append(oil)
                if _needs_type(recipe, categories):
                    type_change, problem = _type_change(recipe, current, categories, classifier)
                    if type_change is not None:
                        changes.append(type_change)
                    else:
                        unresolved.append({"what": "dessert type", "why": problem})
                if unresolved:
                    batch["unresolved"].append({"id": recipe.id, "title": recipe.title, "items": unresolved})
                if not changes:
                    batch["no_change"].append({"id": recipe.id, "title": recipe.title})
                    continue
                result = apply_changes(current, changes)
                batch["recipes"].append({
                    "id": recipe.id, "title": recipe.title, "status": recipe.status, "updated_at": recipe.updated_at.isoformat(),
                    "fingerprint": fingerprint(current), "before": current.model_dump(mode="json"), "changes": changes,
                })
                before.append(recipe.model_dump(mode="json"))
                after.append({**recipe.model_dump(mode="json"), **result.model_dump(mode="json", include={"ingredient_groups", "step_groups", "issues"}),
                              "subcategory": _ref(categories, result.subcategory_id)})
            batch["snapshots"] = {
                "before": {"label": "before this maintenance update", "taken_at": batch["created_at"], "recipes": before},
                "after": {"label": "after this maintenance update, if every proposal is approved (not applied)", "recipes": after},
            }
            return batch
    finally:
        engine.dispose()


def _website_repairs(recipe: schemas.Recipe, record: models.RecipeImport, current: schemas.RecipeInput,
                     categories: list[schemas.Category], reader: website.WebReader | None) -> tuple[list[dict], str | None]:
    saved = (record.source_details or {}).get("structured_data")
    if not isinstance(saved, dict) or "note" in saved:
        return [], "the import did not keep the page's recipe data"
    url = record.url or ""
    data = website.read_recipe(saved, url, record.retrieved_from)  # today's rules, on the data as it was saved
    differences: list[str] = []
    page_note = None
    if reader is None:
        page_note = "the page was not read (--no-fetch): only what the saved data alone shows"
    else:
        try:
            page = reader.page(url)
        except website.WebsiteError as error:
            page_note = f"the page could not be read again ({error.message}): only what the saved data alone shows"
        else:
            soup = BeautifulSoup(page.html, "html.parser")
            now = website.analyze(page).recipe
            for key in ("name", "recipeIngredient", "recipeInstructions", "recipeYield"):
                if now is None or now.raw.get(key) != saved.get(key):
                    differences.append(key)
            data = website.checked_with_page(data, soup)
    proposed = structured_draft(data, record.original_text, categories, None)
    groups = [g.model_copy(update={"ingredients": [i for i in g.ingredients if i.derived_from is None]}) for g in proposed.ingredient_groups]
    groups = [g for g in groups if g.ingredients]
    original = record.original_text
    changes = []
    source_note = (
        f"The page as it is now differs from the data saved at the import in: {', '.join(differences)}. "
        "The proposal is built from the saved data, checked against the page's lists." if differences
        else "The page's recipe data now is the same as the data saved at the import." if page_note is None else page_note
    )
    if [g.model_dump() for g in proposed.step_groups] != [g.model_dump() for g in current.step_groups]:
        evidence = [f"The page's own list of steps ({len(data.steps)} items), in its words:"] + [f"{n}. {s}" for n, s in enumerate(data.steps, 1)] \
            if "steps" in data.from_page else ["Without the page's lists: the saved data's steps, with its shortcodes and sponsor line taken out."]
        changes.append({
            "id": f"{recipe.id}-steps", "recipe_id": recipe.id, "kind": "steps", "group": "content", "field": "step_groups",
            "before": [g.model_dump() for g in current.step_groups], "after": [g.model_dump() for g in proposed.step_groups],
            "evidence": evidence + [source_note], "why": _why_steps(current, original),
            "uncertainty": _edited(original, [s for g in current.step_groups for s in g.steps]),
        })
    if [g.model_dump() for g in groups] != [g.model_dump() for g in current.ingredient_groups]:
        evidence = [f"The page's own ingredient lists: {', '.join(f'{g.name or 'ללא כותרת'} ({len(g.ingredients)})' for g in groups)}."] \
            if "ingredients" in data.from_page else ["The saved recipe data's lines."]
        changes.append({
            "id": f"{recipe.id}-ingredients", "recipe_id": recipe.id, "kind": "ingredients", "group": "content", "field": "ingredient_groups",
            "before": [g.model_dump() for g in current.ingredient_groups], "after": [g.model_dump() for g in groups],
            "evidence": evidence + [source_note],
            "why": "The page shows its ingredients in groups, each line with its own note (\"או סילאן\", \"לא חובה\"); the saved data had one list without them.",
            "uncertainty": _edited(original, [i.text for g in current.ingredient_groups for i in g.ingredients]),
        })
    return changes, (page_note if not changes and page_note else None)


def _why_steps(current: schemas.RecipeInput, original: str) -> str:
    text = " ".join(s for g in current.step_groups for s in g.steps)
    found = [what for what, sign in (("a photo's [caption] shortcode", "caption"), ("a sponsor's line", "בשיתוף")) if sign in text]
    return "The page numbers its steps; the saved data had flattened them into one" + (f", with {' and '.join(found)} in it" if found else "") + "."


def _edited(original: str, lines: list[str]) -> str:
    """Whether the current lines are the import's own (every one in the saved original), or may hold your edits."""
    if all(line in original for line in lines):
        return "The current text is exactly the import's (every line is in the saved original): no sign of an edit of yours."
    return "The current text differs from the import's: it may hold your own edits, which this change would replace. Compare before approving."


def _oil_change(recipe: schemas.Recipe, content: schemas.RecipeInput) -> dict | None:
    result = add_oil_from_steps(content, only_in_step_point)
    added = [line for line in _derived(result) if line not in _derived(content)]
    if not added:
        return None
    listed = [f'"{i.text}" (under "{g.name}")' for g in content.ingredient_groups for i in g.ingredients if "שמן" in i.text and i.derived_from is None]
    noted = f" The list has {', '.join(listed)}: oil the list gives to that part, not assumed to be this one." if listed else ""
    return {
        "id": f"{recipe.id}-oil", "recipe_id": recipe.id, "kind": "oil", "group": "content", "field": "ingredient_groups (one line added)",
        "before": None, "after": added,
        "evidence": [f"The step: \"{line['derived_from']}\"" for line in added],
        "why": "A step fries or greases with oil that the list does not have; a new import adds this line, labeled \"מופיע בהוראות ההכנה\".",
        "uncertainty": "Added as the app's line from the steps, not as a line of the source's list. Edit or remove it like any line." + noted,
    }


def _needs_type(recipe: schemas.Recipe, categories: list[schemas.Category]) -> bool:
    category = next((c for c in categories if recipe.category and c.id == recipe.category.id), None)
    return category is not None and category.healthy_style and bool(category.subcategories) and recipe.subcategory is None


def _type_change(recipe: schemas.Recipe, content: schemas.RecipeInput, categories: list[schemas.Category],
                 classifier: Classifier | None) -> tuple[dict | None, str]:
    if classifier is None:
        return None, "the classifier was not run (--no-types, or no model available)"
    desserts = next(c for c in categories if c.id == recipe.category.id)
    names = {s.id: s.name for s in desserts.subcategories} | {c.id: c.name for c in categories}
    answers = []
    for _ in range(TYPE_RUNS):
        try:
            category_id, subcategory_id, _ = resolve_classification(classifier(content, categories), categories)
        except (ApiError, ValueError) as error:
            return None, f"the classifier failed ({error})"
        answers.append((category_id, subcategory_id))
    said = "; ".join(f"{names.get(c, 'לא מסווג')}{' / ' + names[s] if s else ''}" for c, s in answers)
    if len(set(answers)) != 1:
        return None, f"the classifier's answers differ ({said})"
    category_id, subcategory_id = answers[0]
    if category_id != desserts.id:
        return None, f"the classifier did not see a dessert ({said}); the category stays as you set it"
    if subcategory_id is None:
        return None, "no type clearly fits, by the classifier"
    sub = next(s for s in desserts.subcategories if s.id == subcategory_id)
    return {
        "id": f"{recipe.id}-type", "recipe_id": recipe.id, "kind": "type", "group": "type", "field": "subcategory_id",
        "before": None, "after": {"id": sub.id, "name": sub.name},
        "evidence": [f"The type's description: {sub.description}" if sub.description else f"The type: {sub.name}",
                     f"The local classifier chose it in {TYPE_RUNS} of {TYPE_RUNS} requests, from the title, the ingredients and the steps."],
        "why": "A dessert without a type; the category and the healthy style stay as they are.",
        "uncertainty": "The model's choice (right in 12 of 13 measured desserts, docs/extraction-quality.md): check it." + _title_clue(recipe.title, sub.name),
    }, ""


# A word in a title that names a type: a clue for the reader of the report, never a rule.
TITLE_CLUES = [("עוגת", "עוגות"), ("עוגה", "עוגות"), ("עוגות", "עוגות"), ("עוגיות", "עוגיות וחיתוכיות"), ("טארט", "טארטים ופאי"),
               ("פאי", "טארטים ופאי"), ("גלידה", "גלידות וקינוחים קפואים"), ("גלידת", "גלידות וקינוחים קפואים"), ("מוס", "קינוחי כוסות ומוסים")]


def _title_clue(title: str, chosen: str) -> str:
    words = set(title.replace("/", " ").split())
    hinted = {kind for word, kind in TITLE_CLUES if word in words}
    if hinted and chosen not in hinted:
        return f" The title says \"{next(w for w, k in TITLE_CLUES if w in words)}\", which points to {' or '.join(sorted(hinted))}: look twice."
    return ""


def propose_types(database_path: Path, reviewed: dict, out: Callable[[str], None] = print) -> dict:
    """A batch of dessert types from a reviewed list (read-only), in the same form as an audit's: each assignment
    says what it rests on ("basis"), so a correction made in review is never shown as the model's prediction.
    A recipe that is not a dessert, or already has a type, gets nothing; a type must be an existing one."""
    engine = open_read_only(database_path)
    try:
        with Session(engine) as session:
            categories = crud.list_categories(session)
            batch: dict[str, Any] = {
                "label": "proposed changes of this maintenance update", "basis": reviewed["basis"],
                "created_at": datetime.now(UTC).isoformat(timespec="seconds"), "notebook": str(database_path),
                "recipes": [], "no_change": [], "unresolved": [], "skipped_samples": [],
            }
            before, after = [], []
            for item in reviewed["assignments"]:
                try:
                    recipe = crud.get_recipe(session, item["id"])
                except ApiError:
                    batch["unresolved"].append({"id": item["id"], "title": "?", "items": [{"what": "dessert type", "why": "no such recipe"}]})
                    continue
                if not _needs_type(recipe, categories):
                    batch["unresolved"].append({"id": recipe.id, "title": recipe.title, "items": [{"what": "dessert type", "why": "not a dessert without a type: left as it is"}]})
                    continue
                desserts = next(c for c in categories if c.id == recipe.category.id)
                if item.get("type") is None:
                    batch["unresolved"].append({"id": recipe.id, "title": recipe.title, "items": [{"what": "dessert type", "why": item["note"]}]})
                    continue
                sub = next((s for s in desserts.subcategories if s.name == item["type"]), None)
                if sub is None:
                    raise MaintenanceError(f"{recipe.id}: there is no dessert type {item['type']!r}.")
                change = {
                    "id": f"{recipe.id}-type", "recipe_id": recipe.id, "kind": "type", "group": "type", "field": "subcategory_id",
                    "before": None, "after": {"id": sub.id, "name": sub.name},
                    "evidence": [f"The type's description: {sub.description}" if sub.description else f"The type: {sub.name}", item["basis"]],
                    "why": "A dessert without a type; the category and the healthy style stay as they are.",
                    "uncertainty": item.get("note") or "",
                }
                current = content_of(recipe)
                batch["recipes"].append({"id": recipe.id, "title": recipe.title, "status": recipe.status, "updated_at": recipe.updated_at.isoformat(),
                                         "fingerprint": fingerprint(current), "before": current.model_dump(mode="json"), "changes": [change]})
                before.append(recipe.model_dump(mode="json"))
                after.append({**recipe.model_dump(mode="json"), "subcategory": {"id": sub.id, "name": sub.name}})
            batch["snapshots"] = {
                "before": {"label": "before this maintenance update", "taken_at": batch["created_at"], "recipes": before},
                "after": {"label": "after this maintenance update, if every proposal is approved (not applied)", "recipes": after},
            }
            out(f"{len(batch['recipes'])} type assignments, {len(batch['unresolved'])} left unassigned.")
            return batch
    finally:
        engine.dispose()


# --- Completing a recipe from a page that holds it --------------------------------------------------------------


def propose_from_page(database_path: Path, recipe_id: int, url: str, reader: website.WebReader, new_extractor: Callable[[], Any],
                      reviewed: dict | None = None, out: Callable[[str], None] = print) -> dict:
    """A batch that completes a saved recipe from a page that holds its recipe (read-only): the ingredients, steps
    and notes the website importer reads from the page, and the page as one more source. The import runs as a new
    import would, on a temporary copy of the notebook, so the notebook itself is only read; its draft is shown
    beside each proposal. A reviewed version ("reviewed") may correct the draft, saying each difference, but holds
    only the page's own lines: a line that is not in the text read from the page is refused. The recipe's title,
    category and type, media, cooked mark, review points and imported original are not part of the batch."""
    engine = open_read_only(database_path)
    try:
        with Session(engine) as session:
            try:
                recipe = crud.get_recipe(session, recipe_id)
            except ApiError:
                raise MaintenanceError(f"There is no recipe {recipe_id}.") from None
    finally:
        engine.dispose()
    if recipe.is_sample:
        raise MaintenanceError(f"{recipe_id} is an invented sample.")
    out(f"Reading {url} with the website importer, on a temporary copy of the notebook…")
    draft, record = _import_on_copy(database_path, url, reader, new_extractor)
    text = record.original_text
    current = content_of(recipe)
    proposed = content_of(draft)
    if reviewed is not None:
        if reviewed.get("recipe_id") != recipe_id:
            raise MaintenanceError(f"The reviewed version is for recipe {reviewed.get('recipe_id')}, not {recipe_id}.")
        try:  # the same checks as a save (a quantity is quoted from its own line, for one)
            proposed = schemas.RecipeInput.model_validate({**proposed.model_dump(), **{k: reviewed[k] for k in ("ingredient_groups", "step_groups", "notes")}})
        except ValidationError as error:
            raise MaintenanceError(f"The reviewed version is not valid: {error}") from None
        missing = _not_in_page(proposed, text, reviewed.get("labeled", {}))
        if missing:
            raise MaintenanceError("The reviewed version has lines that are not in the text read from the page: " + "; ".join(missing))
    in_page = _not_in_page(content_of(draft), text)
    review = (reviewed or {}).get("differences", {})
    labeled = {line: words for line, words in (reviewed or {}).get("labeled", {}).items() if line in proposed.notes}
    basis = "the website importer's draft, corrected in review" if reviewed else "the website importer's draft"
    read_as = f"Read from the page by the website importer ({record.retrieved_from}, {len(text):,} characters" + (f"; the model {record.model} read it" if record.model else "") + ")."
    caution = f" The draft has lines that are not word for word in the text read: {'; '.join(in_page)}." if in_page else " Every line of the draft is in the text read from the page."
    changes = []
    for kind, field, now, after, drafted in (
        ("ingredients", "ingredient_groups", current.ingredient_groups, proposed.ingredient_groups, draft.ingredient_groups),
        ("steps", "step_groups", current.step_groups, proposed.step_groups, draft.step_groups),
        ("notes", "notes", current.notes, proposed.notes, draft.notes),
    ):
        dump = lambda items: [i.model_dump() if hasattr(i, "model_dump") else i for i in items]  # noqa: E731
        if dump(after) == dump(now):
            continue
        changes.append({
            "id": f"{recipe_id}-{kind}", "recipe_id": recipe_id, "kind": kind, "group": "content", "field": field,
            "before": dump(now), "after": dump(after), "draft": dump(drafted), "basis": basis,
            "evidence": [read_as + caution] + [f"Corrected in review: {d}" for d in review.get(kind, [])]
            + [f"Labeled in review (only \"{words}\" is the page's): \"{line}\"" for line, words in labeled.items() if kind == "notes"],
            "why": f"The page holds the recipe; the saved recipe has {_count(kind, now)} now.",
            "uncertainty": "Replaces what the recipe has now in this field." if now else "",
        })
    page_source = draft.sources[0]
    if all(source.url != page_source.url for source in current.sources):
        details = record.source_details or {}
        credit = "the page's author" if details.get("author") and details.get("author", {}).get("name") != details.get("site_name") else "the site's name (the page names no author)"
        changes.append({
            "id": f"{recipe_id}-source", "recipe_id": recipe_id, "kind": "source", "group": "content", "field": "sources (one added)",
            "before": [s.model_dump() for s in current.sources], "after": [s.model_dump() for s in [*current.sources, page_source]],
            "basis": basis, "evidence": [f"The page's address, with the credit a website import gives it: {credit}."],
            "why": "The recipe's content comes from this page. The sources it has stay first, as they are, and so does its imported original.",
            "uncertainty": "",
        })
    out(f"{len(changes)} changes proposed for {recipe_id}.")
    batch: dict[str, Any] = {
        "label": "proposed changes of this maintenance update", "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "notebook": str(database_path), "basis": (reviewed or {}).get("basis") or f"Recipe {recipe_id} completed from {url}: {basis}.",
        "page": {"url": page_source.url, "retrieved_from": record.retrieved_from, "model": record.model, "text": text,
                 "points": [issue.model_dump() for issue in draft.issues], "points_review": (reviewed or {}).get("points", "")},
        "recipes": [], "no_change": [], "unresolved": [], "skipped_samples": [],
    }
    if changes:
        batch["recipes"].append({"id": recipe_id, "title": recipe.title, "status": recipe.status, "updated_at": recipe.updated_at.isoformat(),
                                 "fingerprint": fingerprint(current), "before": current.model_dump(mode="json"), "changes": changes})
    else:
        batch["no_change"].append({"id": recipe_id, "title": recipe.title})
    result = apply_changes(current, changes)
    batch["snapshots"] = {
        "before": {"label": "before this maintenance update", "taken_at": batch["created_at"], "recipes": [recipe.model_dump(mode="json")]},
        "after": {"label": "after this maintenance update, if every proposal is approved (not applied)",
                  "recipes": [{**recipe.model_dump(mode="json"), **result.model_dump(mode="json", include={"ingredient_groups", "step_groups", "notes", "sources"})}]},
    }
    return batch


def _import_on_copy(database_path: Path, url: str, reader: website.WebReader, new_extractor: Callable[[], Any]) -> tuple[schemas.Recipe, models.RecipeImport]:
    """The draft a link import of the page makes today, and its import record: the import's own code, run on a
    temporary copy of the notebook (its categories), which is then deleted with the draft and its picture."""
    from app.api.imports import _import_website as import_website_draft  # the link import itself, without its endpoint

    with tempfile.TemporaryDirectory() as temp:
        copy = Path(temp) / "recipes.db"
        with closing(sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True)) as live, closing(sqlite3.connect(copy)) as target:
            live.backup(target)
        engine = make_engine(copy)
        try:
            with Session(engine) as session:
                try:
                    draft = import_website_draft(schemas.LinkImport(url=url, allow_duplicate=True), session, new_extractor, reader, Path(temp) / "media")
                except ApiError as error:
                    raise MaintenanceError(f"The page gave no complete recipe ({error.code}): {error.message}") from None
                record = session.query(models.RecipeImport).filter_by(recipe_id=draft.id).one()
                session.expunge(record)
                return draft, record
        finally:
            engine.dispose()  # before the folder is deleted (Windows keeps open files)


def _not_in_page(content: schemas.RecipeInput, text: str, labeled: dict[str, str] | None = None) -> list[str]:
    """The content's lines (and group names) that are not word for word in the text read from the page. A note
    labeled in review ({note: the page's words in it}, such as a time the page shows only beside an icon) passes
    when those words are in it and in the page."""
    page = " ".join(text.split())
    lines = [g.name for g in [*content.ingredient_groups, *content.step_groups] if g.name]
    lines += [i.text for g in content.ingredient_groups for i in g.ingredients] + [s for g in content.step_groups for s in g.steps] + list(content.notes)
    labeled = {line: words for line, words in (labeled or {}).items() if line in content.notes}
    return [line for line in lines if " ".join((labeled[line] if line in labeled and labeled[line] in line else line).split()) not in page]


def _count(kind: str, value: list) -> str:
    if not value:
        return {"ingredients": "no ingredient lines", "steps": "no steps", "notes": "no notes"}[kind]
    if kind == "notes":
        return f"{len(value)} notes"
    return f"{sum(len(g.ingredients if kind == 'ingredients' else g.steps) for g in value)} {'ingredient lines' if kind == 'ingredients' else 'steps'}"


def _ref(categories: list[schemas.Category], subcategory_id: int | None) -> dict | None:
    for category in categories:
        for sub in category.subcategories:
            if sub.id == subcategory_id:
                return {"id": sub.id, "name": sub.name}
    return None


# --- The batch on disk and its report ----------------------------------------------------------------------


def applied_changes(folder: Path, database: str) -> dict[str, str]:
    """change id -> when it was applied to that notebook file, and not undone since (from the batch's logs)."""
    events: list[tuple[str, str, dict]] = []
    for path in folder.glob("applied-*.json"):
        log = json.loads(path.read_text(encoding="utf-8"))
        if log.get("database") == database:
            events += [(log["applied_at"], "applied", item) for item in log["applied"]]
    for path in folder.glob("undone-*.json"):
        log = json.loads(path.read_text(encoding="utf-8"))
        if log.get("database") == database:
            events += [(log["undone_at"], "undone", {"id": rid}) for rid in log["restored"]]
    state: dict[str, str] = {}
    for at, what, item in sorted(events, key=lambda e: e[0]):
        if what == "applied":
            state.update({change: at for change in item["changes"]})
        else:
            state = {change: when for change, when in state.items() if not change.startswith(f"{item['id']}-")}
    return state


def write_report(folder: Path) -> None:
    """The report again, from the batch and what has been applied to its notebook since."""
    batch = read_batch(folder)
    (folder / "report.html").write_text(report_html(batch, folder), encoding="utf-8")


def write_batch(batch: dict, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    snapshots = batch.pop("snapshots")
    (folder / "batch.json").write_text(json.dumps(batch, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (folder / "before.json").write_text(json.dumps(snapshots["before"], ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (folder / "after.json").write_text(json.dumps(snapshots["after"], ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    write_report(folder)


def read_batch(folder: Path) -> dict:
    path = folder / "batch.json"
    if not path.exists():
        raise MaintenanceError(f"No batch in {folder} (batch.json is missing).")
    return json.loads(path.read_text(encoding="utf-8"))


def _value(kind: str, value: Any) -> str:
    """A field's value as HTML: groups as lists, a line, a type."""
    if value is None:
        return "<p class='none'>(none)</p>"
    if kind == "type":
        return f"<p>{html.escape(value['name'])}</p>"
    if kind == "notes":
        return "<ul>" + "".join(f"<li>{html.escape(note)}</li>" for note in value) + "</ul>" if value else "<p class='none'>(none)</p>"
    if kind == "source":
        return "<ul>" + "".join(
            f"<li>{html.escape(s['kind'])}: <bdi>{html.escape(s['url'] or '')}</bdi>, {html.escape(', '.join(c['name'] for c in s['creators']) or '(no credit)')}</li>" for s in value
        ) + "</ul>"
    parts = []
    for group in value:
        if "derived_from" in group:  # an added line
            parts.append(f"<ul><li>{html.escape(group['text'])} <span class='tag'>מופיע בהוראות ההכנה</span></li></ul>")
            continue
        items = group.get("steps") or [i["text"] for i in group.get("ingredients", [])]
        title = f"<h5>{html.escape(group['name'])}</h5>" if group.get("name") else ""
        tag = "ol" if "steps" in group else "ul"
        parts.append(title + f"<{tag}>" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + f"</{tag}>")
    return "".join(parts) or "<p class='none'>(none)</p>"


def _page_section(page: dict | None) -> str:
    """For a batch made from a page: what was read, and the review points its import raised (never written)."""
    if not page:
        return ""
    points = "".join(f"<li dir='auto'>{html.escape(p['message'])}</li>" for p in page["points"]) or "<li>(none)</li>"
    review = f"<p>{html.escape(page['points_review'])}</p>" if page.get("points_review") else ""
    return (f"<h2>The page</h2><p><bdi>{html.escape(page['url'])}</bdi>: read by the website importer ({html.escape(page['retrieved_from'] or '')}"
            + (f"; the model {html.escape(page['model'])} read its text" if page.get("model") else "") + "). The middle column of each change is the draft that import made.</p>"
            f"<h4>Review points the import raised (shown here, not added to the recipe)</h4><ul class='evidence'>{points}</ul>{review}"
            f"<details><summary>The text read from the page ({len(page['text']):,} characters)</summary><pre class='text'>{html.escape(page['text'])}</pre></details>")


def report_html(batch: dict, folder: Path) -> str:
    content = [c for r in batch["recipes"] for c in r["changes"] if c["group"] == "content"]
    types = [c for r in batch["recipes"] for c in r["changes"] if c["group"] == "type"]
    applied = applied_changes(folder, str(Path(batch["notebook"]).resolve()))
    replaced = set(batch.get("superseded", {}).get("changes", []))
    total = len(content) + len(types)
    open_ = total - len(applied) - len(replaced - set(applied))
    heading = "proposed changes (nothing applied yet)" if not applied and not replaced else (
        f"{len(applied)} of {total} changes applied, {len(replaced - set(applied))} replaced by a later batch, {open_} still proposals")
    rows = []
    for recipe in batch["recipes"]:
        rows.append(f"<section><h2>#{recipe['id']} <bdi>{html.escape(recipe['title'])}</bdi> <span class='status'>{recipe['status']}</span></h2>")
        for change in recipe["changes"]:
            rows.append(
                f"<article class='{change['group']}'><h3><code>{change['id']}</code> {html.escape(change['field'])} "
                + (f"<span class='applied'>APPLIED to the notebook {applied[change['id']]}</span>" if change["id"] in applied
                   else f"<span class='proposed'>replaced by the batch {batch['superseded']['by']}</span>" if change["id"] in replaced
                   else "<span class='proposed'>proposal</span>")
                + "</h3>"
                f"<div class='pair{' three' if 'draft' in change else ''}'><div><h4>Now</h4>{_value(change['kind'], change['before'])}</div>"
                + (f"<div><h4>The import's draft</h4>{_value(change['kind'], change['draft'])}</div>" if "draft" in change else "")
                + f"<div><h4>Proposed{' (' + html.escape(change['basis']) + ')' if 'basis' in change else ''}</h4>{_value(change['kind'], change['after'])}</div></div>"
                "<h4>Support</h4><ul class='evidence'>" + "".join(f"<li dir='auto'>{html.escape(e)}</li>" for e in change["evidence"]) + "</ul>"
                f"<p><b>Why:</b> {html.escape(change['why'])}</p>"
                + (f"<p class='uncertain'><b>Uncertainty:</b> {html.escape(change['uncertainty'])}</p>" if change["uncertainty"] else "") + "</article>"
            )
        rows.append("</section>")
    unresolved = "".join(
        f"<li>#{u['id']} <bdi>{html.escape(u['title'])}</bdi>: " + "; ".join(f"{html.escape(i['what'])}: {html.escape(i['why'])}" for i in u["items"]) + "</li>"
        for u in batch["unresolved"]
    )
    content_ids = " ".join(c["id"] for c in content) or "(none)"
    type_ids = " ".join(c["id"] for c in types) or "(none)"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Recipe maintenance</title><style>
body{{font-family:system-ui,sans-serif;margin:0 auto;max-width:1100px;padding:16px;color:#222;background:#fafaf7;line-height:1.5}}
section{{background:#fff;border:1px solid #ddd;border-radius:10px;padding:12px 16px;margin:16px 0}}
article{{border-top:1px solid #eee;padding-top:8px;margin-top:8px}} article.type{{background:#f4faf6}}
.pair{{display:grid;grid-template-columns:1fr 1fr;gap:16px}} .pair.three{{grid-template-columns:1fr 1fr 1fr}} .pair>div{{direction:rtl;background:#f7f7f7;border-radius:8px;padding:4px 12px}}
@media (max-width:700px){{.pair,.pair.three{{grid-template-columns:1fr}}}} pre.text{{direction:rtl;white-space:pre-wrap;unicode-bidi:plaintext}}
.evidence{{padding:0 20px}} .evidence li{{direction:rtl;text-align:right;unicode-bidi:plaintext}} .uncertain{{color:#7a4b00}} .none{{color:#888}}
bdi,li,p{{overflow-wrap:anywhere}}
.tag{{font-size:.75rem;border:1px dashed #aaa;border-radius:99px;padding:0 6px;color:#666}} code{{background:#eee;padding:0 4px;border-radius:4px}}
.status{{font-size:.8rem;color:#666}} pre{{background:#eee;padding:8px;overflow-x:auto;direction:ltr}}
.applied{{font-size:.8rem;background:#1d6b50;color:#fff;border-radius:99px;padding:1px 8px}} .proposed{{font-size:.8rem;border:1px solid #aaa;border-radius:99px;padding:0 8px;color:#555}}
</style></head><body>
<h1>Recipe maintenance: {heading}</h1>
<p class='label'>{html.escape(batch.get('basis', 'Proposals made by the importer\'s own code and the local classifier.'))}</p>
<p>Batch <code>{folder.name}</code>, made {batch['created_at']} from <code>{html.escape(batch['notebook'])}</code>, read-only.
Snapshots: <code>before.json</code> (the recipes before this maintenance update) and <code>after.json</code> (as they would be if every
proposal is approved). Neither is a model draft from an import.</p>
<ul><li>Recipes with proposals: {len(batch['recipes'])}; content repairs: {len(content)}; dessert types: {len(types)}.</li>
<li>Recipes with no change: {len(batch['no_change'])}. Invented samples left out: {len(batch['skipped_samples'])}.</li></ul>
<h2>Approve</h2><p>Everything (a verified backup is made first):</p>
<pre>.\\maintain-recipes.cmd apply data\\maintenance\\{folder.name} --yes</pre>
<p>Leaving changes out: <code>--exclude 51-ingredients 30-type</code>; only some: <code>--only {' '.join(c['id'] for c in content[:2]) or '51-steps'}</code>.
Content repairs: <code>{content_ids}</code>. Dessert types: <code>{type_ids}</code>.</p>
<p>Undo, afterwards: <pre>.\\maintain-recipes.cmd undo data\\maintenance\\{folder.name} --yes</pre></p>
<h2>Not resolved (no change proposed)</h2><ul>{unresolved or '<li>(none)</li>'}</ul>
{_page_section(batch.get('page'))}
{''.join(rows)}
</body></html>
"""


# --- Applying and undoing ---------------------------------------------------------------------------------------


def verified_backup(database_path: Path, label: str) -> Path:
    """A backup made with SQLite's backup API, then checked: readable, intact, the same recipes."""
    target = backup_database(database_path, label)
    with closing(sqlite3.connect(f"{target.resolve().as_uri()}?mode=ro", uri=True)) as copy, closing(sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True)) as live:
        if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise MaintenanceError(f"The backup {target} is not intact; nothing was changed.")
        if copy.execute("SELECT id, updated_at FROM recipes ORDER BY id").fetchall() != live.execute("SELECT id, updated_at FROM recipes ORDER BY id").fetchall():
            raise MaintenanceError(f"The backup {target} does not hold the same recipes; nothing was changed.")
    return target


def apply_batch(database_path: Path, folder: Path, exclude: list[str] | None = None, only: list[str] | None = None,
                out: Callable[[str], None] = print) -> dict:
    """Apply the approved changes of the batch (all but `exclude`, or only `only`). Returns the log, also written to the folder."""
    batch = read_batch(folder)
    known = {c["id"] for r in batch["recipes"] for c in r["changes"]}
    unknown = sorted((set(exclude or []) | set(only or [])) - known)
    if unknown:
        raise MaintenanceError(f"The batch has no change {', '.join(unknown)}.")
    replaced = set(batch.get("superseded", {}).get("changes", []))  # proposals a later, reviewed batch replaces
    if replaced & set(only or []):
        raise MaintenanceError(f"{', '.join(sorted(replaced & set(only)))}: replaced by the batch {batch['superseded']['by']}; apply that one.")
    approved = lambda c: (only is None or c["id"] in only) and c["id"] not in set(exclude or []) and c["id"] not in replaced  # noqa: E731
    backup = verified_backup(database_path, f"before-maintenance-{folder.name}")
    out(f"Backup, verified: {backup}")
    log: dict[str, Any] = {"label": "what this maintenance update changed", "batch": folder.name, "database": str(database_path.resolve()), "backup": str(backup),
                           "applied_at": datetime.now(UTC).isoformat(timespec="seconds"), "applied": [], "already_applied": [], "skipped": []}
    engine = make_engine(database_path)  # the app's own: foreign keys enforced
    try:
        with Session(engine) as session:
            for entry in batch["recipes"]:
                changes = [c for c in entry["changes"] if approved(c)]
                if not changes:
                    continue
                outcome = _apply_one(session, entry, changes)
                log[outcome["result"]].append(outcome)
                out(f"  {entry['id']} {entry['title'][:40]}: {outcome['result'].replace('_', ' ')} {outcome.get('why', '')}".rstrip())
            session.commit()
    finally:
        engine.dispose()
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")  # to the microsecond: two runs never share a log
    (folder / f"applied-{stamp}.json").write_text(json.dumps(log, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if str(database_path.resolve()) == str(Path(batch["notebook"]).resolve()):
        write_report(folder)  # the report now says which changes are applied
    return log


def _apply_one(session: Session, entry: dict, changes: list[dict]) -> dict:
    try:
        recipe = crud.get_recipe(session, entry["id"])
    except ApiError:
        return {"id": entry["id"], "result": "skipped", "why": "the recipe is no longer in the notebook"}
    before = schemas.RecipeInput.model_validate(entry["before"])
    current = content_of(recipe)
    target = apply_changes(before, changes)
    done = {"id": entry["id"], "changes": [c["id"] for c in changes]}
    if fingerprint(current) == fingerprint(target):
        return {**done, "result": "already_applied"}
    # The report's content, or that with some of these changes already applied (an earlier, smaller approval).
    partial = [list(subset) for n in range(len(changes)) for subset in itertools.combinations(changes, n)]
    if not any(fingerprint(current) == fingerprint(apply_changes(before, subset)) for subset in partial):
        return {**done, "result": "skipped", "why": "it changed after the report: not overwritten (make a new report)"}
    row = session.get(models.Recipe, entry["id"])
    crud.check_classification(session, row.category_id, target.subcategory_id, row.healthy)
    written = {"updated_at": row.updated_at.isoformat()}
    for field, model in (("ingredient_groups", schemas.IngredientGroup), ("step_groups", schemas.StepGroup), ("issues", schemas.Issue)):
        # Compared as content: a recipe saved before a field existed (no "derived_from" key) is not rewritten.
        if [model.model_validate(item) for item in getattr(row, field)] != getattr(target, field):
            written[field] = getattr(row, field)
            setattr(row, field, [item.model_dump() for item in getattr(target, field)])
    if target.subcategory_id != row.subcategory_id:
        written["subcategory_id"] = row.subcategory_id
        row.subcategory_id = target.subcategory_id
    if list(target.notes) != row.notes:
        written["notes"] = row.notes
        row.notes = list(target.notes)
    if target.sources != current.sources:
        # Only added at the end: the sources the recipe has keep their own rows, exactly as stored.
        written["sources"] = [s.model_dump() for s in current.sources]
        row.sources.extend(
            models.RecipeSource(position=index, kind=s.kind, url=s.url, creators=[c.model_dump() for c in s.creators])
            for index, s in enumerate(target.sources) if index >= len(current.sources)
        )
    row.updated_at = utc_now()
    session.flush()
    return {**done, "result": "applied", "previous": written, "fingerprint": fingerprint(target)}


def undo_batch(database_path: Path, folder: Path, out: Callable[[str], None] = print) -> dict:
    """Put back what the batch's applications wrote, newest first, where the recipe still holds it."""
    mine = str(database_path.resolve())  # only what was applied to this notebook (a test copy keeps its own)
    logs = [p for p in sorted(folder.glob("applied-*.json"), reverse=True) if json.loads(p.read_text(encoding="utf-8")).get("database") == mine]
    if not logs:
        raise MaintenanceError(f"Nothing of the batch in {folder} was applied to {database_path}.")
    backup = verified_backup(database_path, f"before-undo-{folder.name}")
    result: dict[str, Any] = {"label": "what undoing this maintenance update put back", "database": mine, "backup": str(backup),
                              "undone_at": datetime.now(UTC).isoformat(timespec="seconds"), "restored": [], "skipped": []}
    engine = make_engine(database_path)  # the app's own: foreign keys enforced
    try:
        with Session(engine) as session:
            for path in logs:
                for item in json.loads(path.read_text(encoding="utf-8"))["applied"]:
                    try:
                        recipe = crud.get_recipe(session, item["id"])
                    except ApiError:
                        result["skipped"].append({"id": item["id"], "why": "no longer in the notebook"})
                        continue
                    if fingerprint(content_of(recipe)) != item["fingerprint"]:
                        result["skipped"].append({"id": item["id"], "why": "changed after the batch, or already undone: left as it is"})
                        continue
                    row = session.get(models.Recipe, item["id"])
                    for field, value in item["previous"].items():
                        if field == "sources":  # the batch only added sources: their rows go, the others stay
                            row.sources = row.sources[:len(value)]
                        else:
                            setattr(row, field, datetime.fromisoformat(value) if field == "updated_at" else value)
                    session.flush()
                    result["restored"].append(item["id"])
                    out(f"  {item['id']}: put back")
            session.commit()
    finally:
        engine.dispose()
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    (folder / f"undone-{stamp}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if mine == str(Path(read_batch(folder)["notebook"]).resolve()):
        write_report(folder)
    return result


# --- The command ---------------------------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]


def batch_folder(given: Path, data_dir: Path) -> Path:
    """The batch folder as given: a path from here or from the project root (maintain-recipes.cmd runs in
    backend/), or the batch's id alone ("20261103-175228")."""
    for candidate in (given, REPO_ROOT / given, data_dir / "maintenance" / given):
        if (candidate / "batch.json").exists():
            return candidate
    return given


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bring saved recipes up to the importer's current rules, with a report first.")
    sub = parser.add_subparsers(dest="command", required=True)
    audit_cmd = sub.add_parser("audit", help="read-only: write a batch of proposals and its report")
    audit_cmd.add_argument("--no-fetch", action="store_true", help="never read a page again")
    audit_cmd.add_argument("--no-types", action="store_true", help="do not ask the classifier for dessert types")
    review = sub.add_parser("propose-types", help="read-only: a batch of dessert types from a reviewed list (JSON)")
    review.add_argument("reviewed", type=Path, help='{"basis": "...", "assignments": [{"id": 12, "type": "עוגות", "basis": "...", "note": "..."}]}')
    page = sub.add_parser("propose-from-page", help="read-only: complete a saved recipe from a page that holds it")
    page.add_argument("recipe", type=int, help="the recipe's id")
    page.add_argument("url", help="the page's address")
    page.add_argument("--reviewed", type=Path, help="a reviewed version of the import's draft (JSON), in place of the draft")
    for name in ("apply", "undo"):
        command = sub.add_parser(name)
        command.add_argument("batch", type=Path, help="the batch folder (data/maintenance/<id>)")
        command.add_argument("--yes", action="store_true", help="really change the notebook")
        if name == "apply":
            command.add_argument("--exclude", nargs="+", default=[], metavar="CHANGE", help="leave these changes out (e.g. 51-oil 30-type)")
            command.add_argument("--only", nargs="+", metavar="CHANGE", help="apply only these changes")
    parser.add_argument("--database", type=Path, help="another notebook file (default: the notebook)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    settings = load_settings()
    database = args.database or settings.database_path
    try:
        if args.command == "audit":
            classifier = None
            if not args.no_types:
                from app.extraction.choose import make_extractor

                extractor = make_extractor(settings)
                classifier = getattr(extractor, "classify_draft", None)
            folder = (database.parent / "maintenance" / datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
            print(f"Reading {database} (read-only)…")
            batch = audit(database, None if args.no_fetch else website.WebReader(), classifier)
            write_batch(batch, folder)
            changes = [c for r in batch["recipes"] for c in r["changes"]]
            print(f"{len(batch['recipes'])} recipes with proposals ({sum(c['group'] == 'content' for c in changes)} content repairs, "
                  f"{sum(c['group'] == 'type' for c in changes)} dessert types); {len(batch['no_change'])} with none; "
                  f"{len(batch['unresolved'])} with something unresolved.")
            print(f"Report: {folder / 'report.html'}")
            return 0
        if args.command == "propose-types":
            folder = database.parent / "maintenance" / (datetime.now(UTC).strftime("%Y%m%d-%H%M%S") + "-types")
            reviewed = args.reviewed if args.reviewed.exists() else REPO_ROOT / args.reviewed  # the .cmd runs in backend/
            write_batch(propose_types(database, json.loads(reviewed.read_text(encoding="utf-8"))), folder)
            print(f"Report: {folder / 'report.html'}")
            return 0
        if args.command == "propose-from-page":
            from app.extraction.choose import make_extractor

            folder = database.parent / "maintenance" / (datetime.now(UTC).strftime("%Y%m%d-%H%M%S") + f"-page-{args.recipe}")
            reviewed = None
            if args.reviewed:
                path = args.reviewed if args.reviewed.exists() else REPO_ROOT / args.reviewed  # the .cmd runs in backend/
                reviewed = json.loads(path.read_text(encoding="utf-8"))
            write_batch(propose_from_page(database, args.recipe, args.url, website.WebReader(), lambda: make_extractor(settings), reviewed), folder)
            print(f"Report: {folder / 'report.html'}")
            return 0
        if not args.yes:
            print(f"Nothing changed: add --yes to {args.command} the batch {args.batch}.", file=sys.stderr)
            return 1
        folder = batch_folder(args.batch, settings.data_dir)
        if args.command == "apply":
            log = apply_batch(database, folder, args.exclude, args.only)
            print(f"Applied: {len(log['applied'])}; already applied: {len(log['already_applied'])}; skipped: {len(log['skipped'])}.")
            return 0 if not log["skipped"] else 2
        result = undo_batch(database, folder)
        print(f"Put back: {len(result['restored'])}; left as they are: {len(result['skipped'])}.")
        return 0
    except MaintenanceError as error:
        print(f"FAILED. {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
