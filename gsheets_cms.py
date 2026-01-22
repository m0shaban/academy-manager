import json
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import gspread
from dateutil import parser as date_parser
from google.oauth2.service_account import Credentials


REQUIRED_COLUMNS = [
    "Timestamp",
    "Image_URL",
    "AI_Caption",
    "Status",
    "Scheduled_Time",
    "Source",
]


@dataclass(frozen=True)
class SheetConfig:
    sheet_id: str
    worksheet: str = "Buffer"


class SheetRateLimitError(RuntimeError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def utc_now_iso() -> str:
    return _utc_now().isoformat()


def parse_time_utc(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        dt = date_parser.parse(s)
    except Exception:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_service_account_info_from_env() -> Optional[Dict[str, Any]]:
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            return None

    file_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    return None


def make_gspread_client(service_account_info: Dict[str, Any]) -> gspread.Client:
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    return gspread.authorize(creds)


def _with_backoff(fn, *, tries: int = 7, base_sleep: float = 0.6):
    last_exc: Optional[BaseException] = None
    for attempt in range(tries):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            sleep = base_sleep * (2**attempt) + random.random() * 0.25
            time.sleep(min(sleep, 10.0))
    if last_exc is None:
        raise SheetRateLimitError("Unknown error")
    msg = str(last_exc).strip() or repr(last_exc)
    raise SheetRateLimitError(f"{type(last_exc).__name__}: {msg}")


def open_worksheet(client: gspread.Client, cfg: SheetConfig) -> gspread.Worksheet:
    sh = _with_backoff(lambda: client.open_by_key(cfg.sheet_id))
    try:
        return _with_backoff(lambda: sh.worksheet(cfg.worksheet))
    except Exception:
        return _with_backoff(
            lambda: sh.add_worksheet(title=cfg.worksheet, rows=1000, cols=30)
        )


def ensure_headers(ws: gspread.Worksheet) -> List[str]:
    values = _with_backoff(lambda: ws.get_all_values())
    if not values:
        _with_backoff(lambda: ws.append_row(REQUIRED_COLUMNS))
        return REQUIRED_COLUMNS

    header = [str(c).strip() for c in (values[0] or []) if str(c).strip()]

    # Ensure required columns exist; preserve extra columns.
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing or header[: len(REQUIRED_COLUMNS)] != REQUIRED_COLUMNS:
        merged = REQUIRED_COLUMNS + [c for c in header if c not in REQUIRED_COLUMNS]
        _with_backoff(lambda: ws.update([merged], "1:1"))
        return merged

    return header


def list_rows(ws: gspread.Worksheet) -> List[Dict[str, Any]]:
    values = _with_backoff(lambda: ws.get_all_values())
    if not values:
        return []

    header = [str(c).strip() for c in (values[0] or [])]
    rows: List[Dict[str, Any]] = []
    for idx, row in enumerate(values[1:], start=2):
        item = {header[i]: (row[i] if i < len(row) else "") for i in range(len(header))}
        item["_row_number"] = idx
        rows.append(item)
    return rows


def append_row(ws: gspread.Worksheet, header: List[str], row: Dict[str, Any]) -> None:
    payload = ["" for _ in header]
    for i, key in enumerate(header):
        if key in row:
            payload[i] = str(row[key]) if row[key] is not None else ""
    _with_backoff(lambda: ws.append_row(payload))


def update_fields(ws: gspread.Worksheet, row_number: int, header: List[str], fields: Dict[str, Any]) -> None:
    for key, value in fields.items():
        if key not in header:
            continue
        col = header.index(key) + 1
        _with_backoff(lambda: ws.update_cell(row_number, col, "" if value is None else str(value)))


def delete_row(ws: gspread.Worksheet, row_number: int) -> None:
    _with_backoff(lambda: ws.delete_rows(row_number))


def find_due_scheduled(rows: List[Dict[str, Any]], now_utc: Optional[datetime] = None) -> List[Dict[str, Any]]:
    now_utc = now_utc or _utc_now()
    due: List[Dict[str, Any]] = []
    for r in rows:
        if str(r.get("Status", "")).strip().lower() != "scheduled":
            continue
        dt = parse_time_utc(r.get("Scheduled_Time"))
        if dt and now_utc >= dt:
            due.append(r)
    due.sort(key=lambda x: parse_time_utc(x.get("Scheduled_Time")) or _utc_now())
    return due


def has_scheduled_within(rows: List[Dict[str, Any]], *, start: datetime, end: datetime) -> bool:
    for r in rows:
        if str(r.get("Status", "")).strip().lower() != "scheduled":
            continue
        dt = parse_time_utc(r.get("Scheduled_Time"))
        if dt and start <= dt <= end:
            return True
    return False
