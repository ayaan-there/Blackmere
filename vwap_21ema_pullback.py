"""Trend pullback: price above VWAP + above 21EMA, pullback to VWAP/21EMA
zone, reclaim candle -> long (inverse short). Positive R:R 1:1.5.
Guardrails: max 3/day, stop after 2 losses, stop after 2 wins.
Compare with/without guardrails.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

HOLD = 12


def run(guard):
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    c,o,h,l,vw,ema21,atr=(d[k].to_numpy() for k in ("close","open","high","low","vwap","ema21","atr"))
    days=d["timestamp"].dt.date.to_numpy(); n=len(d)
    out=[]; state={}
    for i in range(60,n-HOLD-2):
        day=days[i]
        st=state.setdefault(day,{"n":0,"w":0,"ls":0})
        if guard and (st["n"]>=3 or st["ls"]>=2 or st["w"]>=2): continue
        if pd.isna(vw[i]) or pd.isna(ema21[i]): continue
        direction=0
        # trend pullback to VWAP/21EMA zone with reclaim
        if c[i]>vw[i] and c[i]>ema21[i] and l[i]<=max(vw[i],ema21[i])*1.003 and c[i]>o[i] and c[i]>vw[i]:
            direction=1
        elif c[i]<vw[i] and c[i]<ema21[i] and h[i]>=min(vw[i],ema21[i])*0.997 and c[i]<o[i] and c[i]<vw[i]:
            direction=-1
        if not direction: continue
        entry=c[i]; risk=atr[i]
        tp=entry+1.5*risk if direction==1 else entry-1.5*risk
        sl=entry-risk if direction==1 else entry+risk
        res=0.0
        for m in range(i+1,min(i+HOLD,n)):
            if days[m]!=day: break
            if direction==1:
                if l[m]<=sl: res=-1;break
                if h[m]>=tp: res=1.5;break
            else:
                if h[m]>=sl: res=-1;break
                if l[m]<=tp: res=1.5;break
        out.append(res)
        st["n"]+=1
        if res>0: st["w"]+=1
        else: st["ls"]+=1
    return pd.Series(out)


def main():
    for guard in (False,True):
        s=run(guard)
        print(f"guard={'ON' if guard else 'OFF':3s} n={len(s):5d} win={(s>0).mean()*100:5.1f}% "
              f"avgR={s.mean():+.3f} total={s.sum():+.0f}R")


if __name__=="__main__":
    main()
