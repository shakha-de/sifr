from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence


@dataclass(slots=True)
class SheetContext:
    """Lightweight descriptor for the currently selected sheet."""

    root_path: str
    sheet_name: str
    sheet_id: int | None


@dataclass(slots=True)
class SubmissionRecord:
    """Structured view of a submission row."""

    id: int
    path: str
    group_name: str
    submitter: str
    exercise_code: str
    status: str

    @classmethod
    def from_row(cls, row: Sequence):
        return cls(
            id=row[0],
            path=row[1],
            group_name=row[2],
            submitter=row[3],
            exercise_code=row[4],
            status=row[5],
        )


@dataclass(slots=True)
class ErrorCode:
    code: str
    description: str
    deduction: float
    comment: str | None

    @classmethod
    def from_row(cls, row: Sequence):
        return cls(
            code=row[0],
            description=row[1],
            deduction=float(row[2] or 0.0),
            comment=row[3],
        )

    def as_option(self) -> str:
        return f"{self.code}: {self.description} ({self.deduction:g} Punkte)"


def convert_submissions(rows: Iterable[Sequence]) -> list[SubmissionRecord]:
    return [SubmissionRecord.from_row(row) for row in rows]


def resolve_sheet_context(
    current_root: str | None,
    resolver: Callable[[str], int | None],
) -> SheetContext | None:
    if not current_root:
        return None

    sheet_name = os.path.basename(current_root.rstrip(os.sep)) or current_root
    sheet_id = resolver(sheet_name)
    return SheetContext(root_path=current_root, sheet_name=sheet_name, sheet_id=sheet_id)


def apply_error_codes(
    selected_labels: Iterable[str],
    error_codes: Iterable[ErrorCode],
    current_points: float,
    current_markdown: str,
) -> tuple[float, str]:
    code_map = {code.code: code for code in error_codes}
    updated_points = current_points
    updated_markdown = current_markdown

    for label in selected_labels:
        code = label.split(":", 1)[0].strip()
        if code not in code_map:
            continue
        info = code_map[code]
        updated_points = max(0.0, updated_points - info.deduction)
        if info.comment:
            updated_markdown += f"\n\n ### {info.description}: -{info.deduction:g}P\n{info.comment}"

    return updated_points, updated_markdown
