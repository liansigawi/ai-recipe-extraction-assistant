"""Creating, saving and deleting recipes in SQLite, the category rule, and data surviving a restart.

Each test gets its own empty data folder (see conftest.py). A "restart" is a second
`with TestClient(app)` on the same folder: the app starts again and opens the same file.
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app import models
from app.db import utc_now
from app.main import app
from app.sample_data import ADDED_CATEGORIES, STARTER_CATEGORIES

NEW_RECIPE = {
    "title": "עוגת תפוזים",
    "category_id": 1,
    "servings": "10 פרוסות",
    "ingredient_groups": [
        {"name": "לבצק", "ingredients": [{"text": "200 גרם קמח", "quantity": "200 גרם"}, {"text": "מלח", "quantity": None}]},
    ],
    "step_groups": [{"name": None, "steps": ["מערבבים.", "אופים 30–35 דקות ב-180 מעלות."]}],
    "notes": ["אפשר להחליף בלימון."],
    "sources": [{"kind": "manual", "url": "https://www.instagram.com/p/Example12345/", "creators": [{"name": "Baker", "username": "baker"}]}],
}


def restarted() -> TestClient:
    """A fresh start of the app on the same data folder (the environment variable is still set)."""
    return TestClient(app, base_url="http://localhost")


def add_subcategory(client: TestClient, name: str, parent_id: int) -> int:
    """Insert a subcategory directly (category management arrives in milestone 6)."""
    with client.app.state.session_factory() as session:
        row = models.Category(name=name, parent_id=parent_id)
        session.add(row)
        session.commit()
        return row.id


# --- Create, save, delete -----------------------------------------------------------------------


def test_create_returns_the_stored_recipe(client):
    response = client.post("/api/recipes", json=NEW_RECIPE)
    assert response.status_code == 201
    created = response.json()
    assert created["id"] > 0 and created["is_sample"] is False
    assert created["category"] == {"id": 1, "name": "קינוחים"}
    assert created["created_at"] == created["updated_at"] and created["created_at"].endswith("Z")
    for field in ("title", "servings", "ingredient_groups", "step_groups", "notes", "sources"):
        assert created[field] == NEW_RECIPE[field]
    assert client.get(f"/api/recipes/{created['id']}").json() == created
    assert client.get("/api/recipes").json()[0]["id"] == created["id"]  # newest first


def test_save_replaces_the_editable_fields_and_keeps_created_at(client):
    created = client.post("/api/recipes", json=NEW_RECIPE).json()
    edited = {**NEW_RECIPE, "title": "עוגת תפוזים ושקדים", "category_id": None, "notes": [], "sources": []}
    response = client.put(f"/api/recipes/{created['id']}", json=edited)
    assert response.status_code == 200
    saved = response.json()
    assert saved["title"] == "עוגת תפוזים ושקדים" and saved["category"] is None
    assert saved["notes"] == [] and saved["sources"] == []
    assert saved["created_at"] == created["created_at"]
    assert saved["updated_at"] > created["updated_at"]


def test_delete_removes_the_recipe_and_its_sources(client, data_dir):
    created = client.post("/api/recipes", json=NEW_RECIPE).json()
    assert client.delete(f"/api/recipes/{created['id']}").status_code == 204
    assert client.get(f"/api/recipes/{created['id']}").status_code == 404
    with sqlite3.connect(data_dir / "recipes.db") as db:
        assert db.execute("SELECT COUNT(*) FROM recipe_sources WHERE recipe_id = ?", (created["id"],)).fetchone() == (0,)


def test_saving_or_deleting_an_unknown_recipe_is_a_404(client):
    assert client.put("/api/recipes/999", json=NEW_RECIPE).json()["error"]["code"] == "recipe_not_found"
    assert client.delete("/api/recipes/999").json()["error"]["code"] == "recipe_not_found"


def test_editing_a_sample_keeps_its_sample_label(client):
    sample = client.get("/api/recipes").json()[0]
    edited = {**NEW_RECIPE, "title": sample["title"] + " (שלי)"}
    assert client.put(f"/api/recipes/{sample['id']}", json=edited).json()["is_sample"] is True


def test_invalid_input_is_refused_and_nothing_is_saved(client):
    before = len(client.get("/api/recipes").json())
    bad = {**NEW_RECIPE, "ingredient_groups": [{"name": None, "ingredients": [{"text": "200 גרם קמח", "quantity": "2"}]}]}
    response = client.post("/api/recipes", json=bad)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert error["details"][0]["loc"][:5] == ["body", "ingredient_groups", 0, "ingredients", 0]  # the editor can point at the row
    assert len(client.get("/api/recipes").json()) == before


# --- Surviving a restart ------------------------------------------------------------------------------


def test_saved_recipes_and_edits_survive_a_restart(client):
    created = client.post("/api/recipes", json=NEW_RECIPE).json()
    client.put(f"/api/recipes/{created['id']}", json={**NEW_RECIPE, "title": "עוגת תפוזים ערוכה"})
    client.__exit__(None, None, None)  # stop the app (closes the database)

    with restarted() as again:
        reloaded = again.get(f"/api/recipes/{created['id']}").json()
        assert reloaded["title"] == "עוגת תפוזים ערוכה"
        assert reloaded["ingredient_groups"] == NEW_RECIPE["ingredient_groups"]
        assert reloaded["sources"] == NEW_RECIPE["sources"]


def test_samples_are_added_only_once_so_deleted_samples_stay_deleted(client):
    samples = client.get("/api/recipes").json()
    for sample in samples:
        client.delete(f"/api/recipes/{sample['id']}")
    client.__exit__(None, None, None)

    with restarted() as again:
        assert again.get("/api/recipes").json() == []
        assert len(again.get("/api/categories").json()) == len(STARTER_CATEGORIES) + len(ADDED_CATEGORIES)  # categories are not added twice either


# --- The category rule ---------------------------------------------------------------------------------


def test_unknown_category_is_refused_never_created(client):
    response = client.post("/api/recipes", json={**NEW_RECIPE, "category_id": 99})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unknown_category"
    assert len(client.get("/api/categories").json()) == len(STARTER_CATEGORIES) + len(ADDED_CATEGORIES)


def test_subcategory_must_belong_to_the_chosen_category(client):
    cakes = add_subcategory(client, "עוגות", parent_id=1)  # under קינוחים
    accepted = client.post("/api/recipes", json={**NEW_RECIPE, "category_id": 1, "subcategory_id": cakes})
    assert accepted.status_code == 201
    assert accepted.json()["subcategory"] == {"id": cakes, "name": "עוגות"}

    wrong_parent = client.post("/api/recipes", json={**NEW_RECIPE, "category_id": 2, "subcategory_id": cakes})
    assert wrong_parent.json()["error"]["code"] == "subcategory_not_in_category"
    as_top_level = client.post("/api/recipes", json={**NEW_RECIPE, "category_id": cakes})
    assert as_top_level.json()["error"]["code"] == "unknown_category"


FROZEN = 15  # "גלידות וקינוחים קפואים", a dessert type


def test_a_dessert_has_a_type_and_separately_whether_it_is_in_the_healthy_style(client):
    frozen = client.post("/api/recipes", json={**NEW_RECIPE, "category_id": 1, "subcategory_id": FROZEN, "healthy": True})
    assert frozen.status_code == 201
    assert (frozen.json()["subcategory"], frozen.json()["healthy"]) == ({"id": FROZEN, "name": "גלידות וקינוחים קפואים"}, True)
    regular = client.post("/api/recipes", json={**NEW_RECIPE, "category_id": 1, "healthy": False}).json()
    assert (regular["subcategory"], regular["healthy"]) == (None, False)  # a style without a type is fine
    undecided = client.post("/api/recipes", json={**NEW_RECIPE, "category_id": 1}).json()
    assert undecided["healthy"] is None  # not decided until someone decides
    # Saving it again without the field leaves it undecided; a decision can be taken back.
    again = client.put(f"/api/recipes/{frozen.json()['id']}", json={**NEW_RECIPE, "category_id": 1, "subcategory_id": FROZEN, "healthy": None})
    assert again.json()["healthy"] is None


@pytest.mark.parametrize(("category_id", "healthy"), [(2, True), (4, False), (None, True)])
def test_only_a_dessert_can_be_marked_healthy_style_or_not(client, category_id, healthy):
    response = client.post("/api/recipes", json={**NEW_RECIPE, "category_id": category_id, "healthy": healthy})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "healthy_not_dessert" and response.json()["error"]["details"] == {"field": "healthy"}
    # Moving a healthy dessert to another category needs the mark taken off first.
    dessert = client.post("/api/recipes", json={**NEW_RECIPE, "category_id": 1, "healthy": True}).json()
    moved = client.put(f"/api/recipes/{dessert['id']}", json={**NEW_RECIPE, "category_id": 4, "healthy": True})
    assert moved.json()["error"]["code"] == "healthy_not_dessert"
    assert client.put(f"/api/recipes/{dessert['id']}", json={**NEW_RECIPE, "category_id": 4}).json()["healthy"] is None


def test_the_database_itself_refuses_a_subcategory_under_the_wrong_category(client):
    # Bypassing the API on purpose: even buggy code could not store this.
    cakes = add_subcategory(client, "עוגות", parent_id=1)
    with client.app.state.session_factory() as session:
        now = utc_now()
        session.add(models.Recipe(
            title="x", category_id=2, subcategory_id=cakes, ingredient_groups=[], step_groups=[], notes=[],
            created_at=now, updated_at=now,
        ))
        with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
            session.commit()
        session.rollback()
        session.add(models.Recipe(
            title="x", category_id=None, subcategory_id=cakes, ingredient_groups=[], step_groups=[], notes=[],
            created_at=now, updated_at=now,
        ))
        with pytest.raises(IntegrityError, match="subcategory_needs_category"):
            session.commit()


# --- What is stored on disk --------------------------------------------------------------------------------


def test_times_are_stored_in_utc_and_returned_with_their_time_zone(client, data_dir):
    created = client.post("/api/recipes", json=NEW_RECIPE).json()
    with sqlite3.connect(data_dir / "recipes.db") as db:
        stored = db.execute("SELECT created_at FROM recipes WHERE id = ?", (created["id"],)).fetchone()[0]
    assert created["created_at"].startswith(stored[:19].replace(" ", "T"))  # same moment, UTC
    assert created["created_at"].endswith("Z")


def test_hebrew_is_stored_as_readable_text(client, data_dir):
    created = client.post("/api/recipes", json=NEW_RECIPE).json()
    with sqlite3.connect(data_dir / "recipes.db") as db:
        stored = db.execute("SELECT ingredient_groups FROM recipes WHERE id = ?", (created["id"],)).fetchone()[0]
    assert "200 גרם קמח" in stored  # not "\\u05d2..."


# --- Changes are accepted only from the notebook page ------------------------------------------------------


def test_changes_from_another_site_are_refused(client):
    before = len(client.get("/api/recipes").json())
    response = client.post("/api/recipes", json=NEW_RECIPE, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_origin"
    assert len(client.get("/api/recipes").json()) == before
    # The notebook page (Vite dev server) is allowed.
    assert client.post("/api/recipes", json=NEW_RECIPE, headers={"Origin": "http://localhost:5173"}).status_code == 201
