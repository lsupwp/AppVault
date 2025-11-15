from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Tuple, Optional

from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QIcon, QPixmap, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QStyle,
    QToolButton,
    QMessageBox,
)

from core.package_scanner import PackageScanner
from core.models import CategorizedPackage
from core.flatpak_scanner import FlatpakScanner, FlatpakApp
from core.snap_scanner import SnapScanner, SnapApp


def resource_path(*rel_parts: str) -> str:
    """Return absolute path to resource, works for dev and PyInstaller."""
    base = getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)
    return str(Path(base).joinpath(*rel_parts))


LOGO_PATH = resource_path("public", "images", "AppVault_Logo.png")


class ScanWorker(QThread):
    result = Signal(object, object, object, object, object)  # desktop_list, cli_list, flatpak_list, snap_list, error

    def __init__(self, scanner: PackageScanner, fp_scanner: FlatpakScanner, snap_scanner: SnapScanner) -> None:
        super().__init__()
        self.scanner = scanner
        self.fp_scanner = fp_scanner
        self.snap_scanner = snap_scanner

    def run(self) -> None:
        try:
            desktop, cli = self.scanner.scan_and_categorize()
            flatpaks = self.fp_scanner.list_apps()
            snaps = self.snap_scanner.list_apps()
            self.result.emit(desktop, cli, flatpaks, snaps, None)
        except Exception as e:
            # Try at least a flatpak/snap list if dpkg fails
            try:
                flatpaks = self.fp_scanner.list_apps()
            except Exception:
                flatpaks = []
            try:
                snaps = self.snap_scanner.list_apps()
            except Exception:
                snaps = []
            self.result.emit([], [], flatpaks, snaps, e)


class AppListWidget(QListWidget):
    def __init__(self, items: List[CategorizedPackage], is_desktop_tab: bool = False) -> None:
        super().__init__()
        self.all_items = items
        self.is_desktop_tab = is_desktop_tab
        self.setAlternatingRowColors(True)
        self.setIconSize(QSize(24, 24))
        self.refresh()

    def refresh(self, query: str | None = None) -> None:
        self.clear()
        q = (query or "").lower()
        for it in self.all_items:
            if q and q not in it.package.name.lower():
                continue
            li = QListWidgetItem(f"{it.package.name} [{it.package.section or 'unknown'}]")
            li.setData(Qt.UserRole, it)
            if self.is_desktop_tab:
                icon_name = MainWindow.read_icon_from_desktop(it)
                if icon_name:
                    icon = QIcon.fromTheme(icon_name)
                    if icon.isNull():
                        try:
                            import os as _os
                            if _os.path.isfile(icon_name):
                                icon = QIcon(icon_name)
                        except Exception:
                            pass
                    if icon.isNull():
                        # Default icon for desktop apps without logo
                        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
                    li.setIcon(icon)
                else:
                    # Default icon when no icon specified
                    icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
                    li.setIcon(icon)
            else:
                # Generic terminal icon for CLI tab
                icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
                li.setIcon(icon)
            self.addItem(li)

    def update_data(self, items: List[CategorizedPackage]) -> None:
        self.all_items = items
        self.refresh()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AppVault")
        self.resize(1100, 700)
        
        # Set window icon
        logo_path = LOGO_PATH
        if QIcon(logo_path).isNull():
            # Fallback to default icon if logo not found
            self.setWindowIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        else:
            self.setWindowIcon(QIcon(logo_path))

        self.scanner = PackageScanner()
        self.desktop_items: List[CategorizedPackage] = []
        self.cli_items: List[CategorizedPackage] = []
        self.flatpak_items: List[FlatpakApp] = []
        self.snap_items: List[SnapApp] = []

        # Top controls
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search by package name…")
        self.refresh_btn = QPushButton("Refresh")
        self.info_label = QLabel("")

        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("Search:"))
        top_bar.addWidget(self.search_box, 1)
        top_bar.addWidget(self.refresh_btn)

        # Tabs with lists (left)
        self.tabs = QTabWidget()
        self.desktop_list = AppListWidget([], is_desktop_tab=True)
        self.cli_list = AppListWidget([], is_desktop_tab=False)
        self.tabs.addTab(self.desktop_list, "Desktop Apps")
        self.tabs.addTab(self.cli_list, "CLI Apps")

        # Details + actions (right)
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(72, 72)
        # Set AppVault logo as default
        logo_icon = QIcon(LOGO_PATH)
        if not logo_icon.isNull():
            self.icon_label.setPixmap(logo_icon.pixmap(72, 72))
        else:
            # Fallback icon
            fallback = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
            self.icon_label.setPixmap(fallback.pixmap(72, 72))
        self.title_label = QLabel("Select an app to see details.")
        self.title_label.setObjectName("titleLabel")
        self.tags_label = QLabel("")
        self.tags_label.setObjectName("tagsLabel")
        self.launch_btn = QPushButton("Launch")
        self.launch_btn.setEnabled(False)
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setEnabled(False)
        self.delete_btn.setObjectName("deleteButton")

        # Assemble central widget
        # Right detail layout
        right = QVBoxLayout()
        header = QHBoxLayout()
        header.addWidget(self.icon_label)
        header_text = QVBoxLayout()
        header_text.addWidget(self.title_label)
        header_text.addWidget(self.tags_label)
        header.addLayout(header_text, 1)
        right.addLayout(header)
        # No Exec row per request; keep actions only
        # Actions
        actions_bar = QHBoxLayout()
        actions_bar.addWidget(self.launch_btn)
        actions_bar.addWidget(self.delete_btn)
        actions_bar.addStretch(1)
        right.addLayout(actions_bar)
        right.addStretch(1)

        # Splitter
        splitter = QSplitter()
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_layout.addLayout(top_bar)
        # Add Flatpak tab
        self.flatpak_list = QListWidget()
        self.flatpak_list.setAlternatingRowColors(True)
        self.flatpak_list.setIconSize(QSize(24, 24))
        self.tabs.addTab(self.flatpak_list, "Flatpak Apps")
        # Add Snap tab
        self.snap_list = QListWidget()
        self.snap_list.setAlternatingRowColors(True)
        self.snap_list.setIconSize(QSize(24, 24))
        self.tabs.addTab(self.snap_list, "Snap Apps")
        left_layout.addWidget(self.tabs, 1)
        left_layout.addWidget(self.info_label)
        left_widget.setLayout(left_layout)

        right_widget = QWidget()
        right_widget.setLayout(right)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        root_layout = QVBoxLayout()
        root_layout.addWidget(splitter, 1)

        cw = QWidget()
        cw.setLayout(root_layout)
        self.setCentralWidget(cw)

        # Signals
        self.refresh_btn.clicked.connect(self.run_scan)
        self.search_box.textChanged.connect(self.on_search_changed)
        self.desktop_list.currentItemChanged.connect(self.on_selection_changed)
        self.cli_list.currentItemChanged.connect(self.on_selection_changed)
        self.flatpak_list.currentItemChanged.connect(self.on_selection_changed)
        self.snap_list.currentItemChanged.connect(self.on_selection_changed)
        self.launch_btn.clicked.connect(self.on_launch_clicked)
        self.delete_btn.clicked.connect(self.on_delete_clicked)

        # Shortcuts
        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: self.search_box.setFocus())
        QShortcut(QKeySequence("F5"), self, activated=self.run_scan)

        # Initial load
        self.run_scan()

    def run_scan(self) -> None:
        self.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.info_label.setText("Scanning…")
        # Clear detail pane
        self.title_label.setText("Select an app to see details.")
        # Restore AppVault logo
        logo_icon = QIcon(LOGO_PATH)
        if not logo_icon.isNull():
            self.icon_label.setPixmap(logo_icon.pixmap(72, 72))
        else:
            fallback = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
            self.icon_label.setPixmap(fallback.pixmap(72, 72))
        self.tags_label.clear()
        self.launch_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)

        self.fp_scanner = FlatpakScanner()
        self.snap_scanner = SnapScanner()
        self.worker = ScanWorker(self.scanner, self.fp_scanner, self.snap_scanner)
        self.worker.result.connect(self.on_scan_finished)
        self.worker.start()

    def on_scan_finished(self, desktop, cli, flatpaks, snaps, error) -> None:
        QApplication.restoreOverrideCursor()
        self.setEnabled(True)
        if error:
            self.info_label.setText(f"Error: {error}")
            # Continue to show what we could fetch
        self.desktop_items = desktop
        self.cli_items = cli
        self.flatpak_items = flatpaks
        self.snap_items = snaps
        self.desktop_list.update_data(desktop)
        self.cli_list.update_data(cli)
        self._populate_flatpak_list()
        self._populate_snap_list()
        self.info_label.setText(f"Desktop: {len(desktop)}  |  CLI: {len(cli)}  |  Flatpak: {len(flatpaks)}  |  Snap: {len(snaps)}")
        self.statusBar().showMessage("Scan complete", 3000)

    def on_search_changed(self, text: str) -> None:
        self.desktop_list.refresh(text)
        self.cli_list.refresh(text)

    def _current_item(self) -> CategorizedPackage | None:
        idx = self.tabs.currentIndex()
        if idx == 0:
            lw = self.desktop_list
        elif idx == 1:
            lw = self.cli_list
        elif idx == 2:
            lw = self.flatpak_list
        else:
            lw = self.snap_list
        item = lw.currentItem()
        if not item:
            return None
        return item.data(Qt.UserRole)

    def on_selection_changed(self, current, previous) -> None:
        it = self._current_item()
        if not it:
            self.title_label.setText("Select an app to see details.")
            # Restore AppVault logo
            logo_icon = QIcon(LOGO_PATH)
            if not logo_icon.isNull():
                self.icon_label.setPixmap(logo_icon.pixmap(72, 72))
            else:
                fallback = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
                self.icon_label.setPixmap(fallback.pixmap(72, 72))
            self.tags_label.clear()
            self.launch_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            return
        # Handle dpkg app vs flatpak app
        if isinstance(it, CategorizedPackage):
            self.title_label.setText(it.package.name)
            icon_name = self.read_icon_from_desktop(it)
            icon = QIcon.fromTheme(icon_name) if icon_name else QIcon()
            if icon_name and icon.isNull():
                try:
                    import os as _os
                    if _os.path.isfile(icon_name):
                        icon = QIcon(icon_name)
                except Exception:
                    pass
            self._set_icon_or_default(icon)
            tags = [f"Section: {it.package.section or 'unknown'}", "Type: Desktop" if it.has_desktop else "Type: CLI"]
            if it.terminal_desktop is not None:
                tags.append(f"Terminal: {bool(it.terminal_desktop)}")
            self.tags_label.setText("  |  ".join(tags))
            exec_cmd, _icon_name, _term = self._read_desktop_meta(it)
            self.launch_btn.setEnabled(bool(exec_cmd))
            self.delete_btn.setEnabled(True)
        elif isinstance(it, FlatpakApp):
            fp: FlatpakApp = it
            self.title_label.setText(fp.name or fp.app_id)
            icon = QIcon.fromTheme(fp.icon_name) if fp.icon_name else QIcon()
            if fp.icon_name and icon.isNull():
                try:
                    import os as _os
                    if _os.path.isfile(fp.icon_name):
                        icon = QIcon(fp.icon_name)
                except Exception:
                    pass
            self._set_icon_or_default(icon)
            self.tags_label.setText(f"Source: Flatpak ({fp.origin})")
            # flatpak can always be launched via flatpak run <app_id>
            self.launch_btn.setEnabled(True)
            self.delete_btn.setEnabled(True)
        else:
            # Snap app
            snap: SnapApp = it  # type: ignore
            self.title_label.setText(snap.name)
            icon = QIcon.fromTheme(snap.icon_name) if snap.icon_name else QIcon()
            if snap.icon_name and icon.isNull():
                try:
                    import os as _os
                    if _os.path.isfile(snap.icon_name):
                        icon = QIcon(snap.icon_name)
                except Exception:
                    pass
            self._set_icon_or_default(icon)
            self.tags_label.setText(f"Source: Snap ({snap.publisher})")
            # snap can always be launched via snap run <name>
            self.launch_btn.setEnabled(True)
            self.delete_btn.setEnabled(True)

    @staticmethod
    def _read_desktop_meta(it: CategorizedPackage) -> Tuple[str | None, str | None, bool | None]:
        if not it.has_desktop or not it.desktop_files:
            return None, None, it.terminal_desktop
        path = it.desktop_files[0]
        exec_cmd = None
        icon_name = None
        term_flag = it.terminal_desktop
        try:
            import re as _re
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                for raw in fh:
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("Exec=") and exec_cmd is None:
                        value = line.split("=", 1)[1].strip()
                        value = _re.sub(r"%[fFuUdDnNickvm]", "", value)
                        value = _re.sub(r"\s+", " ", value).strip()
                        exec_cmd = value or None
                    elif line.startswith("Icon=") and icon_name is None:
                        icon_name = line.split("=", 1)[1].strip() or None
                    elif line.lower().startswith("terminal=") and term_flag is None:
                        term_flag = line.split("=", 1)[1].strip().lower() == "true"
        except Exception:
            pass
        return exec_cmd, icon_name, term_flag

    @staticmethod
    def read_icon_from_desktop(it: CategorizedPackage) -> str | None:
        _, icon_name, _ = MainWindow._read_desktop_meta(it)
        return icon_name

    def on_launch_clicked(self) -> None:
        it = self._current_item()
        if not it:
            return
        # DPKG-based app
        if isinstance(it, CategorizedPackage):
            cmd, _, _ = self._read_desktop_meta(it)
            if not cmd:
                return
            import subprocess, shlex, os
            try:
                args = shlex.split(cmd)
                subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setpgrp)
            except Exception:
                subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setpgrp)
            return
        elif isinstance(it, FlatpakApp):
            # Flatpak app
            fp: FlatpakApp = it
            import subprocess, os
            try:
                subprocess.Popen(["flatpak", "run", fp.app_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setpgrp)
            except Exception:
                pass
        else:
            # Snap app
            snap: SnapApp = it  # type: ignore
            import subprocess, os
            try:
                subprocess.Popen(["snap", "run", snap.name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setpgrp)
            except Exception:
                pass

    def on_delete_clicked(self) -> None:
        it = self._current_item()
        if not it:
            return
        
        # Determine app name and type
        if isinstance(it, CategorizedPackage):
            app_name = it.package.name
            app_type = "Debian/Ubuntu package"
            cmd = f"pkexec apt-get autoremove --purge -y {app_name}"
        elif isinstance(it, FlatpakApp):
            fp: FlatpakApp = it
            app_name = fp.name or fp.app_id
            app_type = "Flatpak application"
            cmd = f"flatpak uninstall --delete-data -y {fp.app_id}"
        else:
            snap: SnapApp = it  # type: ignore
            app_name = snap.name
            app_type = "Snap package"
            cmd = f"pkexec snap remove --purge {snap.name}"
        
        # Confirmation dialog
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete '{app_name}'?\n\n"
            f"Type: {app_type}\n"
            f"This will remove the application and clean up unused dependencies.\n\n"
            f"This action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # Execute removal
        import subprocess
        try:
            self.statusBar().showMessage(f"Removing {app_name}...", 0)
            QApplication.setOverrideCursor(Qt.WaitCursor)
            result = subprocess.run(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            QApplication.restoreOverrideCursor()
            
            if result.returncode == 0:
                QMessageBox.information(
                    self,
                    "Success",
                    f"'{app_name}' has been successfully removed."
                )
                self.statusBar().showMessage(f"Removed {app_name}", 3000)
                # Refresh the lists
                self.run_scan()
            else:
                error_msg = result.stderr or result.stdout or "Unknown error"
                QMessageBox.critical(
                    self,
                    "Deletion Failed",
                    f"Failed to remove '{app_name}'.\n\nError: {error_msg}"
                )
                self.statusBar().showMessage("Deletion failed", 3000)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(
                self,
                "Error",
                f"An error occurred while removing '{app_name}'.\n\nError: {str(e)}"
            )
            self.statusBar().showMessage("Deletion error", 3000)

    def _populate_flatpak_list(self) -> None:
        self.flatpak_list.clear()
        q = self.search_box.text().lower()
        for fp in self.flatpak_items:
            if q and q not in (fp.name or fp.app_id).lower():
                continue
            li = QListWidgetItem(fp.label)
            li.setData(Qt.UserRole, fp)
            icon = QIcon.fromTheme(fp.icon_name) if fp.icon_name else QIcon()
            if fp.icon_name and icon.isNull():
                try:
                    import os as _os
                    if _os.path.isfile(fp.icon_name):
                        icon = QIcon(fp.icon_name)
                except Exception:
                    pass
            if icon.isNull():
                # Default icon for Flatpak apps without logo
                icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
            li.setIcon(icon)
            self.add_to_flatpak_list(li)

    def add_to_flatpak_list(self, item: QListWidgetItem) -> None:
        self.flatpak_list.addItem(item)

    def _populate_snap_list(self) -> None:
        self.snap_list.clear()
        q = self.search_box.text().lower()
        for snap in self.snap_items:
            if q and q not in snap.name.lower():
                continue
            li = QListWidgetItem(snap.label)
            li.setData(Qt.UserRole, snap)
            icon = QIcon.fromTheme(snap.icon_name) if snap.icon_name else QIcon()
            if snap.icon_name and icon.isNull():
                try:
                    import os as _os
                    if _os.path.isfile(snap.icon_name):
                        icon = QIcon(snap.icon_name)
                except Exception:
                    pass
            if icon.isNull():
                # Default icon for Snap apps without logo
                icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
            li.setIcon(icon)
            self.snap_list.addItem(li)

    def _set_icon_or_default(self, icon: QIcon) -> None:
        if not icon.isNull():
            self.icon_label.setPixmap(icon.pixmap(72, 72))
        else:
            fallback = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
            self.icon_label.setPixmap(fallback.pixmap(72, 72))


def run_gui() -> int:
    app = QApplication(sys.argv)

    # Apply modern theme (try pyqtdarktheme; fallback to Fusion + stylesheet)
    try:
        import pyqtdarktheme  # type: ignore

        pyqtdarktheme.setup_theme("dark")
    except Exception:
        # Fallback
        app.setStyle("Fusion")
        palette = app.palette()
        # Subtle dark tweaks
        from PySide6.QtGui import QColor, QPalette

        palette.setColor(QPalette.ColorRole.Window, QColor(37, 37, 38))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
        palette.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(45, 45, 48))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 225))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(0, 0, 0))
        palette.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
        palette.setColor(QPalette.ColorRole.Button, QColor(45, 45, 48))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
        palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(14, 99, 156))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
        app.setPalette(palette)

        app.setStyleSheet(
            """
            #titleLabel { font-size: 18px; font-weight: 600; }
            QPushButton { 
                padding: 8px 16px; 
                border: 2px solid #0e639c;
                border-radius: 6px;
                background-color: #0e639c;
                color: white;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #1177bb;
                border-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #094771;
                border-color: #094771;
            }
            QPushButton:disabled {
                background-color: #3c3c3c;
                border-color: #555555;
                color: #888888;
            }
            #deleteButton {
                background-color: #c42b1c;
                border-color: #c42b1c;
            }
            #deleteButton:hover {
                background-color: #e03b2a;
                border-color: #e03b2a;
            }
            #deleteButton:pressed {
                background-color: #a52313;
                border-color: #a52313;
            }
            #deleteButton:disabled {
                background-color: #3c3c3c;
                border-color: #555555;
                color: #888888;
            }
            QToolButton {
                padding: 6px 10px;
                border: 1px solid #555555;
                border-radius: 4px;
                background-color: #4a4a4a;
            }
            QToolButton:hover {
                background-color: #5a5a5a;
                border-color: #666666;
            }
            QLineEdit { padding: 6px; border-radius: 6px; border: 1px solid #555555; }
            QTabWidget::pane { border: 1px solid #3c3c3c; border-radius: 6px; }
            QListWidget { border: 1px solid #3c3c3c; border-radius: 6px; }
            #tagsLabel { color: #bbbbbb; }
            """
        )
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run_gui())
