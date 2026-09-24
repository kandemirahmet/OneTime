from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _default_database_path() -> Path:
    app_data_root = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(app_data_root).expanduser() / "OneTime" / "download_history.db"


def _coerce_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def initialize_database(db_path: str | os.PathLike[str] | None = None) -> Path:
    target = Path(db_path).expanduser() if db_path is not None else _default_database_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        connection = sqlite3.connect(str(target))
    except sqlite3.Error as exc:
        raise RuntimeError(f"Unable to open the local OneTime download history database at {target}: {exc}") from exc

    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                downloaded_at TEXT NOT NULL,
                url TEXT NOT NULL,
                filename TEXT NOT NULL,
                destination TEXT NOT NULL,
                file_size INTEGER NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_downloads_downloaded_at ON downloads (downloaded_at)")
        connection.commit()
    except sqlite3.Error as exc:
        connection.close()
        raise RuntimeError(f"The OneTime download history database is unreadable at {target}: {exc}") from exc

    connection.close()
    return target


def record_success(
    url: str,
    filename: str,
    destination: str,
    file_size: int,
    downloaded_at: datetime | None = None,
    db_path: str | os.PathLike[str] | None = None,
) -> int:
    if not url:
        raise ValueError("url is required")
    if not filename:
        raise ValueError("filename is required")

    target = initialize_database(db_path)
    timestamp = _coerce_utc(downloaded_at).isoformat().replace("+00:00", "Z")

    with sqlite3.connect(str(target)) as connection:
        cursor = connection.execute(
            "INSERT INTO downloads (downloaded_at, url, filename, destination, file_size) VALUES (?, ?, ?, ?, ?)",
            (timestamp, url, filename, destination, int(file_size)),
        )
        connection.commit()
        return int(cursor.lastrowid)


def _period_totals(rows: list[tuple[datetime, int]], as_of: datetime) -> dict[str, int]:
    if not rows:
        return {"count": 0, "bytes": 0}

    count = 0
    total_bytes = 0
    for downloaded_at, file_size in rows:
        if downloaded_at <= as_of:
            count += 1
            total_bytes += file_size
    return {"count": count, "bytes": total_bytes}


def _load_rows(db_path: str | os.PathLike[str] | None = None) -> list[tuple[datetime, int]]:
    target = initialize_database(db_path)
    with sqlite3.connect(str(target)) as connection:
        rows = connection.execute(
            "SELECT downloaded_at, file_size FROM downloads ORDER BY downloaded_at ASC"
        ).fetchall()

    parsed: list[tuple[datetime, int]] = []
    for stored_at, file_size in rows:
        try:
            parsed_at = datetime.fromisoformat(stored_at.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            continue
        parsed.append((parsed_at, int(file_size)))
    return parsed


def get_statistics(
    as_of: datetime | None = None,
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, dict[str, int]]:
    as_of_utc = _coerce_utc(as_of)
    rows = _load_rows(db_path)

    local_now = as_of_utc.astimezone()
    start_of_today = datetime.combine(local_now.date(), datetime.min.time()).astimezone().astimezone(timezone.utc)
    end_of_today = start_of_today + timedelta(days=1)

    start_of_week = local_now - timedelta(days=local_now.weekday())
    start_of_week_dt = datetime.combine(start_of_week.date(), datetime.min.time()).astimezone().astimezone(timezone.utc)
    end_of_week = start_of_week_dt + timedelta(days=7)

    start_of_month = datetime(local_now.year, local_now.month, 1, 0, 0, tzinfo=local_now.tzinfo or timezone.utc)
    start_of_month_utc = start_of_month.astimezone(timezone.utc)
    if local_now.month == 12:
        next_month = datetime(local_now.year + 1, 1, 1, 0, 0, tzinfo=local_now.tzinfo or timezone.utc)
    else:
        next_month = datetime(local_now.year, local_now.month + 1, 1, 0, 0, tzinfo=local_now.tzinfo or timezone.utc)
    end_of_month = next_month.astimezone(timezone.utc)

    start_of_year = datetime(local_now.year, 1, 1, 0, 0, tzinfo=local_now.tzinfo or timezone.utc)
    start_of_year_utc = start_of_year.astimezone(timezone.utc)
    end_of_year = datetime(local_now.year + 1, 1, 1, 0, 0, tzinfo=local_now.tzinfo or timezone.utc).astimezone(timezone.utc)

    def period_summary(start: datetime, end: datetime | None = None) -> dict[str, int]:
        total_count = 0
        total_bytes = 0
        for downloaded_at, file_size in rows:
            if downloaded_at < start:
                continue
            if end is not None and downloaded_at >= end:
                continue
            total_count += 1
            total_bytes += file_size
        return {"count": total_count, "bytes": total_bytes}

    statistics: dict[str, dict[str, int]] = {
        "all_time": {"count": 0, "bytes": 0},
        "today": {"count": 0, "bytes": 0},
        "this_week": {"count": 0, "bytes": 0},
        "this_month": {"count": 0, "bytes": 0},
        "this_year": {"count": 0, "bytes": 0},
    }

    statistics["all_time"] = {"count": len(rows), "bytes": sum(file_size for _, file_size in rows)}
    statistics["today"] = period_summary(start_of_today, end_of_today)
    statistics["this_week"] = period_summary(start_of_week_dt, end_of_week)
    statistics["this_month"] = period_summary(start_of_month_utc, end_of_month)
    statistics["this_year"] = period_summary(start_of_year_utc, end_of_year)

    return statistics
