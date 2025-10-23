import os
import pypandoc
from pathlib import Path

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
    """Generate a PDF from markdown content with header."""
    # Create full markdown with header
    full_md = f"""
# Bewertung von Übungsblatt {sheet_number}, Aufgabe {exercise_number}

**Name:** {name}  
**Erreichte Punktzahl:** **{points}**


$$\\underline{{\\text{{ANMERKUNGEN}}}}$$

{markdown_content}

---
"""
    
    # Temporary markdown file
    temp_md = output_path.replace('.pdf', '.md')
    with open(temp_md, 'w', encoding='utf-8') as f:
        f.write(full_md)
    
    # Convert to PDF using pandoc
    try:
        pypandoc.convert_file(temp_md,
         'pdf',
          outputfile=output_path,
           extra_args=[
            '--pdf-engine=xelatex',
            '-V', 'geometry:margin=2.5cm',
            '-V', 'fontsize=12pt',
            '-V', 'colorlinks=true',
            '-V', 'mainfont=DejaVuSerif',
            '-V', 'monofont=DejaVuSansMono',
            ])
        os.remove(temp_md)  # Clean up
        return True
    except Exception as e:
        print(f"Error generating PDF: {e}")
        if os.path.exists(temp_md):
            os.remove(temp_md)
        return False