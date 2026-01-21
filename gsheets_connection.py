from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

import streamlit as st
from streamlit.connections import BaseConnection

from gsheets_cms import SheetConfig, ensure_headers, list_rows, make_gspread_client, open_worksheet


@dataclass(frozen=True)
class GoogleSheetsConfig:
    sheet_id: str
    worksheet: str = "Buffer"


class GoogleSheetsConnection(BaseConnection[GoogleSheetsConfig]):
    """Streamlit Connection wrapper around gspread.

    Secrets format (recommended):

    [connections.gsheets]
    sheet_id = "..."
    worksheet = "Buffer"

    # Provide service account either as dict or as JSON string
    # Option A:
    [gcp_service_account]
    type = "service_account"
    ...

    # Option B:
    GOOGLE_SERVICE_ACCOUNT_JSON = "{...}"
    """

    def _connect(self) -> GoogleSheetsConfig:
        cfg = self._secrets.to_dict() if self._secrets else {}
        sheet_id = str(cfg.get("sheet_id", "") or "").strip()
        worksheet = str(cfg.get("worksheet", "Buffer") or "Buffer").strip()
        if not sheet_id:
            raise RuntimeError("Missing connections.gsheets.sheet_id in Streamlit secrets")
        return GoogleSheetsConfig(sheet_id=sheet_id, worksheet=worksheet or "Buffer")

    def _service_account_info(self) -> Dict[str, Any]:
        # Preferred: [gcp_service_account] dict
        try:
            svc = st.secrets.get("gcp_service_account", None)
            if svc:
                return dict(svc)
        except Exception:
            pass

        # Fallback: GOOGLE_SERVICE_ACCOUNT_JSON string
        try:
            raw = st.secrets.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
            raw = str(raw or "").strip()
            if raw:
                return json.loads(raw)
        except Exception:
            pass

        raise RuntimeError("Missing service account credentials in Streamlit secrets")

    def worksheet(self):
        cfg = self._connect()
        client = make_gspread_client(self._service_account_info())
        ws = open_worksheet(client, SheetConfig(sheet_id=cfg.sheet_id, worksheet=cfg.worksheet))
        header = ensure_headers(ws)
        return ws, header

    def read(self, *, ttl: Optional[int] = 0):
        def _read():
            ws, _header = self.worksheet()
            return list_rows(ws)

        return self._cache(_read, ttl=ttl)
