"""Backtest the DASHBOARD's own mechanical rules on real recorded data.

Rules (no prediction, no probability model):
  signal : PCR > 1 -> BUY CE, else BUY PE   (nearest recorded ATM strike)
  entry  : next 3-min bar close
  exit   : premium close <= entry-20 (SL) or >= entry+40 (target), else day end
  qty    : 1 lot = config.LOT_SIZE (65)
Data: 19-Nov-2026 recorded 1-min index bars + real option ticks (24750-25250).
"""
from __future__ import annotations
import re
from pathlib import Path
import numpy as np
import pandas as pd
import config

R = Path(r"D:\PROJECTS\active\personal\Trading-Assistant\data\recorded")
CORE = Path(r"D:\PROJECTS\active\personal\Trading-Assistant\data\recorded_core_bars\nifty50_index\20261119.parquet")
DAY = "20261119"
TF = 3
SL, TARGET = 20.0, 40.0
LOT = config.LOT_SIZE
STEP = 3

idx = pd.read_parquet(CORE)
idx["ts"] = pd.to_datetime(idx["ts"]).dt.tz_localize(None)
bars = idx.set_index("ts")["close"].resample(f"{TF}min", label="right", closed="right").last().dropna()
clock = pd.Index([x.time() for x in bars.index])
bars = bars.loc[(clock >= pd.Timestamp("09:15").time()) &
                (clock <= pd.Timestamp("15:30").time())].to_frame("spot")

px, oi = {}, {}
for p in R.glob(f"NIFTY*/{DAY}.parquet"):
    m = re.match(r"NIFTY.*?(\d{5})(CE|PE)$", p.parent.name)
    if not m:
        continue
    k, side = int(m.group(1)), m.group(2)
    t = pd.read_parquet(p, columns=["ts", "price", "oi"])
    t["ts"] = pd.to_datetime(t["ts"]).dt.tz_localize(None)
    g = t.set_index("ts").resample(f"{TF}min", label="right", closed="right").agg(
        {"price": "last", "oi": "last"})
    px[(k, side)] = g["price"].reindex(bars.index).ffill()
    oi[(k, side)] = g["oi"].reindex(bars.index).ffill()

chain_px = pd.DataFrame(px)
chain_oi = pd.DataFrame(oi)
strikes = sorted({k for k, _ in px})

rows = []
for i in range(1, len(bars) - 1):
    ts = bars.index[i]
    spot = bars.spot.iloc[i]
    ce = sum(float(oi.get((k, "CE"), pd.Series(dtype=float)).get(ts, np.nan) or 0) for k in strikes)
    pe = sum(float(oi.get((k, "PE"), pd.Series(dtype=float)).get(ts, np.nan) or 0) for k in strikes)
    if ce <= 0 or pe <= 0:
        continue
    pcr = pe / ce
    side = "CE" if pcr > 1 else "PE"
    atm = min(strikes, key=lambda k: abs(k - spot))
    series = chain_px[(atm, side)]
    entry = float(series.iloc[i + 1]) if pd.notna(series.iloc[i + 1]) else np.nan
    if not np.isfinite(entry) or entry <= 0:
        continue
    future_spot = float(bars.spot.iloc[i + 1 + STEP]) if i + 1 + STEP < len(bars) else np.nan
    rows.append({"ts": ts, "spot": spot, "pcr": pcr, "side": side, "strike": atm,
                 "entry": entry, "premiums": [float(x) if pd.notna(x) else np.nan
                                              for x in series.iloc[i + 1:]],
                 "future_spot": future_spot})

# non-overlapping trades
trades = []
last_exit = -1
for j, s in enumerate(rows):
    if j <= last_exit:
        continue
    exit_i, exit_px, reason = None, None, "DAY END"
    for q, p in enumerate(s["premiums"]):
        if not np.isfinite(p):
            continue
        if p <= s["entry"] - SL:
            exit_i, exit_px, reason = j + q, p, "SL"
            break
        if p >= s["entry"] + TARGET:
            exit_i, exit_px, reason = j + q, p, "TARGET"
            break
    if exit_i is None:
        vals = [p for p in s["premiums"] if np.isfinite(p)]
        if not vals:
            continue
        exit_i, exit_px = j + len(s["premiums"]) - 1, vals[-1]
    pts = exit_px - s["entry"]
    dir_ok = (np.isfinite(s["future_spot"]) and
              ((s["side"] == "CE" and s["future_spot"] > s["spot"]) or
               (s["side"] == "PE" and s["future_spot"] < s["spot"])))
    trades.append({**{k: s[k] for k in ("ts", "spot", "pcr", "side", "strike", "entry")},
                   "exit_px": exit_px, "reason": reason, "pts": pts,
                   "pnr": pts * LOT, "dir_ok": dir_ok})
    last_exit = exit_i

t = pd.DataFrame(trades)
closed = t[t.reason != "DAY END"]
wins = closed[closed.pts > 0]
losses = closed[closed.pts <= 0]
print("=== BACKTEST: dashboard rules on REAL 19-Nov data ===")
print(f"bars={len(bars)} signals={len(rows)} trades={len(t)} | 1 lot = {LOT} | SL {SL} / TARGET {TARGET}")
print(f"TARGET hits : {len(closed[closed.reason=='TARGET'])}")
print(f"SL hits     : {len(closed[closed.reason=='SL'])}")
print(f"Day-end exits: {(t.reason=='DAY END').sum()}")
print(f"Win rate (closed, target vs SL): {len(wins)/len(closed)*100:.1f}%  ({len(wins)}/{len(closed)})" if len(closed) else "n/a")
print(f"Directional accuracy (next {STEP} bars): {t.dir_ok.mean()*100:.1f}%  ({int(t.dir_ok.sum())}/{len(t)})")
print(f"Net points  : {t.pts.sum():.2f}")
print(f"Net P&L     : Rs {t.pnr.sum():,.0f}  (1 lot = {LOT})")
print(f"Avg win     : Rs {wins.pnr.mean():,.0f} | Avg loss: Rs {losses.pnr.mean():,.0f}" if len(wins) and len(losses) else "")
print(f"Max DD (trade P&L curve): Rs {t.pnr.cumsum().min():,.0f}")
print("\nFirst 8 trades:")
print(t.head(8)[["ts", "side", "strike", "entry", "exit_px", "reason", "pts", "pnr"]].to_string(index=False))
