"""Robert's VWAP first-touch scalp adapted to Nifty 5-min.

First touch of session VWAP (after a trend move) = A+ long (or short).
Limit entry at VWAP. SL ~10 ticks, TP ~10-15 ticks (scaled to Nifty).
First touch only (2nd/3rd touch = skip). VIX/regime filter proxy (ATR).
Compare: first-touch vs later touches; 1:1 vs 1:1.5.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

HOLD = 6   # quick scalp: 1-2 min aim, allow few bars


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    c, o, h, l, vw, atr = (d[k].to_numpy() for k in ("close","open","high","low","vwap","atr"))
    days = d["timestamp"].dt.date.to_numpy()
    n = len(d)
    rows = []
    touch_count = {}
    for i in range(10, n - HOLD - 1):
        if pd.isna(vw[i]) or pd.isna(atr[i]): continue
        day = days[i]
        # distance to VWAP within small band
        dist = abs(l[i]-vw[i]) if c[i]>=vw[i] else abs(h[i]-vw[i])
        if dist > 0.25*atr[i]: continue
        # direction: trend context (price above vwap -> long fade to vwap; below -> short)
        if c[i] > vw[i] and l[i] <= vw[i] and c[i] > o[i]:
            direc = 1
        elif c[i] < vw[i] and h[i] >= vw[i] and c[i] < o[i]:
            direc = -1
        else:
            continue
        tc = touch_count.get(day, 0) + 1
        touch_count[day] = tc
        # stop/target in Nifty points ~ 10-15 ticks NQ scaled: use 0.25 ATR / 0.30 ATR
        risk = 0.25*atr[i]
        for rr in (1.0, 1.5):
            entry = vw[i]
            tp = entry + rr*risk if direc==1 else entry - rr*risk
            sl = entry - risk if direc==1 else entry + risk
            res = 0.0
            for m in range(i+1, min(i+HOLD, n)):
                if days[m] != day: break
                if direc==1:
                    if l[m]<=sl: res=-1; break
                    if h[m]>=tp: res=rr; break
                else:
                    if h[m]>=sl: res=-1; break
                    if l[m]<=tp: res=rr; break
            rows.append({"touch": 1 if tc==1 else (2 if tc==2 else 3),
                         "rr": rr, "res": res})

    r = pd.DataFrame(rows)
    if r.empty: print("koi signal nahi"); return
    print("VWAP FIRST-TOUCH SCALP on Nifty 5m (5y)\n")
    print(f"{'Setup':20s} {'n':>6s} {'win%':>6s} {'avgR':>7s}")
    for t in (1,2,3):
        for rr in (1.0,1.5):
            sub=r[(r.touch==t)&(r.rr==rr)]
            if sub.empty: continue
            print(f"touch {t} @ {rr}R{'':10s} {len(sub):6d} {(sub.res>0).mean()*100:6.1f} {sub.res.mean():+7.3f}")


if __name__=="__main__":
    main()
