"""Application package for the Streamlit grading tool."""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import for type checkers only
	from . import main_app


def __getattr__(name: str):  # pragma: no cover - simple lazy import shim
	if name == "main_app":
		module = import_module(".main_app", __name__)
		globals()[name] = module
		return module
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
