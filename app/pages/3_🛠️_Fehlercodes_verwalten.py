from __future__ import annotations

from pathlib import Path

import streamlit as st

try:
    from app.db import (
        add_error_code,
        delete_error_code,
        get_error_codes,
        get_sheets,
    )
except ImportError:  # pragma: no cover - fallback when running via "streamlit run app/..."
    from db import (
        add_error_code,
        delete_error_code,
        get_error_codes,
        get_sheets,
    )


st.set_page_config(
    page_title="Sifr | Fehlercodes verwalten",
    page_icon="app/static/img/sifr_logo.png",
    layout="wide",
    initial_sidebar_state="auto",
    menu_items={
        "Get Help": "https://github.com/shakha-de/sifr",
        "Report a bug": "https://github.com/shakha-de/sifr/issues",
        "About": """# sifr - is a grading tool.  based on [Streamlit](https://streamlit.io/) with Markdown & $\\LaTeX$ support.""",
    },
)

st.title("Fehlercodes verwalten")
st.caption(
    "Lege neue Fehlercodes an, passe bestehende Beschreibungen an oder entferne veraltete Einträge."
)

sheets = get_sheets()

if not sheets:
    st.info(
        "Es wurden noch keine Übungsserien gefunden. Lade zunächst eine Abgabe in der Korrekturansicht, damit Sifr automatisch einen Sheet-Eintrag anlegt."
    )
    st.stop()

sheet_lookup = {name: sheet_id for sheet_id, name in sheets}
sheet_names = list(sheet_lookup.keys())

current_root = st.session_state.get("current_root")
current_name = None
if current_root:
    current_name = Path(current_root).name

default_index = 0
if current_name and current_name in sheet_lookup:
    default_index = sheet_names.index(current_name)

selected_sheet_name = st.selectbox(
    "Übungsserie wählen",
    options=sheet_names,
    index=default_index,
    help="Alle Fehlercodes werden sheet-spezifisch gespeichert.",
    key="error_codes_sheet_select",
)
selected_sheet_id = sheet_lookup[selected_sheet_name]


with st.form("add_error_code_form"):
    st.subheader("Neuen Fehlercode hinzufügen")
    new_code = st.text_input("Code", help="Kurzes Kürzel, z. B. FC1").strip()
    new_desc = st.text_input("Beschreibung", help="Kurzbeschreibung des Fehlers").strip()
    new_abzug = st.number_input(
        "Abzug Punkte",
        min_value=0.0,
        step=0.5,
        help="Wieviele Punkte sollen standardmäßig abgezogen werden?",
    )
    new_komm = st.text_area(
        "Kommentar",
        help="Optionaler Langtext, der automatisch dem Feedback hinzugefügt wird.",
    ).strip()

    submitted = st.form_submit_button("Fehlercode speichern", type="primary")
    if submitted:
        if not new_code or not new_desc:
            st.error("Bitte gib mindestens Code und Beschreibung an.")
        else:
            try:
                add_error_code(selected_sheet_id, new_code.strip(), new_desc.strip(), new_abzug, new_komm)
                st.success(f"{new_code} gespeichert.")
                st.rerun()
            except Exception as exc:  # pragma: no cover - surfaces DB issues to UI
                st.error(f"Fehler beim Speichern: {exc}")

st.divider()

st.subheader("Vorhandene Fehlercodes")
error_codes = get_error_codes(selected_sheet_id)

if not error_codes:
    st.info("Noch keine Fehlercodes vorhanden.")
else:
    for code, desc, abzug, komm in error_codes:
        with st.container():
            col_info, col_actions = st.columns([5, 1])
            with col_info:
                st.markdown(
                    f"**{code}** — {desc}<br/>Abzug: **{abzug:g}** Punkte"
                    + (f"<br/><small>{komm}</small>" if komm else ""),
                    unsafe_allow_html=True,
                )
            with col_actions:
                if st.button("Löschen", key=f"del_{selected_sheet_id}_{code}", type="secondary"):
                    delete_error_code(code, sheet_id=selected_sheet_id)
                    st.success(f"{code} gelöscht.")
                    st.rerun()
