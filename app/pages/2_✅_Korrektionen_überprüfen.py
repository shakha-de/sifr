from pathlib import Path
from re import split

import streamlit as st
from streamlit_pdf_viewer import pdf_viewer

from utils import find_pdfs_in_submission
import os
from db import (
    get_submissions,
    get_feedback,
    load_grader_state,
    save_grader_state,
    get_review_current_submission_id,
    set_review_current_submission_id,
)


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


def _build_selectbox_key(root_value: str | None, exercise_filter: str | None) -> str:
    """Create a Streamlit widget key using only safe characters."""
    base = f"{root_value or ''}_{exercise_filter or 'Alle'}"
    sanitized = "".join(ch if ch.isalnum() else "_" for ch in base)
    sanitized = sanitized or "default"
    return f"review_submission_select_{sanitized}"


# Initialize session state
if "review_submission_id" not in st.session_state:
    st.session_state.review_submission_id = None
if "review_exercise_filter" not in st.session_state:
    st.session_state.review_exercise_filter = "Alle"
if "review_nav_action" not in st.session_state:
    st.session_state.review_nav_action = None

# Load submissions
submissions = get_submissions()
if not submissions:
    st.warning("Keine Submissions gefunden. Bitte Archive überprüfen.")
    st.stop()

# Filter by exercise
exercise_names = sorted({row[4] for row in submissions})
exercise_options = ["Alle"] + exercise_names if exercise_names else ["Alle"]

# Lade den letzten Filter aus der Datenbank
saved_exercise_filter = load_grader_state("review_exercise_filter", "Alle")
if saved_exercise_filter not in exercise_options:
    saved_exercise_filter = "Alle"

if st.session_state.review_exercise_filter not in exercise_options:
    st.session_state.review_exercise_filter = saved_exercise_filter

selected_exercise = st.sidebar.selectbox(
    "Aufgabe filtern",
    options=exercise_options,
    index=exercise_options.index(st.session_state.review_exercise_filter) if st.session_state.review_exercise_filter in exercise_options else 0,
    key="review_exercise_filter_select",
)

# Speichere den Filter wenn er sich ändert
if selected_exercise != load_grader_state("review_exercise_filter", "Alle"):
    save_grader_state("review_exercise_filter", selected_exercise)
    st.session_state.review_exercise_filter = selected_exercise

filtered_submissions = [
    row for row in submissions if selected_exercise == "Alle" or row[4] == selected_exercise
]

# Build submission labels and map
def build_submission_label(row):
    status_flag = "✅" if row[5] in ("FINAL_MARK", "PROVISIONAL_MARK") else "⭕"
    return f"{status_flag} {row[3]} ({row[4]})"

submission_labels = [build_submission_label(row) for row in filtered_submissions]
selectbox_key = _build_selectbox_key(st.session_state.get("current_root"), st.session_state.review_exercise_filter)

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

def _get_current_submission_index():
    """Find the current submission index in the filtered list."""
    current_id = st.session_state.review_submission_id
    if current_id is None or current_id not in id_to_label_map:
        # Try to load from DB
        saved_id = get_review_current_submission_id()
        if saved_id and saved_id in id_to_label_map:
            return submission_ids_ordered.index(saved_id)
        return 0
    return submission_ids_ordered.index(current_id)


# Display navigation buttons
col_prev, col_next = st.sidebar.columns([1, 1])

current_index = _get_current_submission_index()

with col_prev:
    if st.button("Letzte", key="review_prev_btn", use_container_width=True, disabled=(current_index <= 0)):
        if current_index > 0:
            st.session_state.review_nav_action = "prev"



with col_next:
    if st.button("Nächste", key="review_next_btn", use_container_width=True, disabled=(current_index >= len(submission_ids_ordered) - 1)):
        if current_index < len(submission_ids_ordered) - 1:
            st.session_state.review_nav_action = "next"

with st.sidebar:
    st.metric("Position", f"{current_index + 1}/{len(submission_ids_ordered)}")

# Handle navigation action
if st.session_state.review_nav_action:
    if st.session_state.review_nav_action == "prev" and current_index > 0:
        new_id = submission_ids_ordered[current_index - 1]
        st.session_state.review_submission_id = new_id
        set_review_current_submission_id(new_id)
    elif st.session_state.review_nav_action == "next" and current_index < len(submission_ids_ordered) - 1:
        new_id = submission_ids_ordered[current_index + 1]
        st.session_state.review_submission_id = new_id
        set_review_current_submission_id(new_id)
    st.session_state.review_nav_action = None
    st.rerun()

# ==================== SUBMISSION SELECTOR ====================
# Resolve which submission to display
current_id = st.session_state.review_submission_id
if current_id is None or current_id not in id_to_label_map:
    # Try to load from DB
    saved_id = get_review_current_submission_id()
    if saved_id and saved_id in id_to_label_map:
        current_id = saved_id
    else:
        current_id = submission_ids_ordered[0]

current_label = id_to_label_map[current_id]
current_index = submission_ids_ordered.index(current_id)

# Display the selectbox
selected_label = st.sidebar.selectbox(
    "Wähle eine Abgabe",
    options=submission_labels,
    index=submission_labels.index(current_label) if current_label in submission_labels else 0,
    key=selectbox_key
)

# Update if selection changed
if selected_label != current_label:
    submission_id = submission_id_map[selected_label]
    st.session_state.review_submission_id = submission_id
    set_review_current_submission_id(submission_id)
    st.rerun()

# WICHTIG: Setze review_submission_id NACH der Selectbox, nicht davor!
st.session_state.review_submission_id = current_id

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

# Load feedback
feedback = get_feedback(submission_id)

# Create two columns
col1, col2 = st.columns(2)

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
                            resolution_boost=3,
                            width="100%",
                            height=800,
                            render_text=True,
                        
                        
                            )
                    except Exception as e:
                        st.error(f"Fehler beim Anzeigen der PDF: {e}")
        else:
            st.info("Keine PDFs in dieser Abgabe gefunden.")
    else:
        st.error(f"Abgabepfad nicht gefunden: {submission_path}")

with col2:
    st.subheader("Feedback & Benotung")
    
    if feedback:
        points, markdown_content = feedback
        st.write(f"**Punkte:** {points}")
        st.markdown("### Feedback")
        st.markdown(markdown_content)
        
        # Look for feedback PDF
        feedback_pdf_dir = Path(submission_path).parent / "feedback"
        if feedback_pdf_dir.exists():
            pdf_files = list(feedback_pdf_dir.glob("*.pdf"))
            if pdf_files:
                st.write("**Feedback PDF:**")
                for pdf_file in pdf_files:
                    try:
                        pdf_viewer(str(pdf_file))
                    except Exception as e:
                        st.error(f"Fehler beim Anzeigen der Feedback-PDF: {e}")
    else:
        st.info("Kein Feedback für diese Abgabe verfügbar.")
