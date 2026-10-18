"""Hermetic contracts for the notes HTMX form routes and their templates.

The CRUD layer is mocked: no PostgreSQL or Redis is required. Fragments are
parsed with the standard-library HTML parser so assertions target structured
attributes (ids, ``hx-*`` targets) rather than rendered text.
"""

from datetime import datetime as dt, timezone
from html.parser import HTMLParser
from unittest.mock import AsyncMock

import pytest
from fastapi.routing import APIRoute
from fastapi.templating import Jinja2Templates

from nabla.api.notes import crud, notes as notes_routes
from nabla.api.notes.models import NoteData, NoteResponse

CREATED_AT = dt(2026, 10, 17, 8, 30, tzinfo=timezone.utc)
HX_METHODS = ("hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete")


def _stored_note(**overrides):
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


class _FragmentParser(HTMLParser):
    """Collect element attributes and text of a rendered HTMX fragment."""

    def __init__(self) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def handle_data(self, data):
        if data.strip():
            self.text.append(data.strip())


def _parse(html: str) -> _FragmentParser:
    parser = _FragmentParser()
    parser.feed(html)
    return parser


def _root_id(html: str) -> str | None:
    return next(attrs.get("id") for tag, attrs in _parse(html).elements if tag == "div")


def _hx_calls(html: str) -> list[tuple[str, str]]:
    return [(attribute.removeprefix("hx-").upper(), value) for _, attrs in _parse(html).elements for attribute, value in attrs.items() if attribute in HX_METHODS and value]


@pytest.fixture
def notes_crud(monkeypatch):
    mocks = {
        "get": AsyncMock(return_value=_stored_note()),
        "get_all": AsyncMock(return_value=[_stored_note()]),
        "post": AsyncMock(return_value=2),
        "put": AsyncMock(return_value=1),
        "delete": AsyncMock(return_value=None),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(crud, name, mock)
    return mocks


def test_add_note_form_creates_note_and_renders_list(test_app, notes_crud):
    response = test_app.post("/notes/add", data={"title": "new title"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert _root_id(response.text) == "notes-list"
    payload = notes_crud["post"].await_args.args[0]
    assert isinstance(payload, NoteResponse)
    assert payload.title == "new title"
    assert payload.completed is False
    notes_crud["get_all"].assert_awaited_once_with()


def test_add_note_form_rejects_short_title(test_app, notes_crud):
    response = test_app.post("/notes/add", data={"title": "ab"})

    assert response.status_code == 422
    notes_crud["post"].assert_not_awaited()


def test_edit_note_form_renders_edit_fragment(test_app, notes_crud):
    response = test_app.get("/notes/1/edit")

    assert response.status_code == 200
    assert _root_id(response.text) == "note-1"
    fields = {attrs.get("name"): attrs for tag, attrs in _parse(response.text).elements if tag in {"input", "textarea"}}
    assert fields["title"]["value"] == "something"
    assert "description" in fields
    assert "something else" in _parse(response.text).text
    notes_crud["get"].assert_awaited_once_with(1)


def test_update_note_form_persists_through_typed_crud(test_app, notes_crud):
    notes_crud["get"].return_value = _stored_note(completed="True")

    response = test_app.post(
        "/notes/1",
        data={"title": "new title", "description": "new description"},
    )

    assert response.status_code == 200
    assert _root_id(response.text) == "note-1"
    assert "new description" in _parse(response.text).text
    note_id, payload = notes_crud["put"].await_args.args
    assert note_id == 1
    assert isinstance(payload, NoteResponse)
    assert payload.model_dump(exclude={"created_date"}) == {
        "title": "new title",
        "description": "new description",
        "type": "note",
        "prompt": "test prompt",
        "completed": True,
    }


def test_update_note_form_rejects_missing_description(test_app, notes_crud):
    response = test_app.post("/notes/1", data={"title": "new title"})

    assert response.status_code == 422
    notes_crud["put"].assert_not_awaited()


@pytest.mark.parametrize(("stored", "expected"), [(False, True), ("True", False)])
def test_toggle_note_form_flips_completed(test_app, notes_crud, stored, expected):
    notes_crud["get"].return_value = _stored_note(completed=stored)

    response = test_app.post("/notes/1/toggle")

    assert response.status_code == 200
    assert _root_id(response.text) == "note-1"
    note_id, payload = notes_crud["put"].await_args.args
    assert note_id == 1
    assert payload.completed is expected
    assert payload.title == "something"
    root_classes = next(attrs["class"] for tag, attrs in _parse(response.text).elements if tag == "div").split()
    assert ("done" in root_classes) is expected


def test_delete_note_form_deletes_and_renders_list(test_app, notes_crud):
    notes_crud["get_all"].return_value = []

    response = test_app.post("/notes/1/delete")

    assert response.status_code == 200
    assert _root_id(response.text) == "notes-list"
    notes_crud["delete"].assert_awaited_once_with(1)


@pytest.mark.parametrize(
    ("method", "path", "data"),
    [
        ("GET", "/notes/9/edit", None),
        ("POST", "/notes/9", {"title": "new title", "description": "new description"}),
        ("POST", "/notes/9/toggle", None),
        ("POST", "/notes/9/delete", None),
    ],
)
def test_htmx_note_routes_return_404_for_missing_note(test_app, notes_crud, method, path, data):
    notes_crud["get"].return_value = None

    response = test_app.request(method, path, data=data)

    assert response.status_code == 404
    assert response.json() == {"detail": "Note not found"}
    notes_crud["put"].assert_not_awaited()
    notes_crud["delete"].assert_not_awaited()


def _route_template(method: str, path: str) -> str | None:
    """Return the notes route template matching ``method`` and ``path``.

    The notes router is mounted without prefix (``app_factory``); the HTTP
    tests above prove the same paths are served by the assembled application.
    """
    for route in notes_routes.router.routes:
        if isinstance(route, APIRoute) and method in route.methods and route.path_regex.match(path):
            return route.path
    return None


def _routed_calls(calls) -> set[tuple[str, str | None]]:
    return {(method, _route_template(method, path)) for method, path in calls}


@pytest.mark.parametrize(
    ("template", "expected_routes"),
    [
        (
            "_note_item.html",
            {
                ("POST", "/notes/{note_id}/toggle"),
                ("GET", "/notes/{note_id}/edit"),
                ("POST", "/notes/{note_id}/delete"),
            },
        ),
        ("_note_item_edit.html", {("POST", "/notes/{note_id}")}),
    ],
)
def test_note_templates_only_call_registered_routes(template, expected_routes):
    note = NoteData.from_record(_stored_note(id=7))
    html = Jinja2Templates(directory="templates").get_template(template).render(note=note)

    assert _routed_calls(_hx_calls(html)) == expected_routes


def test_index_notes_calls_registered_routes(test_app):
    html = test_app.get("/").text

    note_calls = {(method, path) for method, path in _hx_calls(html) if path.startswith("/notes")}

    assert note_calls == {("GET", "/notes/"), ("POST", "/notes/add")}
    assert _routed_calls(note_calls) == {("GET", "/notes/"), ("POST", "/notes/add")}
