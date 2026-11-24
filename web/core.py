"""Cloud-safe data core: TODAY-ONLY, no Streamlit, no recorded fallbacks.

Every value returned here comes from a live source or from today's persisted
rows. If nothing exists yet, empty values are returned — never another day's
data and never synthetic data.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timedelta, timezone

import config
import data_loader
import nse_live

from store import STORE

IST = timezone(timedelta(hours=5, minutes=30))
TFS = (3, 5, 9, 15)
TTL = {"spot": 60, "oi": 30, "nse": 60, "bars": 120}

_cache: dict[str, tuple[float, object]] = {}
_locks = {k: threading.Lock() for k in ("spot", "oi", "nse")}


PREVIEW_DAY = os.getenv("BLACKMERE_PREVIEW_DAY", "")


def today_str() -> str:
    return PREVIEW_DAY or datetime.now(IST).strftime("%Y-%m-%d")


def market_open() -> bool:
    if PREVIEW_DAY:
        return True
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    return 555 <= now.hour * 60 + now.minute <= 930


def _cached(key: str, fn):
    hit = _cache.get(key)
    now = time.time()
    if hit and now - hit[0] < TTL[key]:
        return hit[1]
    with _locks[key]:
        hit = _cache.get(key)
        now = time.time()
        if hit and now - hit[0] < TTL[key]:
            return hit[1]
        value = fn()
        _cache[key] = (now, value)
        return value


def live_spot():
    def get():
        try:
            if config.LIVE_ENABLED and config.all_credentials_present():
                return data_loader.fetch_live_ltp("NIFTY 50", "99926000")
        except Exception:
            pass
        return None
    return _cached("spot", get)


def angel_oi(atm50=None):
    def get():
        try:
            if config.LIVE_ENABLED and config.all_credentials_present():
                return data_loader.fetch_live_oi_chain(atm50)
        except Exception:
            pass
        return None
    return _cached("oi", get)


def get_live():
    def get():
        try:
            return nse_live.all_data()
        except Exception:
            return {}
    return _cached("nse", get)


def today_bars(tf: int) -> list:
    """Real 1-min bars of TODAY only; older days are never returned."""
    day = today_str()
    try:
        bars = data_loader.fetch_index_candles(tf, ttl=TTL["bars"]) or []
    except Exception:
        bars = []
    return [b for b in bars if b.get("d") == day]


def today_rows(tf: int) -> list:
    key = "1s" if tf == 1 else str(tf)
    return STORE.fetch("session_rows", filters={"day": today_str(), "tf": key},
                       order="ts.asc")


def oi_samples() -> list:
    return STORE.fetch("oi_samples", filters={"day": today_str()}, order="ts.asc")


def _num(v):
    try:
        return float(v)
    except Exception:
        return None


def snapshot(tf: int) -> dict:
    """Payload compatible with the current UI, but today-only and honest."""
    rows = today_rows(tf)
    if PREVIEW_DAY:
        stored = STORE.fetch("price_bars", filters={"day": today_str(), "tf": "3"},
                             order="ts.asc")
        hero = [{"t": str(b.get("ts", ""))[11:16], "o": _num(b.get("o")),
                 "h": _num(b.get("h")), "l": _num(b.get("l")), "c": _num(b.get("c"))}
                for b in stored]
    else:
        hero = [{"t": b.get("t"), "o": _num(b.get("o")), "h": _num(b.get("h")),
                 "l": _num(b.get("l")), "c": _num(b.get("c"))}
                for b in today_bars(3)]
    last = rows[-1] if rows else {}
    nse = get_live() or {}
    spot = live_spot() if not PREVIEW_DAY else (float(last["close"]) if rows else None)
    spot_ok = bool(spot) and market_open() and bool(rows)
    source = ("PREVIEW · " + PREVIEW_DAY) if PREVIEW_DAY else ("TODAY · LIVE" if spot_ok else "NO DATA")

    oi_chain = angel_oi() if not PREVIEW_DAY else None
    if oi_chain is not None and not oi_chain.empty and rows:
        call = float(oi_chain[oi_chain.side == "CE"].oi.sum())
        put = float(oi_chain[oi_chain.side == "PE"].oi.sum())
        last = dict(last, CALL=call, PUT=put, PCR=(put / call if call else 0.0),
                    DIFF=put - call, SIG="BUY" if put > call else "SELL")

    ce = pe = []
    if oi_chain is not None and not oi_chain.empty:
        ce = oi_chain[oi_chain.side == "CE"].groupby("strike").oi.sum().nlargest(8).index.tolist()
        pe = oi_chain[oi_chain.side == "PE"].groupby("strike").oi.sum().nlargest(8).index.tolist()

    i50 = [x for x in (nse.get("indices") or []) if x.get("index") == "NIFTY 50"]
    n50 = i50[0] if i50 else {}
    def table(items, nk, lk, ck, limit):
        out = []
        for x in (items or [])[:limit]:
            v = _num(x.get(lk))
            if v is not None:
                out.append([str(x.get(nk, "")), v, _num(x.get(ck))])
        return out

    gift = nse.get("giftnifty") or {}
    glob = table(nse.get("global"), "name", "price", "chg", 20)
    if gift.get("LASTPRICE"):
        glob.insert(0, ["GIFT NIFTY", _num(gift.get("LASTPRICE")),
                        _num(gift.get("PERCHANGE"))])

    out_rows = []
    for r in rows:
        out_rows.append({
            "ts": str(r.get("ts", ""))[11:16], "close": _num(r.get("close")) or 0,
            "FUTURE": _num(r.get("future")) or 0, "VWAP": _num(r.get("vwap")) or 0,
            "FUTVWAP": _num(r.get("fut_vwap")) or 0, "CALL": _num(r.get("call")) or 0,
            "PUT": _num(r.get("put")) or 0, "DIFF": _num(r.get("diff")) or 0,
            "PCR": _num(r.get("pcr")) or 0, "STATE": str(r.get("state") or "FLAT"),
            "STATE_C": str(r.get("state_c") or "n"),
            "SIG": str(r.get("sig") or ("BUY" if (_num(r.get("pcr")) or 0) > 1 else "SELL")),
        })
    if out_rows and last:
        out_rows[-1].update(CALL=_num(last.get("CALL")) or out_rows[-1]["CALL"],
                            PUT=_num(last.get("PUT")) or out_rows[-1]["PUT"],
                            PCR=_num(last.get("PCR")) if _num(last.get("PCR")) is not None else out_rows[-1]["PCR"])

    return {
        "tf": tf, "source": source, "hero": hero, "rows": out_rows,
        "bar_age_s": 0 if hero else 10**9,
        "updated": datetime.now(IST).strftime("%d %b %H:%M:%S IST"),
        "index": {"spot": spot if spot_ok else (_num(last.get("close")) if rows else None),
                  "chg": _num(((nse.get("market") or [{}])[0]).get("percentChange")),
                  "live": spot_ok},
        "most_active": {"ce": ce, "pe": pe,
                        "result": "BUY-CE" if len(ce) < len(pe) else "BUY-PE"},
        "breadth": [["NIFTY 50", _num(n50.get("advances")), _num(n50.get("declines")),
                     _num(n50.get("unchanged"))],
                    ["WHOLE MARKET", _num(nse.get("advances")), _num(nse.get("declines")),
                     _num(nse.get("unchanged"))]],
        "stocks": table(nse.get("stocks"), "symbol", "lastPrice", "pChange", 20),
        "sectors": table(nse.get("indices"), "index", "last", "percentChange", 20),
        "global": glob,
        "status": {"market_open": market_open(), "last_tick_age_s": None,
                   "data_quality": "OK" if rows else "NO DATA"},
    }
