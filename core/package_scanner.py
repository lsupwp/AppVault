from __future__ import annotations

import os
import re
import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple, Set

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

# Standard .desktop file locations
DESKTOP_PATHS = [
    "/usr/share/applications/",
    "/usr/local/share/applications/",
    Path.home() / ".local/share/applications/",
]


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
        desktop_files: List[str] = []
        
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                p = line.strip()
                if p.endswith(".desktop") and os.path.isfile(p):
                    desktop_files.append(p)
        
        # Also search in standard .desktop locations by name
        # This helps find apps that have .desktop files not tracked by dpkg
        for desktop_dir in DESKTOP_PATHS:
            desktop_dir = Path(desktop_dir)
            if not desktop_dir.exists():
                continue
            
            # Look for .desktop files that might belong to this package
            # Common patterns: packagename.desktop, packagename-*.desktop
            for pattern in [f"{pkg.name}.desktop", f"{pkg.name}-*.desktop"]:
                for df in desktop_dir.glob(pattern):
                    if df.is_file() and str(df) not in desktop_files:
                        desktop_files.append(str(df))
        
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

    def _get_standalone_desktop_apps(self) -> List[CategorizedPackage]:
        """Find .desktop files that are not associated with dpkg packages"""
        standalone: List[CategorizedPackage] = []
        seen_desktop_files: Set[str] = set()
        
        # Collect all .desktop files from standard locations
        for desktop_dir in DESKTOP_PATHS:
            desktop_dir = Path(desktop_dir)
            if not desktop_dir.exists():
                continue
            
            for desktop_file in desktop_dir.glob("*.desktop"):
                if not desktop_file.is_file():
                    continue
                
                desktop_path = str(desktop_file)
                if desktop_path in seen_desktop_files:
                    continue
                seen_desktop_files.add(desktop_path)
                
                # Try to extract app name from .desktop file
                try:
                    app_name = None
                    terminal_flag = False
                    
                    with open(desktop_file, "r", encoding="utf-8", errors="ignore") as fh:
                        for line in fh:
                            line = line.strip()
                            if line.startswith("Name="):
                                app_name = line.split("=", 1)[1].strip()
                            elif line.lower().startswith("terminal="):
                                terminal_flag = line.split("=", 1)[1].strip().lower() == "true"
                            
                            if app_name:  # Got what we need
                                break
                    
                    if not app_name:
                        app_name = desktop_file.stem  # Use filename without .desktop
                    
                    # Create a pseudo package record
                    pkg = PackageRecord(name=app_name, section="standalone")
                    cat = CategorizedPackage(
                        package=pkg,
                        has_desktop=True,
                        desktop_files=[desktop_path],
                        terminal_desktop=terminal_flag,
                    )
                    standalone.append(cat)
                    
                except Exception:
                    continue
        
        return standalone

    def categorize(self, packages: Sequence[PackageRecord]) -> Tuple[List[CategorizedPackage], List[CategorizedPackage]]:
        desktop: List[CategorizedPackage] = []
        cli: List[CategorizedPackage] = []
        
        # Track which .desktop files are already associated with packages
        tracked_desktop_files: Set[str] = set()

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(self._check_desktop_files, p): p for p in packages}
            for fut in as_completed(futures):
                cat = fut.result()
                if cat.has_desktop:
                    desktop.append(cat)
                    tracked_desktop_files.update(cat.desktop_files)
                else:
                    cli.append(cat)
        
        # Add standalone .desktop apps that aren't tracked by dpkg
        for standalone_app in self._get_standalone_desktop_apps():
            # Check if this .desktop file is already tracked
            if not any(df in tracked_desktop_files for df in standalone_app.desktop_files):
                desktop.append(standalone_app)

        # Sort for stable output
        desktop.sort(key=lambda c: c.package.name)
        cli.sort(key=lambda c: c.package.name)
        return desktop, cli

    def scan_and_categorize(self) -> Tuple[List[CategorizedPackage], List[CategorizedPackage]]:
        master = self.scan_master_app_list()
        return self.categorize(master)
