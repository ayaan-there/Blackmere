"""REAL-TIME NIFTY 50 index ticks -> SSE -> browser.

The account's single Angel One WebSocket is owned by the data recorder. This
module bridges that SAME feed through a tiny live-tick file and pushes every
update to the dashboard with Server-Sent Events. No second WS connection,
no REST polling, no synthetic values. Only the index chart uses this stream.
"""
from __future__ import annotations
import json
import queue
import threading
import time
from pathlib import Path

LIVE_FILE = Path(__file__).resolve().parents[1] / "data" / "cache" / "nifty_index_live.json"

_LATEST = {"ltp": None, "ts": 0.0}
_LOCK = threading.Lock()
_SUBS = set()
_STARTED = False


def latest() -> dict:
    with _LOCK:
        return dict(_LATEST)


def _subscribe(fmt="sse") -> queue.Queue:
    q = queue.Queue(maxsize=500)
    with _LOCK:
        _SUBS.add((q, fmt))
        first = dict(_LATEST)
    # never replay a stale tick to a newly connected browser
    if first.get("ltp") is not None and time.time() - first.get("ts", 0) < 60:
        q.put(_encode(first["ltp"], first["ts"], True, fmt))
    return q


def subscribe() -> queue.Queue:
    return _subscribe("sse")


def subscribe_raw() -> queue.Queue:
    return _subscribe("json")


def unsubscribe(q):
    with _LOCK:
        _SUBS.discard((q, "sse"))
        _SUBS.discard((q, "json"))


def _encode(ltp, ts, initial=False, fmt="sse") -> str:
    msg = json.dumps({"ltp": round(float(ltp), 2),
                      "ts": round(float(ts), 3),
                      "initial": bool(initial)})
    return ("data: " + msg + "\n\n") if fmt == "sse" else msg


def _frame(ltp, ts, initial=False) -> str:
    return _encode(ltp, ts, initial, "sse")


def publish(ltp, ts=None) -> None:
    if not ltp:
        return
    v = float(ltp)
    if not (1000 < v < 100000):        # sanity: real Nifty range only
        return
    now = float(ts) if ts else time.time()
    if time.time() - now > 60:               # discard yesterday's stale bridge tick
        return
    with _LOCK:
        _LATEST.update({"ltp": v, "ts": now})
        for q, fmt in list(_SUBS):
            try:
                q.put_nowait(_encode(v, now, False, fmt))
            except queue.Full:
                pass


def _run():
    """Watch the recorder's live-tick file and broadcast each new price."""
    last_sig = None
    while True:
        try:
            st = LIVE_FILE.stat()
            sig = (st.st_mtime_ns, st.st_size)
            if sig != last_sig:
                last_sig = sig
                try:
                    d = json.loads(LIVE_FILE.read_text(encoding="utf-8"))
                    if d.get("ltp"):
                        publish(d["ltp"], d.get("ts"))
                except (ValueError, OSError):
                    pass                     # mid-write partial read -> skip
        except (OSError, ValueError):
            pass
        time.sleep(0.01)                     # 100 checks/sec -> near-zero wait


def start():
    global _STARTED
    if _STARTED:
        return
    _STARTED = True
    threading.Thread(target=_run, daemon=True, name="nifty-tick-bridge").start()
