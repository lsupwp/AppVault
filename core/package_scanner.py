from __future__ import annotations

import os
import re
import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, List, Sequence, Tuple

from .models import PackageRecord, CategorizedPackage


BLACKLIST_SECTIONS_DEFAULT: Tuple[str, ...] = (
    "libs",
    "python",
    "perl",
    "kernel",
    "doc",
    "metapackages",
    "oldlibs",
    "debug",
)


class PackageScanner:
    def __init__(
        self,
        blacklist_sections: Sequence[str] | None = None,
        max_workers: int | None = None,
    ) -> None:
        self.blacklist_sections = tuple(blacklist_sections or BLACKLIST_SECTIONS_DEFAULT)
        # Reasonable default for lots of short subprocess calls
        if max_workers is None:
            try:
                cpu = os.cpu_count() or 2
                max_workers = min(32, cpu * 4)
            except Exception:
                max_workers = 8
        self.max_workers = max_workers

    def _run(self, cmd: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    def _bulk_query_packages(self) -> List[PackageRecord]:
        proc = self._run("dpkg-query -W -f='${Package} ${Section}\\n'")
        if proc.returncode != 0:
            stderr = proc.stderr.strip()
            raise RuntimeError(
                f"Failed to run dpkg-query (code {proc.returncode}). {stderr}"
            )
        packages: List[PackageRecord] = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            # Package name cannot contain spaces, section may be missing
            parts = line.split(maxsplit=1)
            if len(parts) == 1:
                name, section = parts[0], ""
            else:
                name, section = parts[0], parts[1]
            packages.append(PackageRecord(name=name, section=section))
        return packages

    def _section_is_blacklisted(self, section: str) -> bool:
        if not section:
            return False
        # Sections often like 'libs/foo' or 'python/foo' — check any token
        tokens = [section] + section.split("/")
        stokens = [t.lower() for t in tokens]
        for bl in self.blacklist_sections:
            bl = bl.lower()
            if any(bl == t or t.startswith(bl + "/") or bl in t.split("/") for t in stokens):
                return True
        return False

    def _filter_non_apps(self, records: Iterable[PackageRecord]) -> List[PackageRecord]:
        result: List[PackageRecord] = []
        for r in records:
            if self._section_is_blacklisted(r.section):
                continue
            result.append(r)
        return result

    def _check_desktop_files(self, pkg: PackageRecord) -> CategorizedPackage:
        # Use dpkg -L to list files owned by the package
        proc = self._run(f"dpkg -L {shlex.quote(pkg.name)}")
        if proc.returncode != 0:
            return CategorizedPackage(package=pkg, has_desktop=False, desktop_files=[])
        desktop_files: List[str] = []
        for line in proc.stdout.splitlines():
            p = line.strip()
            if p.endswith(".desktop"):
                desktop_files.append(p)
        has_desktop = len(desktop_files) > 0

        terminal_flag = None
        if has_desktop:
            # Optional: detect Terminal=true to hint CLI-like desktop launchers
            term_true = False
            for df in desktop_files:
                try:
                    with open(df, "r", encoding="utf-8", errors="ignore") as fh:
                        content = fh.read()
                        if re.search(r"^\s*Terminal\s*=\s*true\s*$", content, re.MULTILINE | re.IGNORECASE):
                            term_true = True
                            break
                except Exception:
                    continue
            terminal_flag = term_true

        return CategorizedPackage(
            package=pkg,
            has_desktop=has_desktop,
            desktop_files=desktop_files,
            terminal_desktop=terminal_flag,
        )

    def scan_master_app_list(self) -> List[PackageRecord]:
        all_records = self._bulk_query_packages()
        return self._filter_non_apps(all_records)

    def categorize(self, packages: Sequence[PackageRecord]) -> Tuple[List[CategorizedPackage], List[CategorizedPackage]]:
        desktop: List[CategorizedPackage] = []
        cli: List[CategorizedPackage] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(self._check_desktop_files, p): p for p in packages}
            for fut in as_completed(futures):
                cat = fut.result()
                if cat.has_desktop:
                    desktop.append(cat)
                else:
                    cli.append(cat)

        # Sort for stable output
        desktop.sort(key=lambda c: c.package.name)
        cli.sort(key=lambda c: c.package.name)
        return desktop, cli

    def scan_and_categorize(self) -> Tuple[List[CategorizedPackage], List[CategorizedPackage]]:
        master = self.scan_master_app_list()
        return self.categorize(master)
