from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from typing import Iterable, Sequence

import streamlit as st

try:  # Allow running inside the app directory or as a package import
    from helpers import SubmissionRecord
except ImportError:  # pragma: no cover - fallback for package imports
    from .helpers import SubmissionRecord

__all__ = [
    "find_candidate_roots",
    "build_exercise_options",
    "filter_submissions",
    "classify_pdf_candidates",
    "filter_by_search",
    "sort_submissions",
    "compute_progress_stats",
    "render_manual_feedback_popover",
]


COMPLETED_STATUSES = {"FINAL_MARK", "PROVISIONAL_MARK"}


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


def filter_by_search(
    submissions: Iterable[SubmissionRecord],
    query: str,
) -> list[SubmissionRecord]:
    """Filter submissions by submitter or group name using a case-insensitive query."""

    normalized = (query or "").strip().lower()
    if not normalized:
        return list(submissions)

    def _matches(record: SubmissionRecord) -> bool:
        haystacks = (record.submitter.lower(), record.group_name.lower())
        return any(normalized in haystack for haystack in haystacks)

    return [record for record in submissions if _matches(record)]


def sort_submissions(
    submissions: Iterable[SubmissionRecord],
    mode: str,
) -> list[SubmissionRecord]:
    """Return submissions sorted according to the requested display mode."""

    mode = (mode or "Nach ID").strip().lower()
    submissions = list(submissions)

    if mode == "alphabetisch":
        return sorted(submissions, key=lambda r: (r.submitter.lower(), r.id))

    if mode == "status: offen zuerst":
        return sorted(
            submissions,
            key=lambda r: (1 if r.status in COMPLETED_STATUSES else 0, r.id),
        )

    if mode == "status: fertig zuerst":
        return sorted(
            submissions,
            key=lambda r: (0 if r.status in COMPLETED_STATUSES else 1, r.id),
        )

    return sorted(submissions, key=lambda r: r.id)


def compute_progress_stats(submissions: Iterable[SubmissionRecord]) -> dict[str, object]:
    """Return aggregate stats (total, corrected, and per-status counts)."""

    submissions = list(submissions)
    total = len(submissions)
    status_counter = Counter(record.status for record in submissions)
    corrected = sum(count for status, count in status_counter.items() if status in COMPLETED_STATUSES)
    return {
        "total": total,
        "corrected": corrected,
        "status_counts": dict(status_counter),
    }


def render_manual_feedback_popover(
    submission_id: int,
    points_key: str,
    markdown_key: str,
):
    """Provide a quick popup to append custom feedback and apply deductions."""

    st.caption("Direktes Feedback hinzufügen")
    with st.popover(
        ":green[Feedback hinzufügen]",
        use_container_width=True,
    ):
        desc_key = f"manual_feedback_desc_{submission_id}"
        deduction_key = f"manual_feedback_deduction_{submission_id}"
        comment_key = f"manual_feedback_comment_{submission_id}"
        reset_flag_key = f"manual_feedback_reset_{submission_id}"

        if desc_key not in st.session_state:
            st.session_state[desc_key] = ""
        if comment_key not in st.session_state:
            st.session_state[comment_key] = ""
        if deduction_key not in st.session_state:
            st.session_state[deduction_key] = 0.0

        if st.session_state.pop(reset_flag_key, False):
            st.session_state[desc_key] = ""
            st.session_state[comment_key] = ""
            st.session_state[deduction_key] = 0.0

        current_points = float(st.session_state.get(points_key, 0.0))
        current_markdown = st.session_state.get(markdown_key, "")

        beschreibung = st.text_input(
            "Beschreibung",
            key=desc_key,
            placeholder="z. B. Randbedingungen fehlen",
        )
        abzugpunkte = st.number_input(
            "Abzugpunkte",
            min_value=0.0,
            max_value=current_points,
            step=0.5,
            key=deduction_key,
        )
        kommentar = st.text_area(
            "Kommentar",
            key=comment_key,
            height=120,
        )

        if st.button(
            "In Markdown übernehmen",
            key=f"manual_feedback_submit_{submission_id}",
            type="primary",
        ):
            if not beschreibung.strip():
                st.error("Bitte eine Beschreibung angeben.")
                return
            if abzugpunkte <= 0:
                st.error("Abzugpunkte müssen größer als 0 sein.")
                return

            addition = f"\n\n### {beschreibung.strip()}: -{abzugpunkte:g}P"
            comment_text = kommentar.strip()
            if comment_text:
                addition += f"\n{comment_text}"

            updated_points = max(0.0, current_points - float(abzugpunkte))
            updated_markdown = current_markdown + addition

            pending_points_key = f"pending_points_{submission_id}"
            pending_markdown_key = f"pending_markdown_{submission_id}"
            st.session_state[pending_points_key] = updated_points
            st.session_state[pending_markdown_key] = updated_markdown
            st.session_state[reset_flag_key] = True

            st.success("Feedback hinzugefügt!")
            st.rerun()
