"""Tests for utility functions in app/utils.py"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.utils import generate_feedback_pdf


@pytest.fixture
def temp_output_dir(tmp_path):
    """Create a temporary output directory for PDF tests."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return output_dir


def test_generate_feedback_pdf_success(temp_output_dir):
    """Test successful PDF generation."""
    output_path = temp_output_dir / "feedback.pdf"
    
    with patch("app.utils.pypandoc.convert_file") as mock_convert:
        mock_convert.return_value = None  # Simulate successful conversion
        
        success, error_msg = generate_feedback_pdf(
            markdown_content="Good work!",
            name="Test Student",
            points=10.0,
            output_path=str(output_path),
            sheet_number=1,
            exercise_number=1,
        )
        
        assert success is True
        assert error_msg is None
        mock_convert.assert_called_once()


def test_generate_feedback_pdf_with_empty_markdown(temp_output_dir):
    """Test PDF generation with empty markdown content."""
    output_path = temp_output_dir / "feedback.pdf"
    
    with patch("app.utils.pypandoc.convert_file") as mock_convert:
        mock_convert.return_value = None
        
        success, error_msg = generate_feedback_pdf(
            markdown_content="",
            name="Test Student",
            points=8.5,
            output_path=str(output_path),
            sheet_number=2,
            exercise_number=3,
        )
        
        assert success is True
        assert error_msg is None


def test_generate_feedback_pdf_with_none_markdown(temp_output_dir):
    """Test PDF generation with None as markdown content."""
    output_path = temp_output_dir / "feedback.pdf"
    
    with patch("app.utils.pypandoc.convert_file") as mock_convert:
        mock_convert.return_value = None
        
        success, error_msg = generate_feedback_pdf(
            markdown_content=None,
            name="Test Student",
            points=7,
            output_path=str(output_path),
            sheet_number=1,
            exercise_number=2,
        )
        
        assert success is True
        assert error_msg is None


def test_generate_feedback_pdf_output_dir_not_exists(tmp_path):
    """Test error handling when output directory doesn't exist."""
    non_existent_dir = tmp_path / "does_not_exist"
    output_path = non_existent_dir / "feedback.pdf"
    
    success, error_msg = generate_feedback_pdf(
        markdown_content="Test",
        name="Student",
        points=10,
        output_path=str(output_path),
        sheet_number=1,
        exercise_number=1,
    )
    
    assert success is False
    assert error_msg is not None
    assert "does not exist" in error_msg.lower()


def test_generate_feedback_pdf_pandoc_not_found(temp_output_dir):
    """Test error handling when pandoc is not installed."""
    output_path = temp_output_dir / "feedback.pdf"
    
    with patch("app.utils.pypandoc.convert_file") as mock_convert:
        mock_convert.side_effect = RuntimeError("pandoc not found")
        
        success, error_msg = generate_feedback_pdf(
            markdown_content="Test content",
            name="Student Name",
            points=9.0,
            output_path=str(output_path),
            sheet_number=1,
            exercise_number=1,
        )
        
        assert success is False
        assert error_msg is not None
        assert "pandoc" in error_msg.lower()


def test_generate_feedback_pdf_latex_error(temp_output_dir):
    """Test error handling when LaTeX engine fails."""
    output_path = temp_output_dir / "feedback.pdf"
    
    with patch("app.utils.pypandoc.convert_file") as mock_convert:
        mock_convert.side_effect = RuntimeError("xelatex: command not found")
        
        success, error_msg = generate_feedback_pdf(
            markdown_content="Test content",
            name="Student",
            points=10,
            output_path=str(output_path),
            sheet_number=1,
            exercise_number=1,
        )
        
        assert success is False
        assert error_msg is not None
        assert "latex" in error_msg.lower()


def test_generate_feedback_pdf_generic_runtime_error(temp_output_dir):
    """Test error handling for generic RuntimeError during conversion."""
    output_path = temp_output_dir / "feedback.pdf"
    
    with patch("app.utils.pypandoc.convert_file") as mock_convert:
        mock_convert.side_effect = RuntimeError("Some other error")
        
        success, error_msg = generate_feedback_pdf(
            markdown_content="Test",
            name="Student",
            points=5,
            output_path=str(output_path),
            sheet_number=1,
            exercise_number=1,
        )
        
        assert success is False
        assert error_msg is not None
        assert "conversion failed" in error_msg.lower()


def test_generate_feedback_pdf_unexpected_exception(temp_output_dir):
    """Test error handling for unexpected exceptions."""
    output_path = temp_output_dir / "feedback.pdf"
    
    with patch("app.utils.pypandoc.convert_file") as mock_convert:
        mock_convert.side_effect = ValueError("Unexpected error")
        
        success, error_msg = generate_feedback_pdf(
            markdown_content="Test",
            name="Student",
            points=10,
            output_path=str(output_path),
            sheet_number=1,
            exercise_number=1,
        )
        
        assert success is False
        assert error_msg is not None
        assert "unexpected error" in error_msg.lower()


def test_generate_feedback_pdf_file_write_permission_error(temp_output_dir):
    """Test error handling when temporary file cannot be written."""
    output_path = temp_output_dir / "feedback.pdf"
    
    with patch("pathlib.Path.write_text") as mock_write:
        mock_write.side_effect = PermissionError("Permission denied")
        
        success, error_msg = generate_feedback_pdf(
            markdown_content="Test",
            name="Student",
            points=10,
            output_path=str(output_path),
            sheet_number=1,
            exercise_number=1,
        )
        
        assert success is False
        assert error_msg is not None
        assert "write" in error_msg.lower() or "permission" in error_msg.lower()


def test_generate_feedback_pdf_cleans_up_temp_file_on_error(temp_output_dir):
    """Test that temporary markdown file is cleaned up on error."""
    output_path = temp_output_dir / "feedback.pdf"
    temp_md_path = output_path.with_suffix(".md")
    
    with patch("app.utils.pypandoc.convert_file") as mock_convert:
        mock_convert.side_effect = RuntimeError("Conversion failed")
        
        # Ensure temp file doesn't exist before
        assert not temp_md_path.exists()
        
        success, error_msg = generate_feedback_pdf(
            markdown_content="Test",
            name="Student",
            points=10,
            output_path=str(output_path),
            sheet_number=1,
            exercise_number=1,
        )
        
        assert success is False
        # Temp file should be cleaned up
        assert not temp_md_path.exists()


def test_generate_feedback_pdf_with_float_points(temp_output_dir):
    """Test PDF generation with floating point scores."""
    output_path = temp_output_dir / "feedback.pdf"
    
    with patch("app.utils.pypandoc.convert_file") as mock_convert:
        mock_convert.return_value = None
        
        success, error_msg = generate_feedback_pdf(
            markdown_content="Great!",
            name="Student",
            points=8.75,
            output_path=str(output_path),
            sheet_number=1,
            exercise_number=1,
        )
        
        assert success is True
        assert error_msg is None


def test_generate_feedback_pdf_with_integer_points(temp_output_dir):
    """Test PDF generation with integer scores."""
    output_path = temp_output_dir / "feedback.pdf"
    
    with patch("app.utils.pypandoc.convert_file") as mock_convert:
        mock_convert.return_value = None
        
        success, error_msg = generate_feedback_pdf(
            markdown_content="Perfect!",
            name="Student",
            points=10,
            output_path=str(output_path),
            sheet_number=1,
            exercise_number=1,
        )
        
        assert success is True
        assert error_msg is None


def test_generate_feedback_pdf_with_string_points(temp_output_dir):
    """Test PDF generation with string-formatted points (edge case)."""
    output_path = temp_output_dir / "feedback.pdf"
    
    with patch("app.utils.pypandoc.convert_file") as mock_convert:
        mock_convert.return_value = None
        
        success, error_msg = generate_feedback_pdf(
            markdown_content="OK",
            name="Student",
            points="N/A",
            output_path=str(output_path),
            sheet_number=1,
            exercise_number=1,
        )
        
        assert success is True
        assert error_msg is None
