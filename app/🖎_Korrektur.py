import os
import tarfile
import re
from pathlib import Path

import streamlit as st
from streamlit_pdf_viewer import pdf_viewer

try:
    from app.config import get_data_dir
    from app.db import (
        add_error_code,
        delete_error_code,
        get_error_codes,
        get_exercise_max_points,
        get_feedback,
        get_submissions,
        init_db,
        save_exercise_max_points,
        save_feedback,
        scan_and_insert_submissions,
        save_grader_state,
        load_grader_state,
        navigate_submissions,
        get_submission_index,
        navigate_to_next,
        navigate_to_prev,
    )
    from app.utils import find_pdfs_in_submission, generate_feedback_pdf, update_marks_csv
except ImportError:  # Fallback when running as a script inside the package folder
    from config import get_data_dir
    from db import (
        add_error_code,
        delete_error_code,
        get_error_codes,
        get_exercise_max_points,
        get_feedback,
        get_submissions,
        init_db,
        save_exercise_max_points,
        save_feedback,
        scan_and_insert_submissions,
        save_grader_state,
        load_grader_state,
        navigate_submissions,
        get_submission_index,
        navigate_to_next,
        navigate_to_prev,
    )
    from utils import find_pdfs_in_submission, generate_feedback_pdf, update_marks_csv


DATA_ROOT = get_data_dir()
DATA_ROOT.mkdir(parents=True, exist_ok=True)

st.set_page_config(
    page_title="Sifr | Korrektur | Feedback Dateien erstellen",
    page_icon="app/static/img/sifr_logo.png",
    layout="wide",
    initial_sidebar_state="auto",
    menu_items={
        "Get Help": 'https://github.com/shakha-de/sifr',
        'Report a bug': "https://github.com/shakha-de/sifr/issues",
        'About': """# sifr - is a grading tool.  based on [Streamlit](https://streamlit.io/) with Markdown & $\\LaTeX$ support."""
        }
    )


def find_candidate_roots(base_dir: os.PathLike[str] | str = DATA_ROOT) -> list[str]:
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
            entry.is_dir()
            and entry.name.lower().startswith(("excercise-", "exercise-"))
            for entry in entries
        )
        if has_marks or has_exercises:
            candidates.append(str(item_path.resolve()))
    return sorted(set(candidates))


# Initialize DB
init_db()

# Initialize session state
if "exercise_max_points" not in st.session_state:
    st.session_state.exercise_max_points = get_exercise_max_points()

if "archive_loaded" not in st.session_state:
    st.session_state.archive_loaded = False
if "available_roots" not in st.session_state:
    st.session_state.available_roots = find_candidate_roots(DATA_ROOT)
if "current_root" not in st.session_state:
    st.session_state.current_root = (
        st.session_state.available_roots[0] if st.session_state.available_roots else None
    )
if "last_scanned_root" not in st.session_state:
    st.session_state.last_scanned_root = None
if "force_rescan" not in st.session_state:
    st.session_state.force_rescan = False
if "submission_selector" not in st.session_state:
    st.session_state.submission_selector = None
if "exercise_filter" not in st.session_state:
    st.session_state.exercise_filter = "Alle"
if "nav_action" not in st.session_state:
    st.session_state.nav_action = None

# Initialize variables
submission_id = None
points = 0.0


# Sidebar
st.sidebar.title("Sifr")

# Archive laden
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
                    uploaded_file.seek(0)
                    with tarfile.open(fileobj=uploaded_file, mode="r:gz") as tar:
                        tar.extractall(str(DATA_ROOT), filter="data")
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
                except Exception as error:
                    st.error(f"Fehler beim Entpacken: {error}")

# Root-Auswahl
if st.session_state.available_roots:
    root_options = st.session_state.available_roots
    current_root = st.session_state.current_root
    if not current_root or current_root not in root_options:
        current_root = root_options[0]
        st.session_state.current_root = current_root
        st.session_state.force_rescan = True

    current_root_index = root_options.index(current_root) if current_root in root_options else 0
    display_root = st.sidebar.selectbox(
        "Arbeitsordner wählen",
        options=root_options,
        format_func=lambda path: os.path.basename(path.rstrip(os.sep)) or path,
        index=current_root_index,
        key="root_selector",
    )
    if display_root != st.session_state.current_root:
        st.session_state.current_root = display_root
        st.session_state.pop("submission_selector", None)
        st.session_state.force_rescan = True

else:
    st.sidebar.info("Bitte lade ein Archive, um zu starten.")

# Scan submissions if needed
current_root = st.session_state.current_root
if current_root and (
    st.session_state.force_rescan or st.session_state.last_scanned_root != current_root
):
    scan_and_insert_submissions(current_root)
    st.session_state.last_scanned_root = current_root
    st.session_state.force_rescan = False

# Load submissions
submissions = get_submissions()
if not submissions and st.session_state.get("archive_loaded"):
    st.warning("Keine Submissions gefunden. Bitte Archive überprüfen.")
total_submissions = len(submissions)
# Status "FINAL_MARK" oder "PROVISIONAL_MARK" bedeutet korrigiert
corrected = sum(1 for row in submissions if row[5] in ['FINAL_MARK', 'PROVISIONAL_MARK'])
st.sidebar.write(f"Korrekturstand: {corrected}/{total_submissions}")

# Filter by exercise
exercise_names = sorted({row[4] for row in submissions})
exercise_options = ["Alle"] + exercise_names if exercise_names else ["Alle"]

# Lade den letzten Filter aus der Datenbank
saved_exercise_filter = load_grader_state("exercise_filter", "Alle")
if saved_exercise_filter not in exercise_options:
    saved_exercise_filter = "Alle"

if st.session_state.exercise_filter not in exercise_options:
    st.session_state.exercise_filter = saved_exercise_filter

selected_exercise = st.sidebar.selectbox(
    "Aufgabe filtern",
    options=exercise_options,
    index=exercise_options.index(st.session_state.exercise_filter) if st.session_state.exercise_filter in exercise_options else 0,
    key="exercise_filter",
)

# Speichere den Filter wenn er sich ändert
if selected_exercise != load_grader_state("exercise_filter", "Alle"):
    save_grader_state("exercise_filter", selected_exercise)
    st.session_state.exercise_filter = selected_exercise

# Build filtered submissions list ONCE (wird mehrfach genutzt)
filtered_submissions = [
    row for row in submissions if selected_exercise == "Alle" or row[4] == selected_exercise
]

# Use new navigation helper
submission_ids_ordered, id_to_label_map, label_to_id_map = navigate_submissions(
    submissions, 
    exercise_filter=selected_exercise
)

# Prepare defaults so downstream widgets always have defined values
submission_row = None
submission_path = ""
group_name = ""
name = ""
current_exercise_name = ""
points_key = ""
markdown_key = ""

# Handle no submissions
if not submission_ids_ordered:
    st.sidebar.warning("Keine Abgaben verfügbar. Bitte ein Archive hochladen oder den Filter anpassen.")
else:
    # ==================== NAVIGATION BUTTONS ====================
    st.sidebar.write("---")
    
    # Resolve current submission ID - USE LAST SAVED STATE!
    # This is THE source of truth for what we're currently viewing
    if not st.session_state.submission_selector or st.session_state.submission_selector not in id_to_label_map:
        # Try to load from DB
        saved_id = load_grader_state("current_submission_id")
        if saved_id:
            try:
                candidate_id = int(saved_id)
                if candidate_id in id_to_label_map:
                    st.session_state.submission_selector = candidate_id
                else:
                    st.session_state.submission_selector = submission_ids_ordered[0]
            except (ValueError, TypeError):
                st.session_state.submission_selector = submission_ids_ordered[0]
        else:
            st.session_state.submission_selector = submission_ids_ordered[0]
    
    current_id = st.session_state.submission_selector
    current_index = get_submission_index(current_id, submission_ids_ordered)
    current_label = id_to_label_map.get(current_id, "")
    
    # Navigation buttons - DIRECTLY update submission_selector
    col_prev, col_next = st.sidebar.columns([1, 1])
    
    with col_prev:
        if st.button("Letzte", key="nav_prev", use_container_width=True, disabled=(current_index <= 0)):
            prev_id = navigate_to_prev(current_index, submission_ids_ordered)
            if prev_id:
                st.session_state.submission_selector = prev_id
                save_grader_state("current_submission_id", str(prev_id))
    
    with col_next:
        if st.button("Nächste",type="primary",  key="nav_next", use_container_width=True, disabled=(current_index >= len(submission_ids_ordered) - 1)):
            next_id = navigate_to_next(current_index, submission_ids_ordered)
            if next_id:
                st.session_state.submission_selector = next_id
                save_grader_state("current_submission_id", str(next_id))
    
    # ==================== SUBMISSION SELECTOR ====================
    st.sidebar.write("---")
    
    # Build list of labels and find current position
    submission_labels = list(id_to_label_map.values())
    
    # Get CURRENT selection state (might have been updated by buttons above!)
    current_id = st.session_state.submission_selector
    current_label = id_to_label_map.get(current_id, submission_labels[0] if submission_labels else "")
    current_index_in_labels = submission_labels.index(current_label) if current_label in submission_labels else 0
    
    # Force re-render of selectbox with dynamic key based on current_id
    # This ensures the index is recalculated each render
    selectbox_key = f"submission_select_{st.session_state.current_root}_{st.session_state.exercise_filter}_{current_id}"
    
    # Use on_change callback to handle selection
    def on_selectbox_change():
        # The selectbox value is always available via the dynamic key
        selected_label = st.session_state[selectbox_key]
        if selected_label in label_to_id_map:
            new_id = label_to_id_map[selected_label]
            st.session_state.submission_selector = new_id
            save_grader_state("current_submission_id", str(new_id))
    
    selected_label = st.sidebar.selectbox(
        "Wähle eine Abgabe",
        options=submission_labels,
        index=current_index_in_labels,
        key=selectbox_key,
        on_change=on_selectbox_change
    )
    
    # Get current submission data using the LATEST current_id
    current_id = st.session_state.submission_selector
    
    # WICHTIG: submission_row neu berechnen basierend auf aktueller current_id!
    submission_row = next((row for row in filtered_submissions if row[0] == current_id), None)
    
    # Initialize variables (WICHTIG: Außerhalb des if-Blocks!)
    submission_id = current_id  # ✅ Immer definieren!
    submission_path = ""
    group_name = ""
    name = ""
    current_exercise_name = ""
    points_key = f"points_input_{current_id}"  # ✅ IMMER einen gültigen Key setzen!
    markdown_key = f"markdown_area_new_{current_id}"  # ✅ IMMER einen gültigen Key setzen!
    
    if submission_row:
        submission_path = submission_row[1]
        group_name = submission_row[2]
        name = submission_row[3]
        current_exercise_name = submission_row[4]
        submission_id = submission_row[0]
        points_key = f"points_input_{submission_id}"
        markdown_key = f"markdown_area_new_{submission_id}"

    # Initialize feedback state for this submission
    if "active_submission_id" not in st.session_state or st.session_state.active_submission_id != submission_id:
        feedback = get_feedback(submission_id)
        max_points_default = float(st.session_state.exercise_max_points.get(current_exercise_name, 0.0))
        st.session_state.active_submission_id = submission_id
        st.session_state.current_markdown = (feedback[1] or "") if feedback else ""
        st.session_state.current_points = float(feedback[0]) if feedback else max_points_default
        st.session_state.current_points = max(0.0, st.session_state.current_points)
        # Sync with widget inputs
        st.session_state["points_input"] = st.session_state.current_points
        st.session_state["markdown_area_new"] = st.session_state.current_markdown

    # Save max points callback (per exercise)
    def make_max_points_callback(exercise):
        def callback():
            key = f"max_points_{exercise}"
            if key in st.session_state:
                value = st.session_state[key]
                save_exercise_max_points(exercise, value)
                st.session_state.exercise_max_points[exercise] = value
        return callback

    # Settings sidebar
    with st.sidebar.expander("Einstellungen"):
        if exercise_names:
            st.write("Maximale Punkte pro Aufgabe")
            for exercise in exercise_names:
                key_name = f"max_points_{exercise}"
                default_value = float(st.session_state.exercise_max_points.get(exercise, 0.0))
                st.number_input(
                    exercise,
                    min_value=0.0,
                    value=default_value,
                    step=0.5,
                    key=key_name,
                    on_change=make_max_points_callback(exercise),
                )
        else:
            st.info("Keine Aufgaben gefunden. Bitte Archive laden.")

        show_meme = st.checkbox("Add Meme Menü anzeigen", value=True)

        render_mode_labels = {
            "Modern (Standard)": "unwrap",
            "Legacy IFrame": "legacy_iframe",
            "Legacy Embed": "legacy_embed",
        }
        default_label = st.session_state.get("pdf_render_mode_label", "Modern (Standard)")
        selected_label = st.selectbox(
            "PDF-Anzeige-Modus",
            options=list(render_mode_labels.keys()),
            index=list(render_mode_labels.keys()).index(default_label)
            if default_label in render_mode_labels
            else 0,
            help="Bei Darstellungsproblemen kann einer der Legacy-Modi helfen.",
        )
        st.session_state.pdf_render_mode_label = selected_label
        st.session_state.pdf_render_mode = render_mode_labels[selected_label]

    max_points_for_exercise = st.session_state.exercise_max_points.get(current_exercise_name)

    # Main area
    left_col, right_col = st.columns([7, 3], gap="large")

    with left_col:
        st.header(f"Abgabe von: {name}")
        st.caption(f"Ordner: {group_name}")
        pdfs = find_pdfs_in_submission(submission_path)
        if pdfs:
            for pdf in pdfs:
                st.markdown(f"**{os.path.basename(pdf)}**")
                pdf_viewer(
                    pdf,
                    zoom_level=1.60,
                    width="100%",
                    height=1200,
                    rendering=st.session_state.get("pdf_render_mode", "unwrap"),
                    key=f"pdf_viewer_{submission_id}_{os.path.basename(pdf)}",  # ✅ Eindeutiger Key
                )
        else:
            st.info("Keine PDFs gefunden.")

    with right_col:
        st.header("Feedback")
        
        # Nur anzeigen wenn submission_row existiert!
        if not submission_row:
            st.error("❌ Abgabe nicht gefunden. Bitte laden Sie ein Archive oder wählen Sie einen anderen Filter.")
        else:
            if max_points_for_exercise:
                st.caption(f"Maximale Punkte für {current_exercise_name}: {max_points_for_exercise}")

            # Lade Feedback-Daten für diese Abgabe
            feedback = get_feedback(submission_id)
            initial_points = float(feedback[0]) if feedback else float(max_points_for_exercise or 0.0)
            initial_points = max(0.0, initial_points)
            initial_markdown = (feedback[1] or "") if feedback else ""

            # Dynamische Keys pro Abgabe
            # WICHTIG: NUR beim ERSTEN Besuch initialisieren (wenn Key noch nicht existiert)!
            if points_key not in st.session_state:
                st.session_state[points_key] = initial_points
            if markdown_key not in st.session_state:
                st.session_state[markdown_key] = initial_markdown

            # Apply pending updates to session state before creating widgets
            if f"pending_points_{submission_id}" in st.session_state:
                st.session_state[points_key] = st.session_state[f"pending_points_{submission_id}"]
                del st.session_state[f"pending_points_{submission_id}"]
            if f"pending_markdown_{submission_id}" in st.session_state:
                st.session_state[markdown_key] = st.session_state[f"pending_markdown_{submission_id}"]
                del st.session_state[f"pending_markdown_{submission_id}"]

            # Widgets mit dynamischen Keys
            points = st.number_input(
            "Punkte",
            min_value=0.0,
            step=0.5,
            key=points_key,
        )
        markdown_input = st.text_area(
            "Korrektur (Markdown)",
            height=350,
            key=markdown_key,
            placeholder="""## Gesamtbewertung
Hier eine kurze Zusammenfassung...

## Detaillierte Kommentare
- **Stärken:** ...
- **Verbesserungsmöglichkeiten:** ...

## Spezifische Hinweise
- Punkt 1
- Punkt 2

*Verwende **fett** für wichtige Teile und *kursiv* für Betonungen.*"""
        )

        # Validierung
        if (
            max_points_for_exercise is not None
            and max_points_for_exercise > 0
            and points > max_points_for_exercise
        ):
            st.warning(
                "Die vergebenen Punkte ({}) überschreiten das Maximum von {} für {}.".format(
                    f"{points:g}",
                    f"{max_points_for_exercise:g}",
                    current_exercise_name,
                )
            )

        # Fehlercodes
        st.subheader("Fehlercodes")
        error_codes = get_error_codes()
        selected_errors = st.multiselect(
            "Häufige Fehler",
            [f"{code}: {desc} ({abzug} Punkte)" for code, desc, abzug, komm in error_codes],
            key=f"error_codes_select_{submission_id}",  # auch hier dynamisch!
        )

        if st.button("Fehler anwenden", key=f"apply_errors_{submission_id}"):
            if selected_errors:
                # Hole aktuellen Punktestand aus dem Widget-State
                current_points = st.session_state[points_key]
                current_markdown = st.session_state[markdown_key]

                for selected in selected_errors:
                    code = selected.split(":")[0].strip()
                    for ec in error_codes:
                        if ec[0] == code:
                            deduction = float(ec[2] or 0.0)
                            current_points = max(0.0, current_points - deduction)
                            comment = ec[3] or ""
                            if comment:
                                current_markdown += f"\n\n*{code}: -{deduction}P*\n{comment}"
                            break

                # Aktualisiere den Session State der Widgets
                st.session_state[f"pending_points_{submission_id}"] = current_points
                st.session_state[f"pending_markdown_{submission_id}"] = current_markdown
                st.success("Fehler angewendet!")
                st.rerun()
            else:
                st.error("Bitte Fehler auswählen.")

        # Status Dropdown
        st.subheader("Status & Abschluss")
        status_options = ['SUBMITTED', 'PROVISIONAL_MARK', 'FINAL_MARK', 'RESUBMITTED', 'ABSEND', 'SICK']
        
        # Lade aktuellen Status aus Datenbank
        current_status = submission_row[4] if submission_row and len(submission_row) > 4 else 'FINAL_MARK'
        try:
            status_index = status_options.index(current_status)
        except (ValueError, IndexError):
            status_index = 2  # Default: "FINAL_MARK"
        
        selected_status = st.selectbox(
            "Status wählen",
            options=status_options,
            index=status_index,
            key=f"status_select_{submission_id}"
        )

        # Meme
        if show_meme:
            st.subheader("Add Meme")
            meme_link = st.text_input("Bild-Link eingeben", key=f"meme_link_{submission_id}")
            if st.button("Add Meme", key=f"add_meme_btn_{submission_id}"):
                if meme_link:
                    current_md = st.session_state[markdown_key]
                    st.session_state[f"pending_markdown_{submission_id}"] = current_md + f"\n\n$\\hfill$ ![]({meme_link}) $\\hfill$ "
                    st.success("Meme hinzugefügt!")
                    st.rerun()
                else:
                    st.error("Bitte einen Link eingeben.")

        # PDF generieren
        if st.button("Feedback PDF generieren", key=f"generate_feedback_{submission_id}", type="primary"):
            sheet_name = os.path.basename(str(current_root))
            sheet_match = re.search(r'\d+', sheet_name)
            sheet_number = sheet_match.group() if sheet_match else "unknown"
            exercise_match = re.search(r'\d+', current_exercise_name)
            exercise_number = exercise_match.group() if exercise_match else "unknown"

            output_pdf = os.path.join(submission_path, f"feedback_{group_name}.pdf")
            try:
                if generate_feedback_pdf(
                    st.session_state[markdown_key],
                    name,
                    st.session_state[points_key],
                    output_pdf,
                    sheet_number,
                    exercise_number
                ):
                    # Hole Status aus Dropdown
                    status_to_save = st.session_state.get(f"status_select_{submission_id}", "graded")
                    points_to_save = st.session_state[points_key]
                    
                    # Speichere Feedback mit Status in Datenbank
                    save_feedback(submission_id, points_to_save, st.session_state[markdown_key], output_pdf)
                    
                    # Aktualisiere auch den Status in der submissions Tabelle
                    import sqlite3
                    from pathlib import Path
                    db_path = Path(get_data_dir()) / "db/intern/grading.db"
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute('UPDATE submissions SET status = ? WHERE id = ?', (status_to_save, submission_id))
                    conn.commit()
                    conn.close()
                    
                    # Aktualisiere marks.csv mit Punkte und Status
                    # Extrahiere submission_identifier aus group_name (letzter Teil nach underscore)
                    submission_identifier = group_name.split("_")[-1] if "_" in group_name else group_name
                    
                    if current_root:
                        try:
                            update_marks_csv(
                                current_root,
                                submission_identifier,
                                points_to_save,
                                status_to_save
                            )
                            st.success(f"Feedback PDF erstellt und marks.csv aktualisiert: {output_pdf}")
                            st.info(f"✓ Punkte: {points_to_save}, Status: {status_to_save}")
                        except Exception as csv_error:
                            st.warning(f"PDF erstellt, aber marks.csv konnte nicht aktualisiert werden: {csv_error}")
                            st.success(f"Feedback PDF erstellt: {output_pdf}")
                    else:
                        st.success(f"Feedback PDF erstellt: {output_pdf}")
                else:
                    st.error("Fehler beim Erstellen der PDF.")
            except Exception as e:
                st.exception(e)

# Fehlercodes verwalten
with st.expander("Fehlercodes verwalten"):
    st.write("Neuen Fehler hinzufügen:")
    new_code = st.text_input("Code", key="new_code")
    new_desc = st.text_input("Beschreibung", key="new_desc")
    new_abzug = st.number_input("Abzug Punkte", min_value=0.0, step=0.5, key="new_abzug")
    new_komm = st.text_area("Kommentar", key="new_komm")
    if st.button("Hinzufügen"):
        if new_code and new_desc:
            add_error_code(new_code, new_desc, new_abzug, new_komm)
            st.success("Fehler hinzugefügt!")
            st.rerun()
        else:
            st.error("Code und Beschreibung erforderlich.")

    st.write("Vorhandene Fehler:")
    for code, desc, abzug, komm in get_error_codes():
        col1, col2 = st.columns([4, 1])
        with col1:
            st.write(f"{code}: {desc} ({abzug} Punkte) - {komm}")
        with col2:
            if st.button(f"Löschen {code}", key=f"del_{code}"):
                delete_error_code(code)
                st.success(f"{code} gelöscht!")
                st.rerun()

st.sidebar.markdown("")