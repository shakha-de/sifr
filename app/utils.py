import csv
import os
from pathlib import Path

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
    """Generate a PDF from markdown content using pandoc and xelatex."""
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
        temp_md_path.write_text(full_md, encoding="utf-8")
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
        temp_md_path.unlink(missing_ok=True)
        return True
    except Exception as e:
        print(f"Error generating PDF: {e}")
        if temp_md_path.exists():
            temp_md_path.unlink()
        return False


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