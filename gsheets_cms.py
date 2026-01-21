import json
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import gspread
from dateutil import parser as date_parser
from google.oauth2.service_account import Credentials


REQUIRED_COLUMNS = ["Timestamp", "Image_URL", "AI_Caption", "Status", "Scheduled_Time"]


@dataclass(frozen=True)
class SheetConfig:
    sheet_id: str
    worksheet: str = "Buffer"


class SheetRateLimitError(RuntimeError):
    pass


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_time(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        dt = date_parser.parse(s)
        if dt.tzinfo is None:
            # Assume UTC if sheet stores naive timestamps
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def load_service_account_info_from_env() -> Optional[Dict[str, Any]]:
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            return None

    file_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
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


def _with_backoff(fn, *, tries: int = 6, base_sleep: float = 0.5):
    last_exc = None
    for attempt in range(tries):
        try:
            return fn()
        except Exception as exc:  # gspread throws various exceptions
            last_exc = exc
            sleep = base_sleep * (2**attempt) + random.random() * 0.25
            time.sleep(min(sleep, 8.0))
    raise SheetRateLimitError(str(last_exc))


def open_worksheet(client: gspread.Client, cfg: SheetConfig) -> gspread.Worksheet:
    sh = _with_backoff(lambda: client.open_by_key(cfg.sheet_id))
    try:
        ws = _with_backoff(lambda: sh.worksheet(cfg.worksheet))
    except Exception:
        ws = _with_backoff(
            lambda: sh.add_worksheet(title=cfg.worksheet, rows=1000, cols=20)
        )
    return ws


def ensure_headers(ws: gspread.Worksheet) -> List[str]:
    values = _with_backoff(lambda: ws.get_all_values())
    if not values:
        _with_backoff(lambda: ws.append_row(REQUIRED_COLUMNS))
        return REQUIRED_COLUMNS

    header = [c.strip() for c in (values[0] or [])]
    if header[: len(REQUIRED_COLUMNS)] != REQUIRED_COLUMNS:
        # Make sure required columns exist; keep extra columns if present
        merged = REQUIRED_COLUMNS + [
            c for c in header if c and c not in REQUIRED_COLUMNS
        ]
        _with_backoff(lambda: ws.update([merged], "1:1"))
        return merged

    return header


def list_rows(ws: gspread.Worksheet) -> List[Dict[str, Any]]:
    values = _with_backoff(lambda: ws.get_all_values())
    if not values:
        return []

    header = values[0]
    rows = []
    for idx, row in enumerate(values[1:], start=2):
        item = {header[i]: (row[i] if i < len(row) else "") for i in range(len(header))}
        item["_row_number"] = idx
        rows.append(item)
    return rows


def append_scheduled_post(
    ws: gspread.Worksheet,
    image_url: str,
    ai_caption: str,
    scheduled_time_iso: str,
    *,
    timestamp_iso: Optional[str] = None,
) -> int:
    timestamp_iso = timestamp_iso or _utc_now_iso()
    row = [timestamp_iso, image_url, ai_caption, "Scheduled", scheduled_time_iso]
    _with_backoff(lambda: ws.append_row(row))
    # Can't reliably read back row number without extra read; return -1.
    return -1


def update_caption(
    ws: gspread.Worksheet, row_number: int, caption: str, header: List[str]
) -> None:
    try:
        col = header.index("AI_Caption") + 1
    except ValueError:
        raise RuntimeError("Sheet missing AI_Caption column")
    _with_backoff(lambda: ws.update_cell(row_number, col, caption))


def update_status(
    ws: gspread.Worksheet, row_number: int, status: str, header: List[str]
) -> None:
    try:
        col = header.index("Status") + 1
    except ValueError:
        raise RuntimeError("Sheet missing Status column")
    _with_backoff(lambda: ws.update_cell(row_number, col, status))


def find_due_scheduled(
    rows: List[Dict[str, Any]], now_utc: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    now_utc = now_utc or datetime.now(timezone.utc)
    due = []
    for r in rows:
        if str(r.get("Status", "")).strip().lower() != "scheduled":
            continue
        dt = _parse_time(r.get("Scheduled_Time"))
        if dt and now_utc >= dt:
            due.append(r)
    # Oldest first
    due.sort(
        key=lambda x: _parse_time(x.get("Scheduled_Time"))
        or datetime.min.replace(tzinfo=timezone.utc)
    )
    return due
