from __future__ import annotations

import importlib
import sqlite3
from io import BytesIO

import pytest

from app.helpers import SheetContext


@pytest.fixture()
def answer_sheet_module(db_module):
    import app.answer_sheet as answer_sheet

    importlib.reload(answer_sheet)
    return answer_sheet


def _insert_sheet(db_module, name: str = "Sheet-Blatt 1") -> int:
    conn = sqlite3.connect(db_module._resolve_db_path())
    sheet_id: int | None = None
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO sheets (name) VALUES (?)", (name,))
        conn.commit()
        sheet_id = cursor.lastrowid
    finally:
        conn.close()

    if sheet_id is None:
        raise RuntimeError("Fehler beim Anlegen des Sheets")
    return int(sheet_id)


def test_resolve_status_without_registered_sheet(answer_sheet_module):
    status = answer_sheet_module.resolve_answer_sheet_status(None)
    assert status.sheet_id is None
    assert status.configured_path is None
    assert status.exists_on_disk is False


def test_save_uploaded_answer_sheet_persists_file_and_db(answer_sheet_module, db_module, tmp_path):
    sheet_root = tmp_path / "Sheet-Blatt 1"
    sheet_root.mkdir()
    sheet_id = _insert_sheet(db_module)
    context = SheetContext(root_path=str(sheet_root), sheet_name="Sheet-Blatt 1", sheet_id=sheet_id)

    pdf_bytes = BytesIO(b"%PDF-1.7\nTest")
    status = answer_sheet_module.save_uploaded_answer_sheet(context, pdf_bytes)

    expected_path = sheet_root / "answer_sheet.pdf"
    assert expected_path.exists()
    assert status.exists_on_disk is True
    assert status.effective_path == expected_path
    assert db_module.get_answer_sheet_path(sheet_id) == str(expected_path)


def test_delete_answer_sheet_removes_file_and_record(answer_sheet_module, db_module, tmp_path):
    sheet_root = tmp_path / "Sheet-Blatt 2"
    sheet_root.mkdir()
    sheet_id = _insert_sheet(db_module, name="Sheet-Blatt 2")
    context = SheetContext(root_path=str(sheet_root), sheet_name="Sheet-Blatt 2", sheet_id=sheet_id)

    existing = sheet_root / "answer_sheet.pdf"
    existing.write_bytes(b"content")
    db_module.save_answer_sheet_path(sheet_id, str(existing))

    status = answer_sheet_module.delete_answer_sheet(context)

    assert not existing.exists()
    assert status.configured_path is None or not status.exists_on_disk
    assert db_module.get_answer_sheet_path(sheet_id) is None


def test_setup_answer_sheet_toggle_persists_preference(answer_sheet_module, db_module):
    storage_key = "review_answer_sheet_pref_7"
    session_state: dict[str, bool] = {}

    widget_key, on_change = answer_sheet_module.setup_answer_sheet_toggle(
        key_prefix="review",
        sheet_id=7,
        has_answer_sheet=True,
        session_state=session_state,
    )

    assert widget_key in session_state
    assert session_state[widget_key] is True

    session_state[widget_key] = False
    on_change()
    assert db_module.load_grader_state(storage_key) == "false"

    # Saved preference should bootstrap the widget, but disappear when no sheet exists
    db_module.save_grader_state(storage_key, "true")
    session_state = {widget_key: True}
    widget_key, _ = answer_sheet_module.setup_answer_sheet_toggle(
        key_prefix="review",
        sheet_id=7,
        has_answer_sheet=False,
        session_state=session_state,
    )
    assert session_state[widget_key] is False
    assert db_module.load_grader_state(storage_key) == "false"


def test_resolve_status_reports_missing_file(answer_sheet_module, db_module, tmp_path):
    sheet_root = tmp_path / "Sheet-Blatt 3"
    sheet_root.mkdir()
    sheet_id = _insert_sheet(db_module, name="Sheet-Blatt 3")
    context = SheetContext(root_path=str(sheet_root), sheet_name="Sheet-Blatt 3", sheet_id=sheet_id)

    missing_path = sheet_root / "answer_sheet.pdf"
    db_module.save_answer_sheet_path(sheet_id, str(missing_path))

    status = answer_sheet_module.resolve_answer_sheet_status(context)
    assert status.configured_path == missing_path
    assert status.exists_on_disk is False
    assert status.effective_path is None
