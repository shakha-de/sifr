from pathlib import Path

import streamlit as st
from streamlit_pdf_viewer import pdf_viewer

from utils import find_pdfs_in_submission
from db import get_submissions, get_feedback


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