from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


MANAGER_ROOT = Path(__file__).resolve().parent
BLOG_ROOT = MANAGER_ROOT.parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Blog Manager for Windows")
    parser.add_argument("--output", type=Path, help="Optional parent directory for the onedir output")
    args = parser.parse_args()
    output = (args.output or (MANAGER_ROOT / "dist")).resolve()
    if args.output and output.exists() and any(output.iterdir()):
        raise SystemExit(f"Refusing to overwrite non-empty output directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    separator = ";" if sys.platform == "win32" else ":"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        "Blog Manager",
        "--icon",
        str(MANAGER_ROOT / "assets" / "app-icon.ico"),
        "--add-data",
        f"{MANAGER_ROOT / 'templates'}{separator}templates",
        "--add-data",
        f"{MANAGER_ROOT / 'static'}{separator}static",
        "--distpath",
        str(output),
        "--workpath",
        str(MANAGER_ROOT / "build"),
        "--specpath",
        str(MANAGER_ROOT),
        str(MANAGER_ROOT / "app.py"),
    ]
    environment = os.environ.copy()
    environment["PYINSTALLER_CONFIG_DIR"] = str(MANAGER_ROOT / "build" / "pyinstaller-config")
    subprocess.run(command, cwd=MANAGER_ROOT, check=True, env=environment)
    app_directory = output / "Blog Manager"
    (app_directory / "blog-manager.json").write_text(
        json.dumps({"blogRoot": str(BLOG_ROOT)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Built: {app_directory / 'Blog Manager.exe'}")


if __name__ == "__main__":
    main()
