"""Reading recipes through the API, and the rules of the recipe contract.

Creating, saving and deleting are in test_persistence.py.
"""

import pytest
from pydantic import ValidationError

from app.schemas import Ingredient, Recipe, RecipeInput
from tests.conftest import recipe_by_title

CHOCOLATE_CAKE, CHICKEN, GRANOLA = "עוגת שוקולד עם גנאש", "עוף בסיר עם אורז", "Oat and Date Granola Bars"


def test_a_new_database_lists_the_four_samples_newest_first(client):
    response = client.get("/api/recipes")
    assert response.status_code == 200
    recipes = response.json()
    assert [recipe["title"] for recipe in recipes] == [CHOCOLATE_CAKE, CHICKEN, "פיצה מבצק יוגורט", GRANOLA]
    assert all(recipe["is_sample"] for recipe in recipes)  # the page labels these as invented examples
    for recipe in recipes:
        Recipe.model_validate(recipe)  # every item matches the contract the frontend types mirror


def test_categories_are_the_three_starter_categories(client):
    categories = client.get("/api/categories").json()
    assert [category["name"] for category in categories] == ["קינוחים", "בישולים", "ארוחות קלילות"]
    assert all(category["subcategories"] == [] for category in categories)


def test_json_uses_snake_case_and_explicit_nulls(client):
    granola = recipe_by_title(client, GRANOLA)
    assert granola["category"] is None  # unclassified: present as null, not missing
    assert granola["ingredient_groups"][0]["name"] is None


def test_get_one_recipe_keeps_alternative_methods_apart(client):
    chicken = client.get(f"/api/recipes/{recipe_by_title(client, CHICKEN)['id']}").json()
    assert [group["name"] for group in chicken["step_groups"]] == ["הכנה", "בסיר לחץ", "בסיר רגיל", "האורז"]


def test_ingredient_without_quantity_stays_null(client):
    chicken = recipe_by_title(client, CHICKEN)
    salt = next(i for i in chicken["ingredient_groups"][0]["ingredients"] if i["text"] == "מלח ופלפל")
    assert salt["quantity"] is None  # never "to taste" or an invented amount


def test_unknown_recipe_uses_the_error_format(client):
    response = client.get("/api/recipes/999")
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "recipe_not_found", "message": "There is no recipe with id 999.", "details": None}
    }


def test_invalid_id_uses_the_error_format(client):
    response = client.get("/api/recipes/abc")
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert error["details"][0]["loc"] == ["path", "recipe_id"]


@pytest.mark.parametrize("recipe_id", ["0", "-1", str(2**63)])
def test_ids_outside_the_valid_range_are_invalid_requests(client, recipe_id):
    response = client.get(f"/api/recipes/{recipe_id}")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_contract_is_published_in_the_openapi_document(client):
    document = client.get("/openapi.json").json()
    schemas = document["components"]["schemas"]
    assert {"Recipe", "RecipeInput", "Category", "CategoryRef"} <= schemas.keys()
    # Models used both in requests and responses get two published variants: in the "-Output" one every
    # field is required (the API always sends it); in the "-Input" one fields with defaults may be left out.
    assert {"Ingredient-Input", "Ingredient-Output", "Source-Input", "Source-Output"} <= schemas.keys()
    assert set(schemas["Recipe"]["required"]) == set(schemas["Recipe"]["properties"])
    assert set(schemas["RecipeInput"]["required"]) == {"title"}
    # Errors are documented with their real shape, {"error": {...}}.
    responses = document["paths"]["/api/recipes/{recipe_id}"]["get"]["responses"]
    for status in ("404", "422"):
        assert responses[status]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")


# --- Contract rules ----------------------------------------------------------------------


def test_quantity_must_be_quoted_exactly_as_written():
    assert Ingredient(text="115 גר’ חמאה רכה", quantity="115 גר’").quantity == "115 גר’"
    with pytest.raises(ValidationError, match="must be quoted exactly as written"):
        Ingredient(text="115 גר’ חמאה רכה", quantity="115 גרם")  # normalized: rejected
    with pytest.raises(ValidationError, match="must be quoted exactly as written"):
        Ingredient(text="115 גר’ חמאה רכה", quantity="115 גר'")  # a different apostrophe: rejected
    with pytest.raises(ValidationError):
        Ingredient(text="מלח ופלפל", quantity="")  # empty is not "no quantity"; None is


@pytest.mark.parametrize(
    ("text", "quantity"),
    [("200 גרם שוקולד מריר", "2"), ("200 גרם שוקולד מריר", "20"), ("1/2 כפית מלח", "1"), ("2.5 cups flour", "2")],
)
def test_quantity_cannot_be_cut_out_of_a_longer_number(text, quantity):
    with pytest.raises(ValidationError, match="must be quoted exactly as written"):
        Ingredient(text=text, quantity=quantity)


@pytest.mark.parametrize(
    ("text", "quantity"),
    [("230גרם סוכר לבן", "230גרם"), ("4 ביצים L (טמפ׳ חדר) מופרדות", "4"), ("2 cups, chopped", "2 cups"), ("קורט מלח", "קורט")],
)
def test_real_shaped_quantities_are_accepted(text, quantity):
    assert Ingredient(text=text, quantity=quantity).quantity == quantity


def test_invisible_marks_at_the_edges_are_trimmed_but_kept_inside():
    lrm, rlm = "\N{LEFT-TO-RIGHT MARK}", "\N{RIGHT-TO-LEFT MARK}"
    # Seen in a real caption: a title line starting with an LRM, which flips a Hebrew heading left to right.
    ingredient = Ingredient(text=f"{lrm}100 גרם חמאה {rlm}רכה{rlm}", quantity="100 גרם")
    assert ingredient.text == f"100 גרם חמאה {rlm}רכה"
    with pytest.raises(ValidationError):
        Ingredient(text=f" {lrm} {rlm} ")  # only invisible marks: empty


def test_timestamps_must_include_a_time_zone(client):
    data = recipe_by_title(client, CHOCOLATE_CAKE)
    assert data["created_at"].endswith("Z")  # sent in UTC, marked as such
    data["created_at"] = "2026-10-19T08:00:00"  # no "Z": the browser would read it as local time
    with pytest.raises(ValidationError, match="timezone"):
        Recipe.model_validate(data)


def test_a_source_keeps_every_creator(client):
    # Seen live: a collaboration post has a main author and a co-author.
    data = recipe_by_title(client, GRANOLA)
    data["sources"] = [{"kind": "instagram", "url": "https://www.instagram.com/p/Example12345/", "creators": ["baker", "partner.shop"]}]
    assert Recipe.model_validate(data).sources[0].creators == ["baker", "partner.shop"]


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///C:/Users/me/notes.txt", "www.example.com", "https://exa mple.com"])
def test_a_source_link_must_be_a_web_address(url):
    # The page shows source links as clickable; only http(s) addresses may become links.
    with pytest.raises(ValidationError, match="should match pattern"):
        RecipeInput(title="עוגה", sources=[{"kind": "website", "url": url}])
    assert RecipeInput(title="עוגה", sources=[{"kind": "website", "url": " https://example.com/cake "}]).sources[0].url == (
        "https://example.com/cake"
    )


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Ingredient(text="2 ביצים", quantity="2", amount_grams=100)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RecipeInput(title="עוגה", category="קינוחים")  # categories are chosen by id, never by name


def test_subcategory_requires_a_category(client):
    data = recipe_by_title(client, GRANOLA)
    data["subcategory"] = {"id": 9, "name": "חטיפים"}
    with pytest.raises(ValidationError, match="a subcategory requires a category"):
        Recipe.model_validate(data)
    with pytest.raises(ValidationError, match="a subcategory requires a category"):
        RecipeInput(title="עוגה", subcategory_id=9)


def test_groups_and_steps_cannot_be_empty():
    with pytest.raises(ValidationError):
        RecipeInput(title="עוגה", step_groups=[{"name": None, "steps": []}])
    with pytest.raises(ValidationError):
        RecipeInput(title="עוגה", ingredient_groups=[{"name": "לבצק", "ingredients": []}])


def test_text_is_trimmed_but_otherwise_kept():
    ingredient = Ingredient(text="  150 גרם חמאה מומסת  ", quantity="150 גרם")
    assert ingredient.text == "150 גרם חמאה מומסת"
