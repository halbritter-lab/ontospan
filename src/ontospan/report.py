"""Validation results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Level = Literal["error", "warning"]


@dataclass(frozen=True)
class Issue:
    level: Level
    code: str
    path: str
    message: str


@dataclass
class ValidationReport:
    issues: list[Issue] = field(default_factory=list)

    def add(self, level: Level, code: str, path: str, message: str) -> None:
        self.issues.append(Issue(level, code, path, message))

    @property
    def errors(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.level == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors


class FormatError(ValueError):
    """Raised by loaders and writers when a document or bundle has errors."""

    def __init__(self, report: ValidationReport) -> None:
        super().__init__("; ".join(f"{i.path}: {i.message}" for i in report.errors))
        self.report = report


def fail(code: str, path: str, message: str) -> FormatError:
    """A ``FormatError`` with a single error."""
    report = ValidationReport()
    report.add("error", code, path, message)
    return FormatError(report)
