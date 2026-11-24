"""In-process NIFTY 50 tick feed (the account's single Angel One WebSocket).

No bridge file, no second process. Real ticks go straight to tick_feed.publish().
"""
from __future__ import annotations

import threading
import time

import config
import data_loader
import tick_feed

from core import market_open

TOKEN = "99926000"
FEED = {"sws": None}


def _number(v):
    try:
        return float(v)
    except Exception:
        return None


def on_data(wsapp, message):
    if not isinstance(message, dict):
        return
    if str(message.get("token", "")) != TOKEN:
        return
    ltp = None
    for k in ("last_traded_price", "ltp", "lastTradedPrice"):
        ltp = _number(message.get(k))
        if ltp:
            break
    if not ltp:
        return
    # Angel One V2 returns NSE prices scaled by 100 in quote mode
    if ltp > 100000:
        ltp /= 100.0
    ts = message.get("exchange_timestamp") or message.get("timestamp") or message.get("ts")
    try:
        ts = float(ts)
        if ts > 1e12:            # milliseconds
            ts /= 1000.0
    except Exception:
        ts = time.time()
    tick_feed.publish(ltp, ts)


def _login():
    try:
        data_loader._smart_connect(force=True)
        return data_loader.feed_credentials()
    except Exception:
        return None


def _supervisor():
    backoff = 5
    while True:
        if not market_open():
            time.sleep(30)
            continue
        cred = _login()
        if not cred or not all(cred):
            time.sleep(backoff)
            backoff = min(backoff * 2, 120)
            continue
        try:
            from SmartApi.smartWebSocketV2 import SmartWebSocketV2
            auth, key, client, feed_token = cred
            sws = SmartWebSocketV2(auth, key, client, feed_token)
            FEED["sws"] = sws

            def on_open(wsapp):
                sws.subscribe("abc123", 2, [{"exchangeType": 1, "tokens": [TOKEN]}])

            def on_error(wsapp, error):
                print(f"[index_feed] ws error: {str(error)[:160]}", flush=True)

            sws.on_data = on_data
            sws.on_open = on_open
            sws.on_error = on_error
            sws.connect()                      # blocks until disconnect
            backoff = 5
        except Exception as exc:
            print(f"[index_feed] reconnect: {type(exc).__name__}: {str(exc)[:160]}", flush=True)
        finally:
            FEED["sws"] = None
        time.sleep(backoff)
        backoff = min(backoff * 2, 120)


def start():
    threading.Thread(target=_supervisor, daemon=True, name="angel-index-feed").start()
