# OneTime v1.0.0

OneTime is a Windows desktop application and Opera/Chromium extension for collecting direct image URLs from visible browser tabs and downloading the original image bytes into a user-selected folder without modifying the original file content.

## Active runtime architecture

Opera
        ↓
OneTime Extension
        ↓
localhost HTTP
        ↓
OneTime Desktop
        ↓
download service

## Project layout

- `desktop/` - Python + PySide6 desktop application and download engine.
- `extension/` - Manifest V3 browser extension.
- `docs/` - setup and development notes.
- `tests/` - regression tests for the HTTP contract, UI, and download behavior.

## Current status

OneTime v1.0.0 uses the local HTTP transport:

1. the Opera extension detects image tabs and sends a JSON payload to `http://127.0.0.1:8765/image-tabs`;
2. the OneTime desktop app listens only on `127.0.0.1`;
3. the app receives the image URLs in the main window;
4. the download service writes the original bytes directly to disk.

The desktop app must be running before the extension can transfer URLs.

## Development setup on Windows

Create a virtual environment and install dependencies:

python -m venv .venv
.venv\Scripts\activate
pip install -r desktop\requirements.txt

## Running the desktop app

python desktop\app\main.py

## Installing the extension in Opera

Load the unpacked extension in Opera by opening `opera:extensions`, enabling Developer Mode, and choosing the `extension/` folder.

The extension sends requests to `http://127.0.0.1:8765/image-tabs` and expects the desktop app to already be running.

## Output folder behavior

The desktop app stores the last-used output path in `QSettings` and restores it on the next launch. If the saved folder no longer exists, it falls back to the default `Downloads\OneTime` location. The Open folder action also creates the folder if needed and opens it with the system file explorer.

## Run tests

pytest -q
