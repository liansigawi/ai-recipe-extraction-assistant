"""Media through the API: saved with an Instagram import, fetched for an existing recipe, uploaded,
served, chosen as the cover, removed. The post and the downloads are stand-ins: no test reaches Instagram."""

import pytest

from app import media
from app.importers.instagram import FetchOutcome
from tests.test_api_imports import StandIn, answer, use  # noqa: F401  (use is a fixture)
from tests.test_api_instagram import POST, Reader, found, reads  # noqa: F401  (reads is a fixture)
from tests.test_media import CDN, EVERYTHING, ITEMS, JPEG, MP4, PNG, serve

ORIGIN = {"Origin": "http://localhost:5173"}


@pytest.fixture
def downloads(client):
    """downloads(files): media downloads answer from this dict (see tests/test_media.serve)."""
    asked: list[list[str]] = []

    def install(files: dict) -> list[str]:
        transport, urls = serve(files)
        client.app.dependency_overrides[media.get_media_transport] = lambda: transport
        asked.append(urls)
        return urls

    yield install
    client.app.dependency_overrides.pop(media.get_media_transport, None)


def import_post(client, **extra):
    return client.post("/api/imports/instagram", json={"url": POST, **extra})


def test_an_instagram_import_saves_the_posts_media_in_its_order(client, use, reads, downloads):
    use(StandIn(answer()))
    reads(found(media=ITEMS))
    downloads(EVERYTHING)
    draft = import_post(client).json()
    assert [(m["post_index"], m["kind"], m["status"]) for m in draft["media"]] == [
        (0, "video", "saved"), (1, "image", "saved"), (2, "video", "saved")
    ]
    first = draft["media"][0]
    assert draft["cover_id"] == first["id"]  # no cover chosen: the first with a picture
    assert first["file"]["content_type"] == "video/mp4" and first["thumbnail"]["content_type"] == "image/jpeg"
    assert "media_incomplete" not in [issue["kind"] for issue in draft["issues"]]
    served = client.get(first["file"]["url"])
    assert served.status_code == 200 and served.headers["content-type"] == "video/mp4" and served.content == MP4
    assert "immutable" in served.headers["cache-control"]


def test_a_video_is_served_in_parts_so_it_can_be_sought(client, use, reads, downloads):
    use(StandIn(answer()))
    reads(found(media=ITEMS[:1]))
    downloads(EVERYTHING)
    video = import_post(client).json()["media"][0]["file"]["url"]
    part = client.get(video, headers={"Range": "bytes=0-9"})
    assert part.status_code == 206 and part.content == MP4[:10]


def test_media_that_cannot_be_saved_never_stops_the_import(client, use, reads, downloads):
    use(StandIn(answer()))
    reads(found(media=ITEMS))
    downloads(EVERYTHING | {f"{CDN}/v2.mp4": 403, f"{CDN}/i1.jpg": 404})
    response = import_post(client)
    assert response.status_code == 201
    draft = response.json()
    assert [(m["post_index"], m["status"]) for m in draft["media"]] == [(0, "saved"), (2, "thumbnail_only")]
    point = draft["issues"][0]
    assert point["kind"] == "media_incomplete" and "1 מתוך 3" in point["message"]


def test_even_an_unexpected_media_error_leaves_the_draft_saved(client, use, reads, monkeypatch):
    use(StandIn(answer()))
    reads(found(media=ITEMS))
    monkeypatch.setattr(media, "attach_post_media", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("disk full")))
    response = import_post(client)
    assert response.status_code == 201
    assert response.json()["media"] == [] and response.json()["issues"][0]["kind"] == "media_incomplete"


def test_a_post_without_media_in_its_data_says_so(client, use, reads, downloads):
    use(StandIn(answer()))
    reads(found())
    downloads({})
    point = import_post(client).json()["issues"][0]
    assert point["kind"] == "media_incomplete" and "לא נמצאו" in point["message"]


def own_recipe(client):
    """A recipe of yours, typed in, with an Instagram source, a category and your credit."""
    body = {
        "title": "עוגיות שקדים שלי", "servings": None,
        "ingredient_groups": [{"name": None, "ingredients": [{"text": "כוס קמח שקדים", "quantity": "כוס"}]}],
        "step_groups": [{"name": None, "steps": ["אופים."]}], "notes": [], "category_id": 1, "subcategory_id": 12, "healthy": True,
        "sources": [{"kind": "instagram", "url": "https://www.instagram.com/reel/Cm1mCdCpSzJ/", "creators": [{"name": "שם שלי", "username": "baker"}]}],
    }
    return client.post("/api/recipes", json=body).json()


def test_fetching_media_for_an_existing_recipe_changes_nothing_else_and_adds_nothing_twice(client, reads, downloads):
    recipe = own_recipe(client)
    upload = client.post(f"/api/recipes/{recipe['id']}/media", content=PNG, headers=ORIGIN).json()["media"][0]
    client.put(f"/api/recipes/{recipe['id']}/cover", json={"media_id": upload["id"]})
    reader = reads(found(media=ITEMS))
    downloads(EVERYTHING)

    result = client.post(f"/api/recipes/{recipe['id']}/media/instagram", json={}).json()
    assert reader.calls == ["https://www.instagram.com/reel/Cm1mCdCpSzJ/"]  # the recipe's own post
    assert {k: result["report"][k] for k in ("found", "saved", "already_had")} == {"found": 3, "saved": 3, "already_had": 0}
    after = result["recipe"]
    for field in ("title", "ingredient_groups", "step_groups", "category", "subcategory", "sources", "status"):
        assert after[field] == recipe[field], field
    # The post's media in its order, then your upload, which is still the cover.
    assert [(m["origin"], m["post_index"]) for m in after["media"]] == [("instagram", 0), ("instagram", 1), ("instagram", 2), ("upload", None)]
    assert after["cover_id"] == upload["id"]

    again = client.post(f"/api/recipes/{recipe['id']}/media/instagram", json={}).json()
    assert (again["report"]["already_had"], again["report"]["saved"]) == (3, 0)
    assert len(again["recipe"]["media"]) == 4


def test_fetching_media_keeps_the_picture_the_card_showed(client, reads, downloads):
    recipe = own_recipe(client)
    upload = client.post(f"/api/recipes/{recipe['id']}/media", content=PNG, headers=ORIGIN).json()["media"][0]
    assert not upload["is_cover"]  # the cover only by default: the first (and only) picture
    reads(found(media=ITEMS))
    downloads(EVERYTHING)
    after = client.post(f"/api/recipes/{recipe['id']}/media/instagram", json={}).json()["recipe"]
    assert after["media"][0]["origin"] == "instagram"  # the post's items come first...
    assert after["cover_id"] == upload["id"]  # ...but the card still shows the upload
    assert [m["is_cover"] for m in after["media"]] == [False, False, False, True]


def test_fetching_media_is_not_stopped_by_the_duplicate_check(client, use, reads, downloads):
    use(StandIn(answer()))
    reads(found(media=ITEMS))
    downloads(EVERYTHING)
    draft = import_post(client).json()
    response = client.post(f"/api/recipes/{draft['id']}/media/instagram", json={})
    assert response.status_code == 200 and response.json()["report"]["already_had"] == 3


def test_a_recipe_without_an_instagram_post_cannot_fetch_media(client):
    recipe = client.get("/api/recipes").json()[0]  # a sample, with a website source or none
    response = client.post(f"/api/recipes/{recipe['id']}/media/instagram", json={})
    assert response.status_code == 422 and response.json()["error"]["code"] == "no_instagram_source"


def test_a_post_that_cannot_be_read_says_why(client, reads):
    recipe = own_recipe(client)
    reads(Reader(FetchOutcome.UNAVAILABLE))
    response = client.post(f"/api/recipes/{recipe['id']}/media/instagram", json={})
    assert response.status_code == 502 and response.json()["error"]["code"] == "instagram_unavailable"
    assert client.get(f"/api/recipes/{recipe['id']}").json()["media"] == []


def test_uploading_a_picture_to_any_recipe(client):
    recipe = client.get("/api/recipes").json()[-1]  # a sample with no Instagram link at all
    response = client.post(f"/api/recipes/{recipe['id']}/media", content=JPEG, headers=ORIGIN)
    assert response.status_code == 201
    [item] = response.json()["media"]
    assert (item["origin"], item["kind"], item["file"]["content_type"]) == ("upload", "image", "image/jpeg")
    assert response.json()["cover_id"] == item["id"]
    assert client.get(item["file"]["url"]).content == JPEG


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        (b"<html>not a picture</html>", 415, "unsupported_media"),
        (MP4, 415, "unsupported_media"),  # uploads are pictures; videos come from a post
        (b"", 422, "empty_upload"),
    ],
)
def test_an_upload_must_be_a_picture(client, body, status, code):
    recipe = client.get("/api/recipes").json()[0]
    response = client.post(f"/api/recipes/{recipe['id']}/media", content=body, headers=ORIGIN)
    assert response.status_code == status and response.json()["error"]["code"] == code


def test_an_upload_over_the_limit_is_refused(client, monkeypatch):
    monkeypatch.setattr(media, "MAX_UPLOAD_BYTES", 100)
    recipe = client.get("/api/recipes").json()[0]
    response = client.post(f"/api/recipes/{recipe['id']}/media", content=JPEG, headers=ORIGIN)
    assert response.status_code == 413 and response.json()["error"]["code"] == "media_too_large"


def test_choosing_and_clearing_the_cover(client, use, reads, downloads):
    use(StandIn(answer()))
    reads(found(media=ITEMS))
    downloads(EVERYTHING)
    draft = import_post(client).json()
    image = draft["media"][1]
    chosen = client.put(f"/api/recipes/{draft['id']}/cover", json={"media_id": image["id"]}).json()
    assert chosen["cover_id"] == image["id"] and [m["is_cover"] for m in chosen["media"]] == [False, True, False]
    assert client.get("/api/recipes").json()[0]["cover_id"] == image["id"]  # on the card too
    cleared = client.put(f"/api/recipes/{draft['id']}/cover", json={"media_id": None}).json()
    assert cleared["cover_id"] == draft["media"][0]["id"]
    assert client.put(f"/api/recipes/{draft['id']}/cover", json={"media_id": 999}).status_code == 404


def test_removing_an_attachment_keeps_a_file_another_recipe_shares(client, use, reads, downloads, data_dir):
    use(StandIn(answer()))
    reads(found(media=ITEMS[1:2]))
    downloads(EVERYTHING)
    first = import_post(client).json()
    copy = import_post(client, allow_duplicate=True).json()  # another copy of the post: the same file
    file_url = first["media"][0]["file"]["url"]
    after = client.delete(f"/api/recipes/{first['id']}/media/{first['media'][0]['id']}").json()
    assert after["media"] == [] and after["cover_id"] is None
    assert client.get(file_url).status_code == 200  # the copy still shows it
    assert client.delete(f"/api/recipes/{copy['id']}").status_code == 204
    assert client.get(file_url).status_code == 404  # no recipe uses it: deleted
    assert not any((data_dir / "media").rglob("*.jpg"))


def test_saving_a_recipe_never_changes_its_media(client, use, reads, downloads):
    use(StandIn(answer()))
    reads(found(media=ITEMS))
    downloads(EVERYTHING)
    draft = import_post(client).json()
    body = {k: draft[k] for k in ("title", "servings", "ingredient_groups", "step_groups", "notes", "sources")}
    saved = client.put(f"/api/recipes/{draft['id']}", json=body | {"title": "שם חדש", "status": "saved"}).json()
    assert saved["media"] == draft["media"] and saved["cover_id"] == draft["cover_id"]
