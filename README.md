# OneTime v1.1.0

OneTime is a Windows desktop application for Opera that collects direct image URLs from the current browser tabs and downloads the original image bytes into a user-selected folder without changing the original file content.

## What is new in v1.1.0

- Successful downloads are removed from the pending list once the files are saved.
- Duplicate URLs are ignored during the current OneTime session, so the same image is not added again while the app stays open.
- Failed downloads stay retryable, which means a URL that did not complete can be sent again later without being blocked by a prior failure.
- The desktop app includes a Help -> Statistics dialog for quick local download totals.
- Statistics cover All time, Today, This week, This month, and This year.
- The stats display both successful download counts and total downloaded data size.
- Download history is stored locally in a SQLite database under the Windows AppData folder for OneTime.
- The application version is 1.1.0.

## Active runtime architecture

Opera
        ↓
OneTime extension
        ↓
localhost HTTP
        ↓
OneTime desktop app
        ↓
download service

## Project layout

- `desktop/` - Python + PySide6 desktop app and download engine.
- `extension/` - Opera extension files.
- `docs/` - setup and development notes.
- `tests/` - regression tests for the HTTP contract, UI, and download behavior.

## How OneTime works

1. The Opera extension checks the current browser tabs and sends a JSON payload to `http://127.0.0.1:8765/image-tabs`.
2. The OneTime desktop app listens only on `127.0.0.1` and validates the browser origin and payload version.
3. The app receives the image URLs in the main window and keeps only the new ones for the current session.
4. Successful downloads are recorded to a local SQLite history database and removed from the pending list.
5. The download service writes the original bytes directly to disk and preserves the filename when it can.

The desktop app must be running before the extension can transfer URLs.

## Development setup on Windows

Create a virtual environment and install the requirements:

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

## Statistics

Open Help -> Statistics in the desktop app to see local counts and sizes for the current download history.

The dialog includes:

- All time
- Today
- This week
- This month
- This year

Each period shows the number of successful downloads and the total downloaded data size.

The statistics are stored in a local SQLite database under the Windows AppData location used by OneTime:

%APPDATA%\OneTime\download_history.db

## Run tests

pytest -q
