import json
from datetime import datetime as dt

import pytest

from nabla.api.notes import crud


@pytest.mark.webtest
def test_homepage(test_app):
    response = test_app.get("/")
    assert response.status_code == 200
    assert "Note Manager" in response.text


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
    response = test_app.post("/notes/", data=json.dumps({"title": "something"}))
    assert response.status_code == 422
    response = test_app.post(
        "/notes/",
        data=json.dumps({"title": "1", "description": "2"}),
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
@pytest.mark.skip(reason="Skipping this test for now")
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
        "created_date": dt.now().strftime("%Y-%m-%d %H:%M"),
    }

    async def mock_get(id):  # noqa: A002
        return test_update_data

    async def mock_put(id, payload):  # noqa: A002
        return test_response

    monkeypatch.setattr(crud, "get", mock_get)
    monkeypatch.setattr(crud, "put", mock_put)

    response = test_app.put("/notes/1/", data=json.dumps(test_changes))
    assert response.status_code == 200
    assert response.json() == test_response


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
        data=json.dumps(payload),
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
