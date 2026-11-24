"""Data loader: 1-min parquet daily files -> clean 5-min OHLCV frame.

Column in raw files is `ts` (tz-aware +05:30). Index data has volume = 0,
so a deterministic bar-range volume proxy is used for VWAP / Market Profile.
"""

from __future__ import annotations

import re
import json
import time
import threading
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

# Bound EVERY Angel One HTTP call. A hung socket used to freeze a background
# refresh forever -> the dashboard showed 38-minute-old data. (6s connect, 12s read)
try:
    import requests as _requests
    _orig_request = _requests.Session.request
    def _bounded_request(self, method, url, **kw):
        kw.setdefault("timeout", (6, 12))
        return _orig_request(self, method, url, **kw)
    _requests.Session.request = _bounded_request
except Exception:  # pragma: no cover
    pass

import config

TIME_KEYS = ["ts", "timestamp", "datetime", "date_time", "time", "date", "dt"]
OPEN_KEYS = ["open", "o"]
HIGH_KEYS = ["high", "h"]
LOW_KEYS = ["low", "l"]
CLOSE_KEYS = ["close", "c", "last", "ltp", "lastprice"]
VOL_KEYS = ["volume", "vol", "v"]
OI_KEYS = ["oi", "openinterest", "open_interest"]


def _norm(s: str) -> str:
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


def _pick(cols, candidates):
    norm = {_norm(c): c for c in cols}
    for key in candidates:
        if key in norm:
            return norm[key]
    return None


def _parse_dates(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce", utc=False)
    if parsed.notna().mean() < 0.5:
        parsed = pd.to_datetime(series, errors="coerce", dayfirst=True)
    if parsed.dt.tz is not None:
        parsed = parsed.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    return parsed


def list_parquet(last_days: int | None = None) -> list[Path]:
    if not config.RAW_DIR.exists():
        return []
    files = sorted(config.RAW_DIR.rglob("*.parquet"))
    return files[-last_days:] if last_days else files


def find_csv() -> Path | None:
    if not config.DATA_DIR.exists():
        return None
    files = [p for p in config.DATA_DIR.glob("*.csv")
             if not p.name.upper().startswith("SAMPLE")]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def _normalise(raw: pd.DataFrame) -> pd.DataFrame:
    raw.columns = [str(c).strip() for c in raw.columns]
    mapping = {
        "timestamp": _pick(raw.columns, TIME_KEYS),
        "open": _pick(raw.columns, OPEN_KEYS),
        "high": _pick(raw.columns, HIGH_KEYS),
        "low": _pick(raw.columns, LOW_KEYS),
        "close": _pick(raw.columns, CLOSE_KEYS),
        "volume": _pick(raw.columns, VOL_KEYS),
        "oi": _pick(raw.columns, OI_KEYS),
    }
    if any(mapping[k] is None for k in ("open", "high", "low", "close")):
        raise ValueError(f"OHLC columns nahi mile. Got {list(raw.columns)}")

    out = pd.DataFrame()
    out["timestamp"] = (_parse_dates(raw[mapping["timestamp"]])
                        if mapping["timestamp"] else
                        pd.date_range(end=pd.Timestamp.now().floor("min"),
                                      periods=len(raw), freq="1min"))
    for std, src in mapping.items():
        if std in ("timestamp",) or src is None:
            continue
        out[std] = pd.to_numeric(raw[src], errors="coerce")
    if out["volume"].isna().all() or (out["volume"] == 0).all():
        # Index feed has no volume: bar range is a sensible activity proxy.
        out["volume"] = 1.0 + (out["high"] - out["low"]).fillna(0).clip(0, 200)
    if "oi" not in out or out["oi"].isna().all():
        out["oi"] = 0
    return out.dropna(subset=["timestamp", "close"]).sort_values("timestamp")


def resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if minutes <= 1:
        return df.reset_index(drop=True)
    rule = f"{minutes}min"
    agg = {"open": "first", "high": "max", "low": "min",
           "close": "last", "volume": "sum", "oi": "last"}
    out = (df.set_index("timestamp").resample(rule, label="left", closed="left")
           .agg(agg).dropna(subset=["open", "high", "low", "close"]).reset_index())
    # Keep only NSE cash-market hours.
    t = out["timestamp"].dt.time
    out = out[(t >= pd.Timestamp("09:15").time()) &
              (t <= pd.Timestamp("15:30").time())].reset_index(drop=True)
    return out


def load_data(last_days: int | None = None, minutes: int | None = None) -> pd.DataFrame:
    minutes = minutes or config.TIMEFRAME_MINUTES
    if config.USE_PARQUET:
        files = list_parquet(last_days or config.LOAD_LAST_DAYS)
        if not files:
            return pd.DataFrame()
        chunks = [_normalise(pd.read_parquet(f)) for f in files]
        raw = pd.concat(chunks, ignore_index=True)
    else:
        path = find_csv()
        if path is None:
            return pd.DataFrame()
        raw = _normalise(pd.read_csv(path))
    return resample(raw, minutes)


_SMART = None   # module-level session cache (login once, reuse)
_SMART_LOCK = threading.Lock()
_FEED_CRED = None   # (auth_token, api_key, client_id, feed_token) for WebSocket


def _smart_connect(force=False):
    """Login with TOTP ONCE, reuse the session for all live calls (thread-safe)."""
    global _SMART, _FEED_CRED
    if _SMART is not None and not force:
        return _SMART
    with _SMART_LOCK:
        if _SMART is not None and not force:
            return _SMART
        from SmartApi import SmartConnect
        import pyotp

        c = config.angel_credentials()
        obj = SmartConnect(api_key=c["api_key"])
        totp = pyotp.TOTP(c["totp_secret"]).now() if c.get("totp_secret") else c.get("totp", "")
        sess = obj.generateSession(c["client_id"], c["password"], totp)
        if not (sess.get("status") and sess.get("data")):
            raise RuntimeError(f"Angel One login failed: {sess.get('message')}")
        # NOTE: generateSession() already sets the Bearer access_token internally.
        # Calling setAccessToken(jwtToken) here would overwrite it with a bare JWT -> "Invalid Token".
        d = sess["data"]
        _FEED_CRED = (d.get("jwtToken") or d.get("access_token"), c["api_key"],
                      c["client_id"], d.get("feedToken"))
        _SMART = obj
        return obj


def feed_credentials():
    """WebSocket credentials from the same login (starts session if needed)."""
    if not _FEED_CRED:
        _smart_connect()
    return _FEED_CRED


def fetch_live_ltp(symbol: str | None = None, token: str = "99926000") -> float | None:
    """Nifty index LTP (default) via ltpData(token 99926000)."""
    if not (config.LIVE_ENABLED and config.all_credentials_present()):
        return None
    try:
        obj = _smart_connect()
        data = obj.ltpData(config.EXCHANGE, symbol or "NIFTY 50", token)
        if data.get("status") and data.get("data"):
            return float(data["data"]["ltp"])
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[live feed] {exc}")
        return None


_OPTS_CACHE = Path(__file__).resolve().parent / "data" / "cache" / "angel_nifty_options.json"


def _nifty_options():
    """NIFTY option tokens (scrip master, cached once)."""
    if _OPTS_CACHE.exists():
        try:
            return json.loads(_OPTS_CACHE.read_text(encoding="utf-8"))
        except Exception:
            pass
    url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    raw = json.loads(urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read())
    opts = []
    for x in raw:
        if x.get("name") == "NIFTY" and x.get("instrumenttype") == "OPTIDX":
            sym = x.get("symbol", "")
            side = sym[-2:]
            if side not in ("CE", "PE"):
                continue
            opts.append({"token": x["token"], "strike": int(float(x["strike"]) / 100),
                         "expiry": x["expiry"], "side": side, "symbol": sym})
    _OPTS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _OPTS_CACHE.write_text(json.dumps(opts), encoding="utf-8")
    return opts


_FUT_CACHE = Path(__file__).resolve().parent / "data" / "cache" / "angel_nifty_futures.json"
_FUT_LTP = None       # (fetched_at, ltp)


def _nifty_futures():
    """NIFTY futures tokens from scrip master (cached once, nearest expiry picked live)."""
    if _FUT_CACHE.exists():
        try:
            return json.loads(_FUT_CACHE.read_text(encoding="utf-8"))
        except Exception:
            pass
    url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    raw = json.loads(urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read())
    futs = [{"token": x["token"], "symbol": x["symbol"], "expiry": x["expiry"]}
            for x in raw if x.get("name") == "NIFTY" and x.get("instrumenttype") == "FUTIDX"]
    _FUT_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _FUT_CACHE.write_text(json.dumps(futs), encoding="utf-8")
    return futs


def fetch_futures_ltp(ttl: int = 60):
    """REAL NIFTY futures LTP (nearest expiry >= today). No spot-10 fabrication."""
    global _FUT_LTP
    now = time.time()
    if _FUT_LTP and now - _FUT_LTP[0] < ttl:
        return _FUT_LTP[1]
    if not (config.LIVE_ENABLED and config.all_credentials_present()):
        return None
    try:
        from datetime import datetime
        obj = _smart_connect()
        futs = _nifty_futures()
        exps = sorted(set(f["expiry"] for f in futs),
                      key=lambda e: datetime.strptime(e, "%d%b%Y"))
        today = datetime.now().date()
        nearest = next((e for e in exps if datetime.strptime(e, "%d%b%Y").date() >= today),
                       exps[0] if exps else None)
        f = next((x for x in futs if x["expiry"] == nearest), None)
        if not f:
            return None
        r = obj.ltpData("NFO", f["symbol"], f["token"])
        if r.get("status") and r.get("data"):
            v = float(r["data"]["ltp"])
            _FUT_LTP = (now, v)
            return v
    except Exception as exc:  # noqa: BLE001
        print(f"[futures ltp] {exc}")
    return None


def fetch_live_oi_chain(spot: float | None = None, max_strikes: int = 8) -> pd.DataFrame | None:
    """LIVE option chain WITH real open interest via Angel One getMarketData(FULL)."""
    if not (config.LIVE_ENABLED and config.all_credentials_present()):
        return None
    try:
        from datetime import datetime
        obj = _smart_connect()
        if spot is None:
            spot = fetch_live_ltp("NIFTY 50", "99926000") or 25800
        opts = _nifty_options()
        exps = sorted(set(o["expiry"] for o in opts),
                      key=lambda e: datetime.strptime(e, "%d%b%Y"))
        today = datetime.now()
        nearest = next((e for e in exps if datetime.strptime(e, "%d%b%Y") >= today),
                       exps[0] if exps else None)
        if not nearest:
            return None
        atm = int(round(float(spot) / config.STRIKE_STEP) * config.STRIKE_STEP)
        lo, hi = atm - max_strikes * config.STRIKE_STEP, atm + max_strikes * config.STRIKE_STEP
        sel = [o for o in opts if o["expiry"] == nearest and lo <= o["strike"] <= hi]
        tokens = list(dict.fromkeys(o["token"] for o in sel))
        if not tokens:
            return None
        rows = []
        for i in range(0, len(tokens), 50):
            r = obj.getMarketData("FULL", {"NFO": tokens[i:i + 50]})
            for q in (r.get("data") or {}).get("fetched", []):
                m = re.search(r"(\d{5})(CE|PE)$", str(q.get("tradingSymbol", "")))
                if not m:
                    continue
                rows.append({"strike": int(m.group(1)), "side": m.group(2),
                             "ltp": float(q.get("ltp") or 0),
                             "oi": float(q.get("opnInterest") or 0)})
        df = pd.DataFrame(rows)
        return df if not df.empty else None
    except Exception as exc:  # noqa: BLE001
        print(f"[live OI chain] {exc}")
        return None


_BASE_CACHE = None       # (fetched_at, 1-minute real bars)
_DERIVED = {}             # mins -> rows
_RATE_LIMIT_UNTIL = 0.0
_FAIL_STREAK = 0
_LAST_ATTEMPT = 0.0
_CANDLE_LOCK = threading.Lock()
_BAR_FILE = Path(__file__).resolve().parent / "data" / "cache" / "last_good_bars.json"


def _load_persisted_bars():
    """Last REAL bars on disk — chart never goes blank during an API outage."""
    global _BASE_CACHE
    if _BASE_CACHE is not None:
        return
    try:
        d = json.loads(_BAR_FILE.read_text(encoding="utf-8"))
        if d.get("bars"):
            _BASE_CACHE = (float(d.get("ts", 0)), d["bars"])
    except Exception:
        pass


def _save_persisted_bars(ts, bars):
    try:
        _BAR_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _BAR_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps({"ts": ts, "bars": bars}), encoding="utf-8")
        tmp.replace(_BAR_FILE)
    except Exception:
        pass


_load_persisted_bars()      # restore last real bars at import


def _bucket(rows: list[dict], mins: int) -> list[dict]:
    """Group real 1-min bars into exact clock-aligned mins bars."""
    out, cur, key = [], None, None
    for r in rows:
        hh, mm = r["t"].split(":")[:2]
        b = (int(hh) * 60 + int(mm)) // mins * mins
        if b != key:
            if cur:
                out.append(cur)
            cur = {"d": r.get("d"), "t": r["t"], "o": r["o"], "h": r["h"],
                   "l": r["l"], "c": r["c"]}
            key = b
        else:
            cur["h"] = max(cur["h"], r["h"])
            cur["l"] = min(cur["l"], r["l"])
            cur["c"] = r["c"]
    if cur:
        out.append(cur)
    return out


def fetch_index_candles(mins: int = 3, ttl: int = 240) -> list[dict]:
    """ONE Angel One 1-min call -> derive 3/5/9/15 min. Persisted real fallback."""
    global _BASE_CACHE, _RATE_LIMIT_UNTIL, _FAIL_STREAK, _LAST_ATTEMPT
    now = time.time()
    cached = _DERIVED.get(mins)
    if cached and now - cached[0] < ttl:
        return cached[1]
    with _CANDLE_LOCK:
        # throttle ALL attempts: stale/persisted bars must never cause a call storm
        if now - _LAST_ATTEMPT >= ttl and now >= _RATE_LIMIT_UNTIL:
            _LAST_ATTEMPT = now
            if config.LIVE_ENABLED and config.all_credentials_present():
                try:
                    from datetime import datetime, timedelta
                    obj = _smart_connect()
                    t = datetime.now()
                    r = obj.getCandleData({
                        "exchange": config.EXCHANGE,
                        "symboltoken": "99926000",
                        "interval": "ONE_MINUTE",
                        "fromdate": (t - timedelta(days=3)).strftime("%Y-%m-%d %H:%M"),
                        "todate": t.strftime("%Y-%m-%d %H:%M"),
                    })
                    base_rows = []
                    for item in (r.get("data") or []):
                        stamp = str(item[0])
                        base_rows.append({"d": stamp[:10], "t": stamp[11:16],
                                          "o": float(item[1]), "h": float(item[2]),
                                          "l": float(item[3]), "c": float(item[4])})
                    if base_rows:
                        _BASE_CACHE = (now, base_rows)
                        _save_persisted_bars(now, base_rows)
                        _FAIL_STREAK = 0
                        _RATE_LIMIT_UNTIL = 0.0
                except Exception as exc:  # noqa: BLE001
                    _FAIL_STREAK += 1
                    if "rate" in str(exc).lower() or "denied" in str(exc).lower():
                        # 90s -> 180s -> 360s -> 720s -> 900s cap
                        back = min(900, 90 * (2 ** min(_FAIL_STREAK - 1, 4)))
                        _RATE_LIMIT_UNTIL = now + back
                        print(f"[candles] rate-limited; backing off {back}s")
    if not _BASE_CACHE:
        _load_persisted_bars()
    if not _BASE_CACHE:
        return []
    rows = _bucket(_BASE_CACHE[1], mins)
    _DERIVED[mins] = (time.time(), rows)
    return rows


def get_base_age() -> float:
    """Age of the real 1-min bars behind the chart (detects stale fallback data)."""
    return (time.time() - _BASE_CACHE[0]) if _BASE_CACHE else 1e9


def fetch_index_vwap() -> float | None:
    """Typical-price VWAP from TODAY's REAL 1-min OHLC bars.

    An index has no traded volume (Angel One returns volume=0, NSE has no VWAP
    field), so a volume-weighted index VWAP does not exist. The standard index
    proxy is the cumulative average of typical price (H+L+C)/3. Uses the exact
    same real bars already cached for the hero chart -> zero extra API calls.
    """
    # make sure the shared real-bar cache exists (parallel callers may race)
    fetch_index_candles(3)
    if not _BASE_CACHE:
        return None
    from datetime import datetime, timezone, timedelta
    today = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d")
    bars = [r for r in _BASE_CACHE[1]
            if r.get("d") == today and "09:15" <= r["t"] <= "15:30"]
    if not bars:
        return None
    vals = [(float(r["h"]) + float(r["l"]) + float(r["c"])) / 3 for r in bars]
    return sum(vals) / len(vals)


def fetch_live_chain(spot: float, expiry_label: str = "01DEC26") -> pd.DataFrame | None:
    """Fetch LTP for ATM +/- 4 strikes CE & PE from Angel One, if creds set."""
    if not (config.LIVE_ENABLED and config.all_credentials_present()):
        return None
    step = config.STRIKE_STEP
    atm = int(round(spot / step) * step)
    syms = []
    for k in range(atm - 4 * step, atm + 5 * step, step):
        for side in ("CE", "PE"):
            syms.append({"exchange": config.EXCHANGE,
                         "symbol": f"NIFTY {expiry_label} {k} {side}"})
    try:
        from SmartApi import SmartConnect
        import pyotp
        c = config.angel_credentials()
        obj = SmartConnect(api_key=c["api_key"])
        totp = pyotp.TOTP(c["totp_secret"]).now() if c.get("totp_secret") else c.get("totp", "")
        sess = obj.generateSession(c["client_id"], c["password"], totp)
        if sess.get("status") and sess.get("data"):
            obj.setAccessToken(sess["data"]["jwtToken"])
            try: obj.setFeedToken(sess["data"]["feedToken"])
            except Exception: pass
        elif c.get("refresh_token"):
            obj.renewAccessToken(c["refresh_token"], c["client_id"], c["api_key"])
        data = obj.getLTP(syms)
        rows = []
        for item in data.get("data", []):
            m = re.search(r"(\d{5})\s+(CE|PE)$", item.get("symbol", ""))
            if not m:
                continue
            rows.append({"strike": int(m.group(1)), "side": m.group(2),
                         "ltp": float(item["ltp"]), "oi": 0})
        return pd.DataFrame(rows) if rows else None
    except Exception as exc:  # noqa: BLE001
        print(f"[live chain] {exc}")
        return None
