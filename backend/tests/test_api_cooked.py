"""Whether you have cooked a recipe: unmarked until you mark it, kept apart from everything else."""

from fastapi.testclient import TestClient

from app.main import app

ORIGIN = {"Origin": "http://localhost:5173"}


def first(client):
    return client.get("/api/recipes").json()[0]


def mark(client, recipe_id, cooked, headers=ORIGIN):
    return client.put(f"/api/recipes/{recipe_id}/cooked", json={"cooked": cooked}, headers=headers)


def test_every_recipe_starts_unmarked(client):
    assert [recipe["cooked"] for recipe in client.get("/api/recipes").json()] == [False] * 4
    body = {"title": "חדש", "servings": None, "ingredient_groups": [], "step_groups": [], "notes": [], "sources": []}
    assert client.post("/api/recipes", json=body, headers=ORIGIN).json()["cooked"] is False


def test_marking_and_unmarking_changes_only_the_mark(client):
    recipe = first(client)
    marked = mark(client, recipe["id"], True)
    assert marked.status_code == 200 and marked.json()["cooked"] is True
    assert {k: v for k, v in marked.json().items() if k != "cooked"} == {k: v for k, v in recipe.items() if k != "cooked"}
    assert client.get(f"/api/recipes/{recipe['id']}").json()["cooked"] is True
    assert [r["cooked"] for r in client.get("/api/recipes").json()].count(True) == 1
    assert mark(client, recipe["id"], False).json()["cooked"] is False


def test_saving_a_recipe_keeps_its_mark_and_cannot_set_it(client):
    recipe = first(client)
    mark(client, recipe["id"], True)
    body = {k: recipe[k] for k in ("title", "servings", "ingredient_groups", "step_groups", "notes", "sources")}
    saved = client.put(f"/api/recipes/{recipe['id']}", json=body | {"title": "שם חדש"}, headers=ORIGIN)
    assert saved.json()["cooked"] is True
    refused = client.put(f"/api/recipes/{recipe['id']}", json=body | {"cooked": False}, headers=ORIGIN)
    assert refused.status_code == 422  # only the mark's own endpoint changes it


def test_only_true_or_false_and_only_an_existing_recipe(client):
    recipe = first(client)
    for value in ("yes", 1, None):
        assert mark(client, recipe["id"], value).status_code == 422
    assert mark(client, 9999, True).status_code == 404
    assert first(client)["cooked"] is False


def test_another_website_cannot_mark_a_recipe(client):
    response = mark(client, first(client)["id"], True, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert first(client)["cooked"] is False


def test_the_mark_survives_a_restart(client):
    recipe = first(client)
    mark(client, recipe["id"], True)
    with TestClient(app, base_url="http://localhost") as again:
        assert again.get(f"/api/recipes/{recipe['id']}").json()["cooked"] is True
