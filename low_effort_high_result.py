"""Low-Effort / High-Result engulfment strategy adapted to Nifty 15-min.

Valid candle = body > longest wick.
Long: pullback into prior session value area, then a valid bullish engulfing
      closing above VAH + prior candle high, with volume falling/below its 20-MA
      (low effort, high result). SL = entry candle low, TP = 1:2.
Structural low invalidation + prior structure high cap included.
ATR regime (14 ATR, 200-percentile) + meta-label studied after base test.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

TICK = 50.0
MAX_HOLD = 16


def profile(sub):
    b = (sub["close"] / TICK).round() * TICK
    v = sub["volume"].fillna(0).to_numpy()
    va = pd.DataFrame({"b": b.to_numpy(), "v": v}).groupby("b")["v"].sum().sort_values(ascending=False)
    if va.empty:
        return np.nan, np.nan, np.nan
    poc = float(va.index[0]); total, acc, chosen = va.sum(), 0.0, [poc]
    for p, q in va.items():
        if acc >= 0.70 * total: break
        chosen.append(float(p)); acc += float(q)
    return poc, max(chosen), min(chosen)


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=15))
    d["day"] = d["timestamp"].dt.date
    g = d.groupby("day")
    days = sorted(g.groups.keys())
    prev = {}
    for k, day in enumerate(days):
        if k: prev[day] = profile(g.get_group(days[k-1]))
    P = pd.DataFrame(prev, index=["poc", "vah", "val"]).T
    for col in ("poc", "vah", "val"):
        d[col] = d["day"].map(P[col])

    c, o, h, l = (d[k].to_numpy() for k in ("close", "open", "high", "low"))
    body = np.abs(c - o)
    wick = np.maximum(h - np.maximum(o, c), np.minimum(o, c) - l)
    valid = body > wick
    volma = pd.Series(d["volume"]).rolling(20).mean().shift(1).to_numpy()

    # ATR regime percentile
    atrp = d["atr"].rolling(200).rank(pct=True)

    rows = []
    n = len(d)
    for i in range(120, n - MAX_HOLD - 2):
        poc, vah, val = (d[k].iloc[i] for k in ("poc", "vah", "val"))
        if any(pd.isna(x) for x in (poc, vah, val)):
            continue
        price = c[i]
        # setup zone: pullback into prior value area (or just below VAH)
        if not (val * 0.98 <= price <= vah * 1.02):
            continue
        # valid bullish engulfment: body>wick, close>prev high, body engulfs prev
        eng = (valid[i] and c[i] > o[i] and c[i] > h[i-1] and o[i] < c[i-1])
        # minimum break distance past VAH (~6 pts NQ scaled -> 0.1% of price)
        if not eng or (c[i] - vah) < 0.001 * price:
            continue
        # low effort: volume below 20-MA
        loweff = d["volume"].iloc[i] < volma[i]
        if not loweff:
            continue
        entry = c[i]
        stop = l[i]
        risk = entry - stop
        if risk <= 0:
            continue
        target = entry + 2 * risk
        pnl, res = np.nan, "TIME"
        for m in range(i + 1, min(i + MAX_HOLD, n)):
            if d["day"].iloc[m] != d["day"].iloc[i]: break
            if l[m] <= stop: pnl, res = -risk, "SL"; break
            if h[m] >= target: pnl, res = 2 * risk, "T"; break
        if np.isnan(pnl):
            pnl = c[min(i + MAX_HOLD, n) - 1] - entry
        rows.append({"pnl": pnl, "r": pnl / risk, "res": res,
                     "regime": ("low" if atrp.iloc[i] <= .25 else "med" if atrp.iloc[i] <= .5
                                else "high" if atrp.iloc[i] <= .75 else "extreme"),
                     "vol_ratio": d["volume"].iloc[i] / volma[i] if volma[i] else np.nan})
    r = pd.DataFrame(rows)
    if r.empty:
        print("koi signal nahi"); return
    print("LOW EFFORT / HIGH RESULT (Nifty 15m, 5y, 1:2)\n")
    print(f"ALL n={len(r)} win={(r.pnl>0).mean()*100:.1f}% avgR={r.r.mean():+.3f} "
          f"T={(r.res=='T').mean()*100:.1f}% SL={(r.res=='SL').mean()*100:.1f}%")
    print("\nBy ATR regime:")
    for k, sub in r.groupby("regime"):
        print(f"  {k:8s} n={len(sub):4d} win={(sub.pnl>0).mean()*100:5.1f}% avgR={sub.r.mean():+.3f}")
    print("\nBy volume efficiency (vol/20MA):")
    r["ve"] = pd.cut(r.vol_ratio, [0, .5, .8, 1.0], labels=["very low", "low", "near avg"])
    for k, sub in r.groupby("ve", observed=True):
        print(f"  {str(k):10s} n={len(sub):4d} win={(sub.pnl>0).mean()*100:5.1f}% avgR={sub.r.mean():+.3f}")


if __name__ == "__main__":
    main()
