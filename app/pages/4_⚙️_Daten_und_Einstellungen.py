from __future__ import annotations

from pathlib import Path

import streamlit as st

from answer_sheet import render_answer_sheet_sidebar
from db import get_sheet_id_by_name, get_submissions, save_exercise_max_points
from helpers import convert_submissions, resolve_sheet_context
from korrektur_utils import build_exercise_options
from sidebar_panels import ensure_session_defaults, render_archive_loader

st.set_page_config(
    page_title="Sifr | Daten & Einstellungen",
    page_icon="app/static/img/sifr_logo.png",
    layout="wide",
)

ensure_session_defaults()

st.title("Archive & Einstellungen")
render_archive_loader()

current_root = st.session_state.get("current_root")
if current_root:
    st.success(f"Aktueller Arbeitsordner: {Path(current_root).name}")
else:
    st.warning("Noch kein Arbeitsordner gewählt. Lade ein Archive oder wähle einen Ordner.")

sheet_context = resolve_sheet_context(current_root, get_sheet_id_by_name)
render_answer_sheet_sidebar(sheet_context)

st.divider()
st.header("Aufgaben & Reviewer-Optionen")

raw_submissions = get_submissions()
submissions = convert_submissions(raw_submissions)
exercise_options = build_exercise_options(submissions)
exercise_names = [name for name in exercise_options if name != "Alle"]

if exercise_names:
    st.write("Maximale Punkte pro Aufgabe")

    def _make_max_points_callback(exercise: str):
        def callback():
            key = f"max_points_{exercise}"
            if key in st.session_state:
                value = st.session_state[key]
                save_exercise_max_points(exercise, value)
                st.session_state.exercise_max_points[exercise] = value

        return callback

    for exercise in exercise_names:
        key_name = f"max_points_{exercise}"
        default_value = float(st.session_state.exercise_max_points.get(exercise, 0.0))
        st.number_input(
            exercise,
            min_value=0.0,
            value=default_value,
            step=0.5,
            key=key_name,
            on_change=_make_max_points_callback(exercise),
        )
else:
    st.info("Keine Aufgaben gefunden. Bitte lade ein Archive und scanne die Abgaben.")

st.write("---")
if "show_meme_menu" not in st.session_state:
    st.session_state["show_meme_menu"] = True

show_meme = st.checkbox(
    "Add Meme Menü anzeigen",
    value=st.session_state["show_meme_menu"],
    key="settings_show_meme_checkbox",
)
st.session_state["show_meme_menu"] = show_meme
st.caption(
    "Steuert, ob das Meme-Eingabefeld auf der Korrektur-Seite eingeblendet wird."
)