"""Corrected paper run + PIVOT confluence on BEES & Index (15m).

Fix: short SL above entry, target below entry.
Pivot filter: prior-day P/R1/S1/R2/S2. Long only if price>P (or near S1/S2 support),
short only if price<P (or near R1/R2 resistance). Compare with/without pivot.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import config
import data_loader
import engine


def load(kind):
    p=config.DATA_DIR/"raw"/kind/"1m"
    ch=[data_loader._normalise(pd.read_parquet(f)) for f in sorted(p.rglob("*.parquet"))]
    return engine.add_indicators(data_loader.resample(pd.concat(ch,ignore_index=True),15))


def pivots(d):
    g=d.groupby(d["timestamp"].dt.date)
    H=g.high.max().shift(1); L=g.low.min().shift(1); C=g.close.last().shift(1)
    P=(H+L+C)/3
    out=pd.DataFrame({"P":P,"R1":2*P-L,"S1":2*P-H,
                      "R2":P+(H-L),"S2":P-(H-L)})
    day=d["timestamp"].dt.date
    return out.reindex(day).reset_index(drop=True)


def run(d, use_pivot):
    pv=pivots(d)
    c,o,h,l,vw,atr=(d[k].to_numpy() for k in ("close","open","high","low","vwap","atr"))
    P,R1,S1,R2,S2=(pv[k].to_numpy() for k in ("P","R1","S1","R2","S2"))
    days=d["timestamp"].dt.date.to_numpy(); res=[]
    for i in range(120,len(d)-16):
        if pd.isna(vw[i]) or pd.isna(atr[i]): continue
        hh=h[i-1]>h[i-3]; hl=l[i-1]>l[i-3]; lh=h[i-1]<h[i-3]; ll=l[i-1]<l[i-3]
        direc=0
        if c[i]>vw[i] and hh and hl and abs(l[i]-vw[i])<=0.5*atr[i] and c[i]>o[i]: direc=1
        elif c[i]<vw[i] and lh and ll and abs(h[i]-vw[i])<=0.5*atr[i] and c[i]<o[i]: direc=-1
        if not direc: continue
        if use_pivot:
            if pd.isna(P[i]): continue
            band=0.4*atr[i]
            if direc==1 and not (c[i]>P[i] or min(abs(c[i]-S1[i]),abs(c[i]-S2[i]))<band): continue
            if direc==-1 and not (c[i]<P[i] or min(abs(c[i]-R1[i]),abs(c[i]-R2[i]))<band): continue
        e=c[i]; r=atr[i]
        sl=e-r if direc==1 else e+r
        tp=e+2*r if direc==1 else e-2*r
        out=None
        for m in range(i+1,min(i+16,len(d))):
            if days[m]!=days[i]: break
            bad=(c[m]<=sl) if direc==1 else (c[m]>=sl)   # close-based SL
            good=(h[m]>=tp) if direc==1 else (l[m]<=tp)
            if bad: out=-1; break
            if good: out=2; break
        if out is None: out=(c[min(i+16,len(d))-1]-e)*direc/r
        res.append(out)
    s=pd.Series(res)
    return len(s), (s>0).mean()*100, s.mean()


def main():
    for name in ("nifty50_index","nifty50_etf"):
        d=load(name)
        print(f"\n{name} (15m):")
        for piv in (False,True):
            n,w,e=run(d,piv)
            print(f"  pivot={'ON' if piv else 'OFF':3s} n={n:5d} win={w:5.1f}% avgR={e:+.3f}")


if __name__=="__main__":
    main()
