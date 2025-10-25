import sqlite3
import os
import csv
from pathlib import Path

try:
    from app.config import get_data_dir
except ImportError:  # Falls Modul direkt gestartet wird
    from config import get_data_dir


DB_PATH = get_data_dir() /"db/intern/corrections.db"


def _resolve_db_path() -> Path:
    return Path(DB_PATH)


def init_db():
    db_path = _resolve_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Table for submissions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE,
            group_name TEXT,
            exercise TEXT,
            status TEXT DEFAULT 'not_started'
        )
    ''')
    
    # Add name column if not exists
    try:
        cursor.execute('ALTER TABLE submissions ADD COLUMN name TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    # Table for feedback
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY,
            submission_id INTEGER,
            points REAL,
            markdown_content TEXT,
            pdf_path TEXT,
            FOREIGN KEY (submission_id) REFERENCES submissions (id)
        )
    ''')
    
    # Table for error codes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS error_codes (
            id INTEGER PRIMARY KEY,
            code TEXT UNIQUE,
            description TEXT,
            abzug_punkte REAL DEFAULT 0.0,
            kommentar TEXT
        )
    ''')
    
    # Add columns if not exist
    try:
        cursor.execute('ALTER TABLE error_codes ADD COLUMN abzug_punkte REAL DEFAULT 0.0')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE error_codes ADD COLUMN kommentar TEXT')
    except sqlite3.OperationalError:
        pass
    
    # Table for exercise max points
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS exercise_max_points (
            exercise TEXT PRIMARY KEY,
            max_points REAL
        )
    ''')
    
    # Insert default error codes
    default_errors = [
        ('E001', 'Syntaxfehler', 0.5, 'Es gibt einen Syntaxfehler im Code.'),
        ('E002', 'Logikfehler', 1.0, 'Die Logik der Lösung ist fehlerhaft.'),
        ('E003', 'Unvollständige Lösung', 0.5, 'Die Lösung ist nicht vollständig.'),
        ('E004', 'Falsche Berechnung', 0.5, 'Eine Berechnung ist falsch.'),
        ('E005', 'Fehlende Dokumentation', 0.5, 'Die Dokumentation fehlt oder ist unzureichend.'),
    ]
    cursor.executemany('INSERT OR IGNORE INTO error_codes (code, description, abzug_punkte, kommentar) VALUES (?, ?, ?, ?)', default_errors)
    
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