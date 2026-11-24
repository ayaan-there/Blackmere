"""Test one NEW mechanical idea: wick-touch stop vs close-based structural invalidation.

On our best strategy (VWAP+Structure style), compare:
 A) SL on wick touch (l <= sl)  [strict]
 B) SL only on CLOSE beyond level (c <= sl), ignoring brief pierce [liquidity sweep logic]
Target 2R, same entry. Which survives better on Nifty?
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

HOLD = 16


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    c,o,h,l,vw,atr=(d[k].to_numpy() for k in ("close","open","high","low","vwap","atr"))
    days=d["timestamp"].dt.date.to_numpy(); n=len(d)
    rows=[]
    for i in range(80,n-HOLD-2):
        if pd.isna(vw[i]) or pd.isna(atr[i]): continue
        hh=h[i-1]>h[i-3]; hl=l[i-1]>l[i-3]
        direc=0
        if c[i]>vw[i] and hh and hl and abs(l[i]-vw[i])<=0.5*atr[i] and c[i]>o[i]: direc=1
        elif c[i]<vw[i] and (h[i-1]<h[i-3]) and (l[i-1]<l[i-3]) and abs(h[i]-vw[i])<=0.5*atr[i] and c[i]<o[i]: direc=-1
        if not direc: continue
        entry=vw[i]; risk=atr[i]
        if risk<=0: continue
        sl=entry-risk if direc==1 else entry+risk
        tp=entry+2*risk if direc==1 else entry-2*risk
        res={}
        for mode in ("wick","close"):
            hit=False; out=0.0
            for m in range(i+1,min(i+HOLD,n)):
                if days[m]!=days[i]: break
                bad = (l[m]<=sl) if mode=="wick" else (c[m]<=sl)
                good = (h[m]>=tp) if direc==1 else (l[m]<=tp)
                if direc==-1:
                    bad = (h[m]>=sl) if mode=="wick" else (c[m]>=sl)
                if bad: out=-1; hit=True; break
                if good: out=2; hit=True; break
            if not hit: out=(c[min(i+HOLD,n)-1]-entry)*direc/risk
            res[mode]=out
        rows.append(res)
    r=pd.DataFrame(rows)
    if r.empty: print("koi signal nahi"); return
    print("WICK-TOUCH STOP vs CLOSE-BASED INVALIDATION (Nifty 5m, 2R)\n")
    for col in ("wick","close"):
        print(f"{col:8s} n={len(r):5d} win={(r[col]>0).mean()*100:5.1f}% avgR={r[col].mean():+.3f}")


if __name__=="__main__":
    main()
