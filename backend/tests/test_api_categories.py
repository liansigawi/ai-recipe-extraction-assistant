"""Creating and editing categories through the API: ids and recipes stay, the parent rule holds."""

import pytest

from tests.test_api_imports import StandIn, answer, use  # noqa: F401  (use is a fixture)
from tests.test_extraction_review import SOURCE

DESSERTS, CAKES, FROZEN = 1, 11, 15


def categories(client) -> list[dict]:
    return client.get("/api/categories").json()


def test_a_new_top_level_category_and_a_subcategory_under_it(client):
    soups = client.post("/api/categories", json={"name": "רטבים", "description": "רטבים וממרחים"})
    assert soups.status_code == 201
    soups = soups.json()
    assert soups == {"id": 17, "name": "רטבים", "description": "רטבים וממרחים", "parent_id": None}
    cold = client.post("/api/categories", json={"name": "רטבים חריפים", "description": "", "parent_id": soups["id"]}).json()
    assert cold["parent_id"] == soups["id"] and cold["description"] is None  # an empty description is none
    listed = categories(client)[-1]
    assert (listed["name"], [s["name"] for s in listed["subcategories"]]) == ("רטבים", ["רטבים חריפים"])


def test_renaming_keeps_the_id_and_every_recipe_in_it(client):
    recipe = next(r for r in client.get("/api/recipes").json() if r["category"] and r["category"]["id"] == DESSERTS)
    response = client.put(f"/api/categories/{DESSERTS}", json={"name": "מתוקים", "description": "כל מה שמתוק"})
    assert response.status_code == 200 and response.json()["id"] == DESSERTS
    again = client.get(f"/api/recipes/{recipe['id']}").json()
    assert again["category"] == {"id": DESSERTS, "name": "מתוקים"}
    assert categories(client)[0]["description"] == "כל מה שמתוק"


def test_editing_a_subcategory_keeps_its_parent(client):
    response = client.put(f"/api/categories/{FROZEN}", json={"name": "גלידות", "description": "גלידות וארטיקים"})
    assert response.json() == {"id": FROZEN, "name": "גלידות", "description": "גלידות וארטיקים", "parent_id": DESSERTS}


@pytest.mark.parametrize(
    "body",
    [
        {"name": "קינוחים"},  # a top-level category of that name exists
        {"name": "  ארוחות בשריות "},  # spaces around it do not make it new
        {"name": "עוגות", "parent_id": DESSERTS},  # that subcategory exists
    ],
)
def test_a_name_that_is_taken_at_its_level_is_refused(client, body):
    response = client.post("/api/categories", json=body)
    assert response.status_code == 409 and response.json()["error"]["code"] == "category_name_taken"


def test_the_same_name_at_another_level_is_allowed(client):
    # "מאפים" under desserts, and later a top-level "מאפים" for savory baking: different places.
    assert client.post("/api/categories", json={"name": "מאפים", "parent_id": DESSERTS}).status_code == 201
    assert client.post("/api/categories", json={"name": "מאפים"}).status_code == 201


def test_renaming_to_a_taken_name_is_refused_and_keeping_your_own_name_is_fine(client):
    assert client.put(f"/api/categories/{CAKES}", json={"name": "מאפים מתוקים"}).status_code == 409
    assert client.put(f"/api/categories/{CAKES}", json={"name": "עוגות", "description": "חדש"}).status_code == 200


@pytest.mark.parametrize("parent_id", [CAKES, 999])  # a subcategory, or nothing: subcategories are one level deep
def test_a_subcategory_needs_an_existing_top_level_parent(client, parent_id):
    response = client.post("/api/categories", json={"name": "פחזניות", "parent_id": parent_id})
    assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_parent"


@pytest.mark.parametrize("body", [{"name": ""}, {"name": "   "}, {"name": "א" * 61}, {"name": "x", "description": "d" * 601}])
def test_names_and_descriptions_are_checked(client, body):
    response = client.post("/api/categories", json=body)
    assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_request"


def test_editing_a_category_that_does_not_exist(client):
    response = client.put("/api/categories/999", json={"name": "x"})
    assert response.status_code == 404 and response.json()["error"]["code"] == "category_not_found"


def test_the_parent_cannot_be_changed_by_an_edit(client):
    response = client.put(f"/api/categories/{FROZEN}", json={"name": "גלידות", "parent_id": 2})
    assert response.status_code == 422  # an unknown field: the parent is not part of an edit


def test_a_new_category_and_its_description_reach_the_next_import(client, use):
    client.post("/api/categories", json={"name": "רטבים", "description": "רטבים וממרחים"})
    extractor = use(StandIn(answer()))
    client.post("/api/imports/text", json={"text": SOURCE})
    [(_, given)] = extractor.calls
    soups = next(category for category in given if category.name == "רטבים")
    assert soups.description == "רטבים וממרחים"


def test_changes_need_the_notebook_page(client):
    response = client.post("/api/categories", json={"name": "רטבים"}, headers={"Origin": "https://example.com"})
    assert response.status_code == 403
