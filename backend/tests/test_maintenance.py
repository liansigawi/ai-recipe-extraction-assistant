"""Bringing saved recipes up to the importer's current rules (scripts/maintain_recipes.py): the read-only audit
and its report, applying an approved batch in place (only approved fields, never over newer work, never
twice), and undoing it. A stand-in page and a stand-in classifier: nothing reaches a website or a model."""

import hashlib
import json
import sqlite3

import httpx2
import pytest

from app import schemas
from app.errors import ApiError
from app.extraction.output import Classification
from app.importers import website
from app.importers.website import WebReader
from scripts.maintain_recipes import (
    REPO_ROOT,
    MaintenanceError,
    apply_batch,
    audit,
    batch_folder,
    propose_from_page,
    propose_types,
    undo_batch,
    write_batch,
)
from tests.test_export_public import attach, new_recipe
from tests.test_media import JPEG
from tests.test_website import FLATTENED, FLATTENED_PAGE, HEBREW_GRAPH, THREE_STEPS, ld

PAGE = "https://www.example.co.il/recipes/green-noodles/"
CAKES, COOKIES = 11, 12  # dessert types (a new database's ids)
OLD_STEP = FLATTENED["recipeInstructions"]  # as the importer saved it before it checked the page's lists


@pytest.fixture
def notebook(client, data_dir):
    """A flattened website import saved long ago (cooked, with a picture and its credit); a recipe that fries in
    oil it does not list; two desserts without a type and one with; a recipe nothing applies to."""
    old = schemas.RecipeInput(
        title=FLATTENED["name"], ingredient_groups=[{"name": None, "ingredients": [{"text": t} for t in FLATTENED["recipeIngredient"]]}],
        step_groups=[{"name": None, "steps": [OLD_STEP]}], sources=[{"kind": "website", "url": PAGE, "creators": [{"name": "צלמת האתר"}]}],
        category_id=3, status="saved",
    )
    as_read = website.read_recipe(FLATTENED, PAGE, "json_ld")
    as_read.step_groups = [(None, [OLD_STEP])]  # the import's own text, from before the cleaning
    original = website.render(as_read)
    with client.app.state.session_factory() as session:
        from app import crud

        noodles = crud.create_import(session, old, original_text=original, model="qwen3:8b", kind="website", url=PAGE,
                                     retrieved_from="json_ld", source_details={"author": {"name": "צלמת האתר", "username": None}, "structured_data": FLATTENED})
    attach(client, data_dir, noodles.id, kind="image", file=JPEG, origin="website", post_url=PAGE, is_cover=True)
    client.put(f"/api/recipes/{noodles.id}/cooked", json={"cooked": True}, headers={"Origin": "http://localhost:5173"})
    omelette = new_recipe(client, "חביתה", category_id=3, ingredient_groups=[{"name": None, "ingredients": [{"text": "3 ביצים", "quantity": "3"}]}],
                          step_groups=[{"name": None, "steps": ["מחממים מעט שמן במחבת.", "יוצקים פנימה את הביצים."]}])
    cake = new_recipe(client, "עוגת שוקולד", healthy=False)
    cookies = new_recipe(client, "עוגיות", healthy=True)
    typed = new_recipe(client, "עוגת גבינה", subcategory_id=CAKES)
    salad = new_recipe(client, "סלט", category_id=7)
    return {"noodles": noodles.id, "omelette": omelette["id"], "cake": cake["id"], "cookies": cookies["id"], "typed": typed["id"], "salad": salad["id"]}


def reader() -> WebReader:
    page = httpx2.Response(200, headers={"content-type": "text/html; charset=utf-8"},
                           content=f"<html><head>{ld(FLATTENED)}</head><body>{FLATTENED_PAGE}</body></html>".encode())
    return WebReader(transport=httpx2.MockTransport(lambda request: page), resolve=lambda host: ["93.184.216.34"], verify_peer=False)


class Classifier:
    """Cakes for "עוגת שוקולד"; for anything else, a different type each time (two runs disagree)."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, draft: schemas.RecipeInput, categories) -> Classification:
        self.calls += 1
        sub = CAKES if draft.title == "עוגת שוקולד" else (CAKES if self.calls % 2 else COOKIES)
        return Classification(fit="clear", category_id=1, subcategory_id=sub, candidate_category_ids=[])


@pytest.fixture
def batch(notebook, data_dir, tmp_path):
    folder = tmp_path / "maintenance" / "batch-1"
    write_batch(audit(data_dir / "recipes.db", reader(), Classifier(), out=lambda _: None), folder)
    return folder


def changes(folder) -> dict[str, dict]:
    return {c["id"]: c for r in json.loads((folder / "batch.json").read_text(encoding="utf-8"))["recipes"] for c in r["changes"]}


def table(data_dir, name: str) -> list[tuple]:
    with sqlite3.connect(data_dir / "recipes.db") as db:
        return db.execute(f"SELECT * FROM {name} ORDER BY id").fetchall()


def recipe(client, recipe_id: int) -> dict:
    return client.get(f"/api/recipes/{recipe_id}").json()


def test_the_audit_proposes_only_what_the_sources_support_and_changes_nothing(notebook, data_dir, tmp_path):
    before = hashlib.sha256((data_dir / "recipes.db").read_bytes()).hexdigest()
    folder = tmp_path / "batch"
    write_batch(audit(data_dir / "recipes.db", reader(), Classifier(), out=lambda _: None), folder)
    assert hashlib.sha256((data_dir / "recipes.db").read_bytes()).hexdigest() == before  # opened read-only
    found = changes(folder)
    n, o, c = notebook["noodles"], notebook["omelette"], notebook["cake"]
    assert sorted(found) == sorted([f"{n}-steps", f"{n}-ingredients", f"{o}-oil", f"{c}-type"])
    assert found[f"{n}-steps"]["after"] == [{"name": None, "steps": THREE_STEPS}]
    assert any("3 items" in line for line in found[f"{n}-steps"]["evidence"])  # the page's own list
    assert "no sign of an edit" in found[f"{n}-steps"]["uncertainty"]  # the saved step is the import's own
    assert [g["name"] for g in found[f"{n}-ingredients"]["after"]] == ["רוטב", "מוקפץ"]
    assert found[f"{o}-oil"]["after"] == [{"text": "מעט שמן לטיגון", "quantity": "מעט", "derived_from": "מחממים מעט שמן במחבת."}]
    assert found[f"{c}-type"]["after"] == {"id": CAKES, "name": "עוגות"}
    data = json.loads((folder / "batch.json").read_text(encoding="utf-8"))
    assert [u["id"] for u in data["unresolved"]] == [notebook["cookies"]]  # two answers that disagree: no type
    assert {r["id"] for r in data["no_change"]} >= {notebook["typed"], notebook["salad"]}  # a type you set stays
    assert json.loads((folder / "before.json").read_text(encoding="utf-8"))["label"] == "before this maintenance update"
    assert "nothing applied yet" in (folder / "report.html").read_text(encoding="utf-8")


def test_applying_changes_only_the_approved_fields_in_place_and_keeps_everything_else(client, notebook, batch, data_dir):
    n = notebook["noodles"]
    keep = {name: table(data_dir, name) for name in ("recipe_imports", "recipe_media", "recipe_sources", "media_files")}
    then = recipe(client, n)
    log = apply_batch(data_dir / "recipes.db", batch, exclude=[f"{n}-ingredients"], out=lambda _: None)
    assert sorted(item["id"] for item in log["applied"]) == sorted([n, notebook["omelette"], notebook["cake"]])
    now = recipe(client, n)
    assert now["step_groups"] == [{"name": None, "steps": THREE_STEPS}]
    assert now["ingredient_groups"] == then["ingredient_groups"]  # left out: unchanged
    for field in ("id", "title", "status", "cooked", "category", "healthy", "sources", "media", "cover_id", "original", "created_at"):
        assert now[field] == then[field], field
    assert now["updated_at"] > then["updated_at"]
    assert {name: table(data_dir, name) for name in keep} == keep  # originals, media, credits: not a row touched
    assert recipe(client, notebook["cake"])["subcategory"] == {"id": CAKES, "name": "עוגות"}
    assert recipe(client, notebook["cake"])["healthy"] is False  # the healthy style stays yours
    assert list(data_dir.glob("recipes.backup-*-before-maintenance-batch-1.db"))


def test_the_backup_is_verified_and_holds_the_notebook_as_it_was(client, notebook, batch, data_dir):
    before = table(data_dir, "recipes")
    log = apply_batch(data_dir / "recipes.db", batch, out=lambda _: None)
    with sqlite3.connect(log["backup"]) as copy:
        assert copy.execute("SELECT * FROM recipes ORDER BY id").fetchall() == before


def test_a_recipe_changed_after_the_report_is_skipped_and_named_never_overwritten(client, notebook, batch, data_dir):
    o = notebook["omelette"]
    mine = {**recipe(client, o), "notes": ["אני מוסיפה עירית."]}
    body = {k: mine[k] for k in ("title", "servings", "ingredient_groups", "step_groups", "notes", "sources", "status", "issues")}
    client.put(f"/api/recipes/{o}", json={**body, "category_id": 3}, headers={"Origin": "http://localhost:5173"})
    log = apply_batch(data_dir / "recipes.db", batch, out=lambda _: None)
    assert [item["id"] for item in log["skipped"]] == [o] and "changed after the report" in log["skipped"][0]["why"]
    assert recipe(client, o)["notes"] == ["אני מוסיפה עירית."] and len(recipe(client, o)["ingredient_groups"][0]["ingredients"]) == 1


def test_applying_the_same_batch_again_adds_nothing_twice(client, notebook, batch, data_dir):
    apply_batch(data_dir / "recipes.db", batch, out=lambda _: None)
    first = table(data_dir, "recipes")
    again = apply_batch(data_dir / "recipes.db", batch, out=lambda _: None)
    assert again["applied"] == [] and len(again["already_applied"]) == 3
    assert table(data_dir, "recipes") == first
    lines = [i["text"] for g in recipe(client, notebook["omelette"])["ingredient_groups"] for i in g["ingredients"]]
    assert lines.count("מעט שמן לטיגון") == 1


def test_what_was_left_out_can_be_applied_later_on_top(client, notebook, batch, data_dir):
    n = notebook["noodles"]
    apply_batch(data_dir / "recipes.db", batch, only=[f"{n}-steps"], out=lambda _: None)
    later = apply_batch(data_dir / "recipes.db", batch, out=lambda _: None)
    assert n in [item["id"] for item in later["applied"]]
    now = recipe(client, n)
    assert now["step_groups"] == [{"name": None, "steps": THREE_STEPS}] and [g["name"] for g in now["ingredient_groups"]] == ["רוטב", "מוקפץ"]


def test_undo_puts_back_what_the_batch_wrote_and_leaves_your_later_edits(client, notebook, batch, data_dir):
    before = {key: recipe(client, rid) for key, rid in notebook.items()}
    apply_batch(data_dir / "recipes.db", batch, out=lambda _: None)
    c = notebook["cake"]
    edited = recipe(client, c)
    body = {k: edited[k] for k in ("title", "servings", "ingredient_groups", "step_groups", "notes", "sources", "status", "issues", "healthy")}
    client.put(f"/api/recipes/{c}", json={**body, "title": "עוגת שוקולד שלי", "category_id": 1, "subcategory_id": COOKIES},
               headers={"Origin": "http://localhost:5173"})
    result = undo_batch(data_dir / "recipes.db", batch, out=lambda _: None)
    assert sorted(result["restored"]) == sorted([notebook["noodles"], notebook["omelette"]])
    assert [item["id"] for item in result["skipped"]] == [c]  # edited after the batch: yours, left as it is
    for key in ("noodles", "omelette"):
        assert recipe(client, notebook[key]) == before[key]  # updated_at too
    assert recipe(client, c)["title"] == "עוגת שוקולד שלי"
    assert undo_batch(data_dir / "recipes.db", batch, out=lambda _: None)["restored"] == []  # twice: nothing more


def test_an_unknown_change_is_refused_before_anything_is_backed_up_or_changed(notebook, batch, data_dir):
    before = table(data_dir, "recipes")
    with pytest.raises(MaintenanceError, match="no change 999-steps"):
        apply_batch(data_dir / "recipes.db", batch, exclude=["999-steps"], out=lambda _: None)
    assert table(data_dir, "recipes") == before and not list(data_dir.glob("recipes.backup-*maintenance*"))


def test_without_reading_the_page_only_the_saved_data_s_own_cleaning_is_proposed(notebook, data_dir, tmp_path):
    data = audit(data_dir / "recipes.db", None, None, out=lambda _: None)
    n = notebook["noodles"]
    [entry] = [r for r in data["recipes"] if r["id"] == n]
    [steps] = [c for c in entry["changes"] if c["kind"] == "steps"]
    [[step]] = [g["steps"] for g in steps["after"]]
    assert "caption" not in step and "בשיתוף" not in step and step.startswith("אופן הכנה")  # cleaned, never split
    assert any("not read" in line for line in steps["evidence"])
    assert all(c["kind"] != "type" for r in data["recipes"] for c in r["changes"])  # no classifier: no types


def test_a_type_alone_leaves_the_rest_of_the_record_exactly_as_stored(client, notebook, data_dir, tmp_path):
    cake = notebook["cake"]
    stored = '[{"name": null, "ingredients": [{"text": "200 גרם קמח", "quantity": "200 גרם"}]}]'  # saved before "derived_from"
    with sqlite3.connect(data_dir / "recipes.db") as db:
        db.execute("UPDATE recipes SET ingredient_groups = ? WHERE id = ?", (stored, cake))
    folder = tmp_path / "batch"
    write_batch(audit(data_dir / "recipes.db", reader(), Classifier(), out=lambda _: None), folder)
    apply_batch(data_dir / "recipes.db", folder, only=[f"{cake}-type"], out=lambda _: None)
    with sqlite3.connect(data_dir / "recipes.db") as db:
        assert db.execute("SELECT ingredient_groups, subcategory_id FROM recipes WHERE id = ?", (cake,)).fetchone() == (stored, CAKES)


def test_undo_uses_only_what_was_applied_to_that_notebook(client, notebook, batch, data_dir, tmp_path):
    copy = tmp_path / "copy.db"
    with sqlite3.connect(data_dir / "recipes.db") as live, sqlite3.connect(copy) as target:
        live.backup(target)
    apply_batch(copy, batch, out=lambda _: None)  # a test copy, with the same batch
    with pytest.raises(MaintenanceError, match="was applied to"):
        undo_batch(data_dir / "recipes.db", batch, out=lambda _: None)  # the notebook itself was never changed
    assert undo_batch(copy, batch, out=lambda _: None)["restored"]


def test_a_second_apply_in_the_same_second_keeps_the_first_one_s_log_for_undo(client, notebook, batch, data_dir):
    before = recipe(client, notebook["omelette"])
    apply_batch(data_dir / "recipes.db", batch, out=lambda _: None)
    apply_batch(data_dir / "recipes.db", batch, out=lambda _: None)  # nothing to add: a log of its own, beside the first
    assert len(list(batch.glob("applied-*.json"))) == 2
    undo_batch(data_dir / "recipes.db", batch, out=lambda _: None)
    assert recipe(client, notebook["omelette"]) == before


def test_a_batch_is_found_by_its_path_from_the_project_root_or_by_its_id(batch, data_dir, monkeypatch):
    monkeypatch.chdir(REPO_ROOT / "backend")  # where maintain-recipes.cmd runs the script
    assert batch_folder(batch, data_dir) == batch
    moved = data_dir / "maintenance" / "20990101-000000"
    moved.parent.mkdir(parents=True, exist_ok=True)
    batch.rename(moved)
    assert batch_folder(type(batch)("20990101-000000"), data_dir) == moved


def test_the_report_says_which_changes_are_applied_and_which_are_still_proposals(client, notebook, data_dir, tmp_path):
    folder = tmp_path / "batch"
    batch = audit(data_dir / "recipes.db", reader(), Classifier(), out=lambda _: None)
    write_batch(batch, folder)
    apply_batch(data_dir / "recipes.db", folder, only=[f"{notebook['omelette']}-oil"], out=lambda _: None)
    report = (folder / "report.html").read_text(encoding="utf-8")
    assert "1 of 4 changes applied" in report and report.count("APPLIED to the notebook") == 1 and report.count(">proposal<") == 3
    undo_batch(data_dir / "recipes.db", folder, out=lambda _: None)
    assert "nothing applied yet" in (folder / "report.html").read_text(encoding="utf-8")


def test_reviewed_types_become_a_batch_that_says_what_each_rests_on(client, notebook, data_dir, tmp_path):
    reviewed = {"basis": "Reviewed by hand.", "assignments": [
        {"id": notebook["cake"], "type": "עוגות", "basis": "The local classifier's proposal, confirmed in review."},
        {"id": notebook["cookies"], "type": "עוגיות וחיתוכיות", "basis": "Assigned in review (the classifier's two answers differed).", "note": "Cookies."},
        {"id": notebook["typed"], "type": "עוגות", "basis": "x"},  # you set its type already: left alone
        {"id": notebook["salad"], "type": "עוגות", "basis": "x"},  # not a dessert
    ]}
    with pytest.raises(MaintenanceError, match="no dessert type"):
        propose_types(data_dir / "recipes.db", {"basis": "x", "assignments": [{"id": notebook["cake"], "type": "פחזניות", "basis": "x"}]}, out=lambda _: None)
    folder = tmp_path / "types"
    write_batch(propose_types(data_dir / "recipes.db", reviewed, out=lambda _: None), folder)
    found = changes(folder)
    assert sorted(found) == sorted([f"{notebook['cake']}-type", f"{notebook['cookies']}-type"])
    assert found[f"{notebook['cookies']}-type"]["evidence"][-1].startswith("Assigned in review")
    apply_batch(data_dir / "recipes.db", folder, out=lambda _: None)
    assert recipe(client, notebook["cookies"])["subcategory"] == {"id": COOKIES, "name": "עוגיות וחיתוכיות"}
    assert recipe(client, notebook["typed"])["subcategory"]["id"] == CAKES and recipe(client, notebook["salad"])["subcategory"] is None


def test_proposals_a_reviewed_batch_replaced_are_never_applied_from_the_old_one(client, notebook, batch, data_dir):
    data = json.loads((batch / "batch.json").read_text(encoding="utf-8"))
    cake = f"{notebook['cake']}-type"
    data["superseded"] = {"changes": [cake], "by": "later-types"}
    (batch / "batch.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(MaintenanceError, match="replaced by the batch later-types"):
        apply_batch(data_dir / "recipes.db", batch, only=[cake], out=lambda _: None)
    log = apply_batch(data_dir / "recipes.db", batch, out=lambda _: None)
    assert recipe(client, notebook["cake"])["subcategory"] is None and all(cake not in item["changes"] for item in log["applied"])


# --- Completing a saved recipe from a page that holds it ----------------------------------------------------------

POST_URL = "https://www.instagram.com/p/ABC123/"


@pytest.fixture
def from_post(client, data_dir):
    """A saved post import whose caption had no recipe (it sends you to the creator's site): cooked, with a video."""
    with client.app.state.session_factory() as session:
        from app import crud

        post = crud.create_import(session, schemas.RecipeInput(
            title="עוגת תפוזים ושקדים", sources=[{"kind": "instagram", "url": POST_URL, "creators": [{"name": "רותי כהן", "username": "ruti"}]}],
            category_id=1, subcategory_id=CAKES, healthy=False, status="saved"), original_text="עוגת תפוזים! המתכון המלא באתר", model="qwen3:8b",
            kind="instagram", url=POST_URL)
    attach(client, data_dir, post.id, kind="image", file=JPEG, origin="instagram", post_url=POST_URL, is_cover=True)
    client.put(f"/api/recipes/{post.id}/cooked", json={"cooked": True}, headers={"Origin": "http://localhost:5173"})
    return post.id


def page_reader(body: str, head: str) -> WebReader:
    def answer(request):
        if request.url.path.endswith(".jpg"):
            return httpx2.Response(404)
        return httpx2.Response(200, headers={"content-type": "text/html; charset=utf-8"}, content=f"<html><head>{head}</head><body>{body}</body></html>".encode())

    return WebReader(transport=httpx2.MockTransport(answer), resolve=lambda host: ["93.184.216.34"], verify_peer=False)


def completion(data_dir, recipe_id, **extra):
    from tests.test_api_website import Classifier as PageClassifier

    reader = page_reader("<h1>עוגת תפוזים ושקדים</h1>", ld(HEBREW_GRAPH) + '<meta property="og:site_name" content="המטבח של רותי">')
    return propose_from_page(data_dir / "recipes.db", recipe_id, PAGE, reader, PageClassifier, out=lambda _: None, **extra)


def test_a_recipe_is_completed_from_its_page_in_place_with_the_page_as_one_more_source(client, from_post, data_dir, tmp_path):
    kept = {name: table(data_dir, name) for name in ("recipes", "recipe_sources", "recipe_imports", "recipe_media", "media_files")}
    folder = tmp_path / "maintenance" / "page"
    write_batch(completion(data_dir, from_post), folder)
    assert {name: table(data_dir, name) for name in kept} == kept  # read-only: no draft, nothing written
    found = changes(folder)
    assert sorted(found) == sorted(f"{from_post}-{kind}" for kind in ("ingredients", "steps", "notes", "source"))
    assert found[f"{from_post}-steps"]["after"] == found[f"{from_post}-steps"]["draft"]  # unreviewed: the import's own draft
    assert "The import's draft" in (folder / "report.html").read_text(encoding="utf-8")
    before = recipe(client, from_post)

    log = apply_batch(data_dir / "recipes.db", folder, out=lambda _: None)
    assert [item["id"] for item in log["applied"]] == [from_post]
    after = recipe(client, from_post)
    assert [i["text"] for g in after["ingredient_groups"] for i in g["ingredients"]] == ["200 גרם קמח", "2 ביצים L", "מיץ מ-3 תפוזים", "קורט מלח"]
    assert [g["name"] for g in after["step_groups"]] == ["לבצק", "אפייה"]
    assert [s["kind"] for s in after["sources"]] == ["instagram", "website"] and after["sources"][1]["creators"][0]["name"] == "רותי כהן"
    for key in ("title", "category", "subcategory", "healthy", "status", "issues", "cooked", "original", "media", "cover_id", "created_at"):
        assert after[key] == before[key], key
    assert table(data_dir, "recipe_imports") == kept["recipe_imports"]  # the post's import, as it was
    assert table(data_dir, "recipe_sources")[0] == kept["recipe_sources"][0]  # the post's source row, untouched
    assert apply_batch(data_dir / "recipes.db", folder, out=lambda _: None)["already_applied"]  # never twice

    undo_batch(data_dir / "recipes.db", folder, out=lambda _: None)
    assert {name: table(data_dir, name) for name in ("recipe_sources", "recipe_imports", "recipe_media")} == {k: kept[k] for k in ("recipe_sources", "recipe_imports", "recipe_media")}
    assert recipe(client, from_post) == before


def test_a_reviewed_version_may_correct_the_draft_but_holds_only_the_page_s_lines(client, from_post, data_dir):
    draft = changes_of(completion(data_dir, from_post))
    steps = draft[f"{from_post}-steps"]["draft"]
    reviewed = {"recipe_id": from_post, "basis": "Reviewed against the page.", "ingredient_groups": draft[f"{from_post}-ingredients"]["draft"],
                "step_groups": [{"name": None, "steps": [s for g in steps for s in g["steps"]]}], "notes": [],
                "differences": {"steps": ["one list of steps"], "notes": ["the times left out"]}}
    batch = completion(data_dir, from_post, reviewed=reviewed)
    found = changes_of(batch)
    assert found[f"{from_post}-steps"]["after"] == reviewed["step_groups"] and found[f"{from_post}-steps"]["draft"] == steps
    assert f"{from_post}-notes" not in found  # the recipe has no notes, and the reviewed version none either
    assert "Corrected in review: one list of steps" in found[f"{from_post}-steps"]["evidence"]

    invented = {**reviewed, "notes": ["אפשר להוסיף שוקולד צ'יפס"]}
    with pytest.raises(MaintenanceError, match="not in the text read from the page"):
        completion(data_dir, from_post, reviewed=invented)
    # A label around the page's own words is allowed only when declared, and only around words of the page.
    labeled = {**reviewed, "notes": ["זמן שהאתר מציין: 10 פרוסות"], "labeled": {"זמן שהאתר מציין: 10 פרוסות": "10 פרוסות"}}
    found = changes_of(completion(data_dir, from_post, reviewed=labeled))
    assert found[f"{from_post}-notes"]["after"] == ["זמן שהאתר מציין: 10 פרוסות"]
    assert any(e.startswith("Labeled in review (only \"10 פרוסות\"") for e in found[f"{from_post}-notes"]["evidence"])
    with pytest.raises(MaintenanceError, match="not in the text read from the page"):
        completion(data_dir, from_post, reviewed={**labeled, "labeled": {}})
    with pytest.raises(MaintenanceError, match="not in the text read from the page"):
        completion(data_dir, from_post, reviewed={**labeled, "notes": ["זמן שהאתר מציין: 12 פרוסות"], "labeled": {"זמן שהאתר מציין: 12 פרוסות": "12 פרוסות"}})
    wrong_amount = {**reviewed, "ingredient_groups": [{"name": None, "ingredients": [{"text": "200 גרם קמח", "quantity": "300 גרם"}]}]}
    with pytest.raises(MaintenanceError, match="not valid"):
        completion(data_dir, from_post, reviewed=wrong_amount)


def test_a_page_without_a_complete_recipe_proposes_nothing(client, from_post, data_dir):
    from tests.test_api_website import Classifier as PageClassifier

    reader = page_reader("<article><h1>עוגת תפוזים</h1><p>" + "מילים על עוגות. " * 20 + "</p></article>", "")
    with pytest.raises(MaintenanceError, match="no complete recipe"):
        propose_from_page(data_dir / "recipes.db", from_post, PAGE, reader, lambda: PageClassifier(ApiError(422, "not_a_recipe", "none")), out=lambda _: None)


def changes_of(batch: dict) -> dict[str, dict]:
    return {c["id"]: c for r in batch["recipes"] for c in r["changes"]}


TORTE = "טורט וניל\n4 ביצים\nאופן הכנה-\nמעבירים לתבנית, אופים 50-60 דקות על 150 מעלות\n (כל תנור עובד אחרת, כדאי לשים לב לעוגה בהתאם לתנור שלכם).\nלקשט בתותים."
TORTE_STEPS = ["מעבירים לתבנית, אופים 50-60 דקות על 150 מעלות", "(כל תנור עובד אחרת, כדאי לשים לב לעוגה בהתאם לתנור שלכם).", "לקשט בתותים."]


def test_a_saved_remark_that_ends_a_step_is_proposed_joined_and_applied_alone(client, data_dir, tmp_path):
    from app import crud

    saved = schemas.RecipeInput(
        title="טורט וניל", category_id=1, subcategory_id=CAKES, healthy=False, status="saved",
        ingredient_groups=[{"name": None, "ingredients": [{"text": "4 ביצים", "quantity": "4"}]}, {"name": "קישוט", "ingredients": [{"text": "תותים"}]}],
        step_groups=[{"name": "אופן הכנה", "steps": TORTE_STEPS}],
        sources=[{"kind": "instagram", "url": "https://www.instagram.com/p/Cm1mCdCpSzJ/", "creators": [{"name": "ריטה קדוש", "username": "ritakadosh_"}]}],
    )
    with client.app.state.session_factory() as session:
        torte = crud.create_import(session, saved, original_text=TORTE, model="qwen3:8b", kind="instagram", url=saved.sources[0].url)
    attach(client, data_dir, torte.id, kind="image", file=JPEG, origin="instagram", post_url=saved.sources[0].url, is_cover=True)
    client.put(f"/api/recipes/{torte.id}/cooked", json={"cooked": True}, headers={"Origin": "http://localhost:5173"})
    folder = tmp_path / "batch"
    write_batch(audit(data_dir / "recipes.db", None, None, out=lambda _: None), folder)

    found = changes(folder)
    assert [key for key in found if key.startswith(f"{torte.id}-")] == [f"{torte.id}-steps"]
    joined = f"{TORTE_STEPS[0]} {TORTE_STEPS[1]}"
    assert found[f"{torte.id}-steps"]["after"] == [{"name": "אופן הכנה", "steps": [joined, TORTE_STEPS[2]]}]
    assert "on its next line" in found[f"{torte.id}-steps"]["evidence"][0]

    before = recipe(client, torte.id)
    sources, imports, media = table(data_dir, "recipe_sources"), table(data_dir, "recipe_imports"), table(data_dir, "recipe_media")
    log = apply_batch(data_dir / "recipes.db", folder, only=[f"{torte.id}-steps"], out=lambda _: None)
    assert [item["id"] for item in log["applied"]] == [torte.id]
    after = recipe(client, torte.id)
    assert after["step_groups"] == [{"name": "אופן הכנה", "steps": [joined, TORTE_STEPS[2]]}]
    unchanged = ("id", "title", "category", "subcategory", "healthy", "ingredient_groups", "notes", "sources", "cooked", "original", "media", "cover_id", "created_at")
    assert {key: after[key] for key in unchanged} == {key: before[key] for key in unchanged}
    assert (table(data_dir, "recipe_sources"), table(data_dir, "recipe_imports"), table(data_dir, "recipe_media")) == (sources, imports, media)

    undo_batch(data_dir / "recipes.db", folder, out=lambda _: None)
    assert recipe(client, torte.id)["step_groups"] == before["step_groups"]


DONUTS = (
    "איזה שם מתאים יותר?\n|קרם:\n500 גר׳ חלב\n|בצק הסופגניות הקלאסי שלי - נמצא בבלוג ובפיד, לעשות בדיוק לפי ההוראות.\n|קרמל:\n500 גר׳ סוכר\n"
    "|אופן ההכנה:\nמבשלים את החלב לקרם. מעבירים לשקית זילוף.\n"
    "מכינים בצק סופגניות לפי המתכון לבצק סופגניות קלאסי שלי מהבלוג. עושים הכל לפי ההוראות כולל הטיגון.\n"
    "ממלאים כל סופגניה בקרם.\nמכינים קרמל. יש להיזהר לא לשרוף את הקרמל.\nבתיאבון 💕\n#סופגניות"
)


def test_a_saved_recipe_gets_back_its_reference_to_a_separate_recipe_where_the_original_has_it(client, data_dir, tmp_path):
    from app import crud

    saved = schemas.RecipeInput(
        title="סופגניות", category_id=1, subcategory_id=16, healthy=False, status="saved",
        ingredient_groups=[{"name": "קרם", "ingredients": [{"text": "500 גר׳ חלב"}]}, {"name": "קרמל", "ingredients": [{"text": "500 גר׳ סוכר"}]}],
        step_groups=[{"name": None, "steps": ["מבשלים את החלב לקרם.", "מעבירים לשקית זילוף.", "ממלאים כל סופגניה בקרם.", "מכינים קרמל."]}],
        notes=["יש להיזהר לא לשרוף את הקרמל."],
        sources=[{"kind": "instagram", "url": "https://www.instagram.com/p/DDTyJa_oNZm/", "creators": []}],
    )
    with client.app.state.session_factory() as session:
        donuts = crud.create_import(session, saved, original_text=DONUTS, model="qwen3:8b", kind="instagram", url=saved.sources[0].url)
    folder = tmp_path / "batch"
    write_batch(audit(data_dir / "recipes.db", None, None, out=lambda _: None), folder)

    found = changes(folder)
    assert sorted(key for key in found if key.startswith(f"{donuts.id}-")) == [f"{donuts.id}-notes", f"{donuts.id}-steps"]
    dough = "מכינים בצק סופגניות לפי המתכון לבצק סופגניות קלאסי שלי מהבלוג. עושים הכל לפי ההוראות כולל הטיגון."
    assert found[f"{donuts.id}-steps"]["after"] == [{"name": None, "steps": [
        "מבשלים את החלב לקרם.", "מעבירים לשקית זילוף.", dough, "ממלאים כל סופגניה בקרם.", "מכינים קרמל."]}]
    assert found[f"{donuts.id}-notes"]["after"] == ["בצק הסופגניות הקלאסי שלי - נמצא בבלוג ובפיד, לעשות בדיוק לפי ההוראות.", "יש להיזהר לא לשרוף את הקרמל."]
    assert "no ingredient, amount, instruction or link" in found[f"{donuts.id}-notes"]["uncertainty"]

    before = recipe(client, donuts.id)
    apply_batch(data_dir / "recipes.db", folder, only=[f"{donuts.id}-steps", f"{donuts.id}-notes"], out=lambda _: None)
    after = recipe(client, donuts.id)
    assert after["step_groups"][0]["steps"][2] == dough and after["notes"][0].startswith("בצק הסופגניות")
    kept = ("title", "category", "subcategory", "healthy", "ingredient_groups", "sources", "cooked", "original", "media")
    assert {key: after[key] for key in kept} == {key: before[key] for key in kept}

    write_batch(audit(data_dir / "recipes.db", None, None, out=lambda _: None), tmp_path / "again")
    assert not [key for key in changes(tmp_path / "again") if key.startswith(f"{donuts.id}-")]  # nothing twice
