"""Shared test setup. pytest finds this file automatically and offers its fixtures to every test.

A *fixture* is reusable setup: a test that names `client` as a parameter gets a started app
whose database lives in a fresh temporary folder, so tests never touch your real recipes.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app


@pytest.fixture(autouse=True)
def no_dotenv_and_no_real_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """Applies to every test: your .env and settings are never used, and no real model is called.

    Your .env may hold a real ANTHROPIC_API_KEY (a test must not spend it) or choose Ollama, which
    may be running on this computer (a test must not depend on it). Tests that need an extractor
    pass a stand-in or a fake connection (see test_api_imports.py, test_extraction_ollama.py).
    """
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for name in (
        "ANTHROPIC_API_KEY", "RECIPES_ANTHROPIC_API_KEY", "RECIPES_MODEL", "RECIPES_MODEL_TIMEOUT_SECONDS",
        "RECIPES_EXTRACTOR", "RECIPES_OLLAMA_MODEL", "RECIPES_OLLAMA_URL", "RECIPES_OLLAMA_CONTEXT_TOKENS",
        "RECIPES_OLLAMA_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    def refuse(what: str):
        def refused(*args: object, **kwargs: object) -> None:
            raise AssertionError(f"A test tried to {what}.")

        return refused

    monkeypatch.setattr("anthropic.Anthropic", refuse("create a real Claude API client"))
    monkeypatch.setattr("app.extraction.ollama.new_client", refuse("connect to a real Ollama"))


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
