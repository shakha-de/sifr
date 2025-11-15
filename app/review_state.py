from __future__ import annotations

from typing import Sequence

import streamlit as st

from db import (
    get_review_current_submission_id,
    set_review_current_submission_id,
    load_grader_state,
    save_grader_state,
)

DEFAULT_FILTER = "Alle"


class ReviewStateManager:
    """Helper to keep the review page's widgets and persistence in sync."""

    SUBMISSION_STATE_KEY = "review_submission_id"
    FILTER_STATE_KEY = "review_exercise_filter"
    NAV_ACTION_KEY = "review_nav_action"
    FILTER_STORAGE_KEY = "review_exercise_filter"

    def __init__(self, current_root: str | None, sheet_id: int | None):
        self.current_root = current_root
        self.sheet_id = sheet_id

    # ------------------------------------------------------------------
    # Session defaults
    # ------------------------------------------------------------------
    def ensure_defaults(self) -> None:
        st.session_state.setdefault(self.SUBMISSION_STATE_KEY, None)
        st.session_state.setdefault(self.FILTER_STATE_KEY, DEFAULT_FILTER)
        st.session_state.setdefault(self.NAV_ACTION_KEY, None)

    # ------------------------------------------------------------------
    # Exercise filter helpers
    # ------------------------------------------------------------------
    def sync_exercise_filter(self, exercise_options: Sequence[str]) -> str:
        if not exercise_options:
            return DEFAULT_FILTER

        saved_filter = load_grader_state(self.FILTER_STORAGE_KEY, DEFAULT_FILTER)
        if saved_filter not in exercise_options:
            saved_filter = DEFAULT_FILTER

        current_filter = st.session_state.get(self.FILTER_STATE_KEY, saved_filter)
        if current_filter not in exercise_options:
            current_filter = saved_filter
            st.session_state[self.FILTER_STATE_KEY] = current_filter

        return current_filter

    def persist_exercise_filter(self, value: str) -> None:
        if value != load_grader_state(self.FILTER_STORAGE_KEY, DEFAULT_FILTER):
            save_grader_state(self.FILTER_STORAGE_KEY, value)
        st.session_state[self.FILTER_STATE_KEY] = value

    # ------------------------------------------------------------------
    # Submission selection helpers
    # ------------------------------------------------------------------
    def submission_selectbox_key(self, exercise_filter: str | None) -> str:
        base = f"{self.current_root or ''}_{exercise_filter or DEFAULT_FILTER}"
        sanitized = "".join(ch if ch.isalnum() else "_" for ch in base)
        sanitized = sanitized or "default"
        return f"review_submission_select_{sanitized}"

    def resolve_current_submission(
        self,
        ordered_ids: Sequence[int],
        valid_ids: dict[int, str],
    ) -> int:
        if not ordered_ids:
            raise ValueError("Es wurden keine Abgaben gefunden.")

        current_id = st.session_state.get(self.SUBMISSION_STATE_KEY)
        if current_id is None or current_id not in valid_ids:
            saved_id = get_review_current_submission_id()
            if saved_id and saved_id in valid_ids:
                current_id = saved_id
            else:
                current_id = ordered_ids[0]

        self.persist_submission_id(current_id)
        return current_id

    def persist_submission_id(self, submission_id: int) -> None:
        st.session_state[self.SUBMISSION_STATE_KEY] = submission_id
        set_review_current_submission_id(submission_id)
