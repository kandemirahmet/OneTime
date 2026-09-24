# OneTime development notes

## Release identity

The current release is OneTime v1.1.0. The desktop application and Opera extension share the same version value, while the HTTP payload contract remains version 1 and is intentionally not changed in this release.

## Active runtime architecture

Opera
        ↓
OneTime extension
        ↓
localhost HTTP (`127.0.0.1:8765`)
        ↓
OneTime desktop app
        ↓
download service

## Current implementation

- `extension/background.js` scans the current Opera tabs for likely image URLs and sends a versioned `image_tabs` JSON payload to the local desktop HTTP listener.
- `desktop/app/services/ipc_adapter.py` binds only to `127.0.0.1`, validates the browser Origin, and enforces the JSON payload contract (`type`, `version`, `browser`, `request_id`, and `tabs`).
- `desktop/app/windows/main_window.py` receives the image URLs, deduplicates them for the current app session, manages the pending list, and exposes Help -> Statistics and About.
- `desktop/app/services/download_service.py` downloads the original bytes directly to disk, preserves the filename when possible, and keeps the byte-for-byte content behavior unchanged.
- `desktop/app/download_history.py` stores successful downloads in a local SQLite database and calculates the visible statistics periods.

## Local SQLite download history

Successful downloads are recorded in a SQLite database at:

%APPDATA%\OneTime\download_history.db

The table is named `downloads` and stores:

- `downloaded_at` - UTC ISO timestamp
- `url` - the original URL that was downloaded
- `filename` - the saved file name
- `destination` - the chosen output folder
- `file_size` - the final file size in bytes

This database is local to the user’s Windows profile and is intended to support the statistics dialog without affecting the browser or network protocol.

## Session-level completed URL tracking

The in-memory `MainWindow.completed_urls` set is used to prevent URLs already downloaded in the current OneTime session from being re-added. This is separate from the local SQLite history database and is intentionally reset when the application restarts.

The logic is:

- incoming URLs are compared against the current `self.urls` pending list;
- URLs already in `self.completed_urls` are ignored for the rest of the running session;
- successful downloads are removed from the pending list immediately;
- failed URLs remain available for retry and are not marked as completed.

This keeps the user experience stable without changing the on-disk history behavior or the HTTP protocol version.

## Statistics calculation

`desktop/app/download_history.py` loads the downloaded entries from the SQLite database and calculates period summaries for:

- All time
- Today
- This week
- This month
- This year

Each row contributes:

- a `count` of successful downloads in the selected period;
- a `bytes` total representing the sum of saved file sizes.

The dialog in `MainWindow.show_statistics_dialog()` displays these values in a user-friendly format.

## Relevant modules and files

- `desktop/app/main.py` - application startup, single-instance guard, and HTTP server startup.
- `desktop/app/version.py` - central version metadata used by the app and packaging.
- `desktop/app/windows/main_window.py` - UI, pending list, About dialog, and Statistics dialog.
- `desktop/app/services/ipc_adapter.py` - HTTP listener and payload validation.
- `desktop/app/services/download_service.py` - direct HTTP download logic.
- `desktop/app/download_history.py` - SQLite history management and statistics.
- `extension/background.js` - Opera extension payload generation.
- `extension/manifest.json` - extension metadata, including the version value.

## Runtime notes

The desktop app must already be running before the Opera extension sends image payloads. OneTime currently targets Opera, and the HTTP transport remains a local localhost-only interface with payload version 1.

The application is intentionally conservative about the protocol: it does not change the request path, validation rules, database file layout, or byte-preservation behavior between releases.

