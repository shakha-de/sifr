import csv
import os
from pathlib import Path
import sqlite3

from config import get_data_dir


DB_PATH = get_data_dir() /"db/intern/grading.db"


def _resolve_db_path() -> Path:
    return Path(DB_PATH)


def init_db():
    db_path = _resolve_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Table for sheets
    cursor.execute('''
            CREATE TABLE IF NOT EXISTS sheets  (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,        -- z.B. "Sheet-Blatt 1"
                description TEXT,
                release_date TEXT,                -- ISO date string
                created_at TEXT DEFAULT (datetime('now'))
        )
    ''')
    
    # Table for exercises per Sheet
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS exercises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sheet_id INTEGER NOT NULL REFERENCES sheets(id) ON DELETE CASCADE,
            code TEXT NOT NULL,               -- z.B. "Exercise-1" oder "1.1"
            title TEXT,
            max_points REAL NOT NULL DEFAULT 0.0,
            UNIQUE(sheet_id, code)
)
    ''')
    
    # Table for error codes per Sheet
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS error_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sheet_id INTEGER NOT NULL REFERENCES sheets(id) ON DELETE CASCADE,
            code TEXT NOT NULL,               
            description TEXT,
            deduction REAL NOT NULL DEFAULT 0.0,
            comment TEXT,
            UNIQUE(sheet_id, code)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_id TEXT,
            sheet_id INTEGER NOT NULL REFERENCES sheets(id) ON DELETE CASCADE,
            exercise_id INTEGER REFERENCES exercises(id) ON DELETE SET NULL,
            group_name TEXT,
            submitter TEXT,
            path TEXT,
            status TEXT NOT NULL DEFAULT 'NOT_STARTED',
            submitted_at TEXT,
            file_count INTEGER DEFAULT 0,
            file_hash TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            CHECK (status IN ('SUBMITTED', 'PROVISIONAL_MARK', 'FINAL_MARK', 'RESUBMITTED', 'ABSEND', 'SICK'))
        )    
    ''')

    # Table for single files of submissions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
            filename TEXT NOT NULL,
            relative_path TEXT,     
            size_bytes INTEGER,
            mime_type TEXT,
            uploaded_at TEXT DEFAULT (datetime('now'))
        )
    ''')

    # Table for feedbacks
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
            sheet_id INTEGER NOT NULL REFERENCES sheets(id) ON DELETE CASCADE, -- redundanz für schnelles Filtern
            exercise_id INTEGER REFERENCES exercises(id) ON DELETE SET NULL,
            grader TEXT,                 -- wer bewertet hat
            points REAL,                 -- erreichte Punkte (kann NULL sein, wenn noch offen)
            markdown_content TEXT,
            pdf_path TEXT,               -- Pfad zur erzeugten Feedback-PDF
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT
        )
    ''')

    # Table for errors in feedbacks
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS feedback_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feedback_id INTEGER NOT NULL REFERENCES feedback(id) ON DELETE CASCADE,
            error_code_id INTEGER NOT NULL REFERENCES error_codes(id) ON DELETE CASCADE,
            count INTEGER NOT NULL DEFAULT 1,
            comment TEXT
        )
    ''')

    # Table for saving history of feedbacks
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS feedback_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feedback_id INTEGER NOT NULL REFERENCES feedback(id) ON DELETE CASCADE,
            grader TEXT,
            points REAL,
            markdown_content TEXT,
            pdf_path TEXT,
            changed_at TEXT DEFAULT (datetime('now'))
        )
    ''')

    # Table for saving grader state (which submission is currently being worked on)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS grader_state (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    ''')

    # Indexes 
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_submissions_sheet_ex ON submissions(sheet_id, exercise_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_submission ON files(submission_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_submission ON feedback(submission_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_error_codes_sheet ON error_codes(sheet_id)")
    
    conn.commit()
    conn.close()

def load_names_from_csv(csv_path):
    names = {}
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f, delimiter=',', fieldnames=['submissionid', 'group', 'sheet', 'exercise', 'points', 'status'])
        next(reader)  # Skip the header line with #
        for row in reader:
            submissionid = row['submissionid']
            group = row['group']
            names[submissionid] = group
    return names

def scan_and_insert_submissions(root_dir):
    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    
    # Get sheet_id from root_dir name
    sheet_name = os.path.basename(root_dir)
    cursor.execute('SELECT id FROM sheets WHERE name = ?', (sheet_name,))
    sheet_row = cursor.fetchone()
    if not sheet_row:
        # Insert new sheet if not exists
        cursor.execute('INSERT INTO sheets (name) VALUES (?)', (sheet_name,))
        sheet_id = cursor.lastrowid
    else:
        sheet_id = sheet_row[0]
    
    # Remember current submission status per path to preserve correction progress
    cursor.execute('SELECT path, status FROM submissions WHERE sheet_id = ?', (sheet_id,))
    existing_status_by_path = {row[0]: row[1] for row in cursor.fetchall()}
    
    csv_path = os.path.join(root_dir, 'marks.csv')
    names = load_names_from_csv(csv_path) if os.path.exists(csv_path) else {}
    
    discovered_paths = set()

    for exercise_dir in os.listdir(root_dir):
        exercise_path = os.path.join(root_dir, exercise_dir)
        if os.path.isdir(exercise_path) and exercise_dir.lower().startswith(('excercise-', 'exercise-')):
            exercise_code = exercise_dir
            # Get exercise_id
            cursor.execute('SELECT id FROM exercises WHERE sheet_id = ? AND code = ?', (sheet_id, exercise_code))
            exercise_row = cursor.fetchone()
            if not exercise_row:
                # Insert new exercise if not exists
                cursor.execute('INSERT INTO exercises (sheet_id, code) VALUES (?, ?)', (sheet_id, exercise_code))
                exercise_id = cursor.lastrowid
            else:
                exercise_id = exercise_row[0]
            for submission_dir in os.listdir(exercise_path):
                submission_path = os.path.join(exercise_path, submission_dir)
                if os.path.isdir(submission_path):
                    # Extract submissionid from folder name (last part after last underscore)
                    parts = submission_dir.split('_')
                    submissionid = parts[-1] if parts else submission_dir
                    submitter = names.get(submissionid, submission_dir)
                    status = existing_status_by_path.get(submission_path, 'not_started')
                    
                    # Check if submission already exists
                    cursor.execute('SELECT id FROM submissions WHERE path = ?', (submission_path,))
                    existing = cursor.fetchone()
                    
                    if existing:
                        # Update existing submission
                        cursor.execute(
                            '''UPDATE submissions SET
                                group_name = ?, submitter = ?, sheet_id = ?, exercise_id = ?, status = ?
                                WHERE path = ?''',
                            (submission_dir, submitter, sheet_id, exercise_id, status, submission_path)
                        )
                    else:
                        # Insert new submission
                        cursor.execute(
                            '''INSERT INTO submissions (path, group_name, submitter, sheet_id, exercise_id, status)
                            VALUES (?, ?, ?, ?, ?, ?)''',
                            (submission_path, submission_dir, submitter, sheet_id, exercise_id, status)
                        )
                    discovered_paths.add(submission_path)

    # Remove submissions that no longer exist on disk
    obsolete_paths = set(existing_status_by_path.keys()) - discovered_paths
    if obsolete_paths:
        cursor.executemany('DELETE FROM submissions WHERE path = ?', [(path,) for path in obsolete_paths])
    
    conn.commit()
    conn.close()

def get_submissions():
    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    cursor.execute('''
        SELECT s.id, s.path, s.group_name, s.submitter, e.code, s.status
        FROM submissions s
        JOIN exercises e ON s.exercise_id = e.id
    ''')
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_feedback(submission_id):
    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    cursor.execute('SELECT points, markdown_content FROM feedback WHERE submission_id = ?', (submission_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def save_feedback(submission_id, points, markdown_content, pdf_path):
    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    
    # Get sheet_id and exercise_id from submission
    cursor.execute('SELECT sheet_id, exercise_id FROM submissions WHERE id = ?', (submission_id,))
    submission_data = cursor.fetchone()
    if not submission_data:
        conn.close()
        raise ValueError(f"Submission with id {submission_id} not found")
    
    sheet_id, exercise_id = submission_data
    
    # Insert or update feedback with all required fields
    cursor.execute('''
        INSERT OR REPLACE INTO feedback (submission_id, sheet_id, exercise_id, points, markdown_content, pdf_path)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (submission_id, sheet_id, exercise_id, points, markdown_content, pdf_path))
    
    cursor.execute('UPDATE submissions SET status = ? WHERE id = ?', ('graded', submission_id))
    conn.commit()
    conn.close()

def get_error_codes():
    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    cursor.execute('SELECT code, description, deduction, comment FROM error_codes')
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_exercise_max_points():
    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    cursor.execute('SELECT code, max_points FROM exercises')
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}

def save_exercise_max_points(exercise, max_points):
    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO exercise_max_points (exercise, max_points) VALUES (?, ?)',
                   (exercise, max_points))
    conn.commit()
    conn.close()

def add_error_code(code, description, deduction, comment):
    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    cursor.execute('INSERT INTO error_codes (code, description, deduction, comment) VALUES (?, ?, ?, ?)',
                   (code, description, deduction, comment))
    conn.commit()
    conn.close()

def delete_error_code(code):
    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    cursor.execute('DELETE FROM error_codes WHERE code = ?', (code,))
    conn.commit()
    conn.close()

def save_grader_state(key, value):
    """Save a key-value pair in the grader_state table."""
    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO grader_state (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

def load_grader_state(key, default=None):
    """Load a value from the grader_state table by key."""
    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM grader_state WHERE key = ?', (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default

def delete_grader_state(key):
    """Delete a key-value pair from the grader_state table."""
    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    cursor.execute('DELETE FROM grader_state WHERE key = ?', (key,))
    conn.commit()
    conn.close()