"""3-Touch range strategy adapted to Nifty 15-min.

Range = rolling swing high/low box. Count touches of each extreme.
After >=3 touches (mature range):
  - Range trade: limit long at bottom / short at top, target opposite edge.
  - Breakout/reclaim: wick beyond edge then close back inside -> fade; or
    close beyond + reclaim -> breakout.
Compare: 1-touch vs 2-touch vs 3-touch maturity (does patience help?).
Fixed SL beyond range, never move. Target = opposite edge or measured move.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

MAX_HOLD = 24
LOOK = 30   # range lookback bars


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=15))
    c, o, h, l = (d[k].to_numpy() for k in ("close", "open", "high", "low"))
    days = d["timestamp"].dt.date.to_numpy()
    n = len(d)
    hi = pd.Series(h).rolling(LOOK).max().shift(1)
    lo = pd.Series(l).rolling(LOOK).min().shift(1)
    # touch counts within last 30 bars
    touch_hi = (h >= hi - 0.001*c).rolling(LOOK).sum()
    touch_lo = (l <= lo + 0.001*c).rolling(LOOK).sum()

    rows = []
    for i in range(LOOK + 5, n - MAX_HOLD - 2):
        rh, rl = hi.iloc[i], lo.iloc[i]
        if pd.isna(rh) or pd.isna(rl) or rh <= rl: continue
        rng = rh - rl
        price = c[i]
        th, tl = touch_hi.iloc[i], touch_lo.iloc[i]
        direction, mode, touches = 0, "", 0
        # bottom of range -> long (fade), top -> short
        if l[i] <= rl + 0.15*rng and tl >= 3:
            direction, mode, touches = 1, "fade_bottom", tl
        elif h[i] >= rh - 0.15*rng and th >= 3:
            direction, mode, touches = -1, "fade_top", th
        if not direction: continue
        # confirmation: reclaim candle close in trade direction
        reclaim = (c[i] > o[i]) if direction == 1 else (c[i] < o[i])
        if not reclaim: continue
        entry = c[i]
        stop = (rl - 0.1*rng) if direction == 1 else (rh + 0.1*rng)
        risk = abs(entry - stop)
        if risk <= 0: continue
        # target opposite edge
        target = rh if direction == 1 else rl
        if abs(target-entry) < 0.5*risk: continue
        pnl, res = np.nan, "TIME"
        for m in range(i+1, min(i+MAX_HOLD, n)):
            if days[m] != days[i]: break
            if direction == 1:
                if l[m] <= stop: pnl, res = -risk, "SL"; break
                if h[m] >= target: pnl, res = abs(target-entry), "T"; break
            else:
                if h[m] >= stop: pnl, res = -risk, "SL"; break
                if l[m] <= target: pnl, res = abs(target-entry), "T"; break
        if np.isnan(pnl): pnl = (c[min(i+MAX_HOLD,n)-1]-entry)*direction
        rows.append({"mode": mode, "touches": int(touches), "pnl": pnl, "r": pnl/risk, "res": res})

    r = pd.DataFrame(rows)
    if r.empty: print("koi signal nahi"); return
    print("3-TOUCH RANGE on Nifty 15m (5y, target=opposite edge)\n")
    print(f"{'Setup':14s} {'n':>5s} {'Win%':>6s} {'AvgR':>7s} {'T%':>5s} {'SL%':>6s}")
    for name, sub in [("fade bottom (L)", r[r["mode"]=="fade_bottom"]),
                      ("fade top (S)", r[r["mode"]=="fade_top"]), ("ALL", r)]:
        if sub.empty: continue
        print(f"{name:14s} {len(sub):5d} {(sub.pnl>0).mean()*100:6.1f} "
              f"{sub.r.mean():+7.3f} {(sub.res=='T').mean()*100:5.1f} {(sub.res=='SL').mean()*100:6.1f}")


if __name__ == "__main__":
    main()
