# OneTime development notes

## Release identity

The current release is OneTime v1.0.0. The desktop application and browser extension share the same version value for the first stable release, while the HTTP payload contract remains version 1 and is intentionally not changed in this release.

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

## Current implementation

- `extension/background.js` collects image tabs and sends the versioned `image_tabs` JSON payload to the local desktop HTTP listener.
- `desktop/app/services/ipc_adapter.py` binds only to `127.0.0.1` and validates the browser extension Origin and payload contract.
- `desktop/app/windows/main_window.py` receives the image URLs, stores the last output folder in `QSettings`, and opens the folder when requested.
- `desktop/app/services/download_service.py` writes the original bytes directly to disk and preserves `Content-Disposition` filenames when present.

## Desktop app

The desktop app is Python-based and uses PySide6:

python desktop\app\main.py

The desktop app must be running before the extension can send image URLs over the local HTTP transport.

## Extension

Use the extension manifest v3 and load the unpacked extension in Opera by opening `opera:extensions` and enabling Developer Mode.

The extension uses `http://127.0.0.1:8765/*` host permissions and sends JSON requests to `/image-tabs`.

## Download rules

The engine must write bytes directly to disk, preserve the filename from `Content-Disposition` whenever possible, and fall back to the image filename from the URL. It must not perform image conversion, recompression, resizing, or content rewrites.

