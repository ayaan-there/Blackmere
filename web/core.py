"""Cloud-safe data core: TODAY-ONLY, no Streamlit, no recorded fallbacks.

Every value returned here comes from a live source or from today's persisted
rows. If nothing exists yet, empty values are returned — never another day's
data and never synthetic data.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import config
import data_loader
import nse_live

from store import STORE

IST = timezone(timedelta(hours=5, minutes=30))
TFS = (3, 5, 9, 15)
TTL = {"spot": 60, "oi": 30, "nse": 30, "bars": 120, "global": 30}

# Exact tracked lists, in the order requested. No extra rows are shown.
SECTOR_SPECS = [
    ("GIFT NIFTY", "__gift__"),
    ("NIFTY 50", "NIFTY 50"),
    ("NIFTY MIDCAP 50", "NIFTY MIDCAP 50"),
    ("NIFTY SMALLCAP 50", "NIFTY SMALLCAP 50"),
    ("NIFTY BANK", "NIFTY BANK"),
    ("NIFTY IT", "NIFTY IT"),
    ("NIFTY AUTO", "NIFTY AUTO"),
    ("NIFTY PHARMA", "NIFTY PHARMA"),
    ("NIFTY HEALTHCARE", "NIFTY HEALTHCARE INDEX"),
    ("NIFTY METAL", "NIFTY METAL"),
    ("NIFTY RETAIL", "NIFTY RETAIL"),
    ("NIFTY FMCG", "NIFTY FMCG"),
    ("NIFTY ENERGY", "NIFTY ENERGY"),
    ("NIFTY INFRASTRUCTURE", "NIFTY INFRASTRUCTURE"),
    ("NIFTY SERVICES SECTOR", "NIFTY SERVICES SECTOR"),
]
GLOBAL_SPECS = [
    ("US · United States NASDAQ 100", "%5ENDX"),
    ("CN · China Hang Seng", "%5EHSCE"),
    ("JP · Japan Nikkei 225", "%5EN225"),
    ("KR · South Korea KOSPI", "%5EKS11"),
    ("HK · Hong Kong Hang Seng Index", "%5EHSI"),
    ("AU · Australia ASX 200", "%5EAXJO"),
    ("FR · France CAC 40", "%5EFCHI"),
    ("DE · Germany DAX 40", "%5EGDAXI"),
    ("GB · United Kingdom FTSE 100", "%5EFTSE"),
    ("EU · Europe Euro Stoxx 50", "%5ESTOXX50E"),
    ("RU · Russia MOEX Russia Index", "MISSING"),
    ("CA · Canada S&P/TSX Composite", "%5EGSPTSE"),
]

_cache: dict[str, tuple[float, object]] = {}
_locks = {k: threading.Lock() for k in ("spot", "oi", "nse", "global")}


PREVIEW_DAY = os.getenv("BLACKMERE_PREVIEW_DAY", "")
PIVOT_DAY = os.getenv("BLACKMERE_PIVOT_DAY", "")   # local preview override only


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


def _yahoo_one(symbol: str):
    if symbol == "MISSING":
        return None
    try:
        u = ("https://query1.finance.yahoo.com/v8/finance/chart/" + symbol
             + "?range=1d&interval=1d")
        r = urllib.request.urlopen(urllib.request.Request(
            u, headers={"User-Agent": "Mozilla/5.0"}), timeout=8)
        m = json.loads(r.read())["chart"]["result"][0]["meta"]
        p = m.get("regularMarketPrice")
        pc = m.get("chartPreviousClose") or m.get("previousClose") or p
        return (round(float(p), 2) if p else None,
                round((float(p) / float(pc) - 1) * 100, 2) if p and pc else None)
    except Exception:
        return None


def fetch_global():
    def get():
        with ThreadPoolExecutor(max_workers=8) as ex:
            vals = list(ex.map(lambda s: _yahoo_one(s[1]), GLOBAL_SPECS))
        return [[label, (v[0] if v else None), (v[1] if v else None)]
                for (label, _), v in zip(GLOBAL_SPECS, vals)]
    return _cached("global", get)


def _tf_key(tf: int) -> str:
    return "1s" if tf == 1 else ("1m" if tf == 0 else str(tf))


def _bars_for(tf: int) -> list:
    return STORE.fetch("price_bars", filters={"day": today_str(), "tf": _tf_key(tf)},
                       order="ts.asc")


def previous_session() -> dict | None:
    """Last trading day before today, from REAL stored 1m bars. Never hardcoded."""
    rows = STORE.fetch("price_bars", filters={"tf": "1m"},
                       columns="day,ts,o,h,l,c", limit=20000)
    today = today_str()
    days = sorted({str(r.get("day", ""))[:10] for r in rows
                   if str(r.get("day", ""))[:10] and str(r.get("day", ""))[:10] < today})
    if PIVOT_DAY:
        day = PIVOT_DAY
    elif days:
        day = days[-1]
    else:
        return None
    bars = [r for r in rows if str(r.get("day", ""))[:10] == day]
    if not bars:
        return None
    return {"day": day,
            "high": max(float(b["h"]) for b in bars if b.get("h") is not None),
            "low": min(float(b["l"]) for b in bars if b.get("l") is not None),
            "close": float(bars[-1]["c"])}


def pivot_levels() -> dict | None:
    s = previous_session()
    if not s:
        return None
    h, l, c = s["high"], s["low"], s["close"]
    p = (h + l + c) / 3
    rng = h - l
    return {"day": s["day"], "H": h, "L": l, "C": c,
            "P": p, "R1": 2 * p - l, "S1": 2 * p - h,
            "R2": p + rng, "S2": p - rng,
            "R3": p + 2 * rng, "S3": p - 2 * rng}


def indicators(tf: int) -> dict:
    """VWAP from today's real 1m bars; pivot from the last prior trading day."""
    bars = _bars_for(tf)
    m1 = STORE.fetch("price_bars", filters={"day": today_str(), "tf": "1m"},
                     order="ts.asc")
    m1 = sorted(m1, key=lambda b: str(b.get("ts", "")))
    points, cum, count, ptr = [], 0.0, 0, 0
    for b in bars:
        stamp = str(b.get("ts", ""))
        while ptr < len(m1) and str(m1[ptr].get("ts", "")) <= stamp:
            mb = m1[ptr]
            cum += (float(mb["h"]) + float(mb["l"]) + float(mb["c"])) / 3
            count += 1
            ptr += 1
        if count:
            points.append({"ts": stamp, "value": cum / count})
    return {"tf": tf, "vwap": points, "vwap_sum": cum, "vwap_count": count,
            "pivot": pivot_levels(),
            "quality": "OK" if points else "NO DATA"}


def today_bars(tf: int) -> list:
    """Real bars of TODAY from the store (built from 1s ticks), never REST."""
    out = []
    for r in _bars_for(tf):
        ts = str(r.get("ts", ""))
        if not ts.startswith(today_str()):
            continue
        out.append({"d": ts[:10], "t": ts[11:19], "ts": ts,
                    "o": _num(r.get("o")), "h": _num(r.get("h")),
                    "l": _num(r.get("l")), "c": _num(r.get("c"))})
    return out


def today_rows(tf: int) -> list:
    key = "1s" if tf == 1 else ("1m" if tf == 0 else str(tf))
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
    glob = fetch_global()
    all_nse = list(nse.get("indices") or []) + list(nse.get("sectors") or [])
    sectors = []
    for label, src in SECTOR_SPECS:
        if src == "__gift__":
            val, chg = _num(gift.get("LASTPRICE")), _num(gift.get("PERCHANGE"))
        else:
            item = next((x for x in all_nse if x.get("index") == src), None)
            val = _num(item.get("last")) if item else None
            chg = _num(item.get("percentChange")) if item else None
        sectors.append([label, val, chg])

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
        "sectors": sectors,
        "global": glob,
        "status": {"market_open": market_open(), "last_tick_age_s": None,
                   "data_quality": "OK" if rows else "NO DATA"},
    }
