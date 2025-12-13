#!/usr/bin/env python3
"""
Validate that all required dependencies are installed and working.

This script checks for system dependencies, Python packages, and basic functionality.
"""

import sys
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple


def check_python_version() -> Tuple[bool, str]:
    """Check Python version."""
    version = sys.version_info
    if version.major == 3 and version.minor >= 9:
        return True, f"Python {version.major}.{version.minor}.{version.micro} ✅"
    else:
        return False, f"Python {version.major}.{version.minor}.{version.micro} ❌ (Requires 3.9+)"


def check_system_command(command: str, description: str) -> Tuple[bool, str]:
    """Check if a system command is available."""
    try:
        result = subprocess.run(
            [command, "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            version_info = result.stdout.strip() or result.stderr.strip()
            return True, f"{description}: {version_info} ✅"
        else:
            return False, f"{description}: Command returned error ❌"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, f"{description}: Not found ❌"


def check_python_import(module_name: str, description: str) -> Tuple[bool, str]:
    """Check if a Python module can be imported."""
    try:
        __import__(module_name)
        return True, f"{description} ✅"
    except ImportError as e:
        return False, f"{description}: {e} ❌"


def check_opencv_functionality() -> Tuple[bool, str]:
    """Check OpenCV video writing functionality."""
    try:
        import cv2
        import numpy as np

        # Create a small test image
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        img[:] = (0, 255, 0)  # Green image

        # Test video writer
        temp_file = Path("/tmp/test_video.mp4")
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(str(temp_file), fourcc, 30.0, (100, 100))

        if writer.isOpened():
            writer.write(img)
            writer.release()

            # Check if file was created
            if temp_file.exists():
                temp_file.unlink()  # Clean up
                return True, "OpenCV video writing functionality ✅"
            else:
                return False, "OpenCV video file not created ❌"
        else:
            return False, "OpenCV video writer failed to open ❌"

    except Exception as e:
        return False, f"OpenCV functionality test failed: {e} ❌"


def main():
    """Run all dependency checks."""
    print("🔍 Timelapse Generator - Dependency Validation")
    print("=" * 60)

    checks: List[Tuple[bool, str]] = []

    # Python version
    checks.append(check_python_version())

    # System commands
    checks.append(check_system_command("ffmpeg", "FFmpeg"))
    checks.append(check_system_command("uv", "UV Package Manager"))

    # Core Python packages
    core_packages = [
        ("cv2", "OpenCV"),
        ("numpy", "NumPy"),
        ("PIL", "Pillow"),
        ("requests", "Requests"),
        ("bs4", "BeautifulSoup4"),
        ("click", "Click"),
        ("yaml", "PyYAML"),
        ("jinja2", "Jinja2"),
        ("tqdm", "tqdm"),
        ("pydantic", "Pydantic"),
    ]

    for module, description in core_packages:
        checks.append(check_python_import(module, description))

    # YouTube API packages
    youtube_packages = [
        ("google.auth", "Google Auth"),
        ("google_auth_oauthlib", "Google Auth OAuthlib"),
        ("googleapiclient", "Google API Client"),
    ]

    print("\n📺 YouTube API Dependencies")
    print("-" * 40)
    for module, description in youtube_packages:
        success, message = check_python_import(module, description)
        checks.append((success, message))

    # Functional tests
    print("\n🧪 Functional Tests")
    print("-" * 40)
    checks.append(check_opencv_functionality())

    # Results summary
    print("\n📋 Results Summary")
    print("=" * 40)

    all_passed = True
    for success, message in checks:
        print(message)
        if not success:
            all_passed = False

    # Installation instructions for missing dependencies
    if not all_passed:
        print("\n🔧 Installation Instructions")
        print("-" * 40)

        print("\nSystem Dependencies:")
        print("  Ubuntu/Debian:")
        print("    sudo apt update")
        print("    sudo apt install python3-opencv ffmpeg")
        print("  Fedora:")
        print("    sudo dnf install opencv-python ffmpeg")

        print("\nPackage Manager (UV):")
        print("  uv sync                    # Install dependencies")
        print("  uv sync --dev             # Install with dev dependencies")

        print("\nYouTube API Setup:")
        print("  python scripts/setup_youtube_auth.py")

        print("\nPython Version:")
        print("  Requires Python 3.9 or higher")
        print("  Current: " + ".".join(map(str, sys.version_info[:3])))

        sys.exit(1)
    else:
        print("\n🎉 All dependencies are installed and working!")
        print("\nYou can now use the timelapse generator:")
        print("  timelapse --help")
        print("  timelapse config")
        print("  timelapse generate /path/to/images output.mp4")


if __name__ == "__main__":
    main()