from pathlib import Path

import streamlit as st
from streamlit_pdf_viewer import pdf_viewer

from utils import find_pdfs_in_submission
from db import (
    get_submissions, 
    get_feedback, 
    load_grader_state, 
    save_grader_state
)


st.set_page_config(
    page_title="Sifr | Korrekturen überprüfen | Split view mode",
    page_icon="app/static/img/sifr_logo.png",
    layout="wide",
    initial_sidebar_state="auto",
    menu_items={
        "Get Help": "https://github.com/shakha-de/sifr",
        "Report a bug": "https://github.com/shakha-de/sifr/issues",
        "About": """# sifr - is a grading tool.  \
        based on [Streamlit](https://streamlit.io/) with Markdown & $\\LaTeX$ support.""",
    },
)

st.sidebar.info("Hier können Sie Ihre Korrekturen überprüfen.")

current_root = st.session_state.get("current_root")
if not current_root:
    st.error("Kein aktiver Ordner wurde gewählt. Bitte wählen sie einen Arbeitsordner zuerst.")
    st.stop()

# Initialize session state
if "review_submission_selector" not in st.session_state:
    st.session_state.review_submission_selector = None
if "review_exercise_filter" not in st.session_state:
    st.session_state.review_exercise_filter = "Alle"

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
    status_flag = "[✓]" if row[5] == "graded" else "[ ]"
    return f"{status_flag} {row[3]} ({row[4]})"

submission_labels = [build_submission_label(row) for row in filtered_submissions]

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

# Load last submission from DB
saved_submission_id = load_grader_state("review_current_submission_id")
current_selection = st.session_state.review_submission_selector

if not current_selection or current_selection not in submission_labels:
    if saved_submission_id:
        try:
            saved_id = int(saved_submission_id)
            for row in filtered_submissions:
                if row[0] == saved_id:
                    matching_label = next(
                        (label for label, id in submission_id_map.items() if id == saved_id),
                        None
                    )
                    if matching_label and matching_label in submission_labels:
                        st.session_state.review_submission_selector = matching_label
                        break
        except (ValueError, StopIteration):
            pass
    
    # Wenn immer noch keine Auswahl, verwende erste
    if not st.session_state.get("review_submission_selector") or st.session_state.review_submission_selector not in submission_labels:
        st.session_state.review_submission_selector = submission_labels[0]

# Submission selector
current_label = st.session_state.review_submission_selector if st.session_state.review_submission_selector in submission_labels else submission_labels[0]
current_index = submission_labels.index(current_label)

selected_label = st.sidebar.selectbox(
    "Wähle eine Abgabe",
    options=submission_labels,
    index=current_index,
    key=f"review_submission_select_{st.session_state.current_root}_{st.session_state.review_exercise_filter}"
)

# Update session state if selection changed and save to DB
if selected_label != st.session_state.review_submission_selector:
    st.session_state.review_submission_selector = selected_label
    submission_id = submission_id_map[selected_label]
    save_grader_state("review_current_submission_id", str(submission_id))
    st.rerun()

# Get current submission
submission_id = submission_id_map[selected_label]
submission_row = next(row for row in filtered_submissions if row[0] == submission_id)
submission_path = submission_row[1]
group_name = submission_row[2]
submitter = submission_row[3]
exercise_code = submission_row[4]


# Find current index by submission_id
current_submission_id = submission_id_map[selected_label]
current_index = submission_ids_ordered.index(current_submission_id)

if st.sidebar.button("Letzte", key="review_prev_btn", use_container_width=True, icon=":material/arrow_back:"):
    prev_index = (current_index - 1) % len(submission_ids_ordered)
    prev_submission_id = submission_ids_ordered[prev_index]
    prev_label = id_to_label_map[prev_submission_id]
    st.session_state.review_submission_selector = prev_label
    save_grader_state("review_current_submission_id", str(prev_submission_id))
    st.rerun()

_ , middle, _ = st.sidebar.columns(3)
middle.metric("Position", f"{current_index + 1}/{len(submission_ids_ordered)}")

if st.sidebar.button("Nächste", key="review_next_btn", use_container_width=True, icon=":material/arrow_forward:"):
    next_index = (current_index + 1) % len(submission_ids_ordered)
    next_submission_id = submission_ids_ordered[next_index]
    next_label = id_to_label_map[next_submission_id]
    st.session_state.review_submission_selector = next_label
    save_grader_state("review_current_submission_id", str(next_submission_id))
    st.rerun()

# Main content
st.title("Korrekturen überprüfen")
st.header(f"Abgabe: {group_name} - {exercise_code}")
st.subheader(f"Eingereicht von: {submitter}")

# Load feedback
feedback = get_feedback(submission_id)

# Create two columns
col1, col2 = st.columns(2)

with col1:
    st.subheader("Originalabgaben")
    
    # Find original submission files
    submission_path_obj = Path(submission_path)
    if submission_path_obj.exists():
        pdf_files = find_pdfs_in_submission(submission_path)
        if pdf_files:
            for pdf_file in pdf_files:
                st.write(f"📄 {pdf_file}")
                try:
                    pdf_viewer(str(pdf_file))
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