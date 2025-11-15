import csv
import os, sys
from pathlib import Path
from loguru import logger

import pypandoc


def find_pdfs_in_submission(submission_path):
    """Find all PDF files in the submission directory."""
    if not os.path.exists(submission_path):
        return []
    pdfs = []
    for file in os.listdir(submission_path):
        if file.lower().endswith('.pdf'):
            pdfs.append(os.path.join(submission_path, file))
    return pdfs

def generate_feedback_pdf(markdown_content, name, points, output_path, sheet_number, exercise_number):
    """Generate a PDF from markdown content using pandoc and xelatex.
    
    Args:
        markdown_content: The markdown feedback content
        name: Student/group name
        points: Points awarded
        output_path: Path where PDF should be saved
        sheet_number: Exercise sheet number
        exercise_number: Exercise number
        
    Returns:
        tuple: (success: bool, error_message: str or None)
    """
    markdown_content = (markdown_content or "").strip()
    points_display = _format_points(points) if isinstance(points, (int, float)) else str(points)

    full_md = f"""
# Bewertung von Übungsblatt {sheet_number}, Aufgabe {exercise_number}

**Name:** {name}  
**Erreichte Punktzahl:** **{points_display}**

---


$$\\underline{{\\textbf{{ANMERKUNGEN}}}}$$

{markdown_content or '_Keine Anmerkungen eingetragen._'}

---
"""

    temp_md_path = Path(output_path).with_suffix(".md")

    try:
        # Validate output directory exists
        output_dir = Path(output_path).parent
        if not output_dir.exists():
            error_msg = f"Output directory does not exist: {output_dir}"
            logger.error(error_msg)
            return False, error_msg
            
        # Write temporary markdown file
        try:
            temp_md_path.write_text(full_md, encoding="utf-8")
        except (IOError, OSError, PermissionError) as e:
            error_msg = f"Failed to write temporary markdown file: {e}"
            logger.error(error_msg)
            return False, error_msg
        
        # Convert to PDF using pandoc
        try:
            pypandoc.convert_file(
                str(temp_md_path),
                "pdf",
                outputfile=output_path,
                extra_args=[
                    "--pdf-engine=xelatex",
                    "-V",
                    "geometry:margin=2.5cm",
                    "-V",
                    "fontsize=12pt",
                    "-V",
                    "mainfont=DejaVuSerif",
                    "-V",
                    "monofont=DejaVuSansMono",
                ],
            )
        except RuntimeError as e:
            # Pandoc or LaTeX engine errors
            error_str = str(e).lower()
            if "pandoc" in error_str and "not found" in error_str:
                error_msg = "Pandoc is not installed or not found in PATH"
            elif "xelatex" in error_str or "latex" in error_str:
                error_msg = f"LaTeX engine error: {e}"
            else:
                error_msg = f"PDF conversion failed: {e}"
            logger.error(error_msg)
            temp_md_path.unlink(missing_ok=True)
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error during PDF conversion: {e}"
            logger.error(error_msg)
            temp_md_path.unlink(missing_ok=True)
            return False, error_msg
            
        # Clean up temporary file
        temp_md_path.unlink(missing_ok=True)
        logger.info(f"Successfully generated PDF: {output_path}")
        return True, None
        
    except Exception as e:
        # Catch-all for any unexpected errors
        error_msg = f"Unexpected error in generate_feedback_pdf: {e}"
        logger.error(error_msg)
        if temp_md_path.exists():
            temp_md_path.unlink(missing_ok=True)
        return False, error_msg


def _format_points(points: float) -> str:
    """Format points for CSV storage without trailing zeros."""
    text = f"{points:.2f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def update_marks_csv(root_dir: str | Path, submission_id: str, points: float, status: str = "FINAL_MARK") -> None:
    """Update points and status for a submission inside marks.csv."""
    marks_path = Path(root_dir) / "marks.csv"
    if not marks_path.exists():
        raise FileNotFoundError(f"marks.csv nicht gefunden unter {marks_path}")

    rows = []
    updated = False

    with marks_path.open("r", encoding="utf-8", newline="") as infile:
        reader = csv.reader(infile)
        rows = list(reader)

    for row in rows[1:]:
        if row and row[0] == submission_id:
            row[4] = _format_points(points)
            row[5] = status
            updated = True
            break

    if not updated:
        raise ValueError(f"Kein Eintrag für Submission-ID {submission_id} in marks.csv gefunden")

    with marks_path.open("w", encoding="utf-8", newline="") as outfile:
        writer = csv.writer(outfile)
        writer.writerows(rows)

def get_markdown_placeholder_text() -> str:
    str = """## Gesamtbewertung
Hier eine kurze Zusammenfassung...

## Detaillierte Kommentare
- **Stärken:** ...
- **Verbesserungsmöglichkeiten:** ...

## Spezifische Hinweise
- Punkt 1
- Punkt 2

*Verwende **fett** für wichtige Teile und *kursiv* für Betonungen.*"""
    return str

def patch_streamlit_html():
    import streamlit
    streamlit_dir = os.path.dirname(streamlit.__file__)
    index_path = os.path.join(streamlit_dir, "static", "index.html")

    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()

    if '<html lang="de">' not in content:
        content = content.replace("<html>", '<html lang="de">')

        with open(index_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info("✔ Streamlit HTML gepatcht: lang=de gesetzt")