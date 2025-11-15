from __future__ import annotations

import importlib

import pytest


@pytest.fixture()
def db_module(tmp_path, monkeypatch):
    """Provide an initialized copy of app.db pointing at a temporary data dir."""

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("SIFR_DATA_DIR", str(data_dir))

    import app.db as db

    importlib.reload(db)
    db.init_db()
    yield db
