#!/usr/bin/env python3
"""
AppVault Uninstall Script
This script removes AppVault from the system
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


def run_command(cmd: list, check: bool = True):
    """Run a shell command"""
    try:
        result = subprocess.run(cmd, check=check, capture_output=True, text=True)
        return result
    except subprocess.CalledProcessError as e:
        print_colored(f"✗ Command failed: {' '.join(cmd)}", Colors.RED)
        print_colored(f"Error: {e}", Colors.RED)
        return None


def check_sudo():
    """Check if running with sudo privileges"""
    if os.geteuid() != 0:
        print_colored("This script requires sudo privileges.", Colors.YELLOW)
        print_colored("Please run with: sudo python3 uninstall_appvault.py", Colors.YELLOW)
        sys.exit(1)


def confirm_uninstall():
    """Ask user to confirm uninstallation"""
    print_colored("This will remove AppVault from your system.", Colors.YELLOW)
    print_colored("The following will be deleted:", Colors.YELLOW)
    print("  • /opt/appvault/")
    print("  • /usr/local/bin/appvault")
    print("  • /usr/share/applications/appvault.desktop")
    print("  • /usr/share/pixmaps/appvault.png")
    print()
    
    response = input("Are you sure you want to continue? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print_colored("Uninstallation cancelled.", Colors.BLUE)
        sys.exit(0)


def stop_running_processes():
    """Stop any running AppVault processes"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "AppVault"],
            capture_output=True,
            text=True
        )
        if result.stdout.strip():
            print_colored("Stopping running AppVault processes...", Colors.BLUE)
            subprocess.run(["pkill", "-f", "AppVault"], check=False)
            import time
            time.sleep(1)
            print_colored("✓ Stopped running processes", Colors.GREEN)
        return True
    except Exception:
        return False


def remove_path(path: Path, description: str):
    """Remove a file or directory"""
    if path.exists():
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            print_colored(f"✓ Removed {description}: {path}", Colors.GREEN)
            return True
        except Exception as e:
            print_colored(f"✗ Failed to remove {description}: {e}", Colors.RED)
            return False
    else:
        print_colored(f"⚠ {description} not found: {path}", Colors.YELLOW)
        return True


def main():
    """Main uninstallation process"""
    print_colored("====================================", Colors.BLUE)
    print_colored("  AppVault Uninstall Script", Colors.BLUE)
    print_colored("====================================", Colors.BLUE)
    print()
    
    # Check for sudo
    check_sudo()
    
    # Confirm uninstallation
    confirm_uninstall()
    print()
    
    # Define paths
    install_dir = Path("/opt/appvault")
    bin_link = Path("/usr/local/bin/appvault")
    desktop_file = Path("/usr/share/applications/appvault.desktop")
    icon_install = Path("/usr/share/pixmaps/appvault.png")
    
    # Stop running processes
    print_colored("Checking for running processes...", Colors.BLUE)
    stop_running_processes()
    print()
    
    # Remove files and directories
    print_colored("Removing AppVault files...", Colors.BLUE)
    success = True
    
    success &= remove_path(install_dir, "installation directory")
    success &= remove_path(bin_link, "binary symlink")
    success &= remove_path(desktop_file, "desktop file")
    success &= remove_path(icon_install, "icon file")
    
    # Update desktop database
    if shutil.which("update-desktop-database"):
        print()
        print_colored("Updating desktop database...", Colors.BLUE)
        result = run_command(["update-desktop-database", "/usr/share/applications/"], check=False)
        if result and result.returncode == 0:
            print_colored("✓ Updated desktop database", Colors.GREEN)
    
    # Summary
    print()
    if success:
        print_colored("====================================", Colors.GREEN)
        print_colored("Uninstallation completed successfully!", Colors.GREEN)
        print_colored("====================================", Colors.GREEN)
        print()
        print_colored("AppVault has been removed from your system.", Colors.BLUE)
    else:
        print_colored("====================================", Colors.YELLOW)
        print_colored("Uninstallation completed with warnings", Colors.YELLOW)
        print_colored("====================================", Colors.YELLOW)
        print()
        print_colored("Some files could not be removed. Please check the messages above.", Colors.YELLOW)
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print_colored("\n✗ Uninstallation cancelled by user", Colors.RED)
        sys.exit(1)
    except Exception as e:
        print_colored(f"\n✗ Unexpected error: {e}", Colors.RED)
        sys.exit(1)
