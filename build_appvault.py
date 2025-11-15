#!/usr/bin/env python3
"""
AppVault Build & Install Script
This script builds the AppVault application and installs it system-wide with .desktop file
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[0;32m'
    BLUE = '\033[0;34m'
    RED = '\033[0;31m'
    YELLOW = '\033[1;33m'
    NC = '\033[0m'  # No Color


def print_colored(message: str, color: str = Colors.NC):
    """Print colored message to terminal"""
    print(f"{color}{message}{Colors.NC}")


def print_step(step: str, total: int, current: int):
    """Print step header"""
    print_colored(f"\n[{current}/{total}] {step}", Colors.BLUE)


def run_command(cmd: list, check: bool = True, capture_output: bool = False):
    """Run a shell command"""
    try:
        result = subprocess.run(
            cmd,
            check=check,
            capture_output=capture_output,
            text=True
        )
        return result
    except subprocess.CalledProcessError as e:
        print_colored(f"✗ Command failed: {' '.join(cmd)}", Colors.RED)
        print_colored(f"Error: {e}", Colors.RED)
        sys.exit(1)


def check_sudo():
    """Check if running with sudo privileges"""
    if os.geteuid() != 0:
        print_colored("Note: This script will need sudo privileges for installation.", Colors.YELLOW)
        print_colored("You will be prompted for your password later.", Colors.YELLOW)
        print()


def check_pip_package(package: str) -> bool:
    """Check if a pip package is installed"""
    result = subprocess.run(
        [sys.executable, "-m", "pip", "show", package],
        capture_output=True,
        text=True
    )
    return result.returncode == 0


def install_pip_package(package: str):
    """Install a pip package"""
    print_colored(f"Installing {package}...", Colors.BLUE)
    run_command([sys.executable, "-m", "pip", "install", package])


def clean_build_dirs(dist_dir: Path, build_dir: Path, spec_file: Path):
    """Clean previous build directories"""
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
        print_colored("✓ Removed dist directory", Colors.GREEN)
    
    if build_dir.exists():
        shutil.rmtree(build_dir)
        print_colored("✓ Removed build directory", Colors.GREEN)
    
    if spec_file.exists():
        spec_file.unlink()
        print_colored("✓ Removed old spec file", Colors.GREEN)


def build_application(project_dir: Path):
    """Build the application using PyInstaller"""
    print_colored("This may take a few minutes...", Colors.BLUE)
    print()
    
    cmd = [
        "pyinstaller",
        "--clean",
        "--onefile",
        "--windowed",
        "--name=AppVault",
        "--add-data=public:public",
        "--hidden-import=PySide6.QtCore",
        "--hidden-import=PySide6.QtGui",
        "--hidden-import=PySide6.QtWidgets",
        "--hidden-import=pyqtdarktheme",
        "--hidden-import=core.package_scanner",
        "--hidden-import=core.models",
        "--hidden-import=core.flatpak_scanner",
        "--hidden-import=core.snap_scanner",
        "--collect-all=pyqtdarktheme",
        "app.py"
    ]
    
    run_command(cmd)
    print()
    print_colored("✓ Build completed successfully!", Colors.GREEN)


def create_desktop_file(desktop_file: Path, install_dir: Path, icon_install: Path):
    """Create .desktop file"""
    desktop_content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=AppVault
Comment=Linux Application Manager
Exec={install_dir}/AppVault
Icon={icon_install}
Terminal=false
Categories=System;Settings;PackageManager;
Keywords=apps;applications;packages;manager;dpkg;flatpak;snap;
StartupNotify=true
"""
    
    # Write desktop file with sudo
    with open("/tmp/appvault.desktop", "w") as f:
        f.write(desktop_content)
    
    run_command(["sudo", "mv", "/tmp/appvault.desktop", str(desktop_file)])
    run_command(["sudo", "chmod", "+x", str(desktop_file)])
    print_colored(f"✓ Created desktop file at {desktop_file}", Colors.GREEN)


def update_desktop_database():
    """Update desktop database if available"""
    if shutil.which("update-desktop-database"):
        run_command(["sudo", "update-desktop-database", "/usr/share/applications/"])
        print_colored("✓ Updated desktop database", Colors.GREEN)


def main():
    """Main build and install process"""
    print_colored("====================================", Colors.BLUE)
    print_colored("  AppVault Build & Install Script", Colors.BLUE)
    print_colored("====================================", Colors.BLUE)
    print()
    
    # Define paths
    project_dir = Path("/home/nanthaphat/Work/AppVault")
    dist_dir = project_dir / "dist"
    build_dir = project_dir / "build"
    spec_file = project_dir / "AppVault.spec"
    icon_path = project_dir / "public" / "images" / "AppVault_Logo.png"
    install_dir = Path("/opt/appvault")
    bin_link = Path("/usr/local/bin/appvault")
    desktop_file = Path("/usr/share/applications/appvault.desktop")
    icon_install = Path("/usr/share/pixmaps/appvault.png")
    
    # Change to project directory
    os.chdir(project_dir)
    
    # Check if AppVault is running and kill it
    try:
        result = subprocess.run(
            ["pgrep", "-f", "AppVault"],
            capture_output=True,
            text=True
        )
        if result.stdout.strip():
            print_colored("Found running AppVault process(es), stopping them...", Colors.YELLOW)
            subprocess.run(["pkill", "-f", "AppVault"], check=False)
            import time
            time.sleep(1)  # Wait for processes to terminate
            print_colored("✓ Stopped running processes", Colors.GREEN)
    except Exception:
        pass
    
    # Step 1: Check for PyInstaller
    print_step("Checking for PyInstaller...", 7, 1)
    if not check_pip_package("pyinstaller"):
        install_pip_package("pyinstaller")
    else:
        print_colored("✓ PyInstaller is already installed", Colors.GREEN)
    
    # Step 2: Clean previous builds
    print_step("Cleaning previous builds...", 7, 2)
    clean_build_dirs(dist_dir, build_dir, spec_file)
    
    # Step 3: Check dependencies
    print_step("Checking dependencies...", 7, 3)
    required_packages = ["PySide6", "pyqtdarktheme"]
    for pkg in required_packages:
        if check_pip_package(pkg):
            print_colored(f"✓ {pkg} is installed", Colors.GREEN)
        else:
            print_colored(f"✗ {pkg} is NOT installed", Colors.RED)
            install_pip_package(pkg)
    
    # Step 4: Build the application
    print_step("Building AppVault...", 7, 4)
    build_application(project_dir)
    
    # Step 5: Verify build
    print_step("Verifying build...", 7, 5)
    executable = dist_dir / "AppVault"
    if executable.exists():
        file_size = executable.stat().st_size / (1024 * 1024)  # Convert to MB
        print_colored(f"✓ Executable created: {executable}", Colors.GREEN)
        print_colored(f"✓ Size: {file_size:.2f} MB", Colors.GREEN)
    else:
        print_colored("✗ Executable not found!", Colors.RED)
        sys.exit(1)
    
    # Step 6: Install the application
    print_step("Installing AppVault system-wide...", 7, 6)
    print_colored("This requires sudo privileges.", Colors.YELLOW)
    
    # Create installation directory
    run_command(["sudo", "mkdir", "-p", str(install_dir)])
    print_colored("✓ Created installation directory", Colors.GREEN)
    
    # Copy executable
    run_command(["sudo", "cp", str(executable), str(install_dir / "AppVault")])
    run_command(["sudo", "chmod", "+x", str(install_dir / "AppVault")])
    print_colored(f"✓ Installed executable to {install_dir}", Colors.GREEN)
    
    # Copy icon
    if icon_path.exists():
        run_command(["sudo", "cp", str(icon_path), str(icon_install)])
        print_colored(f"✓ Installed icon to {icon_install}", Colors.GREEN)
    else:
        print_colored("⚠ Icon file not found, skipping icon installation", Colors.YELLOW)
    
    # Create symlink
    run_command(["sudo", "ln", "-sf", str(install_dir / "AppVault"), str(bin_link)])
    print_colored(f"✓ Created symlink at {bin_link}", Colors.GREEN)
    
    # Step 7: Create .desktop file
    print_step("Creating .desktop file...", 7, 7)
    create_desktop_file(desktop_file, install_dir, icon_install)
    
    # Update desktop database
    update_desktop_database()
    
    # Installation summary
    print()
    print_colored("====================================", Colors.GREEN)
    print_colored("Installation completed successfully!", Colors.GREEN)
    print_colored("====================================", Colors.GREEN)
    print()
    print_colored("AppVault has been installed:", Colors.BLUE)
    print_colored(f"  • Executable: {install_dir}/AppVault", Colors.GREEN)
    print_colored(f"  • Command: appvault", Colors.GREEN)
    print_colored(f"  • Desktop Entry: {desktop_file}", Colors.GREEN)
    print_colored(f"  • Icon: {icon_install}", Colors.GREEN)
    print()
    print_colored("You can now:", Colors.BLUE)
    print_colored("  1. Run from terminal: appvault", Colors.GREEN)
    print_colored("  2. Launch from application menu: Search for 'AppVault'", Colors.GREEN)
    print_colored("  3. Pin to favorites/dock for quick access", Colors.GREEN)
    print()
    print_colored("To uninstall:", Colors.BLUE)
    print(f"  sudo rm -rf {install_dir}")
    print(f"  sudo rm {bin_link}")
    print(f"  sudo rm {desktop_file}")
    print(f"  sudo rm {icon_install}")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print_colored("\n✗ Build cancelled by user", Colors.RED)
        sys.exit(1)
    except Exception as e:
        print_colored(f"\n✗ Unexpected error: {e}", Colors.RED)
        sys.exit(1)
