"""Per-source refresh clocks: OI samples and today's session rows."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import core
import data_loader

from store import STORE

IST = timezone(timedelta(hours=5, minutes=30))
_last_oi = 0.0


def _iso(minute_label: str) -> str:
    now = datetime.now(IST)
    hh, mm = [int(x) for x in minute_label.split(":")[:2]]
    return now.replace(hour=hh, minute=mm, second=0, microsecond=0).isoformat()


def _bucket(bars: list, mins: int) -> list[list]:
    out, cur, key = [], None, None
    for b in bars:
        hh, mm = [int(x) for x in b["t"].split(":")[:2]]
        k = (hh * 60 + mm) // mins * mins
        if k != key:
            if cur:
                out.append(cur)
            cur, key = [b], k
        else:
            cur.append(b)
    if cur:
        out.append(cur)
    return out


def _nearest_oi(samples: list, stamp: str) -> dict:
    prior = [s for s in samples if str(s.get("ts", "")) <= stamp]
    return (prior[-1] if prior else (samples[-1] if samples else {}))


def _oi_loop():
    global _last_oi
    while True:
        now = time.time()
        if core.market_open() and now - _last_oi >= 30:
            _last_oi = now
            try:
                spot = core.live_spot()
                chain = core.angel_oi()
                if spot and chain is not None and not chain.empty:
                    call = float(chain[chain.side == "CE"].oi.sum())
                    put = float(chain[chain.side == "PE"].oi.sum())
                    stamp = datetime.now(IST).replace(second=0, microsecond=0).isoformat()
                    STORE.upsert("oi_samples", [{
                        "day": core.today_str(), "ts": stamp, "spot": float(spot),
                        "call_oi": call, "put_oi": put, "total_oi": call + put}])
                    print(f"[refresh] OI sample {stamp[11:16]} call={call:.0f} put={put:.0f}", flush=True)
            except Exception as exc:
                print(f"[refresh] oi failed: {type(exc).__name__}", flush=True)
        time.sleep(5)


def _rows_loop():
    while True:
        if core.market_open():
            try:
                samples = core.oi_samples()
                fut = data_loader.fetch_futures_ltp()
                for tf in core.TFS:
                    bars = core.today_bars(3)
                    if not bars:
                        continue
                    rows = []
                    for grp in _bucket(bars, tf):
                        label = grp[-1]["t"]
                        stamp = _iso(label)
                        close = float(grp[-1]["c"])
                        vals = [(float(b["h"]) + float(b["l"]) + float(b["c"])) / 3 for b in grp]
                        vwap = sum(vals) / len(vals)
                        s = _nearest_oi(samples, stamp)
                        call = float(s.get("call_oi") or 0)
                        put = float(s.get("put_oi") or 0)
                        pcr = put / call if call else 0.0
                        prev = rows[-1] if rows else None
                        state, state_c = "FLAT", "n"
                        if prev:
                            dp = close - prev["close"]
                            do = (call + put) - (prev["call"] + prev["put"])
                            if dp > 0 and do > 0:
                                state, state_c = "LONG BLD", "g"
                            elif dp < 0 and do > 0:
                                state, state_c = "SHORT BLD", "r"
                            elif dp > 0 and do < 0:
                                state, state_c = "SHORT COV", "y"
                            elif dp < 0 and do < 0:
                                state, state_c = "LONG UNW", "n"
                        rows.append({
                            "day": core.today_str(), "tf": str(tf), "ts": stamp,
                            "close": close, "future": float(fut) if fut else 0.0,
                            "vwap": vwap, "fut_vwap": (float(fut) if fut else 0.0) - vwap,
                            "call": call, "put": put, "diff": put - call, "pcr": pcr,
                            "state": state, "state_c": state_c,
                            "sig": "BUY" if pcr > 1 else "SELL",
                            "oi_as_of": str(s.get("ts", ""))})
                    if rows:
                        STORE.upsert("session_rows", rows)
                        STORE.upsert("price_bars", [{
                            "day": core.today_str(), "tf": "3", "ts": _iso(b["t"]),
                            "o": float(b["o"]), "h": float(b["h"]),
                            "l": float(b["l"]), "c": float(b["c"])} for b in core.today_bars(3)])
            except Exception as exc:
                print(f"[refresh] rows failed: {type(exc).__name__}", flush=True)
        time.sleep(10)


def start():
    threading.Thread(target=_oi_loop, daemon=True, name="oi-refresh").start()
    threading.Thread(target=_rows_loop, daemon=True, name="rows-refresh").start()
