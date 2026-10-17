"""DB-backed routes answer 503, not 500, when the app started without PostgreSQL."""

from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from nabla.api.db.availability import require_database


def _app(*, database_available: bool | None) -> FastAPI:
    app = FastAPI()
    if database_available is not None:
        app.state.database_available = database_available
    router = APIRouter()

    @router.get("/needs-db")
    def needs_db() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(router, dependencies=[Depends(require_database)])
    return app


def test_route_answers_503_when_database_is_unavailable() -> None:
    response = TestClient(_app(database_available=False)).get("/needs-db")

    assert response.status_code == 503
    assert response.json() == {"detail": "PostgreSQL is not available; this route needs the database"}


def test_route_runs_when_database_is_available_or_state_unknown() -> None:
    assert TestClient(_app(database_available=True)).get("/needs-db").json() == {"ok": True}
    assert TestClient(_app(database_available=None)).get("/needs-db").json() == {"ok": True}
