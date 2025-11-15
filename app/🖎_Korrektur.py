import os
import tarfile
import re
from pathlib import Path
from typing import cast

import streamlit as st
from streamlit_pdf_viewer import pdf_viewer


from config import get_data_dir
from db import (
    get_error_codes,
    get_sheet_id_by_name,
    get_exercise_max_points,
    get_feedback,
    get_submissions,
    init_db,
    save_exercise_max_points,
    save_feedback_with_submission,
    get_answer_sheet_path,
    save_answer_sheet_path,
    delete_answer_sheet_path,
    scan_and_insert_submissions,
    save_grader_state,
    load_grader_state,
    navigate_submissions,
    get_submission_index,
    navigate_to_next,
    navigate_to_prev,
)
from utils import (
    find_pdfs_in_submission,
    generate_feedback_pdf,
    update_marks_csv,
    patch_streamlit_html,
    get_markdown_placeholder_text)
from helpers import (
    ErrorCode,
    SheetContext,
    SubmissionRecord,
    apply_error_codes,
    convert_submissions,
    resolve_sheet_context,
)
from korrektur_utils import (
    find_candidate_roots,
    build_exercise_options,
    filter_submissions,
)


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

patch_streamlit_html()


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
                    except Exception as error:  # pragma: no cover - UI feedback only
                        st.error(f"Fehler beim Entpacken: {error}")


def handle_root_selection() -> str | None:
    state = st.session_state
    available = state.available_roots
    if not available:
        st.sidebar.info("Bitte lade ein Archive, um zu starten.")
        return None

    current_root = state.current_root
    if not current_root or current_root not in available:
        current_root = available[0]
        state.current_root = current_root
        state.force_rescan = True

    current_root_index = available.index(current_root) if current_root in available else 0
    display_root = st.sidebar.selectbox(
        "Arbeitsordner wählen",
        options=available,
        format_func=lambda path: os.path.basename(path.rstrip(os.sep)) or path,
        index=current_root_index,
        key="root_selector",
    )

    if display_root != state.current_root:
        state.current_root = display_root
        state.pop("submission_selector", None)
        state.force_rescan = True

    return state.current_root


def maybe_rescan_current_root(current_root: str | None) -> None:
    state = st.session_state
    if current_root and (state.force_rescan or state.last_scanned_root != current_root):
        scan_and_insert_submissions(current_root)
        state.last_scanned_root = current_root
        state.force_rescan = False


def summarize_progress(submissions: list[SubmissionRecord]) -> None:
    total = len(submissions)
    corrected = sum(
        1 for record in submissions if record.status in ["FINAL_MARK", "PROVISIONAL_MARK"]
    )
    st.sidebar.write(f"Korrekturstand: {corrected}/{total}")
def render_exercise_filter(exercise_options: list[str]) -> str:
    saved_filter = load_grader_state("exercise_filter", "Alle")
    if saved_filter not in exercise_options:
        saved_filter = "Alle"

    if st.session_state.exercise_filter not in exercise_options:
        st.session_state.exercise_filter = saved_filter

    selected = st.sidebar.selectbox(
        "Aufgabe filtern",
        options=exercise_options,
        index=exercise_options.index(st.session_state.exercise_filter)
        if st.session_state.exercise_filter in exercise_options
        else 0,
        key="exercise_filter",
    )

    if selected != load_grader_state("exercise_filter", "Alle"):
        save_grader_state("exercise_filter", selected)
        st.session_state.exercise_filter = selected

    return selected
def fetch_error_codes(sheet_context: SheetContext | None) -> list[ErrorCode]:
    if not sheet_context or sheet_context.sheet_id is None:
        return []
    rows = get_error_codes(sheet_context.sheet_id)
    return [ErrorCode.from_row(row) for row in rows]


def render_error_code_section(
    submission_id: int,
    points_key: str,
    markdown_key: str,
    sheet_context: SheetContext | None,
):
    st.subheader("Fehlercodes")
    left_col_error, right_col_error = st.columns((7, 3), vertical_alignment="bottom")
    error_codes = fetch_error_codes(sheet_context)
    options = [code.as_option() for code in error_codes]
    if not options:
        st.info("Für diese Übungsserie sind noch keine Fehlercodes hinterlegt.")

    selected_errors = left_col_error.multiselect(
        "Häufige Fehler",
        options,
        key=f"error_codes_select_{submission_id}",
    )

    if right_col_error.button("Fehler anwenden", key=f"apply_errors_{submission_id}"):
        if not selected_errors:
            st.error("Bitte Fehler auswählen.")
            return

        updated_points, updated_markdown = apply_error_codes(
            selected_errors,
            error_codes,
            st.session_state[points_key],
            st.session_state[markdown_key],
        )
        st.session_state[f"pending_points_{submission_id}"] = updated_points
        st.session_state[f"pending_markdown_{submission_id}"] = updated_markdown
        st.success("Fehler angewendet!")
        st.rerun()


def render_meme_section(submission_id: int, markdown_key: str):
    st.subheader("Memes")
    left_col_meme, right_col_meme = st.columns((7, 3), vertical_alignment="bottom")
    meme_link = left_col_meme.text_input("Bild-Link eingeben", key=f"meme_link_{submission_id}")
    if right_col_meme.button("Add Meme", key=f"add_meme_btn_{submission_id}"):
        if meme_link:
            current_md = st.session_state[markdown_key]
            st.session_state[f"pending_markdown_{submission_id}"] = (
                current_md + f"\n\n$\\hfill$ ![]({meme_link}) $\\hfill$ "
            )
            st.success("Meme hinzugefügt!")
            st.rerun()
        else:
            st.error("Bitte einen Link eingeben.")


def render_answer_sheet_manager(sheet_context: SheetContext | None) -> None:
    with st.sidebar.expander("Lösungsblatt hinterlegen", expanded=False):
        if not sheet_context:
            st.info("Bitte wähle zuerst einen Arbeitsordner, um ein Lösungsblatt zu speichern.")
            return

        sheet_id = sheet_context.sheet_id
        if sheet_id is None:
            st.info(
                "Dieses Blatt ist noch nicht im System registriert. Scanne die Abgaben einmal, "
                "damit ein Lösungsblatt gespeichert werden kann."
            )
            return

        current_path = get_answer_sheet_path(sheet_id)
        if current_path:
            path_obj = Path(current_path)
            if path_obj.exists():
                st.success(f"Aktuell gespeichert: {path_obj.name}")
                st.caption(str(path_obj))
            else:
                st.warning("Verknüpftes Lösungsblatt wurde nicht gefunden. Bitte neu hochladen.")
                st.caption(current_path)
        else:
            st.info("Noch kein Lösungsblatt hinterlegt.")

        uploaded_file = st.file_uploader(
            "PDF auswählen",
            type=["pdf"],
            accept_multiple_files=False,
            key="answer_sheet_uploader",
        )

        col_save, col_remove = st.columns([3, 2])

        with col_save:
            if st.button("Speichern", key="answer_sheet_save_btn"):
                if uploaded_file is None:
                    st.warning("Bitte zuerst eine PDF auswählen.")
                else:
                    target_dir = Path(sheet_context.root_path)
                    target_dir.mkdir(parents=True, exist_ok=True)
                    target_path = target_dir / "answer_sheet.pdf"
                    uploaded_file.seek(0)
                    target_path.write_bytes(uploaded_file.read())
                    save_answer_sheet_path(sheet_id, str(target_path))
                    st.success("Lösungsblatt gespeichert und verknüpft.")
                    st.session_state["answer_sheet_saved_at"] = target_path.stat().st_mtime
                    st.rerun()

        with col_remove:
            remove_disabled = current_path is None
            if st.button(
                "Entfernen",
                key="answer_sheet_remove_btn",
                disabled=remove_disabled,
            ):
                if current_path:
                    Path(current_path).unlink(missing_ok=True)
                    delete_answer_sheet_path(sheet_id)
                    st.info("Lösungsblatt entfernt.")
                    st.rerun()


init_db()
ensure_session_defaults()

st.sidebar.title("Sifr")
render_archive_loader()
current_root = handle_root_selection()
maybe_rescan_current_root(current_root)
sheet_context = resolve_sheet_context(current_root, get_sheet_id_by_name)
render_answer_sheet_manager(sheet_context)

raw_submissions = get_submissions()
submissions = convert_submissions(raw_submissions)

if not submissions and st.session_state.archive_loaded:
    st.warning("Keine Submissions gefunden. Bitte Archive überprüfen.")

summarize_progress(submissions)
exercise_options = build_exercise_options(submissions)
selected_exercise = render_exercise_filter(exercise_options)
filtered_submissions = filter_submissions(submissions, selected_exercise)

submission_ids_ordered, id_to_label_map, label_to_id_map = navigate_submissions(
    raw_submissions,
    exercise_filter=selected_exercise,
)

if not submission_ids_ordered:
    st.sidebar.warning(
        "Keine Abgaben verfügbar. Bitte ein Archive hochladen oder den Filter anpassen."
    )
    st.info("Keine Abgaben für den aktuellen Filter. Passe die Auswahl an oder lade neue Daten.")
    st.stop()

st.sidebar.write("---")

if not st.session_state.submission_selector or (
    st.session_state.submission_selector not in id_to_label_map
):
    saved_id = load_grader_state("current_submission_id")
    candidate_id: int | None = None
    if saved_id:
        try:
            candidate_id = int(saved_id)
        except (ValueError, TypeError):
            candidate_id = None
    if candidate_id in id_to_label_map:
        st.session_state.submission_selector = candidate_id
    else:
        st.session_state.submission_selector = submission_ids_ordered[0]


def persist_selection(new_id: int) -> None:
    st.session_state.submission_selector = new_id
    save_grader_state("current_submission_id", str(new_id))


current_id = cast(int, st.session_state.submission_selector)
current_index = get_submission_index(current_id, submission_ids_ordered)

col_prev, col_next = st.sidebar.columns([1, 1])
with col_prev:
    if st.button("Letzte", key="nav_prev", use_container_width=True, disabled=current_index <= 0):
        previous_id = navigate_to_prev(current_index, submission_ids_ordered)
        if previous_id is not None:
            persist_selection(previous_id)
            st.rerun()

with col_next:
    if st.button(
        "Nächste",
        key="nav_next",
        type="primary",
        use_container_width=True,
        disabled=current_index >= len(submission_ids_ordered) - 1,
    ):
        next_id = navigate_to_next(current_index, submission_ids_ordered)
        if next_id is not None:
            persist_selection(next_id)
            st.rerun()

submission_labels = list(id_to_label_map.values())
current_label = id_to_label_map.get(current_id, submission_labels[0])
current_index_in_labels = submission_labels.index(current_label)

selectbox_key = (
    f"submission_select_{st.session_state.current_root}_"
    f"{st.session_state.exercise_filter}_{current_id}"
)


def on_submission_change():
    selected_label = st.session_state[selectbox_key]
    if selected_label in label_to_id_map:
        persist_selection(label_to_id_map[selected_label])


st.sidebar.selectbox(
    "Wähle eine Abgabe",
    options=submission_labels,
    index=current_index_in_labels,
    key=selectbox_key,
    on_change=on_submission_change,
)

current_id = cast(int, st.session_state.submission_selector)
submission_lookup = {record.id: record for record in filtered_submissions}
submission_record = submission_lookup.get(current_id)

if submission_record is None and filtered_submissions:
    submission_record = filtered_submissions[0]
    persist_selection(submission_record.id)

if submission_record is None:
    st.error("Für diesen Filter stehen keine Abgaben zur Verfügung.")
    st.stop()


def make_max_points_callback(exercise: str):
    def callback():
        key = f"max_points_{exercise}"
        if key in st.session_state:
            value = st.session_state[key]
            save_exercise_max_points(exercise, value)
            st.session_state.exercise_max_points[exercise] = value

    return callback


exercise_names = [name for name in exercise_options if name != "Alle"]
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

submission_id = submission_record.id
submission_path = submission_record.path
group_name = submission_record.group_name
submitter_name = submission_record.submitter
current_exercise_name = submission_record.exercise_code
points_key = f"points_input_{submission_id}"
markdown_key = f"markdown_area_new_{submission_id}"
status_key = f"status_select_{submission_id}"

feedback = get_feedback(submission_id)
max_points_default = float(st.session_state.exercise_max_points.get(current_exercise_name, 0.0))
initial_points = float(feedback[0]) if feedback else max_points_default
initial_points = max(0.0, initial_points)
initial_markdown = (feedback[1] or "") if feedback else ""

if points_key not in st.session_state:
    st.session_state[points_key] = initial_points
if markdown_key not in st.session_state:
    st.session_state[markdown_key] = initial_markdown

pending_points_key = f"pending_points_{submission_id}"
pending_markdown_key = f"pending_markdown_{submission_id}"
if pending_points_key in st.session_state:
    st.session_state[points_key] = st.session_state[pending_points_key]
    del st.session_state[pending_points_key]
if pending_markdown_key in st.session_state:
    st.session_state[markdown_key] = st.session_state[pending_markdown_key]
    del st.session_state[pending_markdown_key]

max_points_for_exercise = st.session_state.exercise_max_points.get(current_exercise_name)

left_col, right_col = st.columns([7, 3], gap="medium")

with left_col:
    st.markdown(f"### Abgabe von: {submitter_name}")
    pdfs = find_pdfs_in_submission(submission_path)
    if pdfs:
        for pdf in pdfs:
            if not os.path.basename(pdf).startswith("feedback_"):
                pdf_viewer(
                    pdf,
                    resolution_boost=3,
                    width="100%",
                    height=800,
                    render_text=True,
                    show_page_separator=False,
                    key=f"pdf_viewer_{submission_id}_{os.path.basename(pdf)}",
                )
    else:
        st.info("Keine PDFs gefunden.")

with right_col:
    st.header("Feedback")
    if max_points_for_exercise:
        st.caption(f"Maximale Punkte für {current_exercise_name}: {max_points_for_exercise:g}")

    points = st.number_input(
        "Punkte",
        min_value=0.0,
        step=0.5,
        key=points_key,
    )
    st.text_area(
        "Korrektur (Markdown)",
        height=350,
        key=markdown_key,
        placeholder=get_markdown_placeholder_text(),
    )

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

    render_error_code_section(submission_id, points_key, markdown_key, sheet_context)

    status_options = [
        "FINAL_MARK",
        "SUBMITTED",
        "PROVISIONAL_MARK",
        "RESUBMITTED",
        "ABSEND",
        "SICK",
    ]
    if status_key not in st.session_state:
        st.session_state[status_key] = "FINAL_MARK"
    current_status = st.session_state[status_key]
    if current_status not in status_options:
        current_status = "FINAL_MARK"
        st.session_state[status_key] = current_status
    status_index = status_options.index(current_status)
    st.selectbox(
        "Status wählen",
        options=status_options,
        index=status_index,
        key=status_key,
    )

    if show_meme:
        render_meme_section(submission_id, markdown_key)

    if st.button(
        "Feedback PDF generieren",
        key=f"generate_feedback_{submission_id}",
        type="primary",
    ):
        sheet_name = sheet_context.sheet_name if sheet_context else os.path.basename(str(current_root))
        sheet_match = re.search(r"\d+", sheet_name)
        sheet_number = sheet_match.group() if sheet_match else "unknown"
        exercise_match = re.search(r"\d+", current_exercise_name)
        exercise_number = exercise_match.group() if exercise_match else "unknown"

        output_pdf = os.path.join(submission_path, f"feedback_{group_name}.pdf")
        try:
            success, error_message = generate_feedback_pdf(
                st.session_state[markdown_key],
                submitter_name,
                st.session_state[points_key],
                output_pdf,
                sheet_number,
                exercise_number,
            )
            if success:
                status_to_save = st.session_state.get(status_key, "FINAL_MARK")
                points_to_save = st.session_state[points_key]

                save_feedback_with_submission(
                    submission_id,
                    status_to_save,
                    points_to_save,
                    st.session_state[markdown_key],
                    output_pdf,
                )

                submission_identifier = (
                    group_name.split("_")[-1] if "_" in group_name else group_name
                )

                if sheet_context:
                    try:
                        update_marks_csv(
                            sheet_context.root_path,
                            submission_identifier,
                            points_to_save,
                            status_to_save,
                        )
                        st.success(
                            f"Feedback PDF erstellt und marks.csv aktualisiert: {output_pdf}"
                        )
                        st.info(f"✓ Punkte: {points_to_save}, Status: {status_to_save}")
                    except Exception as csv_error:
                        st.warning(
                            "PDF erstellt, aber marks.csv konnte nicht aktualisiert werden: "
                            f"{csv_error}"
                        )
                        st.success(f"Feedback PDF erstellt: {output_pdf}")
                else:
                    st.success(f"Feedback PDF erstellt: {output_pdf}")
            else:
                st.error(f"Fehler beim Erstellen der PDF: {error_message or 'Unbekannter Fehler'}")
        except Exception as error:  # pragma: no cover - feedback for UI only
            st.exception(error)

