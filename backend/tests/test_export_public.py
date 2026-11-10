"""The public copy's export (scripts/export_public.py): only chosen saved recipes, only what the public page
shows, the notebook opened read-only, and an import's draft only when a backup really kept it."""

import copy
import hashlib
import sqlite3
import json
from pathlib import Path

import pytest

from app import media, models
from app.db import utc_now
from app.migrate import backup_database, head_revision, upgrade_database
from scripts.export_public import ExportError, Selection, export_notebook, find_kept_draft, main
from scripts.public_pictures import location_in, metadata_in
from tests.test_media import JPEG, MP4, PNG
from tests.test_public_pictures import BLUE, RED, mostly, opened, phone_photo

PHOTO = phone_photo()  # uploaded from a phone: GPS, the phone's make, XMP, a comment, a profile; stored sideways

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
    picture and an upload; one whose only picture is a phone photo uploaded; one with a post's video; a draft; the
    samples."""
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
    client.post(f"/api/recipes/{uploaded['id']}/media", content=PHOTO, headers=ORIGIN)
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

    # Only the cover: the page's picture as it is (not the upload beside it); an uploaded cover as a copy without
    # its metadata; a video's still, never the video.
    [cover] = by_id[ids["cake"]]["media"]
    assert cover["origin"] == "website" and cover["file"]["url"] == f"media/{hashlib.sha256(JPEG).hexdigest()}.jpg"
    assert by_id[ids["cake"]]["cover_id"] == cover["id"]
    [photo] = by_id[ids["uploaded"]]["media"]
    assert photo["origin"] == "upload" and by_id[ids["uploaded"]]["cover_id"] == photo["id"]
    published = (out / photo["file"]["url"]).read_bytes()
    assert metadata_in(published) == [] and not location_in(published) and b"PhoneMaker" not in published
    assert photo["file"]["url"] == f"media/{hashlib.sha256(published).hexdigest()}.jpg"
    assert (photo["file"]["content_type"], photo["file"]["size_bytes"]) == ("image/jpeg", len(published))
    picture = opened(published)  # upright: the blue half on top, and the size the page lays it out by
    assert (photo["width"], photo["height"]) == picture.size == (20, 40)
    assert mostly(picture.getpixel((10, 5)), BLUE) and mostly(picture.getpixel((10, 35)), RED)
    stored = [p for p in media.media_root(data_dir).rglob("*") if p.is_file() and p.read_bytes() == PHOTO]
    assert len(stored) == 1  # the original upload is still there, byte for byte
    [still] = by_id[ids["reel"]]["media"]
    assert still["status"] == "thumbnail_only" and still["file"] is None and still["post_url"] == "https://www.instagram.com/p/abc/"
    assert sorted(p.name for p in (out / "media").iterdir()) == sorted(
        [f"{hashlib.sha256(data).hexdigest()}.jpg" for data in (JPEG, JPEG + b"still")] + [Path(photo["file"]["url"]).name]
    )
    assert (out / "media" / f"{hashlib.sha256(JPEG).hexdigest()}.jpg").read_bytes() == JPEG
    assert report.files == 3 and report.uploads == [f"{ids['uploaded']}: its uploaded cover, as a copy without metadata"]
    assert f"{ids['cake']}: 1 more picture(s) or video(s) besides the cover" in report.left_out  # the upload beside the page's


def test_an_uploaded_cover_that_is_not_a_readable_picture_is_left_out_not_published_as_it_is(client, data_dir, tmp_path):
    recipe = new_recipe(client, "עוגיות", category_id=None)
    client.post(f"/api/recipes/{recipe['id']}/media", content=PNG, headers=ORIGIN)  # a PNG header and nothing a decoder reads
    data, report = export(data_dir, tmp_path / "export", recipes=[recipe["id"]])
    assert data["recipes"][0]["media"] == [] and data["recipes"][0]["cover_id"] is None
    assert list((tmp_path / "export" / "media").iterdir()) == []
    assert [line for line in report.left_out if "cannot be read as a picture" in line]


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
    assert backup.endswith(f"-before-{head_revision()}.db")
    assert (kept.category.name, kept.subcategory, kept.healthy) == ("קינוחים", None, False)


def test_a_line_derived_from_the_steps_is_public_with_where_it_comes_from(client, data_dir, tmp_path):
    oil = {"text": "מעט שמן לטיגון", "quantity": "מעט", "derived_from": "מחממים מעט שמן במחבת."}
    recipe = new_recipe(client, "חביתה", ingredient_groups=[{"name": None, "ingredients": [{"text": "3 ביצים", "quantity": "3"}, oil]}])
    data, _ = export(data_dir, tmp_path / "export", recipes=[recipe["id"]])
    assert data["recipes"][0]["ingredient_groups"][0]["ingredients"][1] == oil


def demonstration_of(recipe_id: int, text: str) -> dict:
    """A recorded demonstration: the draft a new import of `text` made, and the same after its review."""
    draft = {"title": "לימונדה", "servings": None, "category": None, "subcategory": None, "healthy": None,
             "ingredient_groups": [{"name": None, "ingredients": [{"text": "2 לימונים", "quantity": "2"}]}],
             "step_groups": [{"name": None, "steps": ["סוחטים ומערבבים עם סוכר."]}], "notes": [],
             "issues": [{"kind": "ingredient_only_in_steps", "message": 'המצרך "סוכר" מופיע בהוראות ההכנה, אך חסר ברשימת המצרכים.',
                         "quote": "סוחטים ומערבבים עם סוכר.", "proposed": {"text": "סוכר", "quantity": None, "group": None}}],
             "saved_at": "2026-11-04T17:10:00Z"}
    reviewed = {**draft, "issues": [], "resolved_issues": [{**draft["issues"][0], "resolution": "dismissed"}], "saved_at": "2026-11-04T17:20:00Z"}
    return {"recipe_id": recipe_id, "source_sha256": hashlib.sha256(text.encode()).hexdigest(), "run_at": "2026-11-04T17:10:00Z",
            "model": "qwen3:8b", "draft": draft, "reviewed": reviewed}


def test_a_recorded_demonstration_is_public_only_when_made_from_the_recipe_s_own_original(notebook, client, data_dir, tmp_path):
    lemonade = notebook["lemonade"]["id"]
    resolved = [{"kind": "other", "message": "בדקו.", "quote": None, "resolution": "handled"}]
    client.put(f"/api/recipes/{lemonade}", json={**{k: v for k, v in notebook["lemonade"].items() if k in (
        "title", "servings", "ingredient_groups", "step_groups", "notes", "sources", "healthy", "status")},
        "category_id": notebook["lemonade"]["category"]["id"], "issues": [], "resolved_issues": resolved}, headers=ORIGIN)
    out = tmp_path / "public" / "export"
    (tmp_path / "public" / "demonstrations").mkdir(parents=True)
    demo = tmp_path / "public" / "demonstrations" / "lemonade.json"
    demo.write_text(json.dumps(demonstration_of(lemonade, SOURCE), ensure_ascii=False), encoding="utf-8")

    data, report = export(data_dir, out, recipes=[lemonade], show_processing=[lemonade], demonstrations={lemonade: "demonstrations/lemonade.json"})
    [recipe] = data["recipes"]
    shown = recipe["processing"]["demonstration"]
    assert set(shown) == {"run_at", "model", "revision", "settings", "answer", "draft", "reviewed", "automatic"}  # the ids stay out
    assert (shown["answer"], shown["automatic"]) == (None, [])  # an older record: no model answer kept, no rule evidence
    assert shown["draft"]["issues"][0]["proposed"] == {"text": "סוכר", "quantity": None, "group": None}
    assert shown["reviewed"]["resolved_issues"][0]["resolution"] == "dismissed"
    assert recipe["resolved_issues"] == []  # the notebook's own review record is not published
    assert report.demonstrations[lemonade] == "run 2026-11-04 17:10 UTC with qwen3:8b"

    demo.write_text(json.dumps(demonstration_of(lemonade, SOURCE + " ")), encoding="utf-8")  # another text
    with pytest.raises(ExportError, match="not made from recipe"):
        export(data_dir, out, recipes=[lemonade], show_processing=[lemonade], demonstrations={lemonade: "demonstrations/lemonade.json"})
    with pytest.raises(ExportError, match="not in show_processing"):
        export(data_dir, out, recipes=[lemonade], demonstrations={lemonade: "demonstrations/lemonade.json"})
    assert json.loads((out / "notebook.json").read_text(encoding="utf-8")) == data  # a refused export leaves the last one


TORTE = "טורט\n4 ביצים\nאופים 50 דקות על 150 מעלות\n (כל תנור עובד אחרת).\nמגישים."


def check_of(recipe_id: int, text: str) -> dict:
    """A recorded classification check of the given text: the same request answered twice, the same way."""
    answer = {"category": {"id": 1, "name": "קינוחים"}, "subcategory": None, "at": "2026-11-05T14:58:15Z"}
    return {"recipe_id": recipe_id, "source_sha256": hashlib.sha256(text.encode()).hexdigest(), "run_at": "2026-11-05T14:57:40Z",
            "model": "qwen3:8b", "answers": [answer, {**answer, "at": "2026-11-05T14:59:18Z"}]}


def test_a_classification_check_is_public_only_for_a_recipe_whose_import_left_no_suggestion(notebook, client, data_dir, tmp_path):
    # Imported and saved after every backup: no draft of its import is kept.
    draft = client.post("/api/imports/text", json={"text": TORTE, "use_model": False}, headers=ORIGIN).json()
    body = {"title": "טורט", "ingredient_groups": [{"name": None, "ingredients": [{"text": "4 ביצים", "quantity": "4"}]}],
            "step_groups": [{"name": None, "steps": ["מגישים."]}], "notes": [], "sources": draft["sources"],
            "category_id": category_id(client, "קינוחים"), "status": "saved", "issues": []}
    torte = client.put(f"/api/recipes/{draft['id']}", json=body, headers=ORIGIN).json()["id"]
    lemonade = notebook["lemonade"]["id"]  # a backup kept its import's draft
    folder = tmp_path / "public"
    (folder / "classifications").mkdir(parents=True)
    for recipe_id, text in ((torte, TORTE), (lemonade, SOURCE)):
        (folder / "classifications" / f"{recipe_id}.json").write_text(json.dumps(check_of(recipe_id, text), ensure_ascii=False), encoding="utf-8")
    checks = {torte: f"classifications/{torte}.json"}

    data, report = export(data_dir, folder / "export", recipes=[torte], show_processing=[torte], classification_checks=checks)
    shown = data["recipes"][0]["processing"]
    assert shown["draft"] is None
    assert set(shown["classification_check"]) == {"run_at", "model", "answers"}  # the checks' data stays out
    assert [answer["category"]["name"] for answer in shown["classification_check"]["answers"]] == ["קינוחים", "קינוחים"]
    assert report.checks[torte] == "run 2026-11-05 14:57 UTC with qwen3:8b, 2 answer(s)"

    # The import's own draft, or a demonstration's, already holds the model's suggestion.
    with pytest.raises(ExportError, match="own import draft is kept"):
        export(data_dir, folder / "export", recipes=[lemonade], show_processing=[lemonade], classification_checks={lemonade: f"classifications/{lemonade}.json"})
    with pytest.raises(ExportError, match="have a demonstration"):
        export(data_dir, folder / "export", recipes=[torte], show_processing=[torte], classification_checks=checks, demonstrations={torte: "torte.json"})
    with pytest.raises(ExportError, match="not in show_processing"):
        export(data_dir, folder / "export", recipes=[torte], classification_checks=checks)
    (folder / "classifications" / f"{torte}.json").write_text(json.dumps(check_of(torte, TORTE + " ")), encoding="utf-8")  # another text
    with pytest.raises(ExportError, match="not made from recipe"):
        export(data_dir, folder / "export", recipes=[torte], show_processing=[torte], classification_checks=checks)
    assert json.loads((folder / "export" / "notebook.json").read_text(encoding="utf-8")) == data  # a refused export leaves the last one


def test_a_demonstration_s_evidence_of_a_joined_remark_is_checked_and_published_as_the_rules(client, data_dir, tmp_path):
    draft = client.post("/api/imports/text", json={"text": TORTE, "use_model": False}, headers=ORIGIN).json()
    joined = "אופים 50 דקות על 150 מעלות (כל תנור עובד אחרת)."
    body = {"title": "טורט", "ingredient_groups": [{"name": None, "ingredients": [{"text": "4 ביצים", "quantity": "4"}]}],
            "step_groups": [{"name": None, "steps": [joined, "מגישים."]}], "notes": [], "sources": draft["sources"],
            "category_id": category_id(client, "קינוחים"), "status": "saved", "issues": []}
    torte = client.put(f"/api/recipes/{draft['id']}", json=body, headers=ORIGIN).json()
    record = demonstration_of(torte["id"], TORTE)
    for state in ("draft", "reviewed"):
        record[state]["step_groups"] = body["step_groups"]
    record["automatic"] = [{"kind": "joined_remark", "step": "אופים 50 דקות על 150 מעלות", "remark": "(כל תנור עובד אחרת)."}]
    (tmp_path / "public").mkdir()
    demo = tmp_path / "public" / "torte.json"
    demo.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    choose = {"recipes": [torte["id"]], "show_processing": [torte["id"]], "demonstrations": {torte["id"]: "torte.json"}}

    data, _ = export(data_dir, tmp_path / "public" / "export", **choose)
    # What a rule did, shown as the rules' (the same in draft and result: never a review change).
    assert data["recipes"][0]["processing"]["demonstration"]["automatic"] == record["automatic"]

    record["reviewed"]["step_groups"] = [{"name": None, "steps": ["אופים 50 דקות על 150 מעלות", "(כל תנור עובד אחרת).", "מגישים."]}]
    demo.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")  # review split it again: not what was recorded
    with pytest.raises(ExportError, match="joined remark"):
        export(data_dir, tmp_path / "public" / "export", **choose)


def test_a_demonstration_s_model_answer_and_kept_reference_are_published_only_when_they_hold(client, data_dir, tmp_path):
    text = "סופגניות\n500 גר׳ חלב או מים\nמבשלים קרם.\nמכינים בצק לפי המתכון לבצק שלי מהבלוג.\nממלאים."
    steps = ["מבשלים קרם.", "מכינים בצק לפי המתכון לבצק שלי מהבלוג.", "ממלאים."]
    draft = client.post("/api/imports/text", json={"text": text, "use_model": False}, headers=ORIGIN).json()
    desserts = category_id(client, "קינוחים")
    body = {"title": "סופגניות", "ingredient_groups": [{"name": None, "ingredients": [{"text": "500 גר׳ חלב או מים", "quantity": "500 גר׳"}]}],
            "step_groups": [{"name": None, "steps": steps}], "notes": [], "sources": draft["sources"], "category_id": desserts,
            "status": "saved", "issues": []}
    recipe = client.put(f"/api/recipes/{draft['id']}", json=body, headers=ORIGIN).json()
    record = demonstration_of(recipe["id"], text)
    for state in ("draft", "reviewed"):
        record[state]["step_groups"] = body["step_groups"]
    record["draft"]["category"] = {"id": desserts, "name": "קינוחים"}
    record |= {
        "revision": "75bfd06",
        "settings": {"mode": "references", "context_tokens": 8192, "temperature": 0},
        "answer": {"classification": {"fit": "clear", "category_id": desserts, "subcategory_id": None, "candidate_category_ids": []},
                   "points": [{"kind": "ambiguous_alternative", "passage": "מבשלים קרם.", "left_out": "no_alternative"}]},
        "automatic": [{"kind": "kept_reference", "text": steps[1], "kept_as": "step"}],
    }
    (tmp_path / "public").mkdir()
    demo = tmp_path / "public" / "dough.json"
    choose = {"recipes": [recipe["id"]], "show_processing": [recipe["id"]], "demonstrations": {recipe["id"]: "dough.json"}}
    demo.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

    data, _ = export(data_dir, tmp_path / "public" / "export", **choose)
    shown = data["recipes"][0]["processing"]["demonstration"]
    assert (shown["revision"], shown["settings"]["temperature"]) == ("75bfd06", 0)
    assert shown["answer"] == record["answer"] and shown["automatic"] == record["automatic"]
    assert "source_sha256" not in shown and "recipe_id" not in shown

    for change, refused in (
        (lambda r: r["answer"]["classification"].update(fit="no_fit", category_id=None), "classification is not the draft"),
        (lambda r: r["answer"]["points"][0].update(passage="500 גר׳ חלב או מים"), "has one"),  # that passage has an "או"
        (lambda r: r["answer"]["points"][0].update(passage="מבשלים קרם היטב."), "does not have"),
        (lambda r: r["automatic"][0].update(kept_as="note"), "kept reference"),  # not among the notes
    ):
        broken = copy.deepcopy(record)
        change(broken)
        demo.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(ExportError, match=refused):
            export(data_dir, tmp_path / "public" / "export", **choose)
