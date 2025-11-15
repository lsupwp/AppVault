from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class PackageRecord:
    name: str
    section: str


@dataclass
class CategorizedPackage:
    package: PackageRecord
    has_desktop: bool
    desktop_files: List[str] = field(default_factory=list)
    terminal_desktop: Optional[bool] = None

    @property
    def label(self) -> str:
        sec = self.package.section or "unknown"
        return f"{self.package.name} [{sec}]"
