"""Notes model normalization, OpenAPI and authorization-surface contracts."""

from datetime import datetime as dt, timedelta, timezone

import pytest

from nabla.api.notes import models as note_models, notes as notes_routes
from nabla.api.notes.models import NoteData, NoteResponse
from nabla.config import MCP_ALLOWED_ROUTES

CREATED_AT = dt(2026, 10, 17, 8, 30, tzinfo=timezone.utc)
CREATED_AT_JSON = "2026-10-17T08:30:00Z"
NOTE_FIELDS = {
    "title": "something",
    "description": "something else",
    "type": "note",
    "prompt": "test prompt",
}


def test_note_response_generates_utc_timestamp_for_each_instance(monkeypatch):
    timestamps = iter(
        (
            dt(2026, 8, 24, 12, 34, tzinfo=timezone.utc),
            dt(2026, 8, 24, 12, 35, tzinfo=timezone.utc),
        ),
    )

    class Clock:
        @staticmethod
        def now(tz):
            assert tz is timezone.utc
            return next(timestamps)

    monkeypatch.setattr(note_models, "datetime", Clock)

    first_note = NoteResponse(**NOTE_FIELDS)
    second_note = NoteResponse(**NOTE_FIELDS)

    assert first_note.created_date == dt(2026, 8, 24, 12, 34, tzinfo=timezone.utc)
    assert second_note.created_date == dt(2026, 8, 24, 12, 35, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "raw",
    [
        # Legacy client/row format: naive minutes are interpreted as UTC.
        "2026-10-17 08:30",
        dt(2026, 10, 17, 8, 30),
        "2026-10-17T10:30:00+02:00",
        "2026-10-17T08:30:00Z",
    ],
)
def test_note_timestamps_normalize_to_aware_utc(raw):
    note = NoteData(id=1, created_date=raw, **NOTE_FIELDS)

    assert note.created_date == CREATED_AT
    assert note.created_date.utcoffset() == timedelta(0)
    assert note.model_dump(mode="json")["created_date"] == CREATED_AT_JSON


@pytest.mark.parametrize(
    "raw, expected",
    [
        (True, True),
        (False, False),
        ("True", True),
        ("False", False),
        ("true", True),
        ("0", False),
    ],
)
def test_note_completed_accepts_legacy_spellings_and_is_boolean(raw, expected):
    record = {"id": 1, "completed": raw, "created_date": CREATED_AT, **NOTE_FIELDS}

    note = NoteData.from_record(record)

    assert note.completed is expected
    assert note.model_dump(mode="json")["completed"] is expected


def _operation(schema, path, method):
    return schema["paths"][path][method]


def _response_ref(operation, status):
    return operation["responses"][status]["content"]["application/json"]["schema"]


def test_openapi_documents_typed_note_contract(test_app):
    schema = test_app.get("/openapi.json").json()
    note_ref = {"$ref": "#/components/schemas/NoteData"}

    read = _operation(schema, "/notes/{note_id}/", "get")
    delete = _operation(schema, "/notes/{note_id}/", "delete")
    update = _operation(schema, "/notes/{note_id}/", "put")
    create = _operation(schema, "/notes/", "post")

    assert _response_ref(read, "200") == note_ref
    assert _response_ref(delete, "200") == note_ref
    assert _response_ref(update, "200") == note_ref
    assert _response_ref(create, "201") == note_ref
    for operation in (read, delete, update):
        assert operation["responses"]["404"]["description"] == "Note not found"

    listing = _operation(schema, "/notes/", "get")
    assert set(listing["responses"]["200"]["content"]) == {"text/html"}

    note_schema = schema["components"]["schemas"]["NoteData"]["properties"]
    assert note_schema["completed"]["type"] == "boolean"
    assert note_schema["created_date"]["format"] == "date-time"


def test_notes_authorization_surface_is_preserved():
    """Notes have no owner model: no 403 path exists, and MCP must not widen access.

    The FastMCP OpenAPI bridge only exposes MCP_ALLOWED_ROUTES; notes CRUD
    (including destructive DELETE/PUT) must stay out of that allowlist.
    """
    routes = notes_routes.router.routes
    note_routes = {(method, route.path) for route in routes for method in getattr(route, "methods", ())}

    assert ("DELETE", "/notes/{note_id}/") in note_routes
    assert note_routes.isdisjoint(MCP_ALLOWED_ROUTES)
    assert all(not getattr(route, "dependencies", None) for route in routes)
