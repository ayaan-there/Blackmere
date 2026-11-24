"""Adapted NR4 progressive-compression breakout on Nifty 15-min & 60-min.

4 consecutive candles with non-increasing ranges (step-by-step compression).
Mark final tightest candle high/low. Breakout -> entry. One-and-done (no re-entry).
Exit: ATR trailing stop (volatility adaptive), overnight hold allowed.
Compare: 15m vs 60m, fixed 1:2 vs ATR trail.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

MAX_HOLD = 40


def run(d, label):
    c, h, l, atr = (d[k].to_numpy() for k in ("close","high","low","atr"))
    n = len(d)
    rng = h - l
    rows = []
    for i in range(6, n - MAX_HOLD - 2):
        # 4 consecutive non-increasing ranges ending at i-1 (compression done)
        r4 = rng[i-4:i]
        if not np.all(np.diff(r4) <= 1e-9): continue
        top, bot = h[i-1], l[i-1]
        direction = 0
        oc = d["open"].iloc[i]
        if c[i] > top and c[i] > oc: direction = 1
        elif c[i] < bot and c[i] < oc: direction = -1
        if not direction: continue
        entry = c[i]
        trail = entry - 2*atr[i] if direction==1 else entry + 2*atr[i]
        res = 0.0
        for m in range(i+1, min(i+MAX_HOLD, n)):
            if direction==1:
                trail = max(trail, h[m] - 2*atr[m])
                if l[m] <= trail: res = (trail-entry)/ (2*atr[i]); break
                if m == min(i+MAX_HOLD,n)-1: res = (c[m]-entry)/(2*atr[i])
            else:
                trail = min(trail, l[m] + 2*atr[m])
                if h[m] >= trail: res = (entry-trail)/(2*atr[i]); break
                if m == min(i+MAX_HOLD,n)-1: res = (entry-c[m])/(2*atr[i])
        rows.append({"dir":"LONG" if direction==1 else "SHORT","res":res})

    r = pd.DataFrame(rows)
    if r.empty: print(f"{label}: koi signal nahi"); return
    print(f"\n{label}: n={len(r)} win={(r.res>0).mean()*100:.1f}% avgR={r.res.mean():+.3f}")
    for name, sub in [("LONG",r[r.dir=="LONG"]),("SHORT",r[r.dir=="SHORT"])]:
        if len(sub): print(f"  {name:6s} n={len(sub):4d} win={(sub.res>0).mean()*100:5.1f}% avgR={sub.res.mean():+.3f}")


def main():
    for tf in (15, 60):
        d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=tf))
        run(d, f"NR4 compression breakout ({tf}m, ATR trail)")


if __name__ == "__main__":
    main()
