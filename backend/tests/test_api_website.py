"""Importing a recipe page through POST /api/imports/link, offline: the website importer for a page, the
Instagram importer for a post, the draft and its original, the picture, and every way it can fail.
A stand-in transport answers for the websites; nothing reaches the internet."""

import json

import httpx2
import pytest

from app.api.imports import get_web_reader
from app.errors import ApiError
from app.extraction.output import Classification
from app.importers.website import WebReader
from tests.test_api_imports import StandIn, answer, use  # noqa: F401  (use is a fixture)
from tests.test_api_instagram import POST, found, reads  # noqa: F401  (reads is a fixture)
from tests.test_media import JPEG
from tests.test_website import BLOG, ENGLISH_ARRAY, HEBREW_GRAPH, ld

PAGE = "https://www.example.co.il/recipes/orange-cake/"
DESSERT = Classification(fit="clear", category_id=1, subcategory_id=None, candidate_category_ids=[])


class Classifier(StandIn):
    """A stand-in model that also chooses the category of a complete draft."""

    def __init__(self, result=None, classification: Classification | Exception = DESSERT) -> None:
        super().__init__(result if result is not None else answer())
        self.classification = classification
        self.classified: list[str] = []

    def classify_draft(self, draft, categories):
        self.classified.append(draft.title)
        if isinstance(self.classification, Exception):
            raise self.classification
        return self.classification


def html(body: str, head: str = "") -> httpx2.Response:
    return httpx2.Response(200, headers={"content-type": "text/html; charset=utf-8"}, content=f"<html><head>{head}</head><body>{body}</body></html>".encode())


@pytest.fixture
def site(client):
    """site({url: response}): the websites, as the importer will read them. Returns the requested addresses."""
    asked: list[str] = []

    def install(routes: dict[str, httpx2.Response]) -> list[str]:
        def handler(request: httpx2.Request) -> httpx2.Response:
            asked.append(str(request.url))
            return routes.get(str(request.url), httpx2.Response(404))

        reader = WebReader(transport=httpx2.MockTransport(handler), resolve=lambda host: ["93.184.216.34"], verify_peer=False)
        client.app.dependency_overrides[get_web_reader] = lambda: reader
        return asked

    yield install
    client.app.dependency_overrides.pop(get_web_reader, None)


def link(client, url: str = PAGE, **extra):
    return client.post("/api/imports/link", json={"url": url, **extra})


STRUCTURED = html("<h1>עוגת תפוזים ושקדים</h1>", ld(HEBREW_GRAPH) + '<meta property="og:site_name" content="המטבח של רותי">')
IMAGE = "https://www.example.co.il/images/cake.jpg"


def test_a_page_with_recipe_data_becomes_a_draft_in_its_own_words(client, use, site):
    model = use(Classifier())
    asked = site({PAGE: STRUCTURED, IMAGE: httpx2.Response(200, headers={"content-type": "image/jpeg"}, content=JPEG)})
    response = link(client)
    assert response.status_code == 201
    draft = response.json()
    assert draft["title"] == "עוגת תפוזים & שקדים" and draft["status"] == "draft"
    assert draft["ingredient_groups"] == [{"name": None, "ingredients": [
        {"text": "200 גרם קמח", "quantity": "200 גרם", "derived_from": None}, {"text": "2 ביצים L", "quantity": "2", "derived_from": None},
        {"text": "מיץ מ-3 תפוזים", "quantity": "3", "derived_from": None}, {"text": "קורט מלח", "quantity": "קורט", "derived_from": None}]}]
    assert draft["step_groups"] == [
        {"name": "לבצק", "steps": ["מערבבים את הקמח עם הביצים.", "מוסיפים את מיץ התפוזים."]},
        {"name": "אפייה", "steps": ["אופים 40 דקות ב-180 מעלות."]},
    ]
    assert draft["servings"] == "10 פרוסות" and draft["notes"] == ["זמן הכנה: 20 דקות · זמן בישול: שעה"]
    # The model only chose the category: it never read or wrote the recipe.
    assert model.calls == [] and model.classified == ["עוגת תפוזים & שקדים"]
    assert draft["category"] == {"id": 1, "name": "קינוחים"}
    # The credit and the source come from the page.
    assert draft["sources"] == [{"kind": "website", "url": PAGE, "creators": [{"name": "רותי כהן", "username": None}]}]
    original = draft["original"]
    assert (original["kind"], original["url"], original["retrieved_from"], original["model"]) == ("website", PAGE, "json_ld", "claude-test-model")
    assert original["text"].startswith("עוגת תפוזים & שקדים") and original["site_name"] == "המטבח של רותי"
    # The page's main picture, saved like any picture, as the cover.
    [picture] = draft["media"]
    assert (picture["origin"], picture["kind"], picture["post_url"]) == ("website", "image", PAGE)
    assert draft["cover_id"] == picture["id"] and client.get(picture["file"]["url"]).content == JPEG
    assert asked == [PAGE, IMAGE]


def test_the_page_s_recipe_data_is_kept_with_the_original(client, use, site, data_dir):
    use(Classifier())
    site({PAGE: STRUCTURED})
    recipe_id = link(client).json()["id"]
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(data_dir / "recipes.db")) as db:
        details = json.loads(db.execute("SELECT source_details FROM recipe_imports WHERE recipe_id = ?", (recipe_id,)).fetchone()[0])
    assert details["structured_data"]["name"] == "עוגת תפוזים &amp; שקדים"  # exactly as the page had it
    assert details["image"] == IMAGE


def test_without_a_model_the_recipe_data_still_fills_the_draft_unclassified(client, use, site):
    model = use(Classifier())
    site({PAGE: STRUCTURED})
    draft = link(client, use_model=False).json()
    assert model.classified == [] and draft["category"] is None and draft["original"]["model"] is None
    assert draft["ingredient_groups"][0]["ingredients"][0]["text"] == "200 גרם קמח"
    assert "classification_unresolved" in [issue["kind"] for issue in draft["issues"]]


def test_a_model_that_cannot_classify_leaves_the_draft_unclassified_not_unsaved(client, use, site):
    use(Classifier(classification=ApiError(503, "extraction_busy", "busy")))
    site({PAGE: STRUCTURED})
    response = link(client)
    assert response.status_code == 201 and response.json()["category"] is None
    assert any("לא סווג" in issue["message"] for issue in response.json()["issues"])


@pytest.mark.parametrize(
    "picture",
    [httpx2.Response(404), httpx2.Response(200, headers={"content-type": "text/html"}, content=b"<html>not a picture</html>")],
)
def test_a_picture_that_cannot_be_saved_never_stops_the_import(client, use, site, picture):
    use(Classifier())
    site({PAGE: STRUCTURED, IMAGE: picture})
    response = link(client)
    assert response.status_code == 201 and response.json()["media"] == []
    assert response.json()["issues"][0]["kind"] == "media_incomplete"


def test_a_page_without_recipe_data_goes_through_the_extraction_with_its_main_text(client, use, site):
    model = use(Classifier())
    blog = "https://blog.example.com/orange-cake"
    site({blog: html(BLOG, '<meta name="author" content="מירב"><meta property="og:site_name" content="הבלוג של מירב">')})
    draft = link(client, blog).json()
    [(text, _)] = model.calls
    assert "200 גרם קמח" in text and "איזה מתכון מעולה" not in text and "פרסומת" not in text
    assert draft["original"]["retrieved_from"] == "page_text" and draft["original"]["text"] == text
    assert draft["sources"][0]["creators"] == [{"name": "מירב", "username": None}]
    assert model.classified == []  # the extraction classifies as it always does


def test_a_page_whose_text_is_not_a_recipe_says_so_and_keeps_the_address(client, use, site):
    use(Classifier(answer(is_recipe=False)))
    page = "https://news.example.com/article"
    site({page: html("<article><h1>חדשות</h1>" + "<p>ידיעה ארוכה על מזג האוויר מחר.</p>" * 10 + "</article>")})
    response = link(client, page)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "website_no_recipe" and response.json()["error"]["details"]["url"] == page
    assert client.get("/api/recipes").json()[0]["original"] is None  # nothing saved: still the samples


def test_when_the_model_runs_out_of_time_nothing_is_saved_and_the_error_keeps_the_link_and_the_limit(client, use, site):
    use(Classifier(ApiError(504, "extraction_timeout", "The local model did not finish within 300 seconds.", {"seconds": 300})))
    blog = "https://blog.example.com/orange-cake"
    site({blog: html(BLOG)})
    before = len(client.get("/api/recipes").json())
    response = link(client, blog)
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "extraction_timeout"
    assert response.json()["error"]["details"] == {"seconds": 300, "url": blog}
    assert len(client.get("/api/recipes").json()) == before


def test_a_page_whose_text_gives_steps_but_no_ingredients_is_not_saved_half_filled(client, use, site):
    use(Classifier(answer(ingredient_groups=[])))
    blog = "https://blog.example.com/orange-cake"
    site({blog: html(BLOG)})
    response = link(client, blog)
    assert response.status_code == 422 and response.json()["error"]["code"] == "website_incomplete"
    assert response.json()["error"]["details"]["url"] == blog


def test_a_bot_check_is_reported_as_blocked_without_asking_the_model(client, use, site):
    model = use(Classifier())
    site({PAGE: html("<p>...but your activity made us think that you are a bot. Please solve this CAPTCHA.</p>", "<title>Radware Block Page</title>")})
    response = link(client)
    assert response.status_code == 502 and response.json()["error"]["code"] == "website_blocked"
    assert model.calls == []


@pytest.mark.parametrize(
    ("answer_", "status", "code"),
    [(httpx2.Response(403), 502, "website_blocked"), (httpx2.Response(404), 502, "website_not_found"),
     (httpx2.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF"), 422, "website_not_html")],
)
def test_a_page_that_cannot_be_read_says_why(client, use, site, answer_, status, code):
    use(Classifier())
    site({PAGE: answer_})
    response = link(client)
    assert response.status_code == status and response.json()["error"]["code"] == code
    assert response.json()["error"]["details"]["url"] == PAGE


def test_a_private_address_is_never_requested(client, use, site):
    use(Classifier())
    asked = site({})
    response = link(client, "http://192.168.1.1/recipes")
    assert response.status_code == 422 and response.json()["error"]["code"] == "website_forbidden_address"
    assert asked == []


def test_a_page_with_several_recipes_and_none_its_own_is_not_guessed(client, use, site):
    use(Classifier())
    first = {"@type": "Recipe", "name": "Lemon Bars", "recipeIngredient": ["4 lemons"], "recipeInstructions": "Bake."}
    second = {"@type": "Recipe", "name": "Brownies", "recipeIngredient": ["cocoa"], "recipeInstructions": "Bake."}
    site({PAGE: html("<h1>Ten desserts</h1>", ld(first, second))})
    response = link(client)
    assert response.status_code == 422 and response.json()["error"]["code"] == "website_ambiguous"
    assert response.json()["error"]["details"]["recipes"] == ["Lemon Bars", "Brownies"]


def test_the_same_page_again_is_noticed_before_it_is_read(client, use, site):
    use(Classifier())
    asked = site({PAGE: STRUCTURED})
    first = link(client).json()
    read_before = len(asked)
    again = link(client, "http://example.co.il/recipes/orange-cake?utm_source=whatsapp")
    assert again.status_code == 409 and again.json()["error"]["code"] == "duplicate_link"
    assert again.json()["error"]["details"]["matches"][0]["id"] == first["id"]
    assert len(asked) == read_before  # not read again
    assert link(client, allow_duplicate=True).status_code == 201


def test_an_english_page_with_recipe_data(client, use, site):
    use(Classifier())
    page = "https://example.com/banana-bread"
    site({page: html("<h1>Banana Bread</h1>", ld(ENGLISH_ARRAY))})
    draft = link(client, page).json()
    assert [i["text"] for i in draft["ingredient_groups"][0]["ingredients"]] == ["3 ripe bananas", "1/3 cup melted butter", "1 teaspoon baking soda"]
    assert draft["step_groups"][0]["steps"] == ["Mash the bananas.", "Stir in the butter.", "Bake for 55 minutes at 175°C."]
    assert draft["sources"][0]["creators"] == [{"name": "Sam", "username": None}, {"name": "Alex", "username": None}]


def test_an_instagram_link_goes_to_the_instagram_importer(client, use, reads, site):
    use(Classifier())
    reader = reads(found())
    asked = site({})
    response = link(client, POST)
    assert response.status_code == 201 and reader.calls == [POST] and asked == []
    draft = response.json()
    assert draft["original"]["kind"] == "instagram" and draft["sources"][0]["creators"][0]["username"] == "baker"
    assert link(client, POST).json()["error"]["code"] == "duplicate_link"  # its duplicate check, as before


def test_a_page_whose_recipe_data_flattens_its_steps_is_imported_with_the_page_s_steps_and_groups(client, use, site):
    from tests.test_website import FLATTENED, FLATTENED_PAGE, THREE_STEPS

    use(Classifier())
    site({PAGE: html(FLATTENED_PAGE, ld(FLATTENED))})
    draft = link(client).json()
    assert draft["step_groups"] == [{"name": None, "steps": THREE_STEPS}]
    assert [(group["name"], [item["text"] for item in group["ingredients"]]) for group in draft["ingredient_groups"]] == [
        ("רוטב", ["1 פחית קרם קוקוס", "1 כף סוכר חום או סילאן"]),
        ("מוקפץ", ["400 גרם אטריות מבושלות", "1 בצל"]),
    ]
    assert draft["sources"][0]["creators"] == [{"name": "צלמת האתר", "username": None}]
    original = draft["original"]["text"]
    assert "\n1. טוחנים בבלנדר" in original and "caption" not in original and "בשיתוף" not in original


def test_a_page_whose_steps_fry_in_oil_it_does_not_list_gets_a_derived_line_and_keeps_its_original(client, use, site):
    data = {"@type": "Recipe", "name": "חביתת ירק", "author": {"@type": "Person", "name": "שף"},
            "recipeIngredient": ["3 ביצים", "צרור פטרוזיליה"],
            "recipeInstructions": ["טורפים את הביצים עם הפטרוזיליה.", "מחממים מעט שמן במחבת ויוצקים פנימה את התערובת."]}
    use(Classifier())
    site({PAGE: html("<h1>חביתת ירק</h1>", ld(data))})
    draft = link(client).json()
    [line] = [item for group in draft["ingredient_groups"] for item in group["ingredients"] if item["derived_from"]]
    assert line == {"text": "מעט שמן לטיגון", "quantity": "מעט", "derived_from": "מחממים מעט שמן במחבת ויוצקים פנימה את התערובת."}
    assert not any(issue["kind"] == "ingredient_only_in_steps" for issue in draft["issues"])
    assert "לטיגון" not in draft["original"]["text"]  # the original is what the page gave, nothing added

    saved = client.put(f"/api/recipes/{draft['id']}", json={
        "title": draft["title"], "ingredient_groups": draft["ingredient_groups"], "step_groups": draft["step_groups"],
        "notes": draft["notes"], "sources": draft["sources"], "category_id": 1, "status": "saved", "issues": []}).json()
    assert saved["ingredient_groups"] == draft["ingredient_groups"]  # saved with where it comes from
