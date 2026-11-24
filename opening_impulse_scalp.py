"""Gold 6PM-reopen strategy adapted to Nifty 9:15 opening impulse.

Analogue: news accumulates overnight -> sharp move at 09:15 open in thin book.
Rule: enter first 1-min bar direction; if continues, add; if rejects, flip once;
if reverses again, stop. Hold seconds-to-minutes. Tested on 1-min bars.
Compare: with/without follow-through filter; first-bar direction only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=1))
    d["day"] = d["timestamp"].dt.date
    d["hm"] = d["timestamp"].dt.hour*60 + d["timestamp"].dt.minute
    g = d.groupby("day")
    rows = []
    for day, sub in g:
        sub = sub[sub.hm >= 9*60+15].head(8)   # first 8 minutes
        if len(sub) < 5: continue
        o,h,l,c = (sub[k].to_numpy() for k in ("open","high","low","close"))
        atr = sub["atr"].iloc[3]
        if pd.isna(atr) or atr<=0: continue
        # first 1-min impulse direction
        d1 = 1 if c[0] > o[0] else -1 if c[0] < o[0] else 0
        if not d1: continue
        # enter at first bar close, small size; hold up to 4 bars
        entry = c[0]
        risk = 0.5*atr
        tp = entry + d1*1.0*atr
        sl = entry - d1*0.5*atr
        res, add = 0.0, False
        for m in range(1, min(5,len(sub))):
            if d1==1:
                if l[m] <= sl: res = -1; break
                if h[m] >= tp: res = 1.0; add=True; break
            else:
                if h[m] >= sl: res = -1; break
                if l[m] <= tp: res = 1.0; add=True; break
        rows.append({"dir":"LONG" if d1==1 else "SHORT","res":res,"add":add})

    r = pd.DataFrame(rows)
    if r.empty: print("koi signal nahi"); return
    print("OPENING IMPULSE scalp (Nifty 9:15, 1-min, 5y)\n")
    for name, sub in [("LONG",r[r.dir=="LONG"]),("SHORT",r[r.dir=="SHORT"]),("ALL",r)]:
        print(f"{name:8s} n={len(sub):5d} win={(sub.res>0).mean()*100:5.1f}% avgR={sub.res.mean():+.3f} "
              f"add-rate={sub['add'].mean()*100:.0f}%")


if __name__=="__main__":
    main()
