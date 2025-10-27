import sqlite3
import os
import csv
from pathlib import Path
from config import get_data_dir


DB_PATH = get_data_dir() /"db/intern/corrections.db"


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
            status TEXT NOT NULL DEFAULT 'SUBMITTED',
            submitted_at TEXT,
            file_count INTEGER DEFAULT 0,
            file_hash TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            CHECK (status IN ('SUBMITTED', 'PROVISIONAL_MARK', 'FINAL_MARK'))
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

    # Table for persistant saving grader state
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS app_state (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    ''')

    # Indexes 
    cursor.execute("CREATE INDEX idx_submissions_sheet_ex ON submissions(sheet_id, exercise_id)")
    cursor.execute("CREATE INDEX idx_files_submission ON files(submission_id)")
    cursor.execute("CREATE INDEX idx_feedback_submission ON feedback(submission_id)")
    cursor.execute("CREATE INDEX idx_error_codes_sheet ON error_codes(sheet_id)")
    
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
    
    # Remember current submission status per path to preserve correction progress
    cursor.execute('SELECT path, status FROM submissions')
    existing_status_by_path = {row[0]: row[1] for row in cursor.fetchall()}
    
    csv_path = os.path.join(root_dir, 'marks.csv')
    names = load_names_from_csv(csv_path) if os.path.exists(csv_path) else {}
    
    discovered_paths = set()

    for exercise_dir in os.listdir(root_dir):
        exercise_path = os.path.join(root_dir, exercise_dir)
        if os.path.isdir(exercise_path) and exercise_dir.lower().startswith(('excercise-', 'exercise-')):
            exercise = exercise_dir
            for submission_dir in os.listdir(exercise_path):
                submission_path = os.path.join(exercise_path, submission_dir)
                if os.path.isdir(submission_path):
                    # Extract submissionid from folder name (last part after last underscore)
                    parts = submission_dir.split('_')
                    submissionid = parts[-1] if parts else submission_dir
                    name = names.get(submissionid, submission_dir)
                    status = existing_status_by_path.get(submission_path, 'not_started')
                    cursor.execute(
                        '''
                        INSERT INTO submissions (path, group_name, name, exercise, status)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(path) DO UPDATE SET
                            group_name = excluded.group_name,
                            name = excluded.name,
                            exercise = excluded.exercise,
                            status = excluded.status
                        ''',
                        (submission_path, submission_dir, name, exercise, status),
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
    cursor.execute('SELECT id, path, group_name, name, exercise, status FROM submissions')
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
    cursor.execute('INSERT OR REPLACE INTO feedback (submission_id, points, markdown_content, pdf_path) VALUES (?, ?, ?, ?)',
                   (submission_id, points, markdown_content, pdf_path))
    cursor.execute('UPDATE submissions SET status = ? WHERE id = ?', ('completed', submission_id))
    conn.commit()
    conn.close()

def get_error_codes():
    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    cursor.execute('SELECT code, description, abzug_punkte, kommentar FROM error_codes')
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_exercise_max_points():
    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    cursor.execute('SELECT exercise, max_points FROM exercise_max_points')
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

def add_error_code(code, description, abzug_punkte, kommentar):
    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    cursor.execute('INSERT INTO error_codes (code, description, abzug_punkte, kommentar) VALUES (?, ?, ?, ?)',
                   (code, description, abzug_punkte, kommentar))
    conn.commit()
    conn.close()

def delete_error_code(code):
    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    cursor.execute('DELETE FROM error_codes WHERE code = ?', (code,))
    conn.commit()
    conn.close()