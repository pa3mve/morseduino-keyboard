"""
build.py — one-shot build helper
Creates an isolated venv (.venv/), installs deps there, then produces a
single-file executable in dist/ for the current platform.
Safe on Debian/Ubuntu systems that block system-wide pip installs.
"""

import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).parent
VENV = ROOT / ".venv"


def venv_python() -> Path:
    """Return the Python executable inside the venv."""
    if sys.platform == "win32":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def pip(*args):
    subprocess.check_call([venv_python(), "-m", "pip", *args])


def main():
    # Create venv if it doesn't exist yet
    if not VENV.exists():
        print(f"Creating virtual environment in {VENV} …")
        venv.create(VENV, with_pip=True)

    python = venv_python()

    # Upgrade pip silently (avoids noisy warnings)
    subprocess.check_call([python, "-m", "pip", "install", "--quiet",
                           "--upgrade", "pip"])

    # Install runtime + build deps into the venv
    pip("install", "--quiet", "-r", str(ROOT / "requirements.txt"))
    pip("install", "--quiet", "pyinstaller")

    spec = ROOT / "serial_keyboard.spec"
    result = subprocess.run(
        [python, "-m", "PyInstaller", "--clean", str(spec)],
        check=False,
    )

    if result.returncode == 0:
        dist = ROOT / "dist" / "SerialKeyboard"
        exe = dist.with_suffix(".exe") if sys.platform == "win32" else dist
        print(f"\nBuild succeeded.\nExecutable: {exe.resolve()}")
    else:
        print("\nBuild FAILED — see output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
