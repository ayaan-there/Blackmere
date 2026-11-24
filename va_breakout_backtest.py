"""TPO / Volume Profile VAH-VAL breakout strategy adapted to Nifty 5-min.

Core: wait for price to break VAH/VAL (leave balance), require confirming
volume surge + decisive close, enter at close, SL beyond breakout wick,
TP 1.5-2R or opposing POC/LVN. Avoid mid-range entries.

Not available -> proxied: Level 2 heat map, delta profile, big trades, CVD,
TPO exact LVNs. Volume proxy = bar range (index volume = 0).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

MAX_HOLD = 24
TICK = 50.0


def prof(sub):
    b = (sub["close"] / TICK).round() * TICK
    v = sub["volume"].fillna(0).to_numpy()
    va = pd.DataFrame({"b": b.to_numpy(), "v": v}).groupby("b")["v"].sum().sort_values(ascending=False)
    if va.empty:
        return np.nan, np.nan, np.nan
    poc = float(va.index[0])
    total, acc, chosen = va.sum(), 0.0, [poc]
    for p, q in va.items():
        if acc >= 0.70 * total: break
        chosen.append(float(p)); acc += float(q)
    return poc, max(chosen), min(chosen)


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    d["day"] = d["timestamp"].dt.date
    g = d.groupby("day")
    prev = {}
    days = sorted(g.groups.keys())
    for k, day in enumerate(days):
        if k == 0: continue
        prev[day] = prof(g.get_group(days[k-1]))
    P = pd.DataFrame(prev, index=["poc", "vah", "val"]).T
    for col in ("poc", "vah", "val"):
        d[col] = d["day"].map(P[col])

    c, o, h, l = (d[k].to_numpy() for k in ("close", "open", "high", "low"))
    rng = (h - l)
    vol_surge = pd.Series(rng).rolling(20).mean().shift(1).to_numpy()
    rows = []
    n = len(d)
    for i in range(120, n - MAX_HOLD - 2):
        poc, vah, val = (d[k].iloc[i] for k in ("poc", "vah", "val"))
        if any(pd.isna(x) for x in (poc, vah, val)):
            continue
        if d["day"].iloc[i] == d["day"].iloc[i-1] and False:
            continue
        direction = 0
        if c[i] > vah and c[i-1] <= vah and c[i] > o[i] and rng[i] > vol_surge[i]:
            direction = 1        # VAH breakout + volume + bullish close
        elif c[i] < val and c[i-1] >= val and c[i] < o[i] and rng[i] > vol_surge[i]:
            direction = -1       # VAL breakdown
        if not direction:
            continue
        # avoid mid-range (already at edge, so ok); stop beyond breakout wick
        entry = c[i]
        stop = (l[i] - 0.1 * rng[i]) if direction == 1 else (h[i] + 0.1 * rng[i])
        risk = abs(entry - stop)
        if risk <= 0:
            continue
        # target 2R or opposing POC, whichever closer but >= 1.5R
        t2r = entry + 2 * risk if direction == 1 else entry - 2 * risk
        target = t2r
        pnl, res = np.nan, "TIME"
        for m in range(i+1, min(i+MAX_HOLD, n)):
            if d["day"].iloc[m] != d["day"].iloc[i]: break
            if direction == 1:
                if l[m] <= stop: pnl, res = -risk, "SL"; break
                if h[m] >= target: pnl, res = 2*risk, "T"; break
            else:
                if h[m] >= stop: pnl, res = -risk, "SL"; break
                if l[m] <= target: pnl, res = 2*risk, "T"; break
        if np.isnan(pnl):
            pnl = (c[min(i+MAX_HOLD, n)-1] - entry) * direction
        rows.append({"dir": "LONG" if direction == 1 else "SHORT",
                     "pnl": pnl, "r": pnl/risk, "res": res})

    r = pd.DataFrame(rows)
    if r.empty:
        print("koi signal nahi"); return
    print("VAH/VAL BREAKOUT + volume surge on Nifty 5m (5 yrs, 2R)\n")
    print(f"{'Setup':10s} {'n':>5s} {'Win%':>6s} {'AvgR':>7s} {'T%':>5s} {'SL%':>6s}")
    for name, sub in [("LONG", r[r.dir=="LONG"]), ("SHORT", r[r.dir=="SHORT"]), ("ALL", r)]:
        if sub.empty: continue
        print(f"{name:10s} {len(sub):5d} {(sub.pnl>0).mean()*100:6.1f} "
              f"{sub.r.mean():+7.3f} {(sub.res=='T').mean()*100:5.1f} "
              f"{(sub.res=='SL').mean()*100:6.1f}")


if __name__ == "__main__":
    main()
