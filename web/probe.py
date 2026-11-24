"""Outbound connectivity dipstick for the Blackmere dashboard.

Runs the SAME outbound requests the dashboard makes, from wherever this
process runs (laptop or Render). No values are fabricated: every result
records real HTTP status, latency, response size and any error text.

Endpoints:
  GET /probe        -> run (or return cached) probe report as JSON
  GET /probe?rerun=1 -> force a fresh run
  GET /             -> short instructions

Start:  python web/probe.py          (PORT env or 8080)
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "Chrome/120 Safari/537.36")
RESULT = {"ts": 0.0, "probes": []}
BUSY = False


def load_env() -> None:
    """Load local .env only for keys not already provided by Render."""
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def one(name, url, headers=None, opener=None, limit=4096, timeout=20,
        data=None, method=None) -> dict:
    """One real outbound request, measured. Never returns invented data."""
    t = time.time()
    rec = {"name": name, "url": url, "ok": False, "status": None,
           "ms": 0, "bytes": 0, "error": None}
    try:
        req = urllib.request.Request(url, data=data, headers=headers or {},
                                     method=method)
        op = opener or urllib.request.build_opener()
        with op.open(req, timeout=timeout) as r:
            body = r.read(limit)
            rec.update(status=r.status, ok=200 <= r.status < 400,
                       bytes=len(body))
    except urllib.error.HTTPError as e:
        rec.update(status=e.code, error=f"HTTP {e.code} {e.reason}",
                   bytes=len(e.read(limit)))
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    finally:
        rec["ms"] = int((time.time() - t) * 1000)
    return rec


def nse_opener():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", UA),
                     ("Accept", "application/json,text/plain,*/*"),
                     ("Accept-Language", "en-US,en;q=0.9"),
                     ("Referer", "https://www.nseindia.com")]
    return op, cj


def run_probes() -> dict:
    load_env()
    out = []

    # 1. public egress IP (tells us exactly which IP Render used)
    r = one("egress_ip", "https://api.ipify.org?format=json", timeout=10)
    if r["ok"]:
        try:
            r["ip"] = json.loads(urllib.request.urlopen(
                "https://api.ipify.org?format=json", timeout=10).read()).get("ip")
        except Exception:
            pass
    out.append(r)

    # 2. Angel One public scrip master
    sm_url = ("https://margincalculator.angelbroking.com/OpenAPI_File/files/"
              "OpenAPIScripMaster.json")
    out.append(one("angel_scripmaster", sm_url, limit=2048, timeout=30))

    # 3. Angel One authenticated calls (login -> ltp -> candles -> OI)
    api_key = os.getenv("ANGEL_API_KEY", "")
    client = os.getenv("ANGEL_CLIENT_ID") or os.getenv("ANGEL_CLIENT_CODE", "")
    password = os.getenv("ANGEL_PASSWORD") or os.getenv("ANGEL_PIN", "")
    secret = os.getenv("ANGEL_TOTP_SECRET", "")
    totp_literal = os.getenv("ANGEL_TOTP", "")
    if not (api_key and client and password):
        out.append({"name": "angel_login", "ok": False,
                    "error": "credentials not configured in environment"})
    else:
        t = time.time()
        try:
            from SmartApi import SmartConnect
            import pyotp
            obj = SmartConnect(api_key=api_key)
            totp = pyotp.TOTP(secret).now() if secret else totp_literal
            sess = obj.generateSession(client, password, totp)
            ok = bool(sess.get("status"))
            out.append({"name": "angel_login", "ok": ok,
                        "status": 200 if ok else None,
                        "ms": int((time.time() - t) * 1000), "bytes": 0,
                        "error": None if ok else str(sess.get("message"))[:200]})

            def timed(name, fn):
                t0 = time.time()
                rec = {"name": name, "ok": False, "status": None,
                       "ms": 0, "bytes": 0, "error": None}
                try:
                    v = fn()
                    rec["ok"] = True
                    rec["status"] = 200
                    rec["bytes"] = len(json.dumps(v, default=str))
                except Exception as e:
                    rec["error"] = f"{type(e).__name__}: {str(e)[:200]}"
                finally:
                    rec["ms"] = int((time.time() - t0) * 1000)
                out.append(rec)

            if ok:
                from datetime import datetime, timedelta
                timed("angel_ltp_99926000",
                      lambda: obj.ltpData("NSE", "NIFTY 50", "99926000"))
                now = datetime.now()
                timed("angel_candles_1min", lambda: obj.getCandleData({
                    "exchange": "NSE", "symboltoken": "99926000",
                    "interval": "ONE_MINUTE",
                    "fromdate": (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M"),
                    "todate": now.strftime("%Y-%m-%d %H:%M")}))

                # pick one real NFO option token from the same scrip master
                token = None
                try:
                    master = json.loads(urllib.request.urlopen(
                        sm_url, timeout=30).read())
                    token = next((x["token"] for x in master
                                  if "NIFTY" in str(x.get("name", "")).upper()
                                  and x.get("instrumenttype") == "OPTIDX"), None)
                except Exception:
                    pass
                if token:
                    timed("angel_marketdata_FULL",
                          lambda: obj.getMarketData("FULL", {"NFO": [token]}))
                else:
                    out.append({"name": "angel_marketdata_FULL", "ok": False,
                                "error": "no NIFTY option token in scrip master"})
        except Exception as e:
            out.append({"name": "angel_login", "ok": False,
                        "error": f"{type(e).__name__}: {str(e)[:250]}"})

    # 4. NSE cookie bootstrap + internal JSON endpoints
    op, _ = nse_opener()
    out.append(one("nse_home_cookies", "https://www.nseindia.com",
                   opener=op, limit=2048, timeout=20))
    for name, path in (
        ("nse_allIndices", "/api/allIndices"),
        ("nse_equity_stock_indices", "/api/equity-stock-indices?index=NIFTY%2050"),
        ("nse_marketStatus", "/api/marketStatus"),
    ):
        out.append(one(name, "https://www.nseindia.com" + path,
                       opener=op, limit=4096, timeout=20))

    # 5. Yahoo Finance chart endpoint
    for sym in ("000001.SS", "%5EHSI", "%5ENDX"):
        out.append(one(
            "yahoo_" + sym.replace("%5E", ""),
            f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=1d",
            headers={"User-Agent": UA}, limit=4096, timeout=15))

    # 6. Supabase REST reachability + key validity
    sb = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if sb and key:
        out.append(one("supabase_rest", sb + "/rest/v1/",
                       headers={"apikey": key, "Authorization": "Bearer " + key},
                       limit=2048, timeout=15))
    else:
        out.append({"name": "supabase_rest", "ok": False,
                    "error": "SUPABASE_URL / service role key not configured"})

    return {"ts": time.time(), "probes": out,
            "summary": {"total": len(out),
                        "ok": sum(1 for x in out if x.get("ok")),
                        "failed": sum(1 for x in out if not x.get("ok"))}}


class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        global RESULT, BUSY
        if self.path.startswith("/probe"):
            rerun = "rerun=1" in self.path
            if BUSY:
                self._json({"error": "probe already running"}, 503)
                return
            if rerun or not RESULT["probes"]:
                BUSY = True
                try:
                    RESULT = run_probes()
                finally:
                    BUSY = False
            self._json(RESULT)
            return
        body = (b"Blackmere outbound probe. GET /probe for the report, "
                b"GET /probe?rerun=1 to rerun.\n")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print("[probe] " + fmt % args, flush=True)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    print(f"[probe] listening on 0.0.0.0:{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
