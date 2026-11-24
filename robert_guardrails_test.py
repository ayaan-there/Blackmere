"""VWAP pullback scalp + Robert's guardrails (1-2 trades/day, stop after 1 win
or 2 losses) on Nifty 5m. Compare expectancy with/without guardrails.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

HOLD = 6


def run(guard):
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    c,o,h,l,vw,atr = (d[k].to_numpy() for k in ("close","open","high","low","vwap","atr"))
    days = d["timestamp"].dt.date.to_numpy()
    n = len(d)
    out=[]
    state={}
    for i in range(10, n-HOLD-1):
        if pd.isna(vw[i]) or pd.isna(atr[i]): continue
        day=days[i]
        st=state.setdefault(day,{"n":0,"w":0,"ls":0})
        if guard and (st["n"]>=2 or st["w"]>=1 or st["ls"]>=2): continue
        if abs(l[i]-vw[i])<=0.25*atr[i] and c[i]>o[i] and c[i]>vw[i]: direc=1
        elif abs(h[i]-vw[i])<=0.25*atr[i] and c[i]<o[i] and c[i]<vw[i]: direc=-1
        else: continue
        entry=vw[i]; risk=0.25*atr[i]
        tp=entry+risk if direc==1 else entry-risk
        sl=entry-risk if direc==1 else entry+risk
        res=0.0
        for m in range(i+1,min(i+HOLD,n)):
            if days[m]!=day: break
            if direc==1:
                if l[m]<=sl: res=-1;break
                if h[m]>=tp: res=1;break
            else:
                if h[m]>=sl: res=-1;break
                if l[m]<=tp: res=1;break
        out.append(res)
        st["n"]+=1
        if res>0: st["w"]+=1
        else: st["ls"]+=1
    return pd.Series(out)


def main():
    for guard in (False, True):
        s=run(guard)
        print(f"guardrails={'ON' if guard else 'OFF':3s} n={len(s):5d} win={(s>0).mean()*100:5.1f}% avgR={s.mean():+.3f} total={s.sum():+.0f}R")


if __name__=="__main__":
    main()
