"""Compatibility wrapper to expose configuration helpers at the project root."""
from app.config import get_data_dir  # re-export for legacy imports

__all__ = ["get_data_dir"]
