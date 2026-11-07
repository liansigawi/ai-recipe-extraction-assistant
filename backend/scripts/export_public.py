"""Export the public, read-only copy of the notebook: chosen saved recipes, and only what its pages show.

Run from the backend/ folder (the notebook is opened read-only; nothing in it changes):

    uv run python -m scripts.export_public            # the recipes chosen in data/public-notebook/selection.json
    uv run python -m scripts.export_public --list     # every recipe, and whether it can be published

Then build the page in frontend/: `npm run build:public` (docs/public-notebook.md).

The selection file (yours, git-ignored like the rest of data/):

    {"recipes": [15, 12, 6], "show_processing": [12, 6], "repository_url": "https://github.com/...",
     "demonstrations": {"12": "demonstrations/12.json"}}

Only saved recipes can be exported: never a draft, never an invented sample. For each recipe the
export writes its content, category, credit and sources, its cooked mark and its cover picture
(for a video: a still from it, with the link to the post; never the video). Category descriptions,
review points, uploaded pictures (a phone photo can carry its location) and any other file stay out.
For the recipes in "show_processing" it adds the imported original text and, when a backup of the
database still holds the import's own draft from before any review, that draft: found, not rebuilt.
A recipe in "demonstrations" also gets its recorded demonstration (the same original imported again on a
separate copy of the notebook, and its review), only if it was made from that recipe's original text. A recipe in
"classification_checks", one whose import left no draft and that has no demonstration, gets the category the current
model suggests for its original imported again (a recorded check, made from that recipe's original text).
Review decisions of the notebook's own recipes stay out.

Writes <folder>/export/notebook.json and <folder>/export/media/, replacing the previous export.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AwareDatetime, ConfigDict, Field, ValidationError
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app import crud, media, models, schemas
from app.config import load_settings
from app.extraction.output import Classification
from app.extraction.review import join_closing_remarks, names_an_alternative, refers_elsewhere, resolve_classification
from app.schemas import ContractModel, NonEmptyStr


class Selection(ContractModel):
    """data/public-notebook/selection.json"""

    recipes: list[int] = Field(min_length=1)  # recipe ids, as in the address of a recipe (#/recipes/12)
    show_processing: list[int] = []  # of those, the ones whose original text and draft are shown
    repository_url: Annotated[str, Field(pattern=r"^https://\S+$")] | None = None
    # Of those, recipe id -> its recorded demonstration (a JSON file, its path from the selection's folder).
    demonstrations: dict[int, str] = {}
    # Of those, recipe id -> a recorded classification check (a JSON file, its path from the selection's folder).
    classification_checks: dict[int, str] = {}


class KeptDraft(ContractModel):
    """An import's draft as a backup of the database kept it, before any review."""

    model_config = ConfigDict(str_strip_whitespace=False)  # exactly as stored

    title: NonEmptyStr
    servings: str | None
    category: schemas.CategoryRef | None
    subcategory: schemas.CategoryRef | None
    healthy: bool | None = None  # a dessert's healthy style, as the saved recipes have it since migration 0014
    ingredient_groups: list[schemas.IngredientGroup]
    step_groups: list[schemas.StepGroup]
    notes: list[str]
    issues: list[schemas.Issue]  # the review points the import raised
    saved_at: AwareDatetime  # when the import saved it (it was not changed afterwards)


class ReviewedDraft(KeptDraft):
    """A demonstration's draft after its review, as it was saved: the points resolved, and any left open."""

    resolved_issues: list[schemas.ResolvedIssue]


class JoinedRemark(ContractModel):
    """Evidence of what the import did by a fixed rule, not the model: a remark in brackets that ends a step's
    sentence on the original's next line, made part of that step (app/extraction/review.py, _closes_the_step)."""

    model_config = ConfigDict(str_strip_whitespace=False)

    kind: Literal["joined_remark"]
    step: NonEmptyStr  # the step's own line in the original
    remark: NonEmptyStr  # the line after it: "(...)."


class KeptReference(ContractModel):
    """Evidence of what the import did by a fixed rule, not the model: a line that sends the cook to a separate recipe
    for a part of this one, kept as written although the model left it out (app/extraction/review.py, _references)."""

    model_config = ConfigDict(str_strip_whitespace=False)

    kind: Literal["kept_reference"]
    text: NonEmptyStr  # as the draft holds it
    kept_as: Literal["step", "note"]


class RunSettings(ContractModel):
    mode: NonEmptyStr  # "references": the model labels numbered passages
    context_tokens: int
    temperature: float


class ModelPoint(ContractModel):
    """A review point the model's answer raised: its kind and the passage it pointed at (the original's words), and,
    when the import did not show it, the rule that left it out."""

    model_config = ConfigDict(str_strip_whitespace=False)

    kind: schemas.ModelIssueKind
    passage: NonEmptyStr | None  # None: it pointed at no passage
    # no_alternative: an "unclear or" in a passage without "או"; outside_recipe: a passage the model itself left out;
    # no_passage: a point that needs a passage and had none; other_check: another of the import's checks.
    left_out: Literal["no_alternative", "outside_recipe", "no_passage", "other_check"] | None = None


class ModelAnswer(ContractModel):
    """What the model itself answered, beside what the import made of it: its classification as given, and its points."""

    classification: Classification
    points: list[ModelPoint] = []


class Demonstration(ContractModel):
    """A recipe's original text imported again on a separate copy of the notebook, as it was recorded: the draft
    the import made, and the same draft after its review (performed while preparing the demonstration). Never the
    first import's draft (docs/public-notebook.md)."""

    recipe_id: int
    source_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]  # of the text it imported: the recipe's own original
    run_at: AwareDatetime
    model: NonEmptyStr
    revision: NonEmptyStr | None = None  # the code that ran (a commit)
    settings: RunSettings | None = None
    answer: ModelAnswer | None = None
    draft: KeptDraft
    reviewed: ReviewedDraft
    # What the import did by fixed rules, each checked against the original and both recorded states.
    automatic: list[Annotated[JoinedRemark | KeptReference, Field(discriminator="kind")]] = []


class CheckedAnswer(ContractModel):
    """One answer of a classification check, as the import maps it: a category only for a clear, valid choice."""

    category: schemas.CategoryRef | None
    subcategory: schemas.CategoryRef | None
    at: AwareDatetime  # when the model answered


class ClassificationCheck(ContractModel):
    """The category the current model suggests for a recipe whose own import kept no record of it: the recipe's
    original imported again on a separate copy of the notebook, and that draft's classification request answered,
    then sent again unchanged (each answer as it came). Never the first import's suggestion, and no review: the
    recipe's category after review is the saved one (docs/public-notebook.md)."""

    recipe_id: int
    source_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]  # of the text it imported: the recipe's own original
    run_at: AwareDatetime  # when the import ran
    model: NonEmptyStr
    answers: list[CheckedAnswer] = Field(min_length=1)


class ExportError(Exception):
    """Why the selection cannot be exported, for the person running the script."""


@dataclass
class Report:
    recipes: list[str] = field(default_factory=list)
    files: int = 0
    bytes: int = 0
    drafts: dict[int, str | None] = field(default_factory=dict)  # recipe id -> the backup its draft came from
    demonstrations: dict[int, str] = field(default_factory=dict)  # recipe id -> when and with which model it ran
    checks: dict[int, str] = field(default_factory=dict)  # recipe id -> its classification check: when, which model
    left_out: list[str] = field(default_factory=list)


def open_read_only(database_path: Path) -> Engine:
    """The notebook, opened so that nothing can be written to it (SQLite's read-only mode)."""
    if not database_path.exists():
        raise ExportError(f"There is no notebook at {database_path}.")
    uri = f"{database_path.resolve().as_uri()}?mode=ro"
    return create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True, check_same_thread=False))


def read_selection(path: Path) -> Selection:
    if not path.exists():
        raise ExportError(f"No selection yet: write {path} (docs/public-notebook.md), or see the recipes with --list.")
    try:
        return Selection.model_validate_json(path.read_bytes())
    except ValidationError as error:
        raise ExportError(f"{path} is not a valid selection:\n{error}") from None


def publishable(recipe: schemas.Recipe) -> str | None:
    """Why the recipe cannot be published, or None when it can."""
    if recipe.is_sample:
        return "an invented sample recipe"
    if recipe.status != "saved":
        return "a draft that has not been reviewed: review and save it first"
    return None


def export_notebook(database_path: Path, media_root: Path, selection: Selection, out: Path) -> Report:
    """Write the public copy of the selected recipes to `out` (notebook.json and media/). The paths in
    selection.demonstrations are read from out's folder."""
    folder = out.parent
    unknown = set(selection.show_processing) - set(selection.recipes)
    if unknown:
        raise ExportError(f"show_processing names recipes that are not in the selection: {sorted(unknown)}")
    if set(selection.demonstrations) - set(selection.show_processing):
        raise ExportError(f"demonstrations names recipes not in show_processing: {sorted(set(selection.demonstrations) - set(selection.show_processing))}")
    if set(selection.classification_checks) - set(selection.show_processing):
        outside = sorted(set(selection.classification_checks) - set(selection.show_processing))
        raise ExportError(f"classification_checks names recipes not in show_processing: {outside}")
    if set(selection.classification_checks) & set(selection.demonstrations):
        both = sorted(set(selection.classification_checks) & set(selection.demonstrations))
        raise ExportError(f"Recipes {both} have a demonstration: its draft holds the model's suggestion, so no classification check.")
    engine = open_read_only(database_path)
    report = Report()
    staging = out.with_name(out.name + ".partial")  # written in full first, so a failed export leaves the last one
    if staging.exists():
        shutil.rmtree(staging)
    (staging / "media").mkdir(parents=True)
    try:
        with Session(engine) as session:
            by_id = {recipe.id: recipe for recipe in crud.list_recipes(session)}  # newest first, as the app lists them
            missing = [rid for rid in selection.recipes if rid not in by_id]
            if missing:
                raise ExportError(f"The notebook has no recipe {', '.join(map(str, missing))}.")
            refused = [f"{rid} ({why})" for rid in selection.recipes if (why := publishable(by_id[rid])) is not None]
            if refused:
                raise ExportError("Only saved recipes can be published. Not: " + "; ".join(refused))
            chosen = [recipe for recipe in by_id.values() if recipe.id in selection.recipes]
            for recipe in chosen:
                if recipe.id in selection.show_processing and recipe.original is None:
                    raise ExportError(f"Recipe {recipe.id} was typed in by hand: it has no original text to compare with.")
            public = [_public_recipe(session, media_root, recipe, selection, staging / "media", report) for recipe in chosen]
            every_category = crud.list_categories(session)
            demonstrations = {rid: read_demonstration(folder / path, by_id[rid], every_category) for rid, path in selection.demonstrations.items()}
            checks = {rid: read_classification_check(folder / path, by_id[rid]) for rid, path in selection.classification_checks.items()}
            categories = _used_categories(every_category, chosen)
        for recipe in public:
            if recipe["processing"] is not None:
                draft, backup = find_kept_draft(database_path, recipe["id"])
                recipe["processing"]["draft"] = draft.model_dump(mode="json") if draft is not None else None
                report.drafts[recipe["id"]] = backup
                if recipe["id"] in demonstrations:
                    demo = demonstrations[recipe["id"]]
                    # The record's ids stay here; what the model answered and what the rules did are shown apart from
                    # what review changed.
                    recipe["processing"]["demonstration"] = demo.model_dump(mode="json", exclude={"recipe_id", "source_sha256"})
                    report.demonstrations[recipe["id"]] = f"run {demo.run_at:%Y-%m-%d %H:%M} UTC with {demo.model}"
                if recipe["id"] in checks:
                    if draft is not None:
                        raise ExportError(f"Recipe {recipe['id']}'s own import draft is kept ({backup}): it holds the model's suggestion, so no classification check.")
                    check = checks[recipe["id"]]
                    recipe["processing"]["classification_check"] = check.model_dump(mode="json", exclude={"recipe_id", "source_sha256"})
                    report.checks[recipe["id"]] = f"run {check.run_at:%Y-%m-%d %H:%M} UTC with {check.model}, {len(check.answers)} answer(s)"
        notebook = {
            "exported_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "repository_url": selection.repository_url,
            "recipes": public,
            "categories": categories,
        }
        (staging / "notebook.json").write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        engine.dispose()
    if out.exists():
        shutil.rmtree(out)
    staging.rename(out)
    return report


def _public_recipe(
    session: Session, media_root: Path, recipe: schemas.Recipe, selection: Selection, media_out: Path, report: Report
) -> dict:
    """The recipe as the public page reads it: the API's shape, holding only what the page shows."""
    data = recipe.model_dump(mode="json")
    data["issues"] = []  # review points belong to drafts; a saved recipe has none to show
    data["resolved_issues"] = []  # the notebook's own review record stays in the notebook
    shows_processing = recipe.id in selection.show_processing
    if not shows_processing:
        data["original"] = None
    data["processing"] = {"draft": None} if shows_processing else None  # the draft is looked up afterwards
    cover = next((item for item in recipe.media if item.id == recipe.cover_id), None)
    others = len(recipe.media) - (cover is not None)
    data["media"], data["cover_id"] = [], None
    if cover is not None and cover.origin == "upload":
        report.left_out.append(f"{recipe.id}: its cover is an uploaded picture (not exported: a phone photo can carry its location)")
    elif cover is not None:
        data["media"] = [_public_media(session, media_root, cover, media_out, report)]
        data["cover_id"] = cover.id
        if cover.kind == "video":
            report.left_out.append(f"{recipe.id}: the video (a still from it is shown, with the link to the post)")
    if others:
        report.left_out.append(f"{recipe.id}: {others} more picture(s) or video(s) besides the cover")
    report.recipes.append(f"{recipe.id} {recipe.title}")
    return data


def read_demonstration(path: Path, recipe: schemas.Recipe, categories: list[schemas.Category]) -> Demonstration:
    """The recorded demonstration, checked: valid, about this recipe, made from exactly its original text, and its
    evidence (the model's answer, what the rules did) consistent with that text and the recorded draft."""
    try:
        demonstration = Demonstration.model_validate_json(path.read_bytes())
    except FileNotFoundError:
        raise ExportError(f"The demonstration {path} does not exist.") from None
    except ValidationError as error:
        raise ExportError(f"{path} is not a valid demonstration: {error}") from None
    if demonstration.recipe_id != recipe.id:
        raise ExportError(f"{path} is a demonstration of recipe {demonstration.recipe_id}, not {recipe.id}.")
    if recipe.original is None or hashlib.sha256(recipe.original.text.encode()).hexdigest() != demonstration.source_sha256:
        raise ExportError(f"{path} was not made from recipe {recipe.id}'s original text.")
    original = recipe.original.text
    draft = demonstration.draft
    steps = {state: {s for g in getattr(demonstration, state).step_groups for s in g.steps} for state in ("draft", "reviewed")}
    notes = {state: set(getattr(demonstration, state).notes) for state in ("draft", "reviewed")}
    for item in demonstration.automatic:
        if item.kind == "joined_remark":
            # The rule itself joins the two lines of the original, and both the draft and the reviewed recipe hold the result.
            whole = f"{item.step} {item.remark}"
            by_rule = join_closing_remarks([schemas.StepGroup(steps=[item.step, item.remark])], original)[0].steps == [whole]
            if not (by_rule and whole in steps["draft"] and whole in steps["reviewed"]):
                raise ExportError(f"{path}: the joined remark {item.remark!r} is not what the import and its review show.")
        else:
            # The original's own words, a reference by the rule, where the draft has it (a step or a note).
            kept = steps if item.kept_as == "step" else notes
            if not (item.text in original and refers_elsewhere(item.text) and item.text in kept["draft"]):
                raise ExportError(f"{path}: the kept reference {item.text!r} is not what the original and the import show.")
    if demonstration.answer is not None:
        answer = demonstration.answer
        category_id, subcategory_id, _ = resolve_classification(answer.classification, categories)
        drafted = (draft.category.id if draft.category else None, draft.subcategory.id if draft.subcategory else None)
        if (category_id, subcategory_id) != drafted:
            raise ExportError(f"{path}: the model's classification is not the draft's category.")
        for point in answer.points:
            if point.passage is not None and point.passage not in original:
                raise ExportError(f"{path}: the model's point {point.kind} quotes words the original does not have.")
            if point.left_out == "no_alternative" and (point.kind != "ambiguous_alternative" or names_an_alternative(point.passage or "")):
                raise ExportError(f"{path}: a point left out for having no \"או\" points at a passage that has one.")
            if point.left_out is None and point.kind != "multiple_recipes" and not any(
                issue.kind == point.kind and issue.quote is not None and point.passage is not None
                and (issue.quote == point.passage or (issue.quote.endswith("…") and point.passage.startswith(issue.quote[:-1])))
                for issue in draft.issues
            ):
                raise ExportError(f"{path}: the model's point {point.kind} is not among the draft's points.")
    return demonstration


def read_classification_check(path: Path, recipe: schemas.Recipe) -> ClassificationCheck:
    """The recorded classification check, checked: valid, about this recipe, and made from exactly its original text."""
    try:
        check = ClassificationCheck.model_validate_json(path.read_bytes())
    except FileNotFoundError:
        raise ExportError(f"The classification check {path} does not exist.") from None
    except ValidationError as error:
        raise ExportError(f"{path} is not a valid classification check: {error}") from None
    if check.recipe_id != recipe.id:
        raise ExportError(f"{path} is a classification check of recipe {check.recipe_id}, not {recipe.id}.")
    if recipe.original is None or hashlib.sha256(recipe.original.text.encode()).hexdigest() != check.source_sha256:
        raise ExportError(f"{path} was not made from recipe {recipe.id}'s original text.")
    return check


def _public_media(session: Session, media_root: Path, item: schemas.RecipeMediaItem, media_out: Path, report: Report) -> dict:
    """The cover, with its picture copied beside the page: the image itself, or a video's still only."""
    picture = item.file if item.kind == "image" else item.thumbnail
    if picture is None:
        raise ExportError(f"Media item {item.id} has no picture to show.")
    row = session.get(models.MediaFile, picture.id)
    source = media.file_path(media_root, row)
    name = Path(row.path).name  # "<sha256>.<ext>": its content, nothing else
    shutil.copyfile(source, media_out / name)
    report.files += 1
    report.bytes += row.size_bytes
    ref = {**picture.model_dump(mode="json"), "url": f"media/{name}"}
    data = item.model_dump(mode="json")
    if item.kind == "image":
        return {**data, "file": ref}
    # The video itself stays on the post: the page shows its still and links there.
    return {**data, "status": "thumbnail_only", "file": None, "thumbnail": ref}


def _used_categories(categories: list[schemas.Category], recipes: list[schemas.Recipe]) -> list[dict]:
    """The categories and subcategories the exported recipes are in, without their descriptions."""
    used = {ref.id for recipe in recipes for ref in (recipe.category, recipe.subcategory) if ref is not None}
    return [
        {
            "id": category.id,
            "name": category.name,
            "description": None,
            "subcategories": [{"id": s.id, "name": s.name, "description": None} for s in category.subcategories if s.id in used],
            "healthy_style": category.healthy_style,
        }
        for category in categories
        if category.id in used
    ]


# The two subcategories that migration 0014 turned into the healthy-style attribute.
OLD_STYLES = {"קינוחים בריאים": True, "קינוחים רגילים": False}


def find_kept_draft(database_path: Path, recipe_id: int) -> tuple[KeptDraft | None, str | None]:
    """The import's own draft of the recipe, from the newest backup of the database that holds it unreviewed:
    the same recipe (same id and creation time), still a draft, and never saved since the import (its update
    time is its creation time). (None, None) when no backup holds one."""
    with closing(sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True)) as current:
        created = current.execute("SELECT created_at FROM recipes WHERE id = ?", (recipe_id,)).fetchone()[0]
    for backup in sorted(database_path.parent.glob(f"{database_path.stem}.backup-*.db"), reverse=True):
        try:
            with closing(sqlite3.connect(f"{backup.resolve().as_uri()}?mode=ro", uri=True)) as old:
                old.row_factory = sqlite3.Row
                row = old.execute(
                    "SELECT * FROM recipes WHERE id = ? AND created_at = ? AND status = 'draft' AND updated_at = created_at",
                    (recipe_id, created),
                ).fetchone()
                names = dict(old.execute("SELECT id, name FROM categories").fetchall()) if row is not None else {}
        except sqlite3.Error:
            continue  # an older layout (before drafts existed), or not a database
        if row is None:
            continue

        def ref(category_id: int | None) -> dict | None:
            return {"id": category_id, "name": names[category_id]} if category_id is not None else None

        # A backup from before migration 0014 has the healthy style as a subcategory; shown as the saved
        # recipes have it since (the same decision, the same translation), so review is not said to have changed it.
        subcategory, healthy = ref(row["subcategory_id"]), row["healthy"] if "healthy" in row.keys() else None
        if "healthy" not in row.keys() and subcategory is not None and subcategory["name"] in OLD_STYLES:
            subcategory, healthy = None, OLD_STYLES[subcategory["name"]]
        try:
            draft = KeptDraft(
                title=row["title"],
                servings=row["servings"],
                category=ref(row["category_id"]),
                subcategory=subcategory,
                healthy=None if healthy is None else bool(healthy),
                ingredient_groups=json.loads(row["ingredient_groups"]),
                step_groups=json.loads(row["step_groups"]),
                notes=json.loads(row["notes"]),
                issues=json.loads(row["issues"]),
                saved_at=datetime.fromisoformat(row["created_at"]).replace(tzinfo=UTC),
            )
        except (ValidationError, KeyError, ValueError):
            continue  # stored in a form the page cannot show as it is: not converted, not guessed
        return draft, backup.name
    return None, None


def list_candidates(database_path: Path, selection: Selection | None = None) -> list[str]:
    """One line per recipe: whether it can be published, whether the selection has it, and what it has."""
    engine = open_read_only(database_path)
    try:
        with Session(engine) as session:
            lines = ["  id  can be published  in the selection  title  (source, media, cooked mark)"]
            for recipe in crud.list_recipes(session):
                why = publishable(recipe)
                source = recipe.original.kind if recipe.original is not None else (recipe.sources[0].kind if recipe.sources else "manual")
                facts = f"{source}, {len(recipe.media)} media, {'cooked' if recipe.cooked else 'not cooked yet'}"
                chosen = "-"
                if selection is not None and recipe.id in selection.recipes:
                    chosen = "yes, compared" if recipe.id in selection.show_processing else "yes"
                lines.append(f"{recipe.id:>4}  {'yes' if why is None else 'no ':<16}  {chosen:<16}  {recipe.title}  ({facts}){'' if why is None else f'  - {why}'}")
            gone = [rid for rid in (selection.recipes if selection else []) if session.get(models.Recipe, rid) is None]
            if gone:
                lines.append(f"The selection names recipes the notebook no longer has: {', '.join(map(str, gone))}. Take them out of selection.json.")
            return lines
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the public, read-only copy of the notebook.")
    parser.add_argument("--folder", type=Path, help="holds selection.json and receives export/ (default: <data folder>/public-notebook)")
    parser.add_argument("--list", action="store_true", help="list every recipe and whether it can be published")
    args = parser.parse_args(argv)
    settings = load_settings()
    folder = args.folder or settings.data_dir / "public-notebook"
    try:
        if args.list:
            chosen = read_selection(folder / "selection.json") if (folder / "selection.json").exists() else None
            print("\n".join(list_candidates(settings.database_path, chosen)))
            return 0
        selection = read_selection(folder / "selection.json")
        out = folder / "export"
        report = export_notebook(settings.database_path, media.media_root(settings.data_dir), selection, out)
    except ExportError as error:
        print(f"Nothing exported. {error}", file=sys.stderr)
        return 1
    print(f"Exported {len(report.recipes)} recipes to {out / 'notebook.json'}:")
    print("\n".join(f"  {line}" for line in report.recipes))
    print(f"  {report.files} pictures ({report.bytes / 1_000_000:.1f} MB) in {out / 'media'}")
    for recipe_id, backup in report.drafts.items():
        kept = f"the import's draft, from {backup}" if backup else "no copy of the import's draft was kept"
        demo = f"; a demonstration, {report.demonstrations[recipe_id]}" if recipe_id in report.demonstrations else ""
        check = f"; a classification check, {report.checks[recipe_id]}" if recipe_id in report.checks else ""
        print(f"  source comparison for {recipe_id}: original text; {kept}{demo}{check}")
    if report.left_out:
        print("Left out:")
        print("\n".join(f"  {line}" for line in report.left_out))
    print("Next: npm run build:public (in frontend/), then npm run preview:public to look at it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
