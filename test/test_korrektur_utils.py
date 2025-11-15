from __future__ import annotations

from pathlib import Path

import pytest

from app.korrektur_utils import (
    build_exercise_options,
    filter_submissions,
    find_candidate_roots,
)
from app.helpers import SubmissionRecord


def _make_submission(exercise_code: str, idx: int = 1) -> SubmissionRecord:
    return SubmissionRecord(
        id=idx,
        path=f"/tmp/sub_{idx}",
        group_name=f"Group {idx}",
        submitter=f"Student {idx}",
        exercise_code=exercise_code,
        status="SUBMITTED",
    )


def test_find_candidate_roots_detects_marks_and_exercises(tmp_path):
    sheet_with_marks = tmp_path / "Sheet-1"
    sheet_with_marks.mkdir()
    (sheet_with_marks / "marks.csv").write_text("# header\n")

    sheet_with_exercise = tmp_path / "Sheet-2"
    sheet_with_exercise.mkdir()
    (sheet_with_exercise / "exercise-1").mkdir()

    ignored_sheet = tmp_path / "Sheet-ignored"
    ignored_sheet.mkdir()

    result = find_candidate_roots(tmp_path)

    assert str(sheet_with_marks.resolve()) in result
    assert str(sheet_with_exercise.resolve()) in result
    assert str(ignored_sheet.resolve()) not in result
    # Sorted + unique even if duplicates exist
    assert result == sorted(set(result))


def test_find_candidate_roots_handles_missing_directory(tmp_path):
    missing = tmp_path / "does-not-exist"
    assert find_candidate_roots(missing) == []


def test_build_exercise_options_returns_sorted_list():
    submissions = [
        _make_submission("Exercise-2", idx=2),
        _make_submission("Exercise-1", idx=1),
        _make_submission("Exercise-2", idx=3),
    ]
    options = build_exercise_options(submissions)
    assert options == ["Alle", "Exercise-1", "Exercise-2"]


def test_filter_submissions_selects_specific_exercise():
    submissions = [
        _make_submission("Exercise-1", idx=1),
        _make_submission("Exercise-2", idx=2),
    ]
    filtered = filter_submissions(submissions, "Exercise-2")
    assert [record.exercise_code for record in filtered] == ["Exercise-2"]

    # "Alle" should return identical list but as a new list instance
    all_records = filter_submissions(submissions, "Alle")
    assert all_records == submissions
    assert all_records is not submissions
