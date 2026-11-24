"""Hybrid swing: Hurst proxy >50 + autocorrelation <=-0.1 + 5-bar breakout.
Exit: 5xATR target, 4xATR trailing stop. Adapted to Nifty 15-min.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

MAX_HOLD = 48


def hurst_proxy(close, atr, lookback=50):
    """Adapted Hurst 0-100: trend persistence via net displacement / path length."""
    out = np.full(len(close), np.nan)
    for i in range(lookback, len(close)):
        seg = close[i-lookback+1:i+1]
        rets = np.diff(seg)
        net = abs(seg[-1] - seg[0])
        path = np.abs(rets).sum()
        if path > 0:
            # efficiency ratio 0..1 -> scaled 0..100; >50 = persistent
            out[i] = min(net / path * 100 * 2.2, 100)
    return out


def autocorr(close, lag=5, window=20):
    out = np.full(len(close), np.nan)
    for i in range(window, len(close)):
        x = np.sign(np.diff(close[i-window:i+1]))
        if len(x) <= lag: continue
        a, b = x[:-lag], x[lag:]
        if a.std() > 0 and b.std() > 0:
            out[i] = float(np.corrcoef(a, b)[0, 1])
    return out


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=15))
    c, h, l, atr = (d[k].to_numpy() for k in ("close", "high", "low", "atr"))
    days = d["timestamp"].dt.date.to_numpy()
    n = len(d)
    d["hurst"] = hurst_proxy(c, atr)
    d["ac"] = autocorr(c)
    hi5 = pd.Series(h).rolling(5).max().shift(1)
    lo5 = pd.Series(l).rolling(5).min().shift(1)

    rows = []
    for i in range(120, n - MAX_HOLD - 2):
        hu, ac = d["hurst"].iloc[i], d["ac"].iloc[i]
        if pd.isna(hu) or pd.isna(ac) or pd.isna(hi5.iloc[i]): continue
        if not (hu > 50 and ac <= -0.1): continue
        direction = 0
        if c[i] > hi5.iloc[i] and c[i] > d["ema9"].iloc[i]: direction = 1
        elif c[i] < lo5.iloc[i] and c[i] < d["ema9"].iloc[i]: direction = -1
        if not direction: continue

        entry = c[i]
        a = atr[i]
        target = entry + 5*a if direction == 1 else entry - 5*a
        trail = entry - 4*a if direction == 1 else entry + 4*a
        pnl, res = np.nan, "TIME"
        for m in range(i+1, min(i+MAX_HOLD, n)):
            if days[m] != days[i]: break
            if direction == 1:
                trail = max(trail, h[m] - 4*atr[m])
                if l[m] <= trail: pnl, res = trail-entry, "SL"; break
                if h[m] >= target: pnl, res = 5*a, "T"; break
            else:
                trail = min(trail, l[m] + 4*atr[m])
                if h[m] >= trail: pnl, res = entry-trail, "SL"; break
                if l[m] <= target: pnl, res = 5*a, "T"; break
        if np.isnan(pnl): pnl = (c[min(i+MAX_HOLD,n)-1]-entry)*direction
        risk0 = 4*a
        rows.append({"dir": "LONG" if direction == 1 else "SHORT",
                     "pnl": pnl, "r": pnl/risk0, "res": res})

    r = pd.DataFrame(rows)
    if r.empty: print("koi signal nahi"); return
    print("HURST + AUTOCORR + 5BAR BREAKOUT on Nifty 15m (5y)\n")
    print(f"{'Setup':10s} {'n':>5s} {'Win%':>6s} {'AvgR':>7s} {'T%':>5s} {'SL%':>6s}")
    for name, sub in [("LONG", r[r.dir=="LONG"]), ("SHORT", r[r.dir=="SHORT"]), ("ALL", r)]:
        if sub.empty: continue
        print(f"{name:10s} {len(sub):5d} {(sub.pnl>0).mean()*100:6.1f} "
              f"{sub.r.mean():+7.3f} {(sub.res=='T').mean()*100:5.1f} {(sub.res=='SL').mean()*100:6.1f}")


if __name__ == "__main__":
    main()
