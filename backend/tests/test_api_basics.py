"""The API's health check and its single error format (no network: TestClient calls the app in-process)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.errors import install_error_handlers
from app.main import app

client = TestClient(app, base_url="http://localhost")  # the host name a browser uses


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unknown_path_uses_the_error_format():
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Not Found", "details": None}}


def test_trailing_slash_is_a_404_not_a_redirect():
    # A redirect would send the browser past the Vite proxy to the backend's own address.
    response = client.get("/api/recipes/", follow_redirects=False)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_requests_for_other_host_names_are_refused():
    # Protection against DNS rebinding: only requests addressed to this computer by name are answered.
    assert TestClient(app, base_url="http://attacker.example").get("/api/health").status_code == 400
    # The Vite proxy addresses the backend as 127.0.0.1:8000, which is allowed.
    assert TestClient(app, base_url="http://127.0.0.1:8000").get("/api/health").status_code == 200


def test_wrong_method_uses_the_error_format():
    response = client.post("/api/health")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
    assert response.headers["allow"] == "GET"


def test_a_bug_returns_the_error_format_without_internal_details():
    # A small app with the same handlers and a route that fails, standing in for a bug.
    buggy = FastAPI()
    install_error_handlers(buggy)

    @buggy.get("/boom")
    def boom():
        raise RuntimeError("secret internal detail")

    # raise_server_exceptions=False: answer like a real server instead of re-raising inside the test.
    response = TestClient(buggy, raise_server_exceptions=False).get("/boom")
    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Something went wrong on the server.", "details": None}
    }
    assert "secret" not in response.text
