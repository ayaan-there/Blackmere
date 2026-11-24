"""Patrick PBD: impulse -> range -> 'ping-pong' within range OR breakout,
confluent with weekly value area. Nifty 15m.

A) Ping-pong: after impulse, trade range extremes (fade) with weekly VA confluence.
B) Range breakout in impulse direction after chop.
C) Counter-trend: impulse exhaustion -> fade at weekly VA edge.
1:2 target, 20-bar hold.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

TICK = 50.0
HOLD = 20


def profile(sub):
    b=(sub["close"]/TICK).round()*TICK; v=sub["volume"].fillna(0).to_numpy()
    va=pd.DataFrame({"b":b.to_numpy(),"v":v}).groupby("b")["v"].sum().sort_values(ascending=False)
    if va.empty: return np.nan,np.nan
    poc=float(va.index[0]); tot,acc,ch=va.sum(),0.0,[poc]
    for p,q in va.items():
        if acc>=0.7*tot: break
        ch.append(float(p)); acc+=float(q)
    return max(ch),min(ch)


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=15))
    d["day"]=d["timestamp"].dt.date
    d["week"]=d["timestamp"].dt.isocalendar().week.astype(int) + d["timestamp"].dt.year*100
    g=d.groupby("week")
    prof={w:profile(sub) for w,sub in g}
    W=pd.DataFrame(prof,index=["vah","val"]).T.sort_index()
    d["wvah"]=d["week"].map(W["vah"].shift(1))
    d["wval"]=d["week"].map(W["val"].shift(1))
    c,o,h,l,atr=(d[k].to_numpy() for k in ("close","open","high","low","atr"))
    n=len(d)
    rows=[]
    for i in range(80,n-HOLD-2):
        wvah,wval=d["wvah"].iloc[i],d["wval"].iloc[i]
        if any(pd.isna(x) for x in (wvah,wval)) or wvah<=wval: continue
        # impulse detection: last 8-bar range > 2x prior 30-bar avg
        r8=h[i-8:i+1].max()-l[i-8:i+1].min()
        r30=(h[i-30:i-8].max()-l[i-30:i-8].min())
        if r30<=0 or r8 < 1.5*r30: continue
        impulse_dir = 1 if c[i-1]>c[i-8] else -1
        # range after impulse: last 6 bars tight
        rr = h[i-6:i+1].max()-l[i-6:i+1].min()
        if rr > 0.6*r8: continue

        setups=[]
        # A) ping-pong fade at range extreme WITH weekly VA confluence
        if impulse_dir==1 and l[i]<=l[i-6:i+1].min()*1.002 and abs(l[i]-wval)<0.5*(wvah-wval):
            setups.append(("pingpong",1))
        elif impulse_dir==-1 and h[i]>=h[i-6:i+1].max()*0.998 and abs(h[i]-wvah)<0.5*(wvah-wval):
            setups.append(("pingpong",-1))
        # B) breakout in impulse direction from range
        if impulse_dir==1 and c[i]>h[i-6:i].max() and c[i]>o[i]: setups.append(("breakout",1))
        elif impulse_dir==-1 and c[i]<l[i-6:i].min() and c[i]<o[i]: setups.append(("breakout",-1))
        # C) counter-trend fade of impulse at weekly VA edge
        if impulse_dir==1 and h[i]>=wvah*0.998 and c[i]<o[i]: setups.append(("counter",-1))
        elif impulse_dir==-1 and l[i]<=wval*1.002 and c[i]>o[i]: setups.append(("counter",1))

        for label,direc in setups:
            entry=c[i]; risk=atr[i]
            tp=entry+2*risk if direc==1 else entry-2*risk
            sl=entry-risk if direc==1 else entry+risk
            res=0.0
            for m in range(i+1,min(i+HOLD,n)):
                if direc==1:
                    if l[m]<=sl: res=-1;break
                    if h[m]>=tp: res=2;break
                else:
                    if h[m]>=sl: res=-1;break
                    if l[m]<=tp: res=2;break
            rows.append({"setup":label,"res":res})

    r=pd.DataFrame(rows)
    if r.empty: print("koi signal nahi"); return
    print("PBD impulse+range + weekly VA (Nifty 15m, 2R)\n")
    for name,sub in r.groupby("setup"):
        print(f"{name:10s} n={len(sub):5d} win={(sub.res>0).mean()*100:5.1f}% avgR={sub.res.mean():+.3f}")


if __name__=="__main__":
    main()
