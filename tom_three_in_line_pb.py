"""Two UNTESTED ideas from Tom's framework on Nifty 15m/5m:
A) 'Three in a line' candlestick (3 consecutive same-color candles) with context
   (only if no obstacle / clean path), 2R target.
B) 'P/B structure' breakout + acceptance (close beyond balance then hold) ->
   continuation in breakout direction.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

HOLD = 16


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=15))
    c,o,h,l,atr = (d[k].to_numpy() for k in ("close","open","high","low","atr"))
    days = d["timestamp"].dt.date.to_numpy()
    n = len(d)

    # A) three in a line
    rows_a=[]
    for i in range(6,n-HOLD-2):
        if all(c[i-k]>o[i-k] for k in (0,1,2)): direc=1
        elif all(c[i-k]<o[i-k] for k in (0,1,2)): direc=-1
        else: continue
        # context: clean path = price beyond 20-bar range (no obstacle ahead)
        hi20=pd.Series(h).rolling(20).max().shift(1).iloc[i]
        lo20=pd.Series(l).rolling(20).min().shift(1).iloc[i]
        if direc==1 and c[i]<hi20: continue
        if direc==-1 and c[i]>lo20: continue
        entry=c[i]; risk=atr[i]
        tp=entry+2*risk if direc==1 else entry-2*risk
        sl=entry-risk if direc==1 else entry+risk
        res=0.0
        for m in range(i+1,min(i+HOLD,n)):
            if days[m]!=days[i]: break
            if direc==1:
                if l[m]<=sl: res=-1;break
                if h[m]>=tp: res=2;break
            else:
                if h[m]>=sl: res=-1;break
                if l[m]<=tp: res=2;break
        rows_a.append(res)

    # B) balance breakout + acceptance (close outside 20-bar balance then retest/hold)
    rows_b=[]
    for i in range(30,n-HOLD-2):
        bal_hi=pd.Series(h).rolling(20).max().shift(2).iloc[i]
        bal_lo=pd.Series(l).rolling(20).min().shift(2).iloc[i]
        if pd.isna(bal_hi): continue
        if c[i-1]>bal_hi and c[i]>bal_hi*0.995 and c[i]>o[i]: direc=1
        elif c[i-1]<bal_lo and c[i]<bal_lo*1.005 and c[i]<o[i]: direc=-1
        else: continue
        entry=c[i]; risk=atr[i]
        tp=entry+2*risk if direc==1 else entry-2*risk
        sl=entry-risk if direc==1 else entry+risk
        res=0.0
        for m in range(i+1,min(i+HOLD,n)):
            if days[m]!=days[i]: break
            if direc==1:
                if l[m]<=sl: res=-1;break
                if h[m]>=tp: res=2;break
            else:
                if h[m]>=sl: res=-1;break
                if l[m]<=tp: res=2;break
        rows_b.append(res)

    A,B=pd.Series(rows_a),pd.Series(rows_b)
    print("A) 'THREE IN A LINE' + clean path (Nifty 15m, 2R):", end=" ")
    if len(A): print(f"n={len(A)} win={(A>0).mean()*100:.1f}% avgR={A.mean():+.3f}")
    else: print("koi signal nahi")
    print("B) BALANCE BREAKOUT + acceptance (Nifty 15m, 2R):", end=" ")
    if len(B): print(f"n={len(B)} win={(B>0).mean()*100:.1f}% avgR={B.mean():+.3f}")
    else: print("koi signal nahi")


if __name__=="__main__":
    main()
