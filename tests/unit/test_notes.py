import json
from datetime import datetime as dt
from unittest.mock import AsyncMock

import pytest

from nabla.api.notes import crud, models as note_models, notes as notes_routes
from nabla.api.notes.models import NoteResponse


def test_homepage(test_app):
    response = test_app.get("/")
    assert response.status_code == 200
    assert "Sensor Dashboard" in response.text


def test_note_response_generates_timestamp_for_each_instance(monkeypatch):
    timestamps = iter((dt(2026, 8, 24, 12, 34), dt(2026, 8, 24, 12, 35)))

    class Clock:
        @staticmethod
        def now(_timezone):
            return next(timestamps)

    monkeypatch.setattr(note_models, "datetime", Clock)
    payload = {
        "title": "something",
        "description": "something else",
        "type": "note",
        "prompt": "test prompt",
    }

    first_note = NoteResponse(**payload)
    second_note = NoteResponse(**payload)

    assert first_note.created_date == "2026-08-24 12:34"
    assert second_note.created_date == "2026-08-24 12:35"


def test_create_note(test_app, monkeypatch):
    test_request_payload = {
        "title": "something",
        "description": "something else",
        "type": "note",
        "prompt": "test prompt",
        "completed": False,
    }
    test_response_payload = {
        "id": 1,
        "title": "something",
        "description": "something else",
        "type": "note",
        "prompt": "test prompt",
        "completed": False,
        "created_date": dt.now().strftime("%Y-%m-%d %H:%M"),
    }

    async def mock_post(payload):
        return 1

    monkeypatch.setattr(crud, "post", mock_post)

    response = test_app.post("/notes/", json=test_request_payload)
    print(response.json())
    assert response.status_code == 201
    assert response.json() == test_response_payload


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


# These tests should be run in order
def test_read_note(test_app, monkeypatch):
    test_data = {
        "id": 1,
        "title": "something",
        "type": "note",
        "prompt": "test prompt",
        "description": "something else",
        "completed": False,
        "created_date": dt.now().strftime("%Y-%m-%d %H:%M"),
    }

    async def mock_get(note_id):
        return test_data

    monkeypatch.setattr(crud, "get", mock_get)

    response = test_app.get("/notes/1/")
    assert response.status_code == 200
    assert response.json() == test_data


def test_read_note_incorrect_id(test_app, monkeypatch):
    async def mock_get(note_id):
        return None

    monkeypatch.setattr(crud, "get", mock_get)

    response = test_app.get("/notes/999/")
    assert response.status_code == 404
    assert response.json()["detail"] == "Note not found"


def test_read_note_incorrect_id_twice(test_app, monkeypatch):
    async def mock_get(note_id):
        return None

    monkeypatch.setattr(crud, "get", mock_get)

    response = test_app.get("/notes/999/")
    assert response.status_code == 404
    assert response.json()["detail"] == "Note not found"

    response = test_app.get("/notes/0/")
    assert response.status_code == 404


# test for reading all notes:
def test_read_all_notes(test_app, monkeypatch):
    test_data = [
        {
            "title": "something",
            "description": "something else",
            "id": 1,
            "type": "note",
            "prompt": "test prompt",
            "completed": True,
            "created_date": dt.now().strftime("%Y-%m-%d %H:%M"),
        },
        {
            "title": "someone",
            "description": "someone else",
            "id": 2,
            "type": "note",
            "prompt": "test prompt",
            "completed": False,
            "created_date": dt.now().strftime("%Y-%m-%d %H:%M"),
        },
    ]

    async def mock_get_all():
        return test_data

    monkeypatch.setattr(crud, "get_all", mock_get_all)

    response = test_app.get("/notes/")
    assert response.status_code == 200


# Test for the PUT method
def test_update_note(test_app, monkeypatch):
    test_update_data = {
        "title": "something",
        "description": "something else",
        "id": 1,
        "type": "note",
        "prompt": "test prompt",
        "completed": False,
        "created_date": dt.now().strftime("%Y-%m-%d %H:%M"),
    }
    test_changes = {
        "title": "something",
        "description": "something else",
        "id": 1,
        "type": "note",
        "prompt": "test prompt",
        "completed": True,
        "created_date": dt.now().strftime("%Y-%m-%d %H:%M"),
    }
    test_response = {
        "title": "something",
        "description": "something else",
        "id": 1,
        "type": "note",
        "prompt": "test prompt",
        "completed": True,
        "created_date": dt.now().strftime("%Y-%m-%d %H:%M"),
    }

    async def mock_get(id):  # noqa: A002
        return test_update_data

    async def mock_put(note_id, payload):
        assert note_id == 1
        return note_id

    async def mock_enqueue(note_id, note_type, prompt):
        assert note_id == 1
        return note_id

    monkeypatch.setattr(crud, "get", mock_get)
    monkeypatch.setattr(crud, "put", mock_put)
    monkeypatch.setattr(notes_routes, "enqueue_note", mock_enqueue)

    response = test_app.put(
        "/notes/1/",
        content=json.dumps(test_changes),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json() == test_response


def test_update_note_reports_queue_failure(test_app, monkeypatch):
    existing_note = {
        "id": 1,
        "title": "previous",
        "description": "previous description",
        "type": "note",
        "prompt": "previous prompt",
        "completed": False,
        "created_date": dt.now().strftime("%Y-%m-%d %H:%M"),
    }
    payload = {
        "title": "updated",
        "description": "updated description",
        "type": "note",
        "prompt": "updated prompt",
        "completed": True,
    }

    async def mock_enqueue(note_id, note_type, prompt):
        raise ConnectionError("Redis unavailable")

    monkeypatch.setattr(crud, "get", AsyncMock(return_value=existing_note))
    monkeypatch.setattr(crud, "put", AsyncMock(return_value=1))
    monkeypatch.setattr(notes_routes, "enqueue_note", mock_enqueue)

    response = test_app.put("/notes/1/", json=payload)

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Note saved but background processing is unavailable"
    )


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
    assert parameters["title"] == "new note"


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
                "created_date": dt.now().strftime("%Y-%m-%d %H:%M"),
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
    async def mock_get(note_id):
        return None

    monkeypatch.setattr(crud, "get", mock_get)

    response = test_app.put(
        f"/notes/{note_id}/",
        json=payload,
    )
    assert response.status_code == status_code


# Test for DELETE route
def test_remove_note(test_app, monkeypatch):
    test_data = {
        "title": "something",
        "description": "something else",
        "id": 1,
        "type": "note",
        "prompt": "test prompt",
        "completed": False,
        "created_date": dt.now().strftime("%Y-%m-%d %H:%M"),
    }

    async def mock_get(note_id):
        return test_data

    monkeypatch.setattr(crud, "get", mock_get)

    async def mock_delete(note_id):
        return id

    monkeypatch.setattr(crud, "delete", mock_delete)

    response = test_app.delete("/notes/1/")
    assert response.status_code == 200
    assert response.json() == test_data


def test_remove_note_incorrect_id(test_app, monkeypatch):
    async def mock_get(note_id):
        return None

    monkeypatch.setattr(crud, "get", mock_get)

    response = test_app.delete("/notes/999/")
    assert response.status_code == 404
    assert response.json()["detail"] == "Note not found"

    response = test_app.delete("/notes/0/")
    assert response.status_code == 422
