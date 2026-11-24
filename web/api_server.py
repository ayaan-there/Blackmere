"""Static host + live JSON API for AXIOM BLACKMERE (cloud-safe).

Every value comes from today's real sources via web.core. No Streamlit,
no recorded fallback, no synthetic values.
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
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import core          # noqa: E402
import structure     # noqa: E402
import tick_feed     # noqa: E402
from store import STORE  # noqa: E402

_SNAP: dict[int, tuple[float, dict]] = {}
_SNAP_TTL = 2
_LOCK = threading.Lock()


def get_snapshot(tf: int) -> dict:
    now = time.time()
    with _LOCK:
        hit = _SNAP.get(tf)
        if hit and now - hit[0] < _SNAP_TTL:
            return hit[1]
    payload = core.snapshot(tf)
    with _LOCK:
        _SNAP[tf] = (now, payload)
    return payload


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(HERE), **kw)

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse(self):
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
            self._json({"ok": True, "market_open": core.market_open(),
                        "tick_age_s": int(age) if age is not None else None,
                        "tick_feed": bool(last.get("ltp")),
                        "supabase": "connected" if __import__("store").STORE.enabled else "local",
                        "source": "TODAY · LIVE" if (last.get("ltp") and core.market_open()) else "NO DATA"})
            return
        if u.path == "/api/static":
            d = get_snapshot(3)
            self._json({k: d.get(k) for k in ("breadth", "stocks", "sectors", "global")})
            return
        if u.path == "/api/structure":
            samples = STORE.fetch("oi_samples", filters={"day": core.today_str()},
                                  order="ts.asc")
            obs = []
            for i, s in enumerate(samples):
                prev = samples[i - 1] if i else {}
                obs.append({"ts": s.get("ts"), "price": s.get("spot"),
                            "oi": s.get("total_oi"), "price_prev": prev.get("spot"),
                            "oi_prev": prev.get("total_oi"), "tf": "30s"})
            self._json({"as_of": core.today_str(),
                        "single": structure.analyze(obs, tf="30s"),
                        "timeframes": structure.multi_timeframe(obs)})
            return
        if u.path == "/api/bars":
            q = parse_qs(u.query)
            try:
                tf = int(q.get("tf", ["3"])[0])
            except Exception:
                tf = 3
            tf_key = "1s" if tf == 1 else str(tf if tf in core.TFS else 3)
            rows = STORE.fetch("price_bars", filters={"day": core.today_str(), "tf": tf_key},
                               order="ts.asc")
            self._json({"tf": tf, "bars": rows})
            return
        if u.path == "/api/snapshot":
            q = parse_qs(u.query)
            try:
                tf = int(q.get("tf", ["3"])[0])
            except Exception:
                tf = 3
            if tf != 1 and tf not in core.TFS:
                tf = 3
            try:
                self._json(get_snapshot(tf))
            except Exception as exc:
                self._json({"error": f"{type(exc).__name__}: {exc}"}, 503)
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
    port = int(port or os.getenv("PORT", "8502"))
    tick_feed.start()
    print(f"[api] listening on 0.0.0.0:{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    start(int(sys.argv[1]) if len(sys.argv) > 1 else None)
