"""Shared test setup. pytest finds this file automatically and offers its fixtures to every test.

A *fixture* is reusable setup: a test that names `client` as a parameter gets a started app
whose database lives in a fresh temporary folder, so tests never touch your real recipes.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """An empty data folder for this test only (a real environment variable wins over .env)."""
    monkeypatch.setenv("RECIPES_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("RECIPES_SQL_ECHO", raising=False)
    return tmp_path


@pytest.fixture
def client(data_dir: Path) -> Iterator[TestClient]:
    """The app, started like the real server: database created and seeded on entering `with`."""
    with TestClient(app, base_url="http://localhost") as test_client:  # the host name a browser uses
        yield test_client


def recipe_by_title(client: TestClient, title: str) -> dict:
    return next(recipe for recipe in client.get("/api/recipes").json() if recipe["title"] == title)
