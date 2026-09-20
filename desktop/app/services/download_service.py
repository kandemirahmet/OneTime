from __future__ import annotations

import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from http.client import IncompleteRead
from pathlib import Path


IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".avif",
    ".svg",
}

CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tif",
    "image/avif": ".avif",
    "image/svg+xml": ".svg",
}

WINDOWS_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
MAX_FILENAME_LENGTH = 255


def sanitize_filename(name: str) -> str:
    value = str(name or "").strip().replace("\x00", "")
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", value)
    value = value.rstrip(" .")
    if not value:
        value = "image"

    stem, suffix = os.path.splitext(value)
    stem = stem.rstrip(" .")
    suffix = suffix.rstrip(" .")
    if not stem:
        stem = "image"
    if suffix and not suffix.startswith("."):
        suffix = f".{suffix}"
    if not suffix:
        suffix = ""

    if stem.upper() in WINDOWS_RESERVED_NAMES:
        stem = f"{stem}_"

    candidate = f"{stem}{suffix}".rstrip(" .") or "image"
    if len(candidate) > MAX_FILENAME_LENGTH:
        if suffix:
            available = MAX_FILENAME_LENGTH - len(suffix)
            stem = stem[: max(1, available)].rstrip(" .") or "image"
            candidate = f"{stem}{suffix}"
        else:
            candidate = candidate[:MAX_FILENAME_LENGTH].rstrip(" .") or "image"

    if candidate.upper() in WINDOWS_RESERVED_NAMES:
        candidate = f"{candidate}_"
    if len(candidate) > MAX_FILENAME_LENGTH:
        candidate = candidate[:MAX_FILENAME_LENGTH].rstrip(" .") or "image"

    return candidate or "image"


def filename_from_content_disposition(value: str | None) -> str | None:
    if not value:
        return None

    match = re.search(r"filename\*\s*=\s*(?:UTF-8''|utf-8'')([^;]+)", value, re.I)
    if match:
        return sanitize_filename(urllib.parse.unquote(match.group(1).strip().strip('"')))

    match = re.search(r'filename\s*=\s*"([^"]+)"', value, re.I)
    if not match:
        match = re.search(r'filename\s*=\s*([^;]+)', value, re.I)
    if match:
        return sanitize_filename(match.group(1).strip().strip('"'))
    return None


def filename_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    name = Path(urllib.parse.unquote(parsed.path)).name
    if not name or parsed.path.endswith("/"):
        name = "image"
    filename = sanitize_filename(name)
    if Path(filename).suffix.lower() in IMAGE_EXTENSIONS:
        return filename

    format_value = parsed.query and urllib.parse.parse_qs(parsed.query).get("format", [None])[0]
    if isinstance(format_value, str):
        format_extension = f".{format_value.strip().lower().lstrip('.')}"
        if format_extension in IMAGE_EXTENSIONS:
            return f"{filename}{format_extension}"
    return filename


def is_likely_image_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False
        path = parsed.path.lower()
        return any(path.endswith(ext) for ext in IMAGE_EXTENSIONS)
    except ValueError:
        return False


def unique_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 2
    while True:
        candidate = directory / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def download_original(url: str, output_dir: Path) -> Path:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "OneTime/0.1",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        },
        method="GET",
    )

    output_dir = output_dir.expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            content_type = response.headers.get_content_type()
            if not content_type.startswith("image/"):
                raise ValueError(f"Server returned non-image content type: {content_type!r}")

            filename = filename_from_content_disposition(response.headers.get("Content-Disposition"))
            if not filename:
                filename = filename_from_url(url)
                if Path(filename).suffix.lower() not in IMAGE_EXTENSIONS:
                    filename += CONTENT_TYPE_EXTENSIONS.get(content_type, "")

            target = unique_path(output_dir, filename)
            fd, temp_name = tempfile.mkstemp(
                prefix=f".{(Path(target.name).stem or 'image').strip() or 'image'}.",
                suffix=f"{Path(target.name).suffix or '.tmp'}",
                dir=str(output_dir),
            )
            temp_path = Path(temp_name)

            try:
                content_length = response.headers.get("Content-Length")
                expected_length = int(content_length) if content_length is not None else None
                bytes_written = 0

                try:
                    with os.fdopen(fd, "wb") as file:
                        while True:
                            chunk = response.read(1024 * 1024)
                            if not chunk:
                                break
                            file.write(chunk)
                            bytes_written += len(chunk)
                except IncompleteRead as exc:
                    raise ValueError(
                        f"Incomplete image download: expected {expected_length or 'unknown'} bytes but received {len(exc.partial)}."
                    ) from exc

                if expected_length is not None and bytes_written != expected_length:
                    raise ValueError(
                        f"Incomplete image download: expected {expected_length} bytes but received {bytes_written}."
                    )

                os.replace(temp_path, target)
                return target
            except Exception:
                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass
                raise
    except Exception:
        raise
