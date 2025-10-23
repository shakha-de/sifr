import os
import shutil
import sqlite3
import tarfile
import tempfile

import pytest

from app.db import (
    DB_PATH,
    get_error_codes,
    get_feedback,
    get_submissions,
    init_db,
    save_feedback,
    scan_and_insert_submissions,
)


@pytest.fixture
def setup_test_db():
    """Setup a temporary test database."""
    # Use a temporary database for testing
    test_db = 'test_corrections.db'
    if os.path.exists(test_db):
        os.remove(test_db)
    
    # Temporarily change DB_PATH
    from app import db as app_db

    original_db = app_db.DB_PATH
    app_db.DB_PATH = test_db
    
    init_db()
    yield test_db
    
    # Cleanup
    app_db.DB_PATH = original_db
    if os.path.exists(test_db):
        os.remove(test_db)


@pytest.fixture
def test_archive():
    """Create a test archive with sample submission structure."""
    temp_dir = tempfile.mkdtemp()
    archive_dir = os.path.join(temp_dir, 'sheet-blatt-1')
    os.makedirs(archive_dir)
    
    # Create marks.csv
    marks_csv = os.path.join(archive_dir, 'marks.csv')
    with open(marks_csv, 'w') as f:
        f.write('#submissionid,group,sheet,exercise,points,status\n')
        f.write('EMAYT2PGG4YMY,Person 1 + Person 2,Übungsblatt 1,1,2.0,FINAL_MARK\n')
    
    # Create exercise directories with submissions
    exercise_dir = os.path.join(archive_dir, 'excercise-1')
    os.makedirs(exercise_dir)
    
    submission_dir = os.path.join(exercise_dir, 'Person1_Person2_EMAYT2PGG4YMY')
    os.makedirs(submission_dir)
    
    # Create a dummy PDF
    dummy_pdf = os.path.join(submission_dir, 'assignment.pdf')
    with open(dummy_pdf, 'wb') as f:
        f.write(b'%PDF-1.4\n')  # Minimal PDF header
    
    # Create tar.gz archive
    archive_path = os.path.join(temp_dir, 'test_archive.tar.gz')
    with tarfile.open(archive_path, 'w:gz') as tar:
        tar.add(archive_dir, arcname=os.path.basename(archive_dir))
    
    yield archive_path, archive_dir
    
    # Cleanup
    shutil.rmtree(temp_dir)


class TestDatabaseFunctions:
    """Test database operations."""
    
    def test_init_db_creates_tables(self, setup_test_db):
        """Test that init_db creates necessary tables."""
        test_db = setup_test_db
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        
        # Check submissions table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='submissions'")
        assert cursor.fetchone() is not None
        
        # Check feedback table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='feedback'")
        assert cursor.fetchone() is not None
        
        # Check error_codes table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='error_codes'")
        assert cursor.fetchone() is not None
        
        conn.close()
    
    def test_default_error_codes_inserted(self, setup_test_db):
        """Test that default error codes are inserted."""
        error_codes = get_error_codes()
        assert len(error_codes) >= 5
        assert any('Syntaxfehler' in code for code in [str(c) for c in error_codes])


class TestSubmissionScanning:
    """Test submission scanning functionality."""
    
    def test_scan_and_insert_submissions(self, setup_test_db, test_archive):
        """Test that submissions are correctly scanned and inserted."""
        _, archive_dir = test_archive
        scan_and_insert_submissions(archive_dir)
        
        submissions = get_submissions()
        assert len(submissions) > 0
        
        # Check that submission has correct structure
        sub = submissions[0]
        assert sub[3] == 'Person 1 + Person 2'  # name from CSV
        assert 'excercise-1' in sub[4]  # exercise
        
    
    def test_submission_id_extraction(self, setup_test_db, test_archive):
        """Test that submissionid is correctly extracted from folder name."""
        _, archive_dir = test_archive
        scan_and_insert_submissions(archive_dir)
        
        submissions = get_submissions()
        assert len(submissions) > 0
        
        # The folder name is Person1_Person2_EMAYT2PGG4YMY
        # submissionid should be EMAYT2PGG4YMY
        assert 'EMAYT2PGG4YMY' in submissions[0][2] or 'EMAYT2PGG4YMY' in str(submissions[0])
        


class TestFeedbackStorage:
    """Test feedback storage functionality."""
    
    def test_save_and_get_feedback(self, setup_test_db, test_archive):
        """Test saving and retrieving feedback."""
        _, archive_dir = test_archive
        scan_and_insert_submissions(archive_dir)
        
        submissions = get_submissions()
        sub_id = submissions[0][0]
        
        # Save feedback
        points = 8.5
        markdown = "# Feedback\n\nGute Lösung!"
        pdf_path = "/path/to/feedback.pdf"
        
        save_feedback(sub_id, points, markdown, pdf_path)
        
        # Retrieve feedback
        feedback = get_feedback(sub_id)
        assert feedback is not None
        assert feedback[0] == points
        assert feedback[1] == markdown
        
    
    def test_feedback_marks_submission_completed(self, setup_test_db, test_archive):
        """Test that saving feedback marks submission as completed."""
        _, archive_dir = test_archive
        scan_and_insert_submissions(archive_dir)
        
        submissions = get_submissions()
        sub_id = submissions[0][0]
        
        # Initially status should be not_started
        sub = next((s for s in submissions if s[0] == sub_id), None)
        assert sub is not None
        assert sub[5] == 'not_started'
        
        # Save feedback
        save_feedback(sub_id, 8.5, "Feedback", "/path/to/feedback.pdf")
        
        # Check status is now completed
        updated_submissions = get_submissions()
        updated_sub = next((s for s in updated_submissions if s[0] == sub_id), None)
        assert updated_sub is not None
        assert updated_sub[5] == 'completed'
        


class TestArchiveExtraction:
    """Test archive extraction functionality."""
    
    def test_archive_can_be_created(self, test_archive):
        """Test that test archive is properly created."""
        archive_path, _ = test_archive
        assert os.path.exists(archive_path)
        assert archive_path.endswith('.tar.gz')
    
    def test_archive_contains_required_files(self, test_archive):
        """Test that archive contains required directory structure."""
        archive_path, _ = test_archive
        
        with tarfile.open(archive_path, 'r:gz') as tar:
            names = tar.getnames()
            # Should contain marks.csv
            assert any('marks.csv' in name for name in names)
            # Should contain excercise directory
            assert any('excercise' in name for name in names)
            # Should contain PDF
            assert any('.pdf' in name for name in names)


class TestIntegration:
    """Integration tests for the complete workflow."""
    
    def test_complete_workflow(self, setup_test_db, test_archive):
        """Test the complete workflow: scan -> feedback -> status update."""
        _, archive_dir = test_archive
        
        # Step 1: Scan submissions
        scan_and_insert_submissions(archive_dir)
        submissions = get_submissions()
        assert len(submissions) == 1
        assert submissions[0][5] == 'not_started'
        
        # Step 2: Get submission details
        sub_id = submissions[0][0]
        
        # Step 3: Save feedback
        save_feedback(sub_id, 9.0, "Excellent work!", "/path/to/feedback.pdf")
        
        # Step 4: Verify status updated
        updated_submissions = get_submissions()
        updated_sub = next(s for s in updated_submissions if s[0] == sub_id)
        assert updated_sub[5] == 'completed'
        
        # Step 5: Verify feedback can be retrieved
        feedback = get_feedback(sub_id)
        assert feedback is not None
        assert feedback[0] == 9.0
