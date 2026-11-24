"""VWAP std-deviation bands: fade price at +2SD (expensive->short) / -2SD
(cheap->long) in Nifty. Compare with VWAP-touch mean reversion. Also test
'first deviation band tag after trend' with momentum continuation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

HOLD = 16


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    d["day"] = d["timestamp"].dt.date
    c, h, l, vw = (d[k].to_numpy() for k in ("close","high","low","vwap"))
    days = d["timestamp"].dt.date.to_numpy()
    # rolling std of (close - vwap) per session for band width proxy
    dev = pd.Series(c - vw).groupby(days).transform(lambda s: s.expanding().std().fillna(0))
    sd = dev.clip(lower=0.1).to_numpy()
    n=len(d)
    rows=[]
    for i in range(30, n-HOLD-2):
        z = (c[i]-vw[i])/sd[i]
        direction = 0
        # cheap/expensive fade at >=2SD (only when price rejects the extreme)
        if z >= 2.0 and c[i] < h[i]:    # expensive; wait for down close
            if c[i] < d["open"].iloc[i]: direction = -1
        elif z <= -2.0 and c[i] > l[i]:
            if c[i] > d["open"].iloc[i]: direction = 1
        if not direction: continue
        entry=c[i]; risk=abs(c[i]-vw[i])*0.5
        if risk<=0: continue
        tp=entry-risk if direction==-1 else entry+risk
        sl=entry+0.5*risk if direction==-1 else entry-0.5*risk
        res=0.0
        for m in range(i+1,min(i+HOLD,n)):
            if days[m]!=days[i]: break
            if direction==-1:
                if h[m]>=sl: res=-1;break
                if l[m]<=tp: res=1;break
            else:
                if l[m]<=sl: res=-1;break
                if h[m]>=tp: res=1;break
        rows.append({"dir":"SHORT expense" if direction==-1 else "LONG cheap","res":res})

    r=pd.DataFrame(rows)
    if r.empty: print("koi signal nahi"); return
    print("VWAP DEVIATION BAND FADE (>=2SD) on Nifty 5m (5y)\n")
    for name,sub in [("SHORT @ +2SD",r[r.dir=="SHORT expense"]),("LONG @ -2SD",r[r.dir=="LONG cheap"]),("ALL",r)]:
        if sub.empty: continue
        print(f"{name:16s} n={len(sub):5d} win={(sub.res>0).mean()*100:5.1f}% avgR={sub.res.mean():+.3f}")


if __name__=="__main__":
    main()
