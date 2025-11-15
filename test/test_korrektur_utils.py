from __future__ import annotations

from pathlib import Path

import pytest

from app.korrektur_utils import (
    build_exercise_options,
    classify_pdf_candidates,
    compute_progress_stats,
    filter_by_search,
    filter_submissions,
    find_candidate_roots,
    sort_submissions,
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


def test_classify_pdf_candidates_filters_invalid_paths(tmp_path):
    valid_pdf = tmp_path / "valid.pdf"
    valid_pdf.write_bytes(b"%PDF-1.7\n...")

    missing_pdf = tmp_path / "missing.pdf"
    folder_path = tmp_path / "just_a_dir"
    folder_path.mkdir()
    wrong_header = tmp_path / "not_pdf.pdf"
    wrong_header.write_bytes(b"ABCD")

    valid, issues = classify_pdf_candidates(
        [str(valid_pdf), str(missing_pdf), str(folder_path), str(wrong_header)]
    )

    assert valid == [str(valid_pdf)]
    assert (str(missing_pdf), "Datei nicht gefunden") in issues
    assert (str(folder_path), "Pfad ist keine Datei") in issues
    assert (str(wrong_header), "Datei besitzt keinen PDF-Header") in issues


def test_classify_pdf_candidates_reports_unreadable_file(tmp_path, monkeypatch):
    target_pdf = tmp_path / "locked.pdf"
    target_pdf.write_bytes(b"%PDF-1.4\n")

    original_open = Path.open

    def fake_open(self, mode="r", *args, **kwargs):
        if self == target_pdf and "b" in mode:
            raise OSError("permission denied")
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fake_open)

    valid, issues = classify_pdf_candidates([str(target_pdf)])

    assert valid == []
    assert issues and issues[0][0] == str(target_pdf)
    assert "permission denied" in issues[0][1]


def test_filter_by_search_matches_submitter_and_group():
    submissions = [
        _make_submission("Exercise-1", idx=1),
        SubmissionRecord(
            id=2,
            path="/tmp/2",
            group_name="Duo Bravo",
            submitter="Second Student",
            exercise_code="Exercise-2",
            status="SUBMITTED",
        ),
    ]

    assert filter_by_search(submissions, "student 1") == [submissions[0]]
    assert filter_by_search(submissions, "duo") == [submissions[1]]
    assert filter_by_search(submissions, " ") == submissions
    assert filter_by_search(submissions, "nomatch") == []


def test_sort_submissions_modes():
    submissions = [
        SubmissionRecord(3, "/tmp/3", "G3", "Charlie", "Exercise-1", "FINAL_MARK"),
        SubmissionRecord(1, "/tmp/1", "G1", "alice", "Exercise-1", "SUBMITTED"),
        SubmissionRecord(2, "/tmp/2", "G2", "Bob", "Exercise-1", "PROVISIONAL_MARK"),
    ]

    by_id = sort_submissions(submissions, "Nach ID")
    assert [record.id for record in by_id] == [1, 2, 3]

    alpha = sort_submissions(submissions, "Alphabetisch")
    assert [record.submitter for record in alpha] == ["alice", "Bob", "Charlie"]

    open_first = sort_submissions(submissions, "Status: offen zuerst")
    assert [record.id for record in open_first] == [1, 2, 3]

    done_first = sort_submissions(submissions, "Status: fertig zuerst")
    assert [record.id for record in done_first] == [2, 3, 1]


def test_compute_progress_stats_counts_statuses():
    submissions = [
        SubmissionRecord(1, "/tmp/1", "G1", "A", "Exercise-1", "FINAL_MARK"),
        SubmissionRecord(2, "/tmp/2", "G2", "B", "Exercise-1", "SUBMITTED"),
        SubmissionRecord(3, "/tmp/3", "G3", "C", "Exercise-1", "PROVISIONAL_MARK"),
    ]

    stats = compute_progress_stats(submissions)
    assert stats["total"] == 3
    assert stats["corrected"] == 2
    assert stats["status_counts"] == {
        "FINAL_MARK": 1,
        "SUBMITTED": 1,
        "PROVISIONAL_MARK": 1,
    }
