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

@st.cache_data
def load_csv_data(path: Path, mtime: float):
    # mtime is passed just to invalidate cache on file change
    try:
        df = pd.read_csv(path)
        # Clean column names
        df.columns = df.columns.str.replace('^#\s*', '', regex=True).str.strip()
        return df
    except Exception as e:
        return None

# Load the CSV
try:
    current_mtime = marks_path.stat().st_mtime
    df = load_csv_data(marks_path, current_mtime)
    
    if df is None:
        st.error(f"Error loading CSV from {marks_path}")
        st.stop()
        
    st.subheader("CSV Editor")
    edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

    st.divider()
    st.subheader("📊 Statistiken")
    
    if "points" in edited_df.columns:
        # Convert to numeric, coercing errors
        points_series = pd.to_numeric(edited_df["points"], errors="coerce").dropna()
        
        stat_col1, stat_col2 = st.columns([2, 1], gap="large")
        
        with stat_col1:
            st.markdown("#### Punkteverteilung")
            if not points_series.empty:
                # Metrics Row
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Durchschnitt", f"{points_series.mean():.2f}")
                m2.metric("Median", f"{points_series.median():.2f}")
                m3.metric("Min", f"{points_series.min():.2f}")
                m4.metric("Max", f"{points_series.max():.2f}")
                
                # Bar Chart
                chart = alt.Chart(edited_df).mark_bar().encode(
                    x=alt.X("points", bin=alt.Bin(maxbins=20), title="Punkte"),
                    y=alt.Y("count()", title="Anzahl Abgaben"),
                    tooltip=["count()", alt.Tooltip("points", bin=True, title="Punktebereich")]
                ).interactive().properties(height=300)
                st.altair_chart(chart, use_container_width=True)
            else:
                st.info("Keine numerischen Punkte vorhanden.")

        with stat_col2:
            st.markdown("#### Status")
            if "status" in edited_df.columns:
                status_counts = edited_df["status"].value_counts().reset_index()
                status_counts.columns = ["status", "count"]
                
                status_chart = alt.Chart(status_counts).mark_arc(innerRadius=50).encode(
                    theta="count",
                    color=alt.Color("status", legend=alt.Legend(title="Status")),
                    tooltip=["status", "count"]
                ).properties(height=300)
                st.altair_chart(status_chart, use_container_width=True)
            else:
                st.warning("Keine 'status' Spalte gefunden.")
                
    else:
        st.warning("Spalte 'points' nicht gefunden. Bitte überprüfen Sie die CSV-Kopfzeile.")

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