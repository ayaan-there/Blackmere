"""Matias-style: HH/HL structure + VWAP bias + pullback/squeeze entry on Nifty 5m.

Long: price above VWAP + higher-high/higher-low structure; enter on pullback
      wick toward VWAP that fails to push lower (squeeze), reclaim candle close.
      Limit entry near VWAP (better fill), SL below swing/VWAP, TP 2R or next liquidity.
Short: inverse. Avoid chop: require ADX/ATR movement filter.
Trade cap: max 3/day (simplified).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

MAX_HOLD = 16


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    c, o, h, l, vwap, atr = (d[k].to_numpy() for k in ("close", "open", "high", "low", "vwap", "atr"))
    days = d["timestamp"].dt.date.to_numpy()
    n = len(d)
    rows = []
    perday = {}
    for i in range(80, n - MAX_HOLD - 2):
        day = days[i]
        if perday.get(day, 0) >= 3: continue
        if pd.isna(vwap[i]): continue
        # chop filter: ATR must be meaningful
        if atr[i] < 0.0004 * c[i]: continue
        direction = 0
        # structure HH/HL (last 6 bars) + VWAP alignment
        hh = h[i-1] > h[i-3] and h[i-3] > h[i-5]
        hl = l[i-1] > l[i-3] and l[i-3] > l[i-5]
        lh = h[i-1] < h[i-3] and h[i-3] < h[i-5]
        ll = l[i-1] < l[i-3] and l[i-3] < l[i-5]
        if c[i] > vwap[i] and hh and hl: direction = 1
        elif c[i] < vwap[i] and lh and ll: direction = -1
        if not direction: continue
        # pullback to VWAP: wick touches/closes near VWAP but reclaims
        near = abs(l[i] - vwap[i]) <= 0.5 * atr[i] if direction == 1 else abs(h[i] - vwap[i]) <= 0.5 * atr[i]
        if not near: continue
        reclaim = c[i] > max(o[i], vwap[i]) if direction == 1 else c[i] < min(o[i], vwap[i])
        if not reclaim: continue
        # limit entry at VWAP (better fill)
        entry = vwap[i]
        stop = (min(l[i], entry - atr[i])) if direction == 1 else (max(h[i], entry + atr[i]))
        risk = abs(entry - stop)
        if risk <= 0: continue
        target = entry + 2 * risk if direction == 1 else entry - 2 * risk
        pnl, res = np.nan, "TIME"
        for m in range(i + 1, min(i + MAX_HOLD, n)):
            if days[m] != day: break
            if direction == 1:
                if l[m] <= stop: pnl, res = -risk, "SL"; break
                if h[m] >= target: pnl, res = 2 * risk, "T"; break
            else:
                if h[m] >= stop: pnl, res = -risk, "SL"; break
                if l[m] <= target: pnl, res = 2 * risk, "T"; break
        if np.isnan(pnl): pnl = (c[min(i + MAX_HOLD, n) - 1] - entry) * direction
        rows.append({"dir": "LONG" if direction == 1 else "SHORT",
                     "pnl": pnl, "r": pnl / risk, "res": res})
        perday[day] = perday.get(day, 0) + 1

    r = pd.DataFrame(rows)
    if r.empty: print("koi signal nahi"); return
    print("VWAP + STRUCTURE PULLBACK on Nifty 5m (5y, 2R, <=3/day)\n")
    print(f"{'Setup':10s} {'n':>5s} {'Win%':>6s} {'AvgR':>7s} {'T%':>5s} {'SL%':>6s}")
    for name, sub in [("LONG", r[r.dir == "LONG"]), ("SHORT", r[r.dir == "SHORT"]), ("ALL", r)]:
        if sub.empty: continue
        print(f"{name:10s} {len(sub):5d} {(sub.pnl>0).mean()*100:6.1f} "
              f"{sub.r.mean():+7.3f} {(sub.res=='T').mean()*100:5.1f} {(sub.res=='SL').mean()*100:6.1f}")


if __name__ == "__main__":
    main()
