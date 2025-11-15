from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, MutableMapping, cast

try:
    from helpers import SheetContext
    from db import (
        delete_answer_sheet_path,
        get_answer_sheet_path,
        save_answer_sheet_path,
        load_grader_state,
        save_grader_state,
    )
except ImportError:  # pragma: no cover - fallback for package imports
    from .helpers import SheetContext
    from .db import (
        delete_answer_sheet_path,
        get_answer_sheet_path,
        save_answer_sheet_path,
        load_grader_state,
        save_grader_state,
    )


__all__ = [
    "AnswerSheetStatus",
    "resolve_answer_sheet_status",
    "save_uploaded_answer_sheet",
    "delete_answer_sheet",
    "render_answer_sheet_sidebar",
    "setup_answer_sheet_toggle",
]


_TARGET_FILENAME = "answer_sheet.pdf"


@dataclass(slots=True)
class AnswerSheetStatus:
    """Represents the stored answer sheet state for a sheet."""

    sheet_id: int | None
    root_path: str | None
    configured_path: Path | None
    exists_on_disk: bool

    @property
    def effective_path(self) -> Path | None:
        return self.configured_path if self.exists_on_disk else None

    @property
    def display_name(self) -> str | None:
        return self.configured_path.name if self.configured_path else None


def resolve_answer_sheet_status(sheet_context: SheetContext | None) -> AnswerSheetStatus:
    if not sheet_context or sheet_context.sheet_id is None:
        return AnswerSheetStatus(
            sheet_id=sheet_context.sheet_id if sheet_context else None,
            root_path=sheet_context.root_path if sheet_context else None,
            configured_path=None,
            exists_on_disk=False,
        )

    stored_path = get_answer_sheet_path(sheet_context.sheet_id)
    configured_path = Path(stored_path) if stored_path else None
    exists_on_disk = bool(configured_path and configured_path.exists())
    return AnswerSheetStatus(
        sheet_id=sheet_context.sheet_id,
        root_path=sheet_context.root_path,
        configured_path=configured_path,
        exists_on_disk=exists_on_disk,
    )


def save_uploaded_answer_sheet(
    sheet_context: SheetContext,
    uploaded_file: BinaryIO,
    target_name: str | None = None,
) -> AnswerSheetStatus:
    if not sheet_context or sheet_context.sheet_id is None:
        raise ValueError("Sheet context mit gültiger sheet_id wird benötigt.")

    target_dir = Path(sheet_context.root_path)
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = target_name or getattr(uploaded_file, "name", _TARGET_FILENAME) or _TARGET_FILENAME
    target_path = target_dir / filename

    data = _read_file_bytes(uploaded_file)
    target_path.write_bytes(data)
    save_answer_sheet_path(sheet_context.sheet_id, str(target_path))

    return resolve_answer_sheet_status(sheet_context)


def delete_answer_sheet(sheet_context: SheetContext) -> AnswerSheetStatus:
    if not sheet_context or sheet_context.sheet_id is None:
        raise ValueError("Sheet context mit gültiger sheet_id wird benötigt.")

    status = resolve_answer_sheet_status(sheet_context)
    if status.configured_path:
        status.configured_path.unlink(missing_ok=True)
    delete_answer_sheet_path(sheet_context.sheet_id)
    return resolve_answer_sheet_status(sheet_context)


def render_answer_sheet_sidebar(sheet_context: SheetContext | None) -> AnswerSheetStatus:
    import streamlit as st  # Imported lazily for easier testing of pure helpers

    status = resolve_answer_sheet_status(sheet_context)
    with st.sidebar.expander("Lösungsblatt hinterlegen", expanded=False):
        if not sheet_context:
            st.info("Bitte wähle zuerst einen Arbeitsordner, um ein Lösungsblatt zu speichern.")
            return status

        if sheet_context.sheet_id is None:
            st.info(
                "Dieses Blatt ist noch nicht im System registriert. Scanne die Abgaben einmal, "
                "damit ein Lösungsblatt gespeichert werden kann."
            )
            return status

        if status.configured_path:
            if status.exists_on_disk:
                st.success(f"Aktuell gespeichert: {status.configured_path.name}")
                st.caption(str(status.configured_path))
            else:
                st.warning("Verknüpftes Lösungsblatt wurde nicht gefunden. Bitte neu hochladen.")
                st.caption(str(status.configured_path))
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
                    try:
                        updated = save_uploaded_answer_sheet(sheet_context, uploaded_file, _TARGET_FILENAME)
                        st.success("Lösungsblatt gespeichert und verknüpft.")
                        if updated.configured_path and updated.configured_path.exists():
                            st.session_state["answer_sheet_saved_at"] = updated.configured_path.stat().st_mtime
                        st.rerun()
                    except Exception as error:  # pragma: no cover - user feedback only
                        st.error(f"Fehler beim Speichern des Lösungsblatts: {error}")

        with col_remove:
            remove_disabled = status.configured_path is None
            if st.button("Entfernen", key="answer_sheet_remove_btn", disabled=remove_disabled):
                try:
                    delete_answer_sheet(sheet_context)
                    st.info("Lösungsblatt entfernt.")
                    st.rerun()
                except Exception as error:  # pragma: no cover - user feedback only
                    st.error(f"Fehler beim Entfernen des Lösungsblatts: {error}")

    return status


def setup_answer_sheet_toggle(
    key_prefix: str,
    sheet_id: int | None,
    has_answer_sheet: bool,
    session_state: MutableMapping[str, bool] | None = None,
):
    mapping = session_state
    if mapping is None:
        import streamlit as st  # Imported lazily so tests can supply their own mapping

        mapping = cast(MutableMapping[str, bool], st.session_state)

    widget_key = f"{key_prefix}_show_answer_sheet_{sheet_id or 'unknown'}"
    storage_key = f"{key_prefix}_answer_sheet_pref_{sheet_id or 'unknown'}"
    saved_pref = load_grader_state(storage_key)
    default_value = _parse_bool(saved_pref, has_answer_sheet)

    if widget_key not in mapping:
        mapping[widget_key] = default_value
    elif not has_answer_sheet and mapping[widget_key]:
        mapping[widget_key] = False
        save_grader_state(storage_key, "false")

    def _on_change() -> None:
        save_grader_state(storage_key, "true" if mapping[widget_key] else "false")

    return widget_key, _on_change


def _read_file_bytes(uploaded_file: BinaryIO) -> bytes:
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)

    data = uploaded_file.read()
    if isinstance(data, str):
        data = data.encode("utf-8")
    return data


def _parse_bool(value: str | None, fallback: bool) -> bool:
    if value is None:
        return fallback
    return value.lower() in {"true", "1", "yes"}
