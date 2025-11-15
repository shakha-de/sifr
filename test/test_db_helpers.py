from __future__ import annotations

import importlib
import sqlite3
from contextlib import contextmanager

import pytest


@pytest.fixture()
def db_module(tmp_path, monkeypatch):
    """Provide an initialized copy of app.db pointing at a temporary data dir."""

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("SIFR_DATA_DIR", str(data_dir))

    # Reload after setting the env var so the module resolves the new DB path.
    import app.db as db

    importlib.reload(db)
    db.init_db()
    yield db


@contextmanager
def _connect(db_module):
    conn = sqlite3.connect(db_module._resolve_db_path())
    try:
        yield conn
    finally:
        conn.close()


def _insert_sheet(conn, name: str = "Sheet-Blatt 1") -> int:
    cursor = conn.cursor()
    cursor.execute("INSERT INTO sheets (name) VALUES (?)", (name,))
    conn.commit()
    return cursor.lastrowid


def _insert_exercise(conn, sheet_id: int, code: str) -> int:
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO exercises (sheet_id, code) VALUES (?, ?)",
        (sheet_id, code),
    )
    conn.commit()
    return cursor.lastrowid


def _insert_submission(conn, sheet_id: int, exercise_id: int, idx: int) -> int:
    cursor = conn.cursor()
    submission_path = f"/tmp/submission_{idx}"
    cursor.execute(
        """
        INSERT INTO submissions (path, group_name, submitter, sheet_id, exercise_id, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            submission_path,
            f"Team_{idx}",
            f"Student_{idx}",
            sheet_id,
            exercise_id,
            "SUBMITTED",
        ),
    )
    conn.commit()
    return cursor.lastrowid


def test_answer_sheet_crud(db_module, tmp_path):
    with _connect(db_module) as conn:
        sheet_id = _insert_sheet(conn)

    pdf_path = tmp_path / "answers.pdf"
    pdf_path.write_bytes(b"dummy")

    db_module.save_answer_sheet_path(sheet_id, str(pdf_path))
    assert db_module.get_answer_sheet_path(sheet_id) == str(pdf_path)

    new_pdf = tmp_path / "answers_new.pdf"
    new_pdf.write_bytes(b"new")
    db_module.save_answer_sheet_path(sheet_id, str(new_pdf))
    assert db_module.get_answer_sheet_path(sheet_id) == str(new_pdf)

    db_module.delete_answer_sheet_path(sheet_id)
    assert db_module.get_answer_sheet_path(sheet_id) is None


def test_save_feedback_with_submission_upserts(db_module, tmp_path):
    with _connect(db_module) as conn:
        sheet_id = _insert_sheet(conn)
        exercise_id = _insert_exercise(conn, sheet_id, "Exercise-1")
        submission_id = _insert_submission(conn, sheet_id, exercise_id, idx=1)

    pdf_path = tmp_path / "feedback.pdf"
    pdf_path.write_bytes(b"pdf")

    db_module.save_feedback_with_submission(
        submission_id,
        status="FINAL_MARK",
        points=8.5,
        markdown_content="Great work",
        pdf_path=str(pdf_path),
    )

    with _connect(db_module) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT sheet_id, exercise_id, points, markdown_content, pdf_path FROM feedback WHERE submission_id = ?",
            (submission_id,),
        )
        row = cursor.fetchone()
        assert row == (sheet_id, exercise_id, 8.5, "Great work", str(pdf_path))

        cursor.execute("SELECT status FROM submissions WHERE id = ?", (submission_id,))
        assert cursor.fetchone()[0] == "FINAL_MARK"

    updated_pdf = tmp_path / "feedback_updated.pdf"
    updated_pdf.write_bytes(b"new")

    db_module.save_feedback_with_submission(
        submission_id,
        status="PROVISIONAL_MARK",
        points=9.0,
        markdown_content="Updated",
        pdf_path=str(updated_pdf),
    )

    with _connect(db_module) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT points, markdown_content, pdf_path FROM feedback WHERE submission_id = ?",
            (submission_id,),
        )
        assert cursor.fetchone() == (9.0, "Updated", str(updated_pdf))

        cursor.execute("SELECT status FROM submissions WHERE id = ?", (submission_id,))
        assert cursor.fetchone()[0] == "PROVISIONAL_MARK"


def test_step_review_current_submission_handles_navigation(db_module):
    with _connect(db_module) as conn:
        sheet_id = _insert_sheet(conn)
        exercise1 = _insert_exercise(conn, sheet_id, "Exercise-1")
        exercise2 = _insert_exercise(conn, sheet_id, "Exercise-2")
        submissions = [
            _insert_submission(conn, sheet_id, exercise1, idx=1),
            _insert_submission(conn, sheet_id, exercise1, idx=2),
            _insert_submission(conn, sheet_id, exercise2, idx=3),
            _insert_submission(conn, sheet_id, exercise2, idx=4),
        ]

    db_module.set_review_current_submission_id(submissions[1])
    assert db_module.get_review_current_submission_id() == submissions[1]

    assert db_module.step_review_current_submission(1) == submissions[2]
    assert db_module.get_review_current_submission_id() == submissions[2]

    # Clamps at the end of the list
    assert db_module.step_review_current_submission(10) == submissions[3]
    assert db_module.get_review_current_submission_id() == submissions[3]

    # Moving backwards beyond the first submission returns the first entry
    assert db_module.step_review_current_submission(-10) == submissions[0]
    assert db_module.get_review_current_submission_id() == submissions[0]

    # Exercise-specific navigation should only consider matching submissions
    db_module.set_review_current_submission_id(submissions[2])
    assert (
        db_module.step_review_current_submission(1, exercise_code="Exercise-2")
        == submissions[3]
    )
    assert (
        db_module.step_review_current_submission(-5, exercise_code="Exercise-2")
        == submissions[2]
    )
