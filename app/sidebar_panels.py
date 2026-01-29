from __future__ import annotations

import os
import tarfile
from pathlib import Path

import streamlit as st

from config import get_data_dir
from db import get_exercise_max_points
from korrektur_utils import find_candidate_roots

DATA_ROOT = get_data_dir()
DATA_ROOT.mkdir(parents=True, exist_ok=True)


def ensure_session_defaults() -> None:
    state = st.session_state
    if "exercise_max_points" not in state:
        state.exercise_max_points = get_exercise_max_points()

    state.setdefault("archive_loaded", False)
    state.setdefault("available_roots", find_candidate_roots(DATA_ROOT))
    if "current_root" not in state:
        roots = state.available_roots
        state.current_root = roots[0] if roots else None

    defaults = {
        "last_scanned_root": None,
        "force_rescan": False,
        "submission_selector": None,
        "exercise_filter": "Alle",
        "nav_action": None,
    }
    for key, value in defaults.items():
        state.setdefault(key, value)


def render_archive_loader() -> None:
    with st.sidebar.expander("Neues Archive laden"):
        uploaded_file = st.file_uploader(
            "Wähle ein tar.gz Archive", type=["tar.gz"], key="archive_uploader"
        )
        st.caption(f"Datenverzeichnis: {DATA_ROOT}")
        if st.button("Archive entpacken und laden", key="extract_archive"):
            if uploaded_file is None:
                st.warning("Bitte wähle zuerst ein Archive aus.")
            else:
                with st.spinner("Entpacke Archive..."):
                    try:
                        from datetime import datetime
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        safe_name = Path(uploaded_file.name).stem
                        target_dir = DATA_ROOT / f"{safe_name}_{timestamp}"
                        target_dir.mkdir(parents=True, exist_ok=True)
                        
                        uploaded_file.seek(0)
                        with tarfile.open(fileobj=uploaded_file, mode="r:gz") as tar:
                            tar.extractall(str(target_dir), filter="data")
                        candidates = find_candidate_roots(DATA_ROOT)
                        if candidates:
                            st.session_state.available_roots = candidates
                            st.session_state.current_root = candidates[0]
                            st.session_state.last_scanned_root = None
                            st.session_state.force_rescan = True
                            st.session_state.archive_loaded = True
                            st.session_state.pop("submission_selector", None)
                            st.success(
                                f"Archive entpackt. {len(candidates)} mögliche Arbeitsordner gefunden."
                            )
                        else:
                            st.error("Konnte kein gültiges Übungsblatt-Verzeichnis finden.")
                    except Exception as error:  # pragma: no cover - UI feedback only
                        st.error(f"Fehler beim Entpacken: {error}")
