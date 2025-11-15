from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class FlatpakApp:
    app_id: str
    origin: str
    name: Optional[str] = None
    desktop_file: Optional[str] = None
    icon_name: Optional[str] = None

    @property
    def label(self) -> str:
        base = self.name or self.app_id
        return f"{base} [{self.origin}]"


class FlatpakScanner:
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

    def _find_desktop_file(self, app_id: str) -> Optional[str]:
        candidates = [
            os.path.expanduser(f"~/.local/share/flatpak/exports/share/applications/{app_id}.desktop"),
            f"/var/lib/flatpak/exports/share/applications/{app_id}.desktop",
            # Some systems export into XDG data dirs as well
            f"/usr/local/share/applications/{app_id}.desktop",
            f"/usr/share/applications/{app_id}.desktop",
        ]
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

    def list_apps(self) -> List[FlatpakApp]:
        # List installed flatpak apps; if flatpak missing, return empty list
        proc = self._run("flatpak list --app --columns=application,origin")
        if proc.returncode != 0:
            return []
        apps: List[FlatpakApp] = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split()  # application origin
            if len(parts) < 1:
                continue
            app_id = parts[0]
            origin = parts[1] if len(parts) > 1 else "unknown"
            desktop = self._find_desktop_file(app_id)
            name = None
            icon = None
            if desktop:
                name, icon = self._read_desktop_meta(desktop)
            apps.append(FlatpakApp(app_id=app_id, origin=origin, name=name, desktop_file=desktop, icon_name=icon))
        # Sort by display label
        apps.sort(key=lambda a: (a.name or a.app_id).lower())
        return apps
