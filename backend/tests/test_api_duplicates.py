"""A post that is already in the notebook: noticed before anything is fetched, never overwritten, and
imported again only when the person asks for another copy."""

import pytest

from tests.test_api_imports import StandIn, answer, recipe_count, use  # noqa: F401  (use is a fixture)
from tests.test_api_instagram import POST, found, reads  # noqa: F401  (reads is a fixture)
from tests.test_extraction_review import SOURCE

SAME_POST = [
    "https://www.instagram.com/p/Cm1mCdCpSzJ/",
    "https://www.instagram.com/reel/Cm1mCdCpSzJ/?igsh=MWQ1ZGUxMzBkMA==",
    "instagram.com/ritakadosh_/p/Cm1mCdCpSzJ/?img_index=1",
    "https://m.instagram.com/tv/Cm1mCdCpSzJ",
]


def import_post(client, url=POST, **extra):
    return client.post("/api/imports/instagram", json={"url": url, **extra})


@pytest.mark.parametrize("again", SAME_POST)
def test_the_same_post_in_any_form_is_noticed_before_it_is_read(client, use, reads, again):
    use(StandIn(answer()))
    reader = reads(found())
    first = import_post(client).json()
    reader.calls.clear()

    response = import_post(client, again)
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "duplicate_link"
    assert error["details"]["matches"] == [{"id": first["id"], "title": first["title"], "status": "draft"}]
    assert reader.calls == []  # nothing fetched


def test_another_copy_is_imported_only_when_asked_and_nothing_is_overwritten(client, use, reads):
    use(StandIn(answer()))
    reads(found())
    first = import_post(client).json()
    before = recipe_count(client)
    second = import_post(client, SAME_POST[1], allow_duplicate=True)
    assert second.status_code == 201 and second.json()["id"] != first["id"]
    assert recipe_count(client) == before + 1
    assert client.get(f"/api/recipes/{first['id']}").json()["title"] == first["title"]  # untouched


def test_a_link_kept_only_in_a_recipes_sources_counts_and_saved_recipes_are_listed_too(client, use, reads):
    reader = reads(found())
    body = {
        "title": "טורט וניל", "servings": None, "ingredient_groups": [], "step_groups": [], "notes": [],
        "sources": [{"kind": "instagram", "url": "https://www.instagram.com/reel/Cm1mCdCpSzJ/", "creators": []}],
    }
    saved = client.post("/api/recipes", json=body).json()
    response = import_post(client)
    assert response.json()["error"]["details"]["matches"] == [{"id": saved["id"], "title": "טורט וניל", "status": "saved"}]
    assert reader.calls == []


def test_every_recipe_with_the_post_is_listed_once_newest_first(client, use, reads):
    use(StandIn(answer()))
    reads(found())
    first = import_post(client).json()
    second = import_post(client, allow_duplicate=True).json()  # its original and its source both link to the post
    matches = import_post(client).json()["error"]["details"]["matches"]
    assert [m["id"] for m in matches] == [second["id"], first["id"]]


def test_pasted_text_with_a_link_to_a_post_already_here_is_checked_too(client, use, reads):
    extractor = use(StandIn(answer()))
    reads(found())
    first = import_post(client).json()
    extractor.calls.clear()
    response = client.post("/api/imports/text", json={"text": SOURCE, "url": SAME_POST[2]})
    assert response.status_code == 409 and response.json()["error"]["details"]["matches"][0]["id"] == first["id"]
    assert extractor.calls == []  # stopped before the model
    again = client.post("/api/imports/text", json={"text": SOURCE, "url": SAME_POST[2], "allow_duplicate": True})
    assert again.status_code == 201


def test_another_post_and_other_kinds_of_links_are_not_duplicates(client, use, reads):
    use(StandIn(answer()))
    reads(found())
    import_post(client)
    body = {
        "title": "מאתר", "servings": None, "ingredient_groups": [], "step_groups": [], "notes": [],
        "sources": [{"kind": "website", "url": "https://example.com/recipes/cake", "creators": []}],
    }
    client.post("/api/recipes", json=body)
    other = import_post(client, "https://www.instagram.com/p/DPbKEn-CnUt/")
    assert other.status_code == 201
    plain = client.post("/api/imports/text", json={"text": SOURCE})  # pasted text without a link: no check
    assert plain.status_code == 201
