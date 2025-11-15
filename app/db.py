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
            status TEXT NOT NULL DEFAULT 'SUBMITTED',
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

    # Table for saving a path to the answer sheet of a current sheet
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS answer_sheets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sheet_id INTEGER NOT NULL REFERENCES sheets(id),
            path_to_file TEXT NOT NULL
        )
    ''')

    # Indexes 
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_submissions_sheet_ex ON submissions(sheet_id, exercise_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_submission ON files(submission_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_submission ON feedback(submission_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_error_codes_sheet ON error_codes(sheet_id)")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_answer_sheets_sheet_id ON answer_sheets(sheet_id)")

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
                    status = existing_status_by_path.get(submission_path, 'SUBMITTED')
                    
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

def get_submissions(exercise_code: str | None = None):
    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    query = '''
        SELECT s.id, s.path, s.group_name, s.submitter, e.code, s.status
        FROM submissions s
        JOIN exercises e ON s.exercise_id = e.id
    '''
    params: tuple = ()
    if exercise_code:
        query += ' WHERE e.code = ?'
        params = (exercise_code,)
    query += ' ORDER BY s.id'
    cursor.execute(query, params)
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


def get_feedback_submission_ids() -> set[int]:
    """Return all submission IDs that already have feedback entries."""

    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT submission_id FROM feedback')
    rows = cursor.fetchall()
    conn.close()
    return {row[0] for row in rows}


def get_answer_sheet_path(sheet_id: int) -> str | None:
    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    cursor.execute('SELECT path_to_file FROM answer_sheets WHERE sheet_id = ?', (sheet_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def save_feedback_with_submission(
    submission_id: int,
    status: str,
    points: float,
    markdown_content: str,
    pdf_path: str | None,
):
    """Persist feedback data and synchronize submission status in one transaction."""

    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()

    cursor.execute('SELECT sheet_id, exercise_id FROM submissions WHERE id = ?', (submission_id,))
    submission_data = cursor.fetchone()
    if not submission_data:
        conn.close()
        raise ValueError(f"Submission with id {submission_id} not found")

    sheet_id, exercise_id = submission_data

    cursor.execute('SELECT id FROM feedback WHERE submission_id = ?', (submission_id,))
    feedback_exists = cursor.fetchone() is not None

    if feedback_exists:
        cursor.execute(
            '''
            UPDATE feedback
            SET sheet_id = ?,
                exercise_id = ?,
                points = ?,
                markdown_content = ?,
                pdf_path = ?,
                updated_at = datetime('now')
            WHERE submission_id = ?
            ''',
            (sheet_id, exercise_id, points, markdown_content, pdf_path, submission_id),
        )
    else:
        cursor.execute(
            '''
            INSERT INTO feedback (submission_id, sheet_id, exercise_id, points, markdown_content, pdf_path)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (submission_id, sheet_id, exercise_id, points, markdown_content, pdf_path),
        )

    cursor.execute(
        '''
        UPDATE submissions
        SET status = ?
        WHERE id = ?
        ''',
        (status, submission_id),
    )

    conn.commit()
    conn.close()


def save_answer_sheet_path(sheet_id: int, file_path: str) -> None:
    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    cursor.execute(
        '''
        INSERT INTO answer_sheets (sheet_id, path_to_file)
        VALUES (?, ?)
        ON CONFLICT(sheet_id) DO UPDATE SET path_to_file = excluded.path_to_file
        ''',
        (sheet_id, file_path),
    )
    conn.commit()
    conn.close()


def delete_answer_sheet_path(sheet_id: int) -> None:
    """Remove the stored answer sheet entry for the given sheet."""

    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    cursor.execute(
        'DELETE FROM answer_sheets WHERE sheet_id = ?',
        (sheet_id,),
    )
    conn.commit()
    conn.close()

def get_sheets():
    """Return all stored sheets ordered by name."""
    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM sheets ORDER BY name COLLATE NOCASE')
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_sheet_id_by_name(sheet_name: str) -> int | None:
    """Return the sheet id for the given name, or None if it does not exist."""
    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM sheets WHERE name = ?', (sheet_name,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def get_error_codes(sheet_id: int | None = None):
    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    if sheet_id is None:
        cursor.execute('SELECT code, description, deduction, comment FROM error_codes ORDER BY code COLLATE NOCASE')
    else:
        cursor.execute(
            'SELECT code, description, deduction, comment FROM error_codes WHERE sheet_id = ? ORDER BY code COLLATE NOCASE',
            (sheet_id,)
        )
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
    # Update max_points in exercises table (exercise code is stored in 'code' column)
    cursor.execute('UPDATE exercises SET max_points = ? WHERE code = ?',
                   (max_points, exercise))
    conn.commit()
    conn.close()

def add_error_code(sheet_id, code, description, deduction, comment):
    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO error_codes (sheet_id, code, description, deduction, comment) VALUES (?, ?, ?, ?, ?)',
        (sheet_id, code, description, deduction, comment)
    )
    conn.commit()
    conn.close()

def delete_error_code(code, sheet_id: int | None = None):
    conn = sqlite3.connect(_resolve_db_path())
    cursor = conn.cursor()
    if sheet_id is None:
        cursor.execute('DELETE FROM error_codes WHERE code = ?', (code,))
    else:
        cursor.execute('DELETE FROM error_codes WHERE code = ? AND sheet_id = ?', (code, sheet_id))
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


_REVIEW_CURRENT_SUBMISSION_KEY = "review_current_submission_id"


def get_review_current_submission_id(default: int | None = None) -> int | None:
    """Return the currently stored submission id for the review page."""
    value = load_grader_state(_REVIEW_CURRENT_SUBMISSION_KEY)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def set_review_current_submission_id(submission_id: int) -> None:
    """Persist the given submission id for the review page."""
    save_grader_state(_REVIEW_CURRENT_SUBMISSION_KEY, str(int(submission_id)))


def get_review_submission_ids(exercise_code: str | None = None) -> list[int]:
    """Return ordered submission ids matching the optional exercise filter."""
    return [row[0] for row in get_submissions(exercise_code)]


def step_review_current_submission(step: int, exercise_code: str | None = None) -> int:
    """Move the stored submission id by the given step within the filtered list.

    The movement is clamped to the available range and the resulting id is persisted.
    Returns the id after stepping.
    """
    ids = get_review_submission_ids(exercise_code)
    if not ids:
        raise ValueError("Keine Abgaben für den gewählten Filter vorhanden.")

    try:
        step_value = int(step)
    except (TypeError, ValueError):
        step_value = 0

    saved_id = get_review_current_submission_id()
    if saved_id in ids:
        current_index = ids.index(saved_id)
    else:
        current_index = 0 if step_value >= 0 else len(ids) - 1

    new_index = current_index + step_value
    if new_index < 0:
        new_index = 0
    elif new_index >= len(ids):
        new_index = len(ids) - 1

    new_id = ids[new_index]
    set_review_current_submission_id(new_id)
    return new_id


# ============================================================================
# Navigation Helper Functions for Streamlit Apps
# ============================================================================

def navigate_submissions(submissions_list: list, exercise_filter: str | None = None) -> tuple[list, dict, dict]:
    """
    Build navigation maps for submissions.
    
    Args:
        submissions_list: List of submission rows from get_submissions()
        exercise_filter: Optional exercise code to filter by
        
    Returns:
        Tuple of (filtered_ids, id_to_label_map, label_to_id_map)
    """
    # Filter submissions
    filtered = submissions_list
    if exercise_filter and exercise_filter != "Alle":
        filtered = [row for row in submissions_list if row[4] == exercise_filter]
    
    # Build maps
    id_to_label_map = {}
    label_to_id_map = {}
    submission_ids_ordered = []
    
    for row in filtered:
        submission_id = row[0]
        # row[3] is submitter name, row[4] is exercise_code, row[5] is status
        # Status "FINAL_MARK" oder "PROVISIONAL_MARK" bedeutet korrigiert
        status_flag = "✅" if row[5] in ['FINAL_MARK', 'PROVISIONAL_MARK'] else "⭕"
        label = f"{status_flag} {row[3]} ({row[4]})"
        
        id_to_label_map[submission_id] = label
        label_to_id_map[label] = submission_id
        submission_ids_ordered.append(submission_id)
    
    return submission_ids_ordered, id_to_label_map, label_to_id_map


def get_submission_index(submission_id: int, submission_ids_ordered: list) -> int:
    """Get the index of a submission in the ordered list."""
    try:
        return submission_ids_ordered.index(submission_id)
    except ValueError:
        return 0


def navigate_to_next(current_index: int, submission_ids_ordered: list) -> int | None:
    """Navigate to next submission, returns new ID or None if at end."""
    if current_index < len(submission_ids_ordered) - 1:
        return submission_ids_ordered[current_index + 1]
    return None


def navigate_to_prev(current_index: int, submission_ids_ordered: list) -> int | None:
    """Navigate to previous submission, returns new ID or None if at start."""
    if current_index > 0:
        return submission_ids_ordered[current_index - 1]
    return None