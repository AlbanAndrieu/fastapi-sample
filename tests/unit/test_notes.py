import json
from datetime import datetime as dt, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from nabla.api.notes import crud, notes as notes_routes
from nabla.api.notes.models import NoteResponse

CREATED_AT = dt(2026, 10, 17, 8, 30, tzinfo=timezone.utc)
CREATED_AT_JSON = "2026-10-17T08:30:00Z"


def _stored_note(**overrides):
    """A persisted note row as returned by the ``databases`` layer."""
    row = {
        "id": 1,
        "title": "something",
        "description": "something else",
        "type": "note",
        "prompt": "test prompt",
        "completed": False,
        "created_date": CREATED_AT,
    }
    row.update(overrides)
    return row


def _note_json(**overrides):
    """The public JSON contract of a note (``NoteData``)."""
    body = {
        "id": 1,
        "title": "something",
        "description": "something else",
        "type": "note",
        "prompt": "test prompt",
        "completed": False,
        "created_date": CREATED_AT_JSON,
    }
    body.update(overrides)
    return body


def test_homepage(test_app):
    response = test_app.get("/")
    assert response.status_code == 200
    assert "Sensor Dashboard" in response.text


def test_create_note(test_app, monkeypatch):
    test_request_payload = {
        "title": "something",
        "description": "something else",
        "type": "note",
        "prompt": "test prompt",
        "completed": False,
    }
    post = AsyncMock(return_value=1)
    monkeypatch.setattr(crud, "post", post)
    monkeypatch.setattr(notes_routes, "utc_now", lambda: CREATED_AT)

    response = test_app.post("/notes/", json=test_request_payload)

    assert response.status_code == 201
    assert response.json() == _note_json()
    assert post.await_args.kwargs["created_date"] == CREATED_AT


def test_create_note_ignores_client_timestamp_and_coerces_legacy_completed(
    test_app,
    monkeypatch,
):
    monkeypatch.setattr(crud, "post", AsyncMock(return_value=3))
    monkeypatch.setattr(notes_routes, "utc_now", lambda: CREATED_AT)

    response = test_app.post(
        "/notes/",
        json={
            "title": "something",
            "description": "something else",
            "type": "note",
            "prompt": "test prompt",
            "completed": "True",
            "created_date": "1999-01-01 00:00",
        },
    )

    assert response.status_code == 201
    assert response.json() == _note_json(id=3, completed=True)


def test_create_note_rejects_non_boolean_completed(test_app, monkeypatch):
    post = AsyncMock(return_value=1)
    monkeypatch.setattr(crud, "post", post)

    response = test_app.post(
        "/notes/",
        json={
            "title": "something",
            "description": "something else",
            "type": "note",
            "prompt": "test prompt",
            "completed": "maybe",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "completed"]
    post.assert_not_awaited()


def test_create_note_invalid_json(test_app):
    response = test_app.post(
        "/notes/",
        content=json.dumps({"title": "something"}),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    response = test_app.post(
        "/notes/",
        content=json.dumps({"title": "1", "description": "2"}),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422


def test_read_note(test_app, monkeypatch):
    monkeypatch.setattr(crud, "get", AsyncMock(return_value=_stored_note()))

    response = test_app.get("/notes/1/")

    assert response.status_code == 200
    assert response.json() == _note_json()


def test_read_note_normalizes_legacy_row(test_app, monkeypatch):
    legacy_row = _stored_note(completed="True", created_date=dt(2026, 10, 17, 8, 30))
    monkeypatch.setattr(crud, "get", AsyncMock(return_value=legacy_row))

    response = test_app.get("/notes/1/")

    assert response.status_code == 200
    assert response.json() == _note_json(completed=True)


def test_read_note_incorrect_id(test_app, monkeypatch):
    monkeypatch.setattr(crud, "get", AsyncMock(return_value=None))

    response = test_app.get("/notes/999/")
    assert response.status_code == 404
    assert response.json()["detail"] == "Note not found"


def test_read_note_incorrect_id_twice(test_app, monkeypatch):
    monkeypatch.setattr(crud, "get", AsyncMock(return_value=None))

    response = test_app.get("/notes/999/")
    assert response.status_code == 404
    assert response.json()["detail"] == "Note not found"

    response = test_app.get("/notes/0/")
    assert response.status_code == 404


def test_read_all_notes_renders_normalized_html(test_app, monkeypatch):
    test_data = [
        _stored_note(id=1, completed="True"),
        _stored_note(id=2, title="someone", completed="False"),
    ]
    monkeypatch.setattr(crud, "get_all", AsyncMock(return_value=test_data))

    response = test_app.get("/notes/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    # Legacy "False" strings were truthy in Jinja; only note 1 is completed.
    assert response.text.count("✔") == 1


def test_update_note(test_app, monkeypatch):
    test_changes = {
        "title": "something",
        "description": "something else",
        "id": 1,
        "type": "note",
        "prompt": "test prompt",
        "completed": True,
        "created_date": "2000-01-01 00:00",
    }

    async def mock_put(note_id, payload):
        assert note_id == 1
        assert payload.completed is True
        return note_id

    async def mock_enqueue(note_id, note_type, prompt):
        assert note_id == 1
        return note_id

    monkeypatch.setattr(crud, "get", AsyncMock(return_value=_stored_note()))
    monkeypatch.setattr(crud, "put", mock_put)
    monkeypatch.setattr(notes_routes, "enqueue_note", mock_enqueue)

    response = test_app.put(
        "/notes/1/",
        content=json.dumps(test_changes),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    # The original creation timestamp is preserved, not the client value.
    assert response.json() == _note_json(completed=True)


def test_update_note_reports_queue_failure(test_app, monkeypatch):
    payload = {
        "title": "updated",
        "description": "updated description",
        "type": "note",
        "prompt": "updated prompt",
        "completed": True,
    }

    async def mock_enqueue(note_id, note_type, prompt):
        raise ConnectionError("Redis unavailable")

    monkeypatch.setattr(crud, "get", AsyncMock(return_value=_stored_note()))
    monkeypatch.setattr(crud, "put", AsyncMock(return_value=1))
    monkeypatch.setattr(notes_routes, "enqueue_note", mock_enqueue)

    response = test_app.put("/notes/1/", json=payload)

    assert response.status_code == 503
    assert response.json()["detail"] == ("Note saved but background processing is unavailable")


@pytest.mark.asyncio
async def test_crud_post_uses_async_database_and_returns_persisted_id(
    monkeypatch,
) -> None:
    execute = AsyncMock(return_value=42)
    monkeypatch.setattr(crud.database, "execute", execute)
    payload = NoteResponse(
        title="new note",
        description="new description",
        type="note",
        prompt="new prompt",
    )

    note_id = await crud.post(payload)

    assert note_id == 42
    query = execute.await_args.kwargs["query"]
    parameters = query.compile().params
    assert isinstance(parameters["created_date"], dt)
    assert parameters["created_date"].utcoffset() == timedelta(0)
    assert parameters["completed"] is False
    assert parameters["title"] == "new note"


@pytest.mark.asyncio
async def test_crud_post_persists_server_timestamp_as_utc(monkeypatch) -> None:
    execute = AsyncMock(return_value=1)
    monkeypatch.setattr(crud.database, "execute", execute)
    payload = NoteResponse(
        title="new note",
        description="new description",
        type="note",
        prompt="new prompt",
        completed=True,
    )
    paris = timezone(timedelta(hours=2))

    await crud.post(payload, created_date=dt(2026, 10, 17, 10, 30, tzinfo=paris))

    parameters = execute.await_args.kwargs["query"].compile().params
    assert parameters["created_date"] == CREATED_AT
    assert parameters["created_date"].utcoffset() == timedelta(0)
    assert parameters["completed"] is True


@pytest.mark.asyncio
async def test_crud_put_preserves_creation_timestamp(monkeypatch) -> None:
    execute = AsyncMock(return_value=7)
    monkeypatch.setattr(crud.database, "execute", execute)
    payload = NoteResponse(
        title="updated note",
        description="updated description",
        type="note",
        prompt="updated prompt",
    )

    note_id = await crud.put(7, payload)

    assert note_id == 7
    parameters = execute.await_args.kwargs["query"].compile().params
    assert 7 in parameters.values()
    assert "created_date" not in parameters
    assert parameters["completed"] is False


@pytest.mark.parametrize(
    "note_id, payload, status_code",
    [
        [1, {}, 422],
        [1, {"description": "bar"}, 422],
        [
            999,
            {
                "title": "foo",
                "description": "bar",
                "type": "note",
                "prompt": "test prompt",
                "created_date": "2026-10-17 08:30",
                "completed": True,
            },
            404,
        ],
        [1, {"title": "1", "description": "bar"}, 422],
        [1, {"title": "foo", "description": "1"}, 422],
        [0, {"title": "foo", "description": "bar"}, 422],
    ],
)
def test_update_note_invalid(test_app, monkeypatch, note_id, payload, status_code):
    monkeypatch.setattr(crud, "get", AsyncMock(return_value=None))
    put = AsyncMock(return_value=note_id)
    monkeypatch.setattr(crud, "put", put)

    response = test_app.put(
        f"/notes/{note_id}/",
        json=payload,
    )
    assert response.status_code == status_code
    put.assert_not_awaited()


def test_remove_note(test_app, monkeypatch):
    delete = AsyncMock(return_value=1)
    monkeypatch.setattr(crud, "get", AsyncMock(return_value=_stored_note()))
    monkeypatch.setattr(crud, "delete", delete)

    response = test_app.delete("/notes/1/")

    assert response.status_code == 200
    assert response.json() == _note_json()
    delete.assert_awaited_once_with(1)


def test_remove_note_incorrect_id(test_app, monkeypatch):
    delete = AsyncMock()
    monkeypatch.setattr(crud, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(crud, "delete", delete)

    response = test_app.delete("/notes/999/")
    assert response.status_code == 404
    assert response.json()["detail"] == "Note not found"

    response = test_app.delete("/notes/0/")
    assert response.status_code == 422
    delete.assert_not_awaited()
