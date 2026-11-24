"""NSE live data fetcher — ONE shared cookie session, all endpoints in parallel.
Fixes latency: old version made 4 separate homepage fetches + 3 dead 404 calls.
"""
from __future__ import annotations
import json
import urllib.request
import http.cookiejar
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
BASE = "https://www.nseindia.com"


def _session():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", UA), ("Accept", "application/json,text/plain,*/*"),
                     ("Accept-Language", "en-US,en;q=0.9"), ("Referer", BASE)]
    try:
        op.open(BASE, timeout=8).read()   # get cookies once
    except Exception:
        pass
    return op


def all_data():
    out = {"indices": [], "stocks": [], "sectors": [], "global": [],
           "advances": None, "declines": None, "unchanged": None,
           "market": None, "giftnifty": None}
    op = _session()                      # single shared session

    def fetch(path):
        try:
            return json.loads(op.open(BASE + path, timeout=10).read())
        except Exception:
            return {}

    # 3 useful endpoints in parallel (no dead global 404s)
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_idx = ex.submit(fetch, "/api/allIndices")
        f_stk = ex.submit(fetch, "/api/equity-stock-indices?index=NIFTY%2050")
        f_mkt = ex.submit(fetch, "/api/marketStatus")
        idx, stk, mkt = f_idx.result(), f_stk.result(), f_mkt.result()

    if "data" in idx:
        out["indices"] = idx["data"]
        out["advances"], out["declines"], out["unchanged"] = idx.get("advances"), idx.get("declines"), idx.get("unchanged")
        out["sectors"] = [x for x in idx["data"]
                          if any(k in str(x.get("index", "")) for k in
                                 ("BANK", "IT", "PHARMA", "AUTO", "METAL", "FINANCIAL",
                                  "FMCG", "REALTY", "ENERGY", "CPSE", "PVT", "SERVICES"))]
    if "data" in stk:
        out["stocks"] = stk["data"]
    if "marketState" in mkt:
        out["market"] = mkt["marketState"]
        out["giftnifty"] = mkt.get("giftnifty")
    return out


if __name__ == "__main__":
    d = all_data()
    for k, v in d.items():
        print(k, len(v) if isinstance(v, list) else v)
