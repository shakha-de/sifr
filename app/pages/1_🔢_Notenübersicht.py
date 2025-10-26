import streamlit as st
import pandas as pd
from pathlib import Path

st.title("Notenübersicht")

st.set_page_config(
    page_title="Sifr | Notenübersicht | marks.csv bearbeiten",
    page_icon="app/static/img/sifr_logo.png",
    layout="wide",
    initial_sidebar_state="auto",
    menu_items={
        "Get Help": 'https://github.com/shakha-de/sifr',
        'Report a bug': "https://github.com/shakha-de/sifr/issues",
        'About': """# sifr - is a grading tool.  based on [Streamlit](https://streamlit.io/) with Markdown & $\\LaTeX$ support."""
        }
    )

current_root = st.session_state.get("current_root")
if not current_root:
    st.error("Kein aktiver Ordner wurde gewählt. Bitte wählen sie einen Arbeitsordner zuerst.")
    st.stop()

marks_path = Path(current_root) / "marks.csv"
if not marks_path.exists():
    st.error(f"marks.csv not found in {current_root}")
    st.stop()

# Load the CSV
try:
    df = pd.read_csv(marks_path)
    st.write("Current marks.csv:")
    st.dataframe(df)
except Exception as e:
    st.error(f"Error loading CSV: {e}")
    st.stop()

# Edit the dataframe
st.subheader("Edit the CSV")
edited_df = st.data_editor(df, num_rows="dynamic")

if st.button("Save Changes"):
    try:
        edited_df.to_csv(marks_path, index=False)
        st.success("Changes saved successfully!")
    except Exception as e:
        st.error(f"Error saving CSV: {e}")

if st.button("Back to Main"):
    st.switch_page("main_app.py")