"""Importing an Instagram post through the API: caption -> draft, what is kept, and every failure.

Both the reading of the post and the model are stand-ins, so these tests never reach Instagram
or a model.
"""

import pytest

from app.api.imports import get_caption_retriever
from app.importers.instagram import CaptionRetrieval, FetchOutcome, PostPerson, RetrievalAttempt
from tests.test_api_imports import StandIn, answer, recipe_count, use  # noqa: F401  (use is a fixture)
from tests.test_extraction_review import SOURCE

POST = "https://www.instagram.com/p/Cm1mCdCpSzJ/"
PASTED_FORM = "instagram.com/reel/Cm1mCdCpSzJ/?igsh=abc123"
CANONICAL_REEL = "https://www.instagram.com/reel/Cm1mCdCpSzJ/"


class Reader:
    """Stands in for reading the post: records the references, returns a prepared result."""

    def __init__(self, outcome: FetchOutcome, caption: str | None = None, **extra) -> None:
        self.outcome, self.caption, self.extra = outcome, caption, extra
        self.calls: list[str] = []

    def __call__(self, ref) -> CaptionRetrieval:
        self.calls.append(ref.canonical_url)
        attempt = RetrievalAttempt(page="post_page", outcome=self.outcome, http_status=200, elapsed_ms=4200)
        return CaptionRetrieval(
            url=ref.canonical_url, outcome=self.outcome, caption=self.caption,
            complete=self.outcome is FetchOutcome.CAPTION_FOUND, attempts=[attempt], **self.extra,
        )


@pytest.fixture
def reads(client):
    def install(reader: Reader) -> Reader:
        client.app.dependency_overrides[get_caption_retriever] = lambda: reader
        return reader

    yield install
    client.app.dependency_overrides.pop(get_caption_retriever, None)


def found(**extra) -> Reader:
    return Reader(
        FetchOutcome.CAPTION_FOUND, SOURCE, retrieved_from="post_page",
        author=PostPerson(username="baker", full_name="אופה ביתית"), **extra,
    )


def test_a_post_becomes_a_draft_with_its_caption_and_address_kept(client, use, reads):
    extractor = use(StandIn(answer()))
    reader = reads(found(coauthors=[PostPerson(username="friend")]))
    response = client.post("/api/imports/instagram", json={"url": POST})

    assert response.status_code == 201
    draft = response.json()
    assert draft["status"] == "draft" and draft["category"] == {"id": 1, "name": "קינוחים"}
    assert draft["original"] | {"imported_at": None} == {
        "kind": "instagram", "text": SOURCE, "model": "claude-test-model", "imported_at": None,
        "url": POST, "retrieved_from": "post_page",
        "author": {"name": "אופה ביתית", "username": "baker"}, "coauthors": [{"name": None, "username": "friend"}],
        "site_name": None,
    }
    # The editable source: the post, its author and co-author.
    credit = [{"name": "אופה ביתית", "username": "baker"}, {"name": None, "username": "friend"}]
    assert draft["sources"] == [{"kind": "instagram", "url": POST, "creators": credit}]
    # Who posted it, as read: kept with the original, apart from the credit you can edit.
    assert (draft["original"]["author"], draft["original"]["coauthors"]) == (credit[0], credit[1:])
    assert reader.calls == [POST] and [text for text, _ in extractor.calls] == [SOURCE]
    # Kept after a reload of the page.
    assert client.get(f"/api/recipes/{draft['id']}").json()["original"]["url"] == POST


def test_the_address_is_normalized_from_what_people_paste(client, use, reads):
    use(StandIn(answer()))
    reader = reads(found())
    draft = client.post("/api/imports/instagram", json={"url": PASTED_FORM}).json()
    assert reader.calls == [CANONICAL_REEL] and draft["original"]["url"] == CANONICAL_REEL


def test_saving_without_the_model_keeps_the_caption_to_fill_in_by_hand(client, use, reads):
    extractor = use(StandIn(answer()))
    reads(found())
    draft = client.post("/api/imports/instagram", json={"url": POST, "use_model": False}).json()
    assert draft["original"]["model"] is None and draft["original"]["kind"] == "instagram"
    assert "not_extracted" in [issue["kind"] for issue in draft["issues"]]
    assert extractor.calls == []


@pytest.mark.parametrize("url", ["https://example.com/p/abc", "https://www.instagram.com/stories/baker/123/", "  "])
def test_an_address_that_is_not_a_post_is_refused_before_anything_is_read(client, use, reads, url):
    reader = reads(found())
    response = client.post("/api/imports/instagram", json={"url": url})
    assert response.status_code == 422
    assert response.json()["error"]["code"] in ("invalid_instagram_url", "invalid_request")
    assert reader.calls == []


@pytest.mark.parametrize(
    ("outcome", "status"),
    [
        (FetchOutcome.UNAVAILABLE, 502),
        (FetchOutcome.LOGIN_REQUIRED, 502),
        (FetchOutcome.RATE_LIMITED, 429),
        (FetchOutcome.NO_CAPTION, 422),
        (FetchOutcome.CAPTION_NOT_FOUND, 502),
        (FetchOutcome.TIMEOUT, 504),
        (FetchOutcome.ERROR, 502),
    ],
)
def test_a_post_that_cannot_be_read_saves_nothing_and_says_why(client, use, reads, outcome, status):
    extractor = use(StandIn(answer()))
    reads(Reader(outcome))
    before = recipe_count(client)
    response = client.post("/api/imports/instagram", json={"url": POST})
    assert response.status_code == status
    error = response.json()["error"]
    assert error["code"] == f"instagram_{outcome}"
    assert error["details"]["url"] == POST and error["details"]["caption"] is None  # the page keeps the address
    assert error["details"]["attempts"][0]["page"] == "post_page"
    assert recipe_count(client) == before and extractor.calls == []


def test_a_preview_that_may_be_cut_off_is_not_presented_as_complete(client, use, reads):
    extractor = use(StandIn(answer()))
    reads(Reader(FetchOutcome.CAPTION_INCOMPLETE, "עוגת תפוזים\nמצרכים: 2 כוסות קמח…", retrieved_from="post_page"))
    before = recipe_count(client)
    response = client.post("/api/imports/instagram", json={"url": POST})
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "instagram_caption_incomplete"
    assert error["details"]["caption"] == "עוגת תפוזים\nמצרכים: 2 כוסות קמח…" and error["details"]["url"] == POST
    assert recipe_count(client) == before and extractor.calls == []


def test_when_the_model_finds_no_recipe_the_read_caption_comes_back(client, use, reads):
    use(StandIn(answer(is_recipe=False, ingredient_groups=[], step_groups=[])))
    reads(found())
    response = client.post("/api/imports/instagram", json={"url": POST})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "not_a_recipe" and error["details"]["caption"] == SOURCE and error["details"]["url"] == POST


def test_pasted_text_after_a_failed_read_keeps_the_post_address(client, use):
    use(StandIn(answer()))
    response = client.post("/api/imports/text", json={"text": SOURCE, "url": PASTED_FORM})
    assert response.status_code == 201
    draft = response.json()
    assert draft["original"]["kind"] == "text" and draft["original"]["url"] == CANONICAL_REEL
    assert draft["original"]["retrieved_from"] is None
    assert draft["sources"] == [{"kind": "instagram", "url": CANONICAL_REEL, "creators": []}]


def test_pasted_text_keeps_a_recipe_page_as_its_website_source(client, use):
    use(StandIn(answer()))
    draft = client.post("/api/imports/text", json={"text": SOURCE, "url": "https://www.example.com/recipe#top"}).json()
    assert draft["sources"] == [{"kind": "website", "url": "https://www.example.com/recipe", "creators": []}]
    assert draft["original"]["kind"] == "text" and draft["original"]["url"] == "https://www.example.com/recipe"


@pytest.mark.parametrize(
    ("url", "code"),
    [("ftp://example.com/recipe", "website_invalid_url"), ("http://localhost:8000/api", "website_forbidden_address"),
     ("https://www.instagram.com/ritakadosh_/", "invalid_instagram_url")],
)
def test_pasted_text_with_an_address_that_cannot_be_a_source_is_refused(client, use, url, code):
    extractor = use(StandIn(answer()))
    response = client.post("/api/imports/text", json={"text": SOURCE, "url": url})
    assert response.status_code == 422 and response.json()["error"]["code"] == code
    assert extractor.calls == []


def test_a_preview_sent_unchanged_is_flagged_on_the_draft(client, use):
    use(StandIn(answer()))
    draft = client.post(
        "/api/imports/text", json={"text": SOURCE, "url": POST, "possibly_incomplete": True}
    ).json()
    assert draft["issues"][0]["kind"] == "caption_incomplete"
    assert "קטוע" in draft["issues"][0]["message"]


def test_an_instagram_draft_saved_unclassified_keeps_its_original(client, use, reads):
    no_fit = {"fit": "no_fit", "category_id": None, "subcategory_id": None, "candidate_category_ids": []}
    use(StandIn(answer(classification=no_fit)))
    reads(found())
    draft = client.post("/api/imports/instagram", json={"url": POST}).json()
    assert draft["category"] is None
    body = {
        "title": draft["title"], "servings": draft["servings"], "ingredient_groups": draft["ingredient_groups"],
        "step_groups": draft["step_groups"], "notes": draft["notes"], "sources": draft["sources"],
        "category_id": None, "subcategory_id": None, "status": "saved",
    }
    saved = client.put(f"/api/recipes/{draft['id']}", json=body)
    assert saved.status_code == 200
    again = client.get(f"/api/recipes/{draft['id']}").json()
    assert again["status"] == "saved" and again["category"] is None
    assert again["original"]["text"] == SOURCE and again["original"]["url"] == POST
