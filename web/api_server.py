"""Static host + live JSON API for the HTML terminal.

Serves web/ on / and /api/snapshot?tf=3|5|9|15 from the SAME real data
sources the Streamlit terminal uses (Angel One live OI/LTP, NSE, Yahoo,
recorded 3-min candles). No synthetic / placeholder values.
"""
from __future__ import annotations
import base64
import hashlib
import json
import mimetypes
import os
import queue
import struct
import sys
import time
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import nifty_pro_terminal as M   # real data functions (reused, not duplicated)
import data_loader               # real index candles from Angel One
import tick_feed                 # real-time NIFTY index ticks (WebSocket -> SSE)


def _market_open() -> bool:
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    if now.weekday() >= 5:
        return False
    m = now.hour * 60 + now.minute
    return 555 <= m <= 930


def _rows_from_frame(src, tf):
    out = []
    for _, r in src.iterrows():
        ts = r["ts"]
        label = (pd.to_datetime(ts).strftime("%H:%M") if not isinstance(ts, str)
                 else (ts[11:16] if len(ts) >= 16 else ts))
        g = lambda k, d=0.0: float(r[k]) if k in r and pd.notna(r[k]) else d
        pcr = g("PCR")
        out.append({
            "ts": label,
            "close": g("close"), "FUTURE": g("FUTURE"), "VWAP": g("VWAP"),
            "FUTVWAP": g("FUT-VWAP"), "CALL": g("CALL"), "PUT": g("PUT"),
            "DIFF": g("DIFF"), "PCR": pcr,
            "STATE": str(r.get("STATE", "FLAT")), "STATE_C": str(r.get("STATE_C", "n")),
            "SIG": "BUY" if pcr > 1 else "SELL",
        })
    return out


def snapshot(tf: int) -> dict:
    d, opt = M.get_data(tf)
    last = d.iloc[-1]
    atm50 = int(round(float(last.close) / 50) * 50)

    # independent live sources in parallel (biggest latency win)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as ex:
        f_spot = ex.submit(M.live_spot)
        f_oi = ex.submit(M.angel_oi, atm50)
        f_nse = ex.submit(M.get_live)
        f_cand = ex.submit(data_loader.fetch_index_candles, tf)
        f_fut = ex.submit(data_loader.fetch_futures_ltp)
        f_vwap = ex.submit(data_loader.fetch_index_vwap)
        lv = f_spot.result()
        lc = f_oi.result()
        nse, glob = f_nse.result()
        hero = f_cand.result()
        fut = f_fut.result()
        vwap = f_vwap.result()

    oi = None
    if lc is not None and not lc.empty:
        call = float(lc[lc.side == "CE"].oi.sum())
        put = float(lc[lc.side == "PE"].oi.sum())
        oi = {"call": call, "put": put, "pcr": put / call if call else 0.0, "chain": lc}

    # append today's real live bar (market hours only), then serve it
    M._append_live_row(last, oi, tf, lv, fut, vwap)
    sess = M._load_session(tf)
    from datetime import datetime, timezone, timedelta
    today = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    live = [r for r in sess if pd.to_datetime(r["ts"]).date() == today]

    if live:
        src = pd.DataFrame(live).sort_values("ts")
        source = "TODAY · LIVE"
    else:
        src = d
        source = f"RECORDED · {M.DAY}"

    rows = _rows_from_frame(src, tf)
    if not rows:
        return {"error": "no data available"}

    # latest point mirrors the real live OI snapshot (same as the terminal)
    if oi:
        last_row = rows[-1]
        last_row["CALL"] = oi["call"]
        last_row["PUT"] = oi["put"]
        last_row["DIFF"] = oi["put"] - oi["call"]
        last_row["PCR"] = oi["pcr"]
        last_row["SIG"] = "BUY" if oi["pcr"] > 1 else "SELL"

    # keep VWAP / FUT-VWAP on the latest row live between bucket appends
    if vwap and rows:
        rows[-1]["VWAP"] = float(vwap)
        rows[-1]["FUT-VWAP"] = float(rows[-1]["FUTURE"]) - float(vwap)

    # most active strikes — live chain when available, else recorded chain
    ch = oi["chain"] if oi else opt
    ce = ch[ch.side == "CE"].groupby("strike").oi.sum().nlargest(8).index.tolist()
    pe = ch[ch.side == "PE"].groupby("strike").oi.sum().nlargest(8).index.tolist()

    gift = nse.get("giftnifty") or {}
    if gift.get("LASTPRICE"):
        try:
            glob.insert(0, {"name": "GIFT NIFTY", "price": float(gift["LASTPRICE"]),
                            "chg": float(gift.get("PERCHANGE") or 0)})
        except Exception:
            pass

    adv, dec, unc = nse.get("advances"), nse.get("declines"), nse.get("unchanged")
    i50 = [x for x in (nse.get("indices") or []) if x.get("index") == "NIFTY 50"]
    n50 = i50[0] if i50 else {}

    def num(v):
        try:
            return float(v)
        except Exception:
            return None

    def table_rows(items, name_key, last_key, chg_key, limit):
        out = []
        for x in (items or [])[:limit]:
            out.append([str(x.get(name_key, "")), num(x.get(last_key)), num(x.get(chg_key))])
        return [r for r in out if r[1] is not None]

    stocks = table_rows(nse.get("stocks"), "symbol", "lastPrice", "pChange", 10)
    stocks = [r for r in stocks if r[0] != "NIFTY 50"][:10]

    sectors = []
    seen = set()
    cap_names = {"NIFTY 100": "NIFTY LARGE (100)", "NIFTY MIDCAP 100": "NIFTY MIDCAP 100",
                 "NIFTY SMALLCAP 100": "NIFTY SMALLCAP 100"}
    for x in (nse.get("indices") or []):
        nm = str(x.get("index", ""))
        if nm in cap_names and x.get("last") is not None:
            sectors.append([cap_names[nm], num(x.get("last")), num(x.get("percentChange"))])
    for x in (nse.get("sectors") or []):
        nm = str(x.get("index", ""))
        up = nm.upper()
        if (nm in seen or "FINANCIAL" in up or "PSU BANK" in up
                or "PRIVATE BANK" in up or "REALTY" in up
                or "MIDSMALL IT & TELECOM" in up or "DIVIDEND OPPORTUNIT" in up):
            continue
        if x.get("last") is None:
            continue
        seen.add(nm)
        sectors.append([nm, num(x.get("last")), num(x.get("percentChange"))])
        if len(sectors) >= 9:
            break
    sectors = sectors[:9]

    gl = []
    for g in glob:
        gl.append([str(g.get("name", "")), num(g.get("price")), num(g.get("chg"))])

    mkt = nse.get("market") or []
    m0 = mkt[0] if mkt else {}
    try:
        chg = float(m0.get("percentChange")) if m0.get("percentChange") not in (None, "") else None
    except Exception:
        chg = None

    # REAL Nifty index price candles (fetched in parallel above)
    if lv and hero and _market_open():
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        stamp = now.strftime("%H:%M")
        if stamp != hero[-1]["t"]:
            hero.append({"t": stamp, "o": float(lv), "h": float(lv),
                         "l": float(lv), "c": float(lv)})

    return {
        "tf": tf, "source": source, "hero": hero,
        "bar_age_s": int(data_loader.get_base_age()),
        "updated": datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%d %b %H:%M:%S IST"),
        "index": {"spot": (lv if (lv and _market_open() and source == "TODAY · LIVE")
                           else float(rows[-1]["close"])), "chg": chg,
                  "live": bool(lv) and _market_open() and source == "TODAY · LIVE"},
        "rows": rows,
        "most_active": {"ce": ce, "pe": pe,
                        "result": "BUY-CE" if len(ce) < len(pe) else "BUY-PE"},
        "breadth": [
            ["NIFTY 50", num(n50.get("advances")), num(n50.get("declines")), num(n50.get("unchanged"))],
            ["WHOLE MARKET", num(adv), num(dec), num(unc)],
        ],
        "stocks": stocks, "sectors": sectors, "global": gl,
    }


# ---- instant serving: stale-while-revalidate + independent refresh ticker ----
_SNAP_CACHE = {}          # tf -> (age_ts, payload)
_BG_AT = {}
_REFRESH_LOCK = threading.Lock()
_REFRESH_AT = 0.0
_TTL = 70                 # serve stale after this; ticker keeps us well inside it


def _bounded(fn, *args, secs=25):
    """Never let one hung data call freeze the refresh loop forever."""
    box = {}
    def run():
        try:
            box["v"] = fn(*args)
        except Exception:
            pass
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(secs)
    return box.get("v")


def _refresh_all():
    """One worker refreshes every timeframe. Lock prevents thread pile-ups."""
    global _REFRESH_AT
    if not _REFRESH_LOCK.acquire(blocking=False):
        return
    try:
        stamp = time.time()
        for tf in (3, 5, 9, 15):
            payload = _bounded(snapshot, tf)
            if payload and not payload.get("error"):
                _SNAP_CACHE[tf] = (stamp, payload)
        _REFRESH_AT = time.time()
    finally:
        _REFRESH_LOCK.release()


def _ticker():
    """Refresh on a fixed 45s clock even when nobody opens the page."""
    while True:
        try:
            time.sleep(45)
            if time.time() - _REFRESH_AT > 40:
                _refresh_all()
        except Exception as exc:            # ticker itself must never die
            print(f"[ticker] {exc}")


def _with_age(payload, age):
    """Attach cache age so the UI can honestly report DELAYED instead of LIVE."""
    out = dict(payload)
    out["age_s"] = int(age)
    return out


def get_snapshot(tf):
    now = time.time()
    hit = _SNAP_CACHE.get(tf)
    if hit and now - hit[0] < _TTL:
        return _with_age(hit[1], now - hit[0])   # fresh -> instant
    if hit:                                 # stale -> serve now, refresh behind
        if now - _BG_AT.get("all", 0) > 15:
            _BG_AT["all"] = now
            threading.Thread(target=_refresh_all, daemon=True).start()
        return _with_age(hit[1], now - hit[0])
    _refresh_all()                          # first load only
    h = _SNAP_CACHE.get(tf)
    return _with_age(h[1], now - h[0]) if h else {"error": "data unavailable"}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(HERE), **kw)

    def _sse(self):
        """Push every Angel One index tick to the browser instantly."""
        self._sse_mode = True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        q = tick_feed.subscribe()
        try:
            while True:
                try:
                    msg = q.get(timeout=15)
                except queue.Empty:
                    msg = ": keep-alive\n\n"
                self.wfile.write(msg.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            tick_feed.unsubscribe(q)

    def _ws_ticks(self):
        """Raw WebSocket feed — avoids proxy SSE buffering over ngrok."""
        key = self.headers.get("Sec-WebSocket-Key")
        if not key or "websocket" not in (self.headers.get("Upgrade") or "").lower():
            self.send_error(400, "websocket upgrade required")
            return
        accept = base64.b64encode(hashlib.sha1(
            (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        self.send_response(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        q = tick_feed.subscribe_raw()
        try:
            while True:
                try:
                    msg = q.get(timeout=20)
                except queue.Empty:
                    continue
                payload = msg.encode("utf-8")
                n = len(payload)
                if n < 126:
                    head = bytes([0x81, n])
                elif n < 65536:
                    head = bytes([0x81, 126]) + struct.pack("!H", n)
                else:
                    head = bytes([0x81, 127]) + struct.pack("!Q", n)
                self.connection.sendall(head + payload)
        except (OSError, BrokenPipeError, ConnectionResetError):
            pass
        finally:
            tick_feed.unsubscribe(q)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/ws/ticks":
            self._ws_ticks()
            return
        if u.path == "/api/ticks":
            self._sse()
            return
        if u.path == "/api/health":
            last = tick_feed.latest()
            age = (time.time() - float(last["ts"])) if last.get("ts") else None
            payload = {"ok": True, "market_open": _market_open(),
                       "tick_age_s": int(age) if age is not None else None,
                       "tick_feed": bool(last.get("ltp")),
                       "sources": sorted(_SNAP_CACHE.keys())}
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if u.path == "/api/snapshot":
            q = parse_qs(u.query)
            try:
                tf = int(q.get("tf", ["3"])[0])
            except Exception:
                tf = 3
            if tf not in (3, 5, 9, 15):
                tf = 3
            try:
                payload = get_snapshot(tf)
                code = 200
            except Exception as exc:
                payload = {"error": f"{type(exc).__name__}: {exc}"}
                code = 503
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def end_headers(self):
        if not getattr(self, "_sse_mode", False):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def guess_type(self, path):
        return mimetypes.guess_type(path)[0] or "application/octet-stream"

    def log_message(self, fmt, *args):
        pass


def start(port: int | None = None) -> None:
    """Production entrypoint used by both web/main.py and local dev."""
    port = int(port or os.getenv("PORT", "8502"))
    tick_feed.start()                                     # real-time index ticks
    threading.Thread(target=_ticker, daemon=True).start()   # keep data fresh on a clock
    threading.Thread(target=_refresh_all, daemon=True).start()  # prewarm, non-blocking
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    start(int(sys.argv[1]) if len(sys.argv) > 1 else None)
