"""Automated release packaging script for OneTime.

Builds the PyInstaller executable bundle and packages it along with
the browser extension and README into a distribution ZIP archive.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


def main() -> int:
    build_dir = Path(__file__).resolve().parent
    desktop_dir = build_dir.parent
    project_root = desktop_dir.parent

    # Read current version from desktop/app/version.py
    version_file = desktop_dir / "app" / "version.py"
    version_namespace: dict[str, str] = {}
    exec(version_file.read_text(encoding="utf-8"), version_namespace)
    version = version_namespace.get("APP_VERSION", "1.0.0")

    dist_dir = project_root / "dist"
    dist_dir.mkdir(exist_ok=True)
    staging_root = project_root / "build" / "package_staging"
    if staging_root.exists():
        shutil.rmtree(staging_root)

    package_name = f"OneTime-v{version}-windows-x64"
    package_dir = staging_root / package_name
    package_dir.mkdir(parents=True)

    spec_file = build_dir / "one_time.spec"
    print(f"--> Building OneTime with PyInstaller (version {version})...")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(spec_file),
        ],
        cwd=str(project_root),
    )
    if result.returncode != 0:
        print("PyInstaller build failed!", file=sys.stderr)
        return result.returncode

    built_app_dir = dist_dir / "OneTime"
    if not built_app_dir.exists():
        print(f"Built application directory not found: {built_app_dir}", file=sys.stderr)
        return 1

    # 1. Copy built application into package
    print(f"--> Staging application bundle...")
    shutil.copytree(built_app_dir, package_dir / "OneTime")

    # 2. Copy extension directory
    extension_dir = project_root / "extension"
    if extension_dir.exists():
        print(f"--> Staging Opera extension...")
        shutil.copytree(extension_dir, package_dir / "extension")
    else:
        print(f"Warning: Extension directory not found: {extension_dir}", file=sys.stderr)

    # 3. Copy README.md
    readme_file = project_root / "README.md"
    if readme_file.exists():
        print(f"--> Staging README.md...")
        shutil.copy2(readme_file, package_dir / "README.md")

    # 4. Create release ZIP archive
    zip_path = dist_dir / f"{package_name}.zip"
    print(f"--> Creating distribution archive: {zip_path.name}...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(package_dir):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(staging_root).as_posix()
                zf.write(file_path, arcname)

    # Clean up staging directory
    shutil.rmtree(staging_root, ignore_errors=True)
    print(f"\n[OK] Successfully packaged: {zip_path}")
    print(f"     Archive size: {zip_path.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
