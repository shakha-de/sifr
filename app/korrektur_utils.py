from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Sequence

try:  # Allow running inside the app directory or as a package import
    from helpers import SubmissionRecord
except ImportError:  # pragma: no cover - fallback for package imports
    from .helpers import SubmissionRecord

__all__ = [
    "find_candidate_roots",
    "build_exercise_options",
    "filter_submissions",
    "classify_pdf_candidates",
]


def find_candidate_roots(base_dir: os.PathLike[str] | str) -> list[str]:
    """Return directories that look like valid sheet roots."""

    base_path = Path(base_dir)
    if not base_path.exists():
        return []

    candidates: list[str] = []
    for item_path in base_path.iterdir():
        if not item_path.is_dir():
            continue

        try:
            entries = list(item_path.iterdir())
        except PermissionError:
            continue

        has_marks = (item_path / "marks.csv").exists()
        has_exercises = any(
            entry.is_dir() and entry.name.lower().startswith(("excercise-", "exercise-"))
            for entry in entries
        )
        if has_marks or has_exercises:
            candidates.append(str(item_path.resolve()))

    return sorted(set(candidates))


def build_exercise_options(submissions: Sequence[SubmissionRecord]) -> list[str]:
    """Return the filter dropdown options for the given submissions."""

    exercise_names = sorted({record.exercise_code for record in submissions})
    return ["Alle"] + exercise_names if exercise_names else ["Alle"]


def filter_submissions(
    submissions: Iterable[SubmissionRecord],
    selected_exercise: str,
) -> list[SubmissionRecord]:
    """Filter submissions to the exercise code if not 'Alle'."""

    if selected_exercise == "Alle":
        return list(submissions)
    return [record for record in submissions if record.exercise_code == selected_exercise]


def classify_pdf_candidates(pdfs: Iterable[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Return readable PDFs plus (path, reason) tuples for anything we skip."""

    valid: list[str] = []
    issues: list[tuple[str, str]] = []

    for candidate in pdfs:
        path = Path(candidate)
        reason: str | None = None

        if not path.exists():
            reason = "Datei nicht gefunden"
        elif not path.is_file():
            reason = "Pfad ist keine Datei"
        else:
            try:
                with path.open("rb") as handle:
                    header = handle.read(4)
                if len(header) < 4 or not header.startswith(b"%PDF"):
                    reason = "Datei besitzt keinen PDF-Header"
            except OSError as exc:
                reason = f"Datei konnte nicht gelesen werden: {exc}"

        if reason:
            issues.append((str(path), reason))
        else:
            valid.append(str(path))

    return valid, issues
