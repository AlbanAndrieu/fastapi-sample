"""Test the API."""

from typing import Dict

import pytest
from fastapi.testclient import TestClient

from server_app import app

# from unittest.mock import patch


@pytest.fixture(scope="module")
def test_app():
    client = TestClient(app)
    yield client  # testing happens here


def test_pong_v1(test_app) -> None:
    """It runs and gives correct response from pong."""

    expected_status: int = 200
    expected_response: Dict[str, str] = {"ping": "pong v1!"}

    # when
    response = test_app.get("/v1/pong")

    # then
    assert response.status_code == expected_status
    assert response.json() == expected_response


def test_ping_v1(test_app) -> None:
    """It runs and gives correct response from ping."""

    expected_status: int = 200

    # QUOTES = [
    # "Strive not to be a success, but rather to be of value. - Albert Einstein",
    # "Believe you can and you're halfway there. - Theodore Roosevelt",
    # "The future belongs to those who believe in the beauty of their dreams. - Eleanor Roosevelt",
    # ]

    # when
    response = test_app.get("/v1/ping")

    # then
    assert response.status_code == expected_status
    assert response.json() is not None


def test_ping_v2(test_app) -> None:
    """It runs and gives correct response from ping."""

    expected_status: int = 200

    # when
    response = test_app.get("/v2/ping")

    # then
    assert response.status_code == expected_status
    assert response.json() == {"ping": "pong v2!"}


def test_message_hello_world_v1(test_app) -> None:
    """It runs and gives Hello World."""

    expected_status: int = 200

    # when
    response = test_app.get("/v1/message")

    # then
    assert response.status_code == expected_status
    assert response.json() == {"Hello": "World"}


def test_exception(test_app) -> None:
    """It runs and gives exception."""

    expected_status: int = 500

    # when
    response = test_app.get("/test/exception")

    # then
    assert response.status_code == expected_status
    assert response.json() == {"detail": "Got sadness"}


def test_env(test_app) -> None:
    """It runs and gives env"""

    expected_status: int = 500

    response = test_app.get("/test/env")

    assert response.status_code == expected_status
    assert response.json() == {
        "detail": "Env not available outside of Cloudflare worker",
    }


def test_invalid(test_app) -> None:
    """It runs and gives error"""

    expected_status: int = 500

    # with pytest.raises(TypeError("Invalid")):
    response = test_app.get("/test/invalid")
    assert response.status_code == expected_status
    assert response.json() == {
        "detail": "Invalid request",
    }


def test_global_exception_handler_returns_json_response(test_app, monkeypatch) -> None:
    """Unhandled exceptions should return JSON via the global exception handler."""

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("nabla.main.build_healthz_payload", _boom)

    response = test_app.get("/healthz")

    assert response.status_code == 500
    payload = response.json()
    assert payload["error"] == "Internal server error"
    assert "timestamp" in payload


def test_health(test_app) -> None:
    """It runs and gives health status."""

    expected_status: int = 200

    # when
    response = test_app.get("/health")

    # then
    assert response.status_code == expected_status
    status = response.json()
    assert status["status"] == "healthy"
    assert status["readings_count"] == 50
    assert status["active_connections"] == 0
    assert status["total_requests"] == 1


def test_tavily_search_returns_503_without_api_key(test_app, monkeypatch) -> None:
    """Tavily route returns 503 when the API key is missing or empty."""
    monkeypatch.setenv("TAVILY_API_KEY", "")
    response = test_app.post("/v1/tavily/search", json={"query": "hello"})
    assert response.status_code == 503


def test_tavily_search_ok_when_mocked(test_app, monkeypatch) -> None:
    """Tavily route forwards the body and returns the search payload."""

    def _fake(query: str, *, search_depth: str = "advanced") -> dict:
        return {"query": query, "results": [], "search_depth": search_depth}

    monkeypatch.setattr("nabla.api.tavily_route.tavily_search", _fake)
    response = test_app.post(
        "/v1/tavily/search",
        json={"query": "hello", "search_depth": "basic"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "hello"
    assert body["search_depth"] == "basic"


def test_brave_search_returns_503_without_api_key(test_app, monkeypatch) -> None:
    """Brave route returns 503 when the API key is missing or empty."""
    monkeypatch.setenv("BRAVE_API_KEY", "")
    response = test_app.post("/v1/brave/search", json={"query": "hello"})
    assert response.status_code == 503


def test_brave_search_ok_when_mocked(test_app, monkeypatch) -> None:
    """Brave route forwards the body and returns the search payload."""

    def _fake(query: str, *, count: int = 10) -> dict:
        return {"query": query, "web": {"results": []}, "count": count}

    monkeypatch.setattr("nabla.api.brave_route.brave_web_search", _fake)
    response = test_app.post(
        "/v1/brave/search",
        json={"query": "hello", "count": 5},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "hello"
    assert body["count"] == 5


def test_google_search_returns_503_without_api_key(test_app, monkeypatch) -> None:
    """Google route returns 503 when the API key is missing or empty."""
    monkeypatch.setenv("GOOGLE_SEARCH_API_KEY", "")
    monkeypatch.setenv("GOOGLE_SEARCH_CX", "cx123")
    response = test_app.post("/v1/google/search", json={"query": "hello"})
    assert response.status_code == 503


def test_google_search_returns_503_without_cx(test_app, monkeypatch) -> None:
    """Google route returns 503 when cx is missing (Custom Search requires it)."""
    monkeypatch.setenv("GOOGLE_SEARCH_API_KEY", "fake-key")
    monkeypatch.setenv("GOOGLE_SEARCH_CX", "")
    response = test_app.post("/v1/google/search", json={"query": "hello"})
    assert response.status_code == 503


def test_google_search_ok_when_mocked(test_app, monkeypatch) -> None:
    """Google route forwards the body and returns the search payload."""

    def _fake(query: str, *, num: int = 10) -> dict:
        return {"queries": {"request": []}, "items": [], "q": query, "num": num}

    monkeypatch.setattr(
        "nabla.api.google_search_route.google_programmable_search",
        _fake,
    )
    response = test_app.post(
        "/v1/google/search",
        json={"query": "hello", "num": 10},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["q"] == "hello"
    assert body["num"] == 10


def test_appwrite_health_returns_503_without_config(test_app, monkeypatch) -> None:
    """Appwrite route returns 503 when endpoint/project/key are not configured."""
    monkeypatch.setenv("APPWRITE_ENDPOINT", "")
    monkeypatch.setenv("APPWRITE_PROJECT_ID", "")
    monkeypatch.setenv("APPWRITE_API_KEY", "")
    response = test_app.get("/v1/appwrite/health")
    assert response.status_code == 503


def test_appwrite_health_ok_when_mocked(test_app, monkeypatch) -> None:
    """Appwrite route returns integration payload when helper succeeds."""

    def _fake() -> dict:
        return {"status": "pass"}

    monkeypatch.setattr("nabla.api.appwrite_route.appwrite_health", _fake)
    response = test_app.get("/v1/appwrite/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pass"


@pytest.mark.skip(reason="Skipping this test for now")
def test_chain(test_app) -> None:
    """It runs and chain io_task and cpu_task."""

    expected_status: int = 200

    # when
    response = test_app.get("/chain")

    # then
    assert response.status_code == expected_status
    assert response.json() == {"path": "/chain"}
