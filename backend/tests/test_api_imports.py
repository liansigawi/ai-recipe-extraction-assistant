"""Importing pasted text through the API: draft, original text, review and save, failures.

The extractor is replaced by a stand-in that returns a prepared answer, so these tests run
offline. (conftest.py also makes sure no test can create a real Claude client.)
"""

import sqlite3
from contextlib import closing

import pytest

from app.api.imports import get_extractor_factory
from app.errors import ApiError
from app.extraction.output import ExtractionOutput
from tests.test_extraction_review import SOURCE
from tests.test_extraction_review import answer as review_answer

DESSERT = {"fit": "clear", "category_id": 1, "subcategory_id": None, "candidate_category_ids": []}


def answer(**changes) -> ExtractionOutput:
    """The faithful answer, classified into a starter category (a new database has no subcategories)."""
    return review_answer(**({"classification": DESSERT} | changes))


class StandIn:
    """Behaves like ClaudeExtractor: records what it was given, returns or raises what it was told."""

    model = "claude-test-model"

    def __init__(self, result: ExtractionOutput | Exception) -> None:
        self.result = result
        self.calls: list[tuple[str, list]] = []

    def extract(self, text, categories):
        self.calls.append((text, categories))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def use(client):
    """use(StandIn(...)): the import endpoint gets this extractor instead of a real one."""

    def install(extractor: StandIn) -> StandIn:
        client.app.dependency_overrides[get_extractor_factory] = lambda: lambda: extractor
        return extractor

    yield install
    client.app.dependency_overrides.clear()


def recipe_count(client) -> int:
    return len(client.get("/api/recipes").json())


def test_extraction_info_says_whether_a_key_is_set_and_never_shows_it(client, monkeypatch):
    assert client.get("/api/extraction").json() == {"configured": False, "model": "claude-opus-5-5"}
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-never-real")
    monkeypatch.setenv("RECIPES_MODEL", "claude-sonnet-5-5")
    response = client.get("/api/extraction")
    assert response.json() == {"configured": True, "model": "claude-sonnet-5-5"}
    assert "sk-ant" not in response.text


def test_an_import_saves_a_draft_with_the_original_text_exactly_as_pasted(client, use):
    extractor = use(StandIn(answer()))
    pasted = SOURCE + "\n\n"  # trailing line breaks too: the original is kept exactly
    response = client.post("/api/imports/text", json={"text": pasted})

    assert response.status_code == 201
    draft = response.json()
    assert draft["status"] == "draft"
    assert draft["title"] == "עוגת תפוזים"
    assert draft["category"] == {"id": 1, "name": "קינוחים"}
    assert draft["original"]["text"] == pasted
    assert draft["original"]["model"] == "claude-test-model"
    assert draft["original"]["imported_at"].endswith("Z")
    assert draft["issues"] == []
    # The extractor got the text and the categories from the database.
    [(text, categories)] = extractor.calls
    assert text == pasted and [category.name for category in categories] == ["קינוחים", "בישולים", "ארוחות קלילות"]


def test_the_review_save_keeps_the_original_and_cannot_change_it(client, use):
    use(StandIn(answer(title_written_in_text=False)))
    draft = client.post("/api/imports/text", json={"text": SOURCE}).json()
    assert [issue["kind"] for issue in draft["issues"]] == ["missing_title"]

    edited = {key: draft[key] for key in ("title", "servings", "ingredient_groups", "step_groups", "notes", "sources")}
    edited |= {"title": "עוגת התפוזים של סבתא", "category_id": 1, "status": "saved", "issues": []}
    saved = client.put(f"/api/recipes/{draft['id']}", json=edited).json()
    assert saved["status"] == "saved" and saved["issues"] == [] and saved["title"] == "עוגת התפוזים של סבתא"
    assert saved["original"] == draft["original"]

    # The original is not part of what a save accepts.
    response = client.put(f"/api/recipes/{draft['id']}", json=edited | {"original": {"kind": "text", "text": "x"}})
    assert response.status_code == 422
    assert client.get(f"/api/recipes/{draft['id']}").json()["original"]["text"] == SOURCE


def test_a_draft_can_be_saved_as_a_draft_with_its_remaining_issues(client, use):
    use(StandIn(answer(title_written_in_text=False, classification={"fit": "no_fit", "category_id": None, "subcategory_id": None, "candidate_category_ids": []})))
    draft = client.post("/api/imports/text", json={"text": SOURCE}).json()
    assert len(draft["issues"]) == 2
    body = {key: draft[key] for key in ("title", "servings", "ingredient_groups", "step_groups", "notes", "sources")}
    kept = client.put(f"/api/recipes/{draft['id']}", json=body | {"status": "draft", "issues": draft["issues"][:1]}).json()
    assert kept["status"] == "draft" and kept["issues"] == draft["issues"][:1]
    assert kept["category"] is None  # unresolved stays unclassified until the person chooses


@pytest.mark.parametrize(
    "error",
    [
        ApiError(502, "extraction_unreachable", "Could not reach the Claude API."),
        ApiError(504, "extraction_timeout", "The Claude API did not answer in time."),
        ApiError(502, "extraction_invalid_output", "Claude's answer did not have the expected shape."),
    ],
)
def test_when_extraction_fails_nothing_is_saved_and_the_error_says_why(client, use, error):
    use(StandIn(error))
    before = recipe_count(client)
    response = client.post("/api/imports/text", json={"text": SOURCE})
    assert response.status_code == error.status_code
    assert response.json()["error"]["code"] == error.code
    assert recipe_count(client) == before


def test_text_that_is_not_a_recipe_is_refused_and_not_saved(client, use):
    use(StandIn(answer(is_recipe=False, ingredient_groups=[], step_groups=[], notes=[])))
    before = recipe_count(client)
    response = client.post("/api/imports/text", json={"text": "היה ערב נעים במסעדה."})
    assert (response.status_code, response.json()["error"]["code"]) == (422, "not_a_recipe")
    assert recipe_count(client) == before


def test_without_an_api_key_the_import_explains_how_to_set_one(client):
    response = client.post("/api/imports/text", json={"text": SOURCE})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "extraction_not_configured"
    assert "README" in response.json()["error"]["message"]


def test_without_the_model_the_text_is_saved_as_a_draft_to_fill_in(client):
    # Works with no API key at all, and never calls an extractor.
    response = client.post("/api/imports/text", json={"text": SOURCE, "use_model": False})
    assert response.status_code == 201
    draft = response.json()
    assert draft["status"] == "draft" and draft["original"]["model"] is None
    assert draft["original"]["text"] == SOURCE
    assert [issue["kind"] for issue in draft["issues"]] == ["not_extracted", "missing_title"]


@pytest.mark.parametrize(
    "text",
    ["", "   \n\t ", "\N{LEFT-TO-RIGHT MARK}\n", "א" * 20_001],
    ids=["empty", "only-spaces", "only-an-invisible-mark", "too-long"],  # short names: the text itself is huge
)
def test_empty_or_too_long_text_is_refused(client, text):
    response = client.post("/api/imports/text", json={"text": text})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_an_invalid_category_from_the_model_never_reaches_the_database(client, use, data_dir):
    use(StandIn(answer(classification={"fit": "clear", "category_id": 99, "subcategory_id": None, "candidate_category_ids": []})))
    draft = client.post("/api/imports/text", json={"text": SOURCE}).json()
    assert draft["category"] is None
    assert [issue["kind"] for issue in draft["issues"]] == ["classification_unresolved"]
    with closing(sqlite3.connect(data_dir / "recipes.db")) as db:
        assert db.execute("SELECT count(*) FROM categories").fetchone() == (3,)  # nothing created


def test_imports_are_refused_from_other_sites(client, use):
    extractor = use(StandIn(answer()))
    response = client.post("/api/imports/text", json={"text": SOURCE}, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert extractor.calls == []  # refused before any paid call
