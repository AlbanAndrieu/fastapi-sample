import json
from datetime import datetime as dt

import pytest
from httpx import ASGITransport, AsyncClient

from nabla.api.notes import crud
from nabla.api.notes.models import NoteResponse
from nabla.main import app


@pytest.fixture
async def test_app():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.webtest
async def test_homepage(test_app):
    response = await test_app.get("/")
    assert response.status_code == 200
    assert "Sensor Dashboard" in response.text


async def test_create_note(test_app, monkeypatch):
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

    response = await test_app.post("/notes/", json=test_request_payload)
    print(response.json())
    assert response.status_code == 201
    assert response.json() == test_response_payload


async def test_crud_post_returns_generated_id_and_closes_session(monkeypatch):
    class FakeSession:
        committed = False
        closed = False
        note = None

        def add(self, note):
            self.note = note

        def commit(self):
            self.committed = True

        def refresh(self, note):
            note.id = 42

        def rollback(self):
            raise AssertionError("rollback should not be called")

        def close(self):
            self.closed = True

    session = FakeSession()
    monkeypatch.setattr(crud, "SessionLocal", lambda: session)
    payload = NoteResponse(
        title="something",
        description="something else",
        type="note",
        prompt="test prompt",
    )

    note_id = await crud.post(payload)

    assert note_id == 42
    assert session.committed is True
    assert session.closed is True


async def test_create_note_invalid_json(test_app):
    response = await test_app.post("/notes/", content=json.dumps({"title": "something"}))
    assert response.status_code == 422
    response = await test_app.post(
        "/notes/",
        content=json.dumps({"title": "1", "description": "2"}),
    )
    assert response.status_code == 422


# These tests should be run in order
async def test_read_note(test_app, monkeypatch):
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

    response = await test_app.get("/notes/1/")
    assert response.status_code == 200
    assert response.json() == test_data


async def test_read_note_incorrect_id(test_app, monkeypatch):
    async def mock_get(note_id):
        return None

    monkeypatch.setattr(crud, "get", mock_get)

    response = await test_app.get("/notes/999/")
    assert response.status_code == 404
    assert response.json()["detail"] == "Note not found"


async def test_read_note_incorrect_id_twice(test_app, monkeypatch):
    async def mock_get(note_id):
        return None

    monkeypatch.setattr(crud, "get", mock_get)

    response = await test_app.get("/notes/999/")
    assert response.status_code == 404
    assert response.json()["detail"] == "Note not found"

    response = await test_app.get("/notes/0/")
    assert response.status_code == 404


# test for reading all notes:
async def test_read_all_notes(test_app, monkeypatch):
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

    response = await test_app.get("/notes/")
    assert response.status_code == 200


# Test for the PUT method
async def test_update_note(test_app, monkeypatch):
    test_update_data = {
        "title": "something",
        "description": "something else",
        "id": 1,
        "type": "note",
        "prompt": "test prompt",
        "completed": False,
    }
    test_changes = {
        "title": "something",
        "description": "something else",
        # "id": 1,
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
    }

    async def mock_get(note_id):
        return test_update_data

    seen_ids: list[int] = []

    async def mock_put(note_id, payload):
        seen_ids.append(note_id)
        return note_id

    async def mock_enqueue(note_id, note_type, prompt):
        return note_id

    monkeypatch.setattr(crud, "get", mock_get)
    monkeypatch.setattr(crud, "put", mock_put)
    monkeypatch.setattr("nabla.api.notes.notes.enqueue_note", mock_enqueue)

    response = await test_app.put("/notes/1/", json=test_changes)
    assert response.status_code == 200
    assert response.json() == test_response
    assert seen_ids == [1]


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
async def test_update_note_invalid(test_app, monkeypatch, note_id, payload, status_code):
    async def mock_get(note_id):
        return None

    monkeypatch.setattr(crud, "get", mock_get)

    response = await test_app.put(
        f"/notes/{note_id}/",
        json=payload,
    )
    assert response.status_code == status_code


# Test for DELETE route
async def test_remove_note(test_app, monkeypatch):
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

    response = await test_app.delete("/notes/1/")
    assert response.status_code == 200
    assert response.json() == test_data


async def test_remove_note_incorrect_id(test_app, monkeypatch):
    async def mock_get(note_id):
        return None

    monkeypatch.setattr(crud, "get", mock_get)

    response = await test_app.delete("/notes/999/")
    assert response.status_code == 404
    assert response.json()["detail"] == "Note not found"

    response = await test_app.delete("/notes/0/")
    assert response.status_code == 422
