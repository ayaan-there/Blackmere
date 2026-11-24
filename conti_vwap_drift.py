"""Conti VWAP drift system adapted to Nifty 5-min.

Trend (all 3): price above VWAP + VWAP rising + price up >=0.1% over last hour.
Entry: first opposite (red) candle pulling back toward VWAP; enter next bar open.
SL/TP: 80pt/40pt scaled to Nifty via ATR (negative R:R ~0.5).
Guardrails: 1 position, max 4 trades/day, stop after 2 losses, cutoff, flat EOD.
Reported: ~64-65% win with low R:R (prop-challenge tuned).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

HOLD = 16


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    c, o, h, l, vw, atr = (d[k].to_numpy() for k in ("close","open","high","low","vwap","atr"))
    days = d["timestamp"].dt.date.to_numpy()
    hm = d["timestamp"].dt.hour*60 + d["timestamp"].dt.minute
    n = len(d)
    rows = []
    perday = {}
    for i in range(90, n - HOLD - 2):
        day = days[i]
        if hm[i] < 10*60+15: continue          # skip first hour (10:15 IST ~ 9:45 ET equivalent)
        st = perday.setdefault(day, {"n":0,"loss":0})
        if st["n"] >= 4 or st["loss"] >= 2: continue
        if pd.isna(vw[i]) or pd.isna(atr[i]): continue
        # trend conditions
        rising = vw[i] > vw[i-3]
        up1h = c[i] >= c[i-12] * 1.001
        dn1h = c[i] <= c[i-12] * 0.999
        direc = 0
        if c[i] > vw[i] and rising and up1h: direc = 1
        elif c[i] < vw[i] and (not rising) and dn1h: direc = -1
        if not direc: continue
        # first opposite candle pulling back toward VWAP
        if direc == 1:
            if c[i] > o[i] or abs(l[i]-vw[i]) > 0.5*atr[i]: continue
        else:
            if c[i] < o[i] or abs(h[i]-vw[i]) > 0.5*atr[i]: continue
        if i+1 >= n or days[i+1] != day: continue
        entry = o[i+1]
        risk = 0.8*atr[i]      # 80pt scaled
        reward = 0.4*atr[i] if direc==1 else 0.5*atr[i]   # 40/50pt scaled
        tp = entry + reward if direc==1 else entry - reward
        sl = entry - risk if direc==1 else entry + risk
        res = 0.0
        for m in range(i+1, min(i+HOLD, n)):
            if days[m] != day: break
            if direc==1:
                if l[m]<=sl: res=-1; break
                if h[m]>=tp: res=reward/risk; break
            else:
                if h[m]>=sl: res=-1; break
                if l[m]<=tp: res=reward/risk; break
        rows.append({"dir":"LONG" if direc==1 else "SHORT","res":res})
        st["n"] += 1
        if res < 0: st["loss"] += 1

    r = pd.DataFrame(rows)
    if r.empty: print("koi signal nahi"); return
    print("CONTI VWAP DRIFT on Nifty 5m (5y, negative R:R, guardrails)\n")
    for name, sub in [("LONG",r[r.dir=="LONG"]),("SHORT",r[r.dir=="SHORT"]),("ALL",r)]:
        if sub.empty: continue
        print(f"{name:8s} n={len(sub):5d} win={(sub.res>0).mean()*100:5.1f}% avgR={sub.res.mean():+.3f}")


if __name__=="__main__":
    main()
