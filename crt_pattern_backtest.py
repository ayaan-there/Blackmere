"""CRT 3-candle pattern adapted to Nifty 15-min.

C1: extreme high/low (wick to wick).
C2: sweeps C1 low (long) / high (short) but body closes back INSIDE C1 range.
C3: entry when price breaks above C2 high (long) / below C2 low (short).
HTF bias: prior H1 sweep-and-reversal direction (proxy).
Target = opposing extreme of C1; SL adjusted for 1.5 R:R; no early exits.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

MAX_HOLD = 16


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=15))
    d["day"] = d["timestamp"].dt.date
    c, o, h, l = (d[k].to_numpy() for k in ("close", "open", "high", "low"))
    n = len(d)

    # H1 trend proxy: 60-min EMA direction mapped to 15m
    d60 = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=60))
    hdir = pd.Series(np.where(d60.ema9 > d60.ema21, 1,
                       np.where(d60.ema9 < d60.ema21, -1, 0)).astype(float),
                     index=d60["timestamp"])
    d["htf"] = hdir.reindex(d["timestamp"], method="ffill").fillna(0).astype(int).values

    rows = []
    for i in range(60, n - MAX_HOLD - 2):
        # C1 = candle i, C2 = i+1, C3 entry zone from i+2
        c1h, c1l = h[i], l[i]
        if c1h <= c1l: continue
        j = i + 1
        if j >= n: break
        # C2 sweep with body close back inside C1 range
        long_c2 = (l[j] < c1l) and (c1l < c[j] < c1h)
        short_c2 = (h[j] > c1h) and (c1l < c[j] < c1h)
        htf = d["htf"].iloc[i]
        if htf == 1 and not long_c2: continue
        if htf == -1 and not short_c2: continue
        if long_c2: direction = 1
        elif short_c2: direction = -1
        else: continue
        # wick-heavy chop filter: C2 body should be reasonable
        if abs(c[j]-o[j]) < 0.15*(h[j]-l[j]): continue

        entry = None
        for k in range(j+1, min(j+4, n)):
            if d["day"].iloc[k] != d["day"].iloc[i]: break
            if direction == 1 and c[k] > h[j] and h[k] > h[j]:
                entry = h[j]; break
            if direction == -1 and c[k] < l[j] and l[k] < l[j]:
                entry = l[j]; break
        if entry is None: continue
        stop = min(l[i], l[j]) - 0.05*(c1h-c1l) if direction == 1 else max(h[i], h[j]) + 0.05*(c1h-c1l)
        risk = abs(entry-stop)
        if risk <= 0: continue
        # target opposing extreme of C1, require >=1.5R by widening stop if needed
        target = c1h if direction == 1 else c1l
        if abs(target-entry) < 1.5*risk:
            # adjust stop so that R:R = 1.5
            risk = abs(target-entry)/1.5
            stop = entry - risk if direction == 1 else entry + risk
        pnl,res = np.nan,"TIME"
        for m in range(k, min(k+MAX_HOLD,n)):
            if d["day"].iloc[m]!=d["day"].iloc[i]: break
            if direction==1:
                if l[m]<=stop: pnl,res=-risk,"SL"; break
                if h[m]>=target: pnl,res=abs(target-entry),"T"; break
            else:
                if h[m]>=stop: pnl,res=-risk,"SL"; break
                if l[m]<=target: pnl,res=abs(target-entry),"T"; break
        if np.isnan(pnl): pnl=(c[min(k+MAX_HOLD,n)-1]-entry)*direction
        rows.append({"dir":"LONG" if direction==1 else "SHORT","pnl":pnl,
                     "r":pnl/risk,"res":res,"htf":htf})

    r=pd.DataFrame(rows)
    if r.empty: print("koi signal nahi"); return
    print("CRT 3-CANDLE PATTERN on Nifty 15m (5y, 1.5R, HTF bias)\n")
    print(f"{'Setup':12s} {'n':>5s} {'Win%':>6s} {'AvgR':>7s} {'T%':>5s} {'SL%':>6s}")
    for name,sub in [("LONG",r[r.dir=="LONG"]),("SHORT",r[r.dir=="SHORT"]),("ALL",r)]:
        if sub.empty: continue
        print(f"{name:12s} {len(sub):5d} {(sub.pnl>0).mean()*100:6.1f} "
              f"{sub.r.mean():+7.3f} {(sub.res=='T').mean()*100:5.1f} {(sub.res=='SL').mean()*100:6.1f}")


if __name__=="__main__":
    main()
