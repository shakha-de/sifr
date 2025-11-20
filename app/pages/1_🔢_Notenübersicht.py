import streamlit as st
import pandas as pd
from pathlib import Path
import io
import altair as alt

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
    st.subheader("CSV Editor")
    edited_df = st.data_editor(df, num_rows="dynamic")

    st.divider()
    st.subheader("Statistiken")
    
    if "points" in edited_df.columns:
        # Convert to numeric, coercing errors
        points_series = pd.to_numeric(edited_df["points"], errors="coerce").dropna()
        
        if not points_series.empty:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Durchschnitt", f"{points_series.mean():.2f}")
            col2.metric("Median", f"{points_series.median():.2f}")
            col3.metric("Min", f"{points_series.min():.2f}")
            col4.metric("Max", f"{points_series.max():.2f}")
            
            st.caption("Punkteverteilung")
            chart = alt.Chart(edited_df).mark_bar().encode(
                x=alt.X("points", bin=True, title="Punkte"),
                y=alt.Y("count()", title="Anzahl")
            ).interactive()
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("Keine numerischen Punkte gefunden.")
    else:
        st.warning("Spalte 'points' nicht gefunden.")

    st.divider()
    st.subheader("Export")
    
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        edited_df.to_excel(writer, index=False, sheet_name='Noten')
    
    st.download_button(
        label="Download als Excel",
        data=buffer.getvalue(),
        file_name="noten_export.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        icon=":material/download:"
    )

except Exception as e:
    st.error(f"Error loading CSV: {e}")
    st.stop()

left, right = st.columns(2, vertical_alignment="center")
if left.button("Save Changes", type="primary", icon=":material/save:"):
    try:
        edited_df.to_csv(marks_path, index=False)
        st.success("Changes saved successfully!")
    except Exception as e:
        st.error(f"Error saving CSV: {e}")

if right.button("Zurück zu Korrekturen", icon=":material/arrow_back:" ):
    st.switch_page("🖎_Korrektur.py")