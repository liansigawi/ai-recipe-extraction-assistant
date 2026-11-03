"""The public copy's export (scripts/export_public.py): only chosen saved recipes, only what the public page
shows, the notebook opened read-only, and an import's draft only when a backup really kept it."""

import hashlib
import sqlite3
import json
from pathlib import Path

import pytest

from app import media, models
from app.db import utc_now
from app.migrate import backup_database, upgrade_database
from scripts.export_public import ExportError, Selection, export_notebook, find_kept_draft, main
from tests.test_media import JPEG, MP4, PNG

ORIGIN = {"Origin": "http://localhost:5173"}
SOURCE = "לימונדה של קיץ\n2 לימונים\n3 כוסות מים\nסוחטים ומערבבים."


def category_id(client, name: str) -> int:
    return next(c["id"] for c in client.get("/api/categories").json() if c["name"] == name)


def new_recipe(client, title: str, **fields) -> dict:
    body = {
        "title": title,
        "ingredient_groups": [{"name": None, "ingredients": [{"text": "200 גרם קמח", "quantity": "200 גרם"}]}],
        "step_groups": [{"name": None, "steps": ["מערבבים ואופים."]}],
        "sources": [{"kind": "website", "url": "https://example.com/cake", "creators": [{"name": "Example Kitchen", "username": None}]}],
        "category_id": category_id(client, "קינוחים"),
        **fields,
    }
    response = client.post("/api/recipes", json=body, headers=ORIGIN)
    assert response.status_code == 201, response.text
    return response.json()


def attach(client, data_dir: Path, recipe_id: int, **fields) -> None:
    """A media item written straight to the database, as an import would leave it."""
    root = media.media_root(data_dir)
    with client.app.state.session_factory() as session:
        files = {}
        for key in ("file", "thumbnail"):
            data = fields.pop(key, None)
            if data is not None:
                stored = media.store_bytes(root, data, media.IMAGES | media.VIDEOS)
                row = models.MediaFile(sha256=stored.sha256, path=stored.path, content_type=stored.content_type, size_bytes=stored.size_bytes, created_at=utc_now())
                session.add(row)
                session.flush()
                files[f"{key}_id" if key == "file" else "thumbnail_file_id"] = row.id
        session.add(models.RecipeMedia(recipe_id=recipe_id, status="saved", created_at=utc_now(), **files, **fields))
        session.commit()


@pytest.fixture
def notebook(client, data_dir):
    """A notebook with: a pasted text whose draft a backup kept before it was saved; a recipe with a page's
    picture and an upload; one whose only picture is an upload; one with a post's video; a draft; the samples."""
    draft = client.post("/api/imports/text", json={"text": SOURCE, "use_model": False}, headers=ORIGIN).json()
    backup_database(data_dir / "recipes.db", "before-test")
    fixed = {
        "title": "לימונדה",
        "ingredient_groups": [{"name": None, "ingredients": [{"text": "2 לימונים", "quantity": "2"}, {"text": "3 כוסות מים", "quantity": "3 כוסות"}]}],
        "step_groups": [{"name": None, "steps": ["סוחטים ומערבבים."]}],
        "notes": [],
        "sources": draft["sources"],
        "category_id": category_id(client, "משקאות"),
        "status": "saved",
        "issues": [],
    }
    lemonade = client.put(f"/api/recipes/{draft['id']}", json=fixed, headers=ORIGIN).json()
    client.put(f"/api/recipes/{lemonade['id']}/cooked", json={"cooked": True}, headers=ORIGIN)

    cake = new_recipe(client, "עוגת תפוזים")
    attach(client, data_dir, cake["id"], kind="image", file=JPEG, origin="website", post_url="https://example.com/cake")
    client.post(f"/api/recipes/{cake['id']}/media", content=PNG, headers=ORIGIN)
    uploaded = new_recipe(client, "עוגיות", category_id=None)
    client.post(f"/api/recipes/{uploaded['id']}/media", content=PNG, headers=ORIGIN)
    reel = new_recipe(client, "טורט", sources=[{"kind": "instagram", "url": "https://www.instagram.com/p/abc/", "creators": [{"name": None, "username": "baker"}]}])
    attach(client, data_dir, reel["id"], kind="video", file=MP4, thumbnail=JPEG + b"still", origin="instagram", post_url="https://www.instagram.com/p/abc/", post_shortcode="abc", post_index=0)
    still_draft = client.post("/api/imports/text", json={"text": "עוד מתכון\nכוס קמח", "use_model": False}, headers=ORIGIN).json()
    return {"lemonade": lemonade, "draft": draft, "cake": cake, "uploaded": uploaded, "reel": reel, "still_draft": still_draft}


def export(data_dir: Path, out: Path, **selection) -> tuple[dict, object]:
    report = export_notebook(data_dir / "recipes.db", media.media_root(data_dir), Selection(**selection), out)
    return json.loads((out / "notebook.json").read_text(encoding="utf-8")), report


def test_only_the_chosen_saved_recipes_and_only_what_the_page_shows(notebook, data_dir, tmp_path):
    ids = {name: notebook[name]["id"] for name in ("lemonade", "cake", "uploaded", "reel")}
    before = hashlib.sha256((data_dir / "recipes.db").read_bytes()).hexdigest()
    out = tmp_path / "public" / "export"
    data, report = export(data_dir, out, recipes=list(ids.values()), show_processing=[ids["lemonade"]], repository_url="https://github.com/example/recipes")

    assert hashlib.sha256((data_dir / "recipes.db").read_bytes()).hexdigest() == before  # opened read-only
    assert data["repository_url"] == "https://github.com/example/recipes"
    assert [r["id"] for r in data["recipes"]] == sorted(ids.values(), reverse=True)  # newest first, as the app lists them
    by_id = {r["id"]: r for r in data["recipes"]}
    for recipe in data["recipes"]:
        assert recipe["status"] == "saved" and not recipe["is_sample"] and recipe["issues"] == []
    # The categories the recipes are in, without the descriptions written for the model.
    assert {c["name"] for c in data["categories"]} == {"קינוחים", "משקאות"}
    assert all(c["description"] is None and all(s["description"] is None for s in c["subcategories"]) for c in data["categories"])
    assert all(c["subcategories"] == [] for c in data["categories"])  # none of these recipes is in a subcategory

    # The original text only where the comparison is shown.
    assert by_id[ids["lemonade"]]["original"]["text"] == SOURCE and by_id[ids["lemonade"]]["cooked"] is True
    assert all(by_id[i]["original"] is None and by_id[i]["processing"] is None for i in (ids["cake"], ids["uploaded"], ids["reel"]))

    # Only the cover: the page's picture (not the upload beside it); nothing for an uploaded cover; a video's still, never the video.
    [cover] = by_id[ids["cake"]]["media"]
    assert cover["origin"] == "website" and cover["file"]["url"] == f"media/{hashlib.sha256(JPEG).hexdigest()}.jpg"
    assert by_id[ids["cake"]]["cover_id"] == cover["id"]
    assert by_id[ids["uploaded"]]["media"] == [] and by_id[ids["uploaded"]]["cover_id"] is None
    [still] = by_id[ids["reel"]]["media"]
    assert still["status"] == "thumbnail_only" and still["file"] is None and still["post_url"] == "https://www.instagram.com/p/abc/"
    assert sorted(p.name for p in (out / "media").iterdir()) == sorted(
        f"{hashlib.sha256(data).hexdigest()}.jpg" for data in (JPEG, JPEG + b"still")
    )
    assert (out / "media" / f"{hashlib.sha256(JPEG).hexdigest()}.jpg").read_bytes() == JPEG
    assert report.files == 2 and any("uploaded picture" in line for line in report.left_out)


def test_the_draft_a_backup_kept_is_shown_as_it_was(notebook, data_dir, tmp_path):
    lemonade, draft = notebook["lemonade"], notebook["draft"]
    data, report = export(data_dir, tmp_path / "export", recipes=[lemonade["id"]], show_processing=[lemonade["id"]])
    kept = data["recipes"][0]["processing"]["draft"]
    assert kept["title"] == draft["title"] and kept["title"] != "לימונדה"
    assert kept["ingredient_groups"] == draft["ingredient_groups"] and kept["category"] is None
    assert [issue["kind"] for issue in kept["issues"]] == [issue["kind"] for issue in draft["issues"]]
    assert kept["saved_at"].replace("Z", "+00:00")[:19] == draft["created_at"].replace("Z", "+00:00")[:19]
    assert report.drafts == {lemonade["id"]: next(data_dir.glob("recipes.backup-*-before-test.db")).name}


def test_no_backup_with_an_untouched_draft_means_no_draft(notebook, client, data_dir, tmp_path):
    # Saved as a draft again after an edit, then backed up: no longer the import's own draft.
    edited = notebook["still_draft"]
    client.put(f"/api/recipes/{edited['id']}", json={"title": "עוד מתכון", "sources": edited["sources"], "status": "draft", "issues": []}, headers=ORIGIN)
    backup_database(data_dir / "recipes.db", "after-edit")
    assert find_kept_draft(data_dir / "recipes.db", edited["id"]) == (None, None)
    # A recipe created after every backup: nothing to find either.
    later = client.post("/api/imports/text", json={"text": SOURCE, "use_model": False}, headers=ORIGIN).json()
    assert find_kept_draft(data_dir / "recipes.db", later["id"]) == (None, None)


@pytest.mark.parametrize(
    ("chosen", "processing", "message"),
    [
        ("draft_of_still", None, "a draft that has not been reviewed"),
        ("sample", None, "an invented sample recipe"),
        ("unknown", None, "has no recipe 999"),
        ("cake", "lemonade", "not in the selection"),
        ("cake", "cake", "typed in by hand"),
    ],
)
def test_what_cannot_be_published_is_refused_and_the_last_export_stays(notebook, client, data_dir, tmp_path, chosen, processing, message):
    out = tmp_path / "export"
    export(data_dir, out, recipes=[notebook["cake"]["id"]])
    last = (out / "notebook.json").read_text(encoding="utf-8")
    ids = {
        "draft_of_still": notebook["still_draft"]["id"],
        "sample": next(r["id"] for r in client.get("/api/recipes").json() if r["is_sample"]),
        "unknown": 999,
        "cake": notebook["cake"]["id"],
        "lemonade": notebook["lemonade"]["id"],
    }
    with pytest.raises(ExportError, match=message):
        export(data_dir, out, recipes=[ids[chosen]], show_processing=[ids[processing]] if processing else [])
    assert (out / "notebook.json").read_text(encoding="utf-8") == last
    assert not (tmp_path / "export.partial").exists()


def test_the_command_lists_what_can_be_published_and_exports_the_selection(notebook, data_dir, capsys):
    assert main(["--list"]) == 0
    listing = capsys.readouterr().out
    assert f"{notebook['still_draft']['id']:>4}  no   " in listing and f"{notebook['lemonade']['id']:>4}  yes  " in listing
    assert "an invented sample recipe" in listing

    assert main([]) == 1
    assert "No selection yet" in capsys.readouterr().err
    folder = data_dir / "public-notebook"
    folder.mkdir()
    (folder / "selection.json").write_text(json.dumps({"recipes": [notebook["lemonade"]["id"]], "show_processing": [notebook["lemonade"]["id"]]}), encoding="utf-8")
    assert main([]) == 0
    assert "the import's draft, from recipes.backup-" in capsys.readouterr().out
    assert json.loads((folder / "export" / "notebook.json").read_text(encoding="utf-8"))["recipes"][0]["title"] == "לימונדה"


def test_a_dessert_s_type_and_healthy_style_are_public_with_only_the_types_in_use(client, data_dir, tmp_path):
    frozen = new_recipe(client, "גלידת קוטג׳", subcategory_id=15, healthy=True)
    plain = new_recipe(client, "עוגת שמרים", healthy=False)
    data, _ = export(data_dir, tmp_path / "export", recipes=[frozen["id"], plain["id"]])
    by_title = {recipe["title"]: recipe for recipe in data["recipes"]}
    assert (by_title["גלידת קוטג׳"]["subcategory"]["name"], by_title["גלידת קוטג׳"]["healthy"]) == ("גלידות וקינוחים קפואים", True)
    assert (by_title["עוגת שמרים"]["subcategory"], by_title["עוגת שמרים"]["healthy"]) == (None, False)
    [desserts] = data["categories"]
    assert desserts["healthy_style"] is True  # the page offers the "קינוח בריא" filter
    assert [(s["name"], s["description"]) for s in desserts["subcategories"]] == [("גלידות וקינוחים קפואים", None)]


def test_a_draft_kept_from_before_the_healthy_attribute_is_shown_as_saved_recipes_have_it(tmp_path):
    from tests.test_migrations import database_at_0004, upgrade_to

    notebook = tmp_path / "recipes.db"
    database_at_0004(notebook)
    upgrade_to(notebook, "0013")
    with sqlite3.connect(notebook) as db:  # an import's draft, in "קינוחים רגילים" as the model chose it
        db.execute("UPDATE recipes SET category_id = 1, subcategory_id = 5, status = 'draft', updated_at = created_at WHERE id = 2")
    upgrade_database(notebook)  # its backup keeps the draft as it was
    with sqlite3.connect(notebook) as db:  # then reviewed and saved, unchanged
        db.execute("UPDATE recipes SET status = 'saved', updated_at = '2026-11-02 10:00:00' WHERE id = 2")

    kept, backup = find_kept_draft(notebook, 2)
    assert backup.endswith("-before-0014.db")
    assert (kept.category.name, kept.subcategory, kept.healthy) == ("קינוחים", None, False)


def test_a_line_derived_from_the_steps_is_public_with_where_it_comes_from(client, data_dir, tmp_path):
    oil = {"text": "מעט שמן לטיגון", "quantity": "מעט", "derived_from": "מחממים מעט שמן במחבת."}
    recipe = new_recipe(client, "חביתה", ingredient_groups=[{"name": None, "ingredients": [{"text": "3 ביצים", "quantity": "3"}, oil]}])
    data, _ = export(data_dir, tmp_path / "export", recipes=[recipe["id"]])
    assert data["recipes"][0]["ingredient_groups"][0]["ingredients"][1] == oil
