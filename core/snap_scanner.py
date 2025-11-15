from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class SnapApp:
    name: str
    version: str
    revision: str
    publisher: str
    notes: Optional[str] = None
    desktop_file: Optional[str] = None
    icon_name: Optional[str] = None

    @property
    def label(self) -> str:
        base = self.name
        if self.publisher:
            return f"{base} [{self.publisher}]"
        return base


class SnapScanner:
    def __init__(self) -> None:
        pass

    def _run(self, cmd: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    def _find_desktop_file(self, snap_name: str) -> Optional[str]:
        candidates = [
            f"/var/lib/snapd/desktop/applications/{snap_name}_{snap_name}.desktop",
            f"/var/lib/snapd/desktop/applications/{snap_name}.desktop",
        ]
        # Also check for variants with app name
        snap_dir = f"/snap/{snap_name}/current"
        if os.path.isdir(snap_dir):
            try:
                meta_gui = os.path.join(snap_dir, "meta/gui")
                if os.path.isdir(meta_gui):
                    for f in os.listdir(meta_gui):
                        if f.endswith(".desktop"):
                            candidates.append(os.path.join(meta_gui, f))
            except Exception:
                pass
        
        for p in candidates:
            if os.path.isfile(p):
                return p
        return None

    def _read_desktop_meta(self, path: str) -> Tuple[Optional[str], Optional[str]]:
        name = None
        icon = None
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                for raw in fh:
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    if name is None and line.startswith("Name="):
                        name = line.split("=", 1)[1].strip() or None
                    elif icon is None and line.startswith("Icon="):
                        icon = line.split("=", 1)[1].strip() or None
                    if name and icon:
                        break
        except Exception:
            pass
        return name, icon

    def list_apps(self) -> List[SnapApp]:
        # List installed snap apps; if snap missing, return empty list
        proc = self._run("snap list")
        if proc.returncode != 0:
            return []
        apps: List[SnapApp] = []
        lines = proc.stdout.splitlines()
        # Skip header line
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            name = parts[0]
            version = parts[1]
            revision = parts[2]
            publisher = parts[3]
            notes = parts[4] if len(parts) > 4 else None
            
            desktop = self._find_desktop_file(name)
            display_name = None
            icon = None
            if desktop:
                display_name, icon = self._read_desktop_meta(desktop)
            
            apps.append(SnapApp(
                name=name,
                version=version,
                revision=revision,
                publisher=publisher,
                notes=notes,
                desktop_file=desktop,
                icon_name=icon
            ))
        
        # Sort by name
        apps.sort(key=lambda a: a.name.lower())
        return apps
