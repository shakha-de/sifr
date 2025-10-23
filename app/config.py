"""Configuration helpers for runtime paths."""
from __future__ import annotations

import os
from pathlib import Path


def _default_data_dir() -> Path:
    """Return the default data directory inside the project."""
    return (Path(__file__).resolve().parent.parent / "data").resolve()


def get_data_dir() -> Path:
    """Return the directory where user-generated data should be stored."""
    env_value = os.getenv("SIFR_DATA_DIR")
    if env_value:
        return Path(env_value).expanduser().resolve()
    return _default_data_dir()
