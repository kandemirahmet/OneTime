# -*- mode: python ; coding: utf-8 -*-
import re
from pathlib import Path

block_cipher = None

spec_dir = Path(SPECPATH) if 'SPECPATH' in globals() else Path.cwd()
app_dir = spec_dir.parent
project_dir = app_dir.parent
icon_file = project_dir / 'OneTime.ico'

if not icon_file.is_file():
    raise FileNotFoundError(f'Application icon not found: {icon_file}')

version_source = app_dir / 'app' / 'version.py'
app_version = '1.0.0'
match = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', version_source.read_text(encoding='utf-8'))
if match:
    app_version = match.group(1)

version_numbers = [int(part) for part in app_version.split('.')]
while len(version_numbers) < 4:
    version_numbers.append(0)
major, minor, patch, *_ = version_numbers

version_file = spec_dir / 'one_time_version.py'
version_file.write_text(
    "VSVersionInfo(\n"
    "  ffi=FixedFileInfo(\n"
    f"    filevers=({major}, {minor}, {patch}, 0),\n"
    f"    prodvers=({major}, {minor}, {patch}, 0),\n"
    "    mask=0x3F,\n"
    "    flags=0x0,\n"
    "    OS=0x40004,\n"
    "    fileType=0x1,\n"
    "    subtype=0x0,\n"
    "    date=(0, 0),\n"
    "  ),\n"
    "  kids=[\n"
    "    StringFileInfo([\n"
    "      StringTable(\n"
    "        u'040904B0',\n"
    "        [StringStruct(u'CompanyName', u''),\n"
    "         StringStruct(u'FileDescription', u'OneTime'),\n"
    f"         StringStruct(u'FileVersion', u'{app_version}'),\n"
    "         StringStruct(u'InternalName', u'OneTime'),\n"
    "         StringStruct(u'LegalCopyright', u''),\n"
    "         StringStruct(u'OriginalFilename', u'OneTime.exe'),\n"
    "         StringStruct(u'ProductName', u'OneTime'),\n"
    f"         StringStruct(u'ProductVersion', u'{app_version}')]\n"
    "      )\n"
    "    ]),\n"
    "    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])\n"
    "  ]\n"
    ")\n",
    encoding='utf-8',
)

a = Analysis(
    [str(app_dir / 'app' / 'main.py')],
    pathex=[str(app_dir)],
    binaries=[],
    datas=[(str(icon_file), '.')],
    hiddenimports=[
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='OneTime',
    debug=False,
    strip=False,
    upx=False,
    version=str(version_file),
    console=False,
    icon=str(icon_file),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='OneTime',
)
