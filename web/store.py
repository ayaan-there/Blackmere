"""Persistence abstraction: Supabase in production, local JSON for dev.

No fabricated data. All reads are filtered by day by the callers. The backend
uses the service-role key server-side; RLS stays enabled with no anon policies.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
LOCAL_FILE = ROOT / "data" / "cache" / "cloud_store.json"
TABLES = ("price_bars", "oi_samples", "session_rows", "app_cache")
_LOCK = threading.Lock()


class Store:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        self.enabled = bool(self.url and self.key)
        self._local = self._load_local()

    # ---------------- local dev fallback ----------------
    def _load_local(self) -> dict:
        try:
            d = json.loads(LOCAL_FILE.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                return {t: d.get(t, []) for t in TABLES}
        except Exception:
            pass
        return {t: [] for t in TABLES}

    def _save_local(self) -> None:
        try:
            LOCAL_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = LOCAL_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._local), encoding="utf-8")
            tmp.replace(LOCAL_FILE)
        except Exception:
            pass

    # ---------------- Supabase REST ----------------
    def _headers(self, prefer: str | None = None) -> dict:
        h = {"apikey": self.key, "Authorization": "Bearer " + self.key,
             "Content-Type": "application/json"}
        if prefer:
            h["Prefer"] = prefer
        return h

    def fetch(self, table: str, filters: dict | None = None,
              columns: str = "*", order: str | None = None,
              limit: int | None = None, offset: int = 0) -> list:
        if table not in TABLES:
            return []
        if not self.enabled:
            rows = self._local.get(table, [])
            if filters:
                rows = [r for r in rows if all(
                    str(r.get(k)) == str(v).split(".")[-1]
                    for k, v in filters.items())]
            return list(rows)
        params = {"select": columns}
        for k, v in (filters or {}).items():
            params[k] = "eq." + str(v)
        if order:
            params["order"] = order
        if limit:
            params["limit"] = str(min(int(limit), 1000))
        if offset:
            params["offset"] = str(int(offset))
        try:
            r = requests.get(f"{self.url}/rest/v1/{table}", headers=self._headers(),
                             params=params, timeout=(6, 20))
            if r.ok:
                return r.json()
        except Exception:
            pass
        return []

    def upsert(self, table: str, rows: list) -> bool:
        if not rows or table not in TABLES:
            return False
        if not self.enabled:
            with _LOCK:
                existing = self._local.setdefault(table, [])
                keys = {k for k in rows[0] if k not in ("updated_at",)}
                idx = {}
                for i, r in enumerate(existing):
                    idx[tuple(r.get(k) for k in sorted(keys))] = i
                for row in rows:
                    ik = tuple(row.get(k) for k in sorted(keys))
                    if ik in idx:
                        existing[idx[ik]] = row
                    else:
                        existing.append(row)
                        idx[ik] = len(existing) - 1
                self._save_local()
            return True
        try:
            r = requests.post(f"{self.url}/rest/v1/{table}",
                              headers=self._headers("resolution=merge-duplicates,return=minimal"),
                              json=rows, timeout=(6, 20))
            return r.ok
        except Exception:
            return False

    # ---------------- key/value app cache ----------------
    def get_cache(self, key: str, default=None):
        rows = self.fetch("app_cache", filters={"key": key}, columns="payload")
        if rows:
            return rows[0].get("payload", default)
        return default

    def set_cache(self, key: str, payload) -> bool:
        row = {"key": key, "payload": payload, "updated_at": time.time()}
        if not self.enabled:
            with _LOCK:
                rows = self._local.setdefault("app_cache", [])
                for i, r in enumerate(rows):
                    if r.get("key") == key:
                        rows[i] = row
                        break
                else:
                    rows.append(row)
                self._save_local()
            return True
        try:
            r = requests.post(f"{self.url}/rest/v1/app_cache",
                              headers=self._headers("resolution=merge-duplicates,return=minimal"),
                              json=[row], timeout=(6, 20))
            return r.ok
        except Exception:
            return False


STORE = Store()


def fetch_all(table: str, filters: dict | None = None, order: str | None = None,
              columns: str = "*", max_pages: int = 60) -> list:
    """Page through Supabase's 1000-row REST cap (no local fallback change)."""
    out, offset = [], 0
    for _ in range(max_pages):
        rows = STORE.fetch(table, filters=filters, columns=columns,
                           order=order, limit=1000, offset=offset)
        out.extend(rows)
        if len(rows) < 1000:
            break
        offset += 1000
    return out
