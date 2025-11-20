from pathlib import Path
from re import split

import streamlit as st
from streamlit_pdf_viewer import pdf_viewer

from utils import find_pdfs_in_submission
import os
from db import (
    get_submissions,
    get_feedback,
    get_sheet_id_by_name,
    get_feedback_submission_ids,
)
from review_state import ReviewStateManager
from helpers import SheetContext
from answer_sheet import resolve_answer_sheet_status, setup_answer_sheet_toggle


st.set_page_config(
    page_title="Sifr | Korrekturen überprüfen | Split view mode",
    page_icon="app/static/img/sifr_logo.png",
    layout="wide",
    initial_sidebar_state="auto",
    menu_items={
        "Get Help": "https://github.com/shakha-de/sifr",
        "Report a bug": "https://github.com/shakha-de/sifr/issues",
        "About": """# sifr - is a grading tool.  based on [Streamlit](https://streamlit.io/) with Markdown & $\\LaTeX$ support.""",
    },
)

current_root = st.session_state.get("current_root")
if not current_root:
    st.error("Kein aktiver Ordner wurde gewählt. Bitte wählen sie einen Arbeitsordner zuerst.")
    st.stop()

current_sheet_name = Path(current_root).name
current_sheet_id = get_sheet_id_by_name(current_sheet_name)
sheet_context = SheetContext(
    root_path=current_root,
    sheet_name=current_sheet_name,
    sheet_id=current_sheet_id,
)
state_manager = ReviewStateManager(current_root, current_sheet_id)
state_manager.ensure_defaults()

# Load submissions + feedback map
submissions = get_submissions()
feedback_ids = get_feedback_submission_ids()
if not submissions:
    st.warning("Keine Submissions gefunden. Bitte Archive überprüfen.")
    st.stop()

# Filter by exercise
exercise_names = sorted({row[4] for row in submissions})
exercise_options = ["Alle"] + exercise_names if exercise_names else ["Alle"]

# Lade den letzten Filter aus der Datenbank
current_filter = state_manager.sync_exercise_filter(exercise_options)

selected_exercise = st.sidebar.selectbox(
    "Aufgabe filtern",
    options=exercise_options,
    index=exercise_options.index(current_filter) if current_filter in exercise_options else 0,
    key="review_exercise_filter_select",
)

# Speichere den Filter wenn er sich ändert
if selected_exercise != current_filter:
    state_manager.persist_exercise_filter(selected_exercise)

filtered_submissions = [
    row for row in submissions if selected_exercise == "Alle" or row[4] == selected_exercise
]

# Show progress bar in sidebar
total_count = len(filtered_submissions)
corrected_count = sum(
    1 for row in filtered_submissions 
    if row[5] in ("FINAL_MARK", "PROVISIONAL_MARK") or row[0] in feedback_ids
)

if total_count > 0:
    progress = corrected_count / total_count
    st.sidebar.progress(progress, text=f"{corrected_count} / {total_count} erledigt")

# Build submission labels and map
def build_submission_label(row):
    submission_id = row[0]
    corrected = row[5] in ("FINAL_MARK", "PROVISIONAL_MARK") or submission_id in feedback_ids
    status_flag = "✅" if corrected else "⭕"
    return f"{status_flag} {row[3]} ({row[4]})"

submission_labels = [build_submission_label(row) for row in filtered_submissions]
selectbox_key = state_manager.submission_selectbox_key(selected_exercise)

# Create comprehensive maps
submission_id_map = {}  # label -> id
id_to_label_map = {}    # id -> label
submission_ids_ordered = []  # ids in order

for row in filtered_submissions:
    label = build_submission_label(row)
    submission_id = row[0]
    submission_id_map[label] = submission_id
    id_to_label_map[submission_id] = label
    submission_ids_ordered.append(submission_id)

# Handle no submissions after filter
if not submission_labels:
    st.sidebar.warning("Keine Abgaben verfügbar mit diesem Filter.")
    st.stop()

# ==================== NAVIGATION BUTTONS (BEFORE SELECTBOX) ====================
# Process navigation FIRST, then resolve which submission to show

current_id = state_manager.resolve_current_submission(submission_ids_ordered, id_to_label_map)
current_index = submission_ids_ordered.index(current_id)

# Display navigation buttons
col_prev, col_next = st.sidebar.columns([1, 1])

with col_prev:
    if st.button("Letzte", key="review_prev_btn", use_container_width=True, disabled=(current_index <= 0)):
        if current_index > 0:
            st.session_state.review_nav_action = "prev"



with col_next:
    if st.button("Nächste",type="primary", key="review_next_btn", use_container_width=True, disabled=(current_index >= len(submission_ids_ordered) - 1)):
        if current_index < len(submission_ids_ordered) - 1:
            st.session_state.review_nav_action = "next"

with st.sidebar:
    st.metric("Position", f"{current_index + 1}/{len(submission_ids_ordered)}")

# Handle navigation action
if st.session_state.review_nav_action:
    if st.session_state.review_nav_action == "prev" and current_index > 0:
        new_id = submission_ids_ordered[current_index - 1]
        state_manager.persist_submission_id(new_id)
    elif st.session_state.review_nav_action == "next" and current_index < len(submission_ids_ordered) - 1:
        new_id = submission_ids_ordered[current_index + 1]
        state_manager.persist_submission_id(new_id)
    st.session_state.review_nav_action = None
    st.rerun()

# ==================== SUBMISSION SELECTOR ====================
current_label = id_to_label_map[current_id]

if (
    selectbox_key not in st.session_state
    or st.session_state[selectbox_key] not in submission_labels
):
    st.session_state[selectbox_key] = current_label

# Display the selectbox
selected_label = st.sidebar.selectbox(
    "Wähle eine Abgabe",
    options=submission_labels,
    key=selectbox_key,
)

# Update if selection changed
if selected_label != current_label:
    submission_id = submission_id_map[selected_label]
    state_manager.persist_submission_id(submission_id)
    st.rerun()

# Get current submission details
submission_id = submission_id_map[selected_label]
submission_row = next(row for row in filtered_submissions if row[0] == submission_id)
submission_path = submission_row[1]
group_name = submission_row[2]
submitter = submission_row[3]
exercise_code = submission_row[4]
exercise_number = split("-", exercise_code)[1]

# Main content
st.sidebar.markdown(f"""Aufgabe # {exercise_number}

  Eingereicht von: **{submitter}**""")

# Load feedback + answer sheet info
feedback = get_feedback(submission_id)
answer_sheet_status = resolve_answer_sheet_status(sheet_context)
checkbox_key, checkbox_on_change = setup_answer_sheet_toggle(
    key_prefix="review",
    sheet_id=answer_sheet_status.sheet_id,
    has_answer_sheet=answer_sheet_status.exists_on_disk,
)

show_answer_sheet = st.sidebar.checkbox(
    "Lösungsblatt anzeigen",
    key=checkbox_key,
    on_change=checkbox_on_change,
)

if show_answer_sheet:
    col1, col2, col3 = st.columns(3)
else:
    col1, col2 = st.columns(2)
    col3 = None

with col1:
    # Find original submission files
    submission_path_obj = Path(submission_path)
    if submission_path_obj.exists():
        pdf_files = find_pdfs_in_submission(submission_path)
        if pdf_files:
            for pdf_file in pdf_files:
                if not os.path.basename(pdf_file).startswith(f"feedback_{group_name}"):
                    try:
                        pdf_viewer(
                            str(pdf_file),
                            resolution_boost=2,
                            width="100%",
                            render_text=True,
                            height=800
                        )
                    except Exception as e:
                        st.error(f"Fehler beim Anzeigen der PDF: {e}")
        else:
            st.info("Keine PDFs in dieser Abgabe gefunden.")
    else:
        st.error(f"Abgabepfad nicht gefunden: {submission_path}")

with col2:
    if feedback:
        feedback_pdf_dir = Path(submission_path)
        feedback_pdfs = (
            sorted(feedback_pdf_dir.glob("feedback_*.pdf")) if feedback_pdf_dir.exists() else []
        )
        if feedback_pdfs:
            for pdf_file in feedback_pdfs:
                try:
                    pdf_viewer(
                        str(pdf_file),
                        resolution_boost=2,
                        width="100%",
                        render_text=True,
                        height=800
                    )
                except Exception as e:
                    st.error(f"Fehler beim Anzeigen der Feedback-PDF: {e}")
    else:
        st.info("Kein Feedback für diese Abgabe verfügbar.")

if show_answer_sheet and col3 is not None:
    with col3:
        if answer_sheet_status.effective_path:
            try:
                pdf_viewer(
                    str(answer_sheet_status.effective_path),
                    resolution_boost=2,
                    width="100%",
                    render_text=True,
                    height=800
                )
            except Exception as error:
                st.error(f"Fehler beim Anzeigen des Lösungsblatts: {error}")
        elif answer_sheet_status.configured_path:
            st.warning("Gespeichertes Lösungsblatt wurde nicht gefunden.")
            st.caption(str(answer_sheet_status.configured_path))
        else:
            st.info("Kein Lösungsblatt für dieses Blatt hinterlegt.")