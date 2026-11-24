"""Value-migration drift strategy adapted to Nifty 15-min.

Value migration = POC / value-area midpoint shifting up or down across
consecutive sessions. Trade in direction of migration:
  - POC rising -> long bias, enter on pullback/reclaim at value levels.
  - POC falling -> short bias.
Compare: with chop filter (trend only) vs all; 1:1 and 1:2.
Uses proxy volume (bar range); no real delta/footprint/effort boxes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

TICK = 50.0
HOLD = 16


def profile(sub):
    b = (sub["close"]/TICK).round()*TICK
    v = sub["volume"].fillna(0).to_numpy()
    va = pd.DataFrame({"b":b.to_numpy(),"v":v}).groupby("b")["v"].sum().sort_values(ascending=False)
    if va.empty: return np.nan, np.nan, np.nan
    poc=float(va.index[0]); tot,acc,ch=va.sum(),0.0,[poc]
    for p,q in va.items():
        if acc>=0.7*tot: break
        ch.append(float(p)); acc+=float(q)
    return poc, max(ch), min(ch)


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=15))
    d["day"] = d["timestamp"].dt.date
    g = d.groupby("day")
    days = sorted(g.groups.keys())
    prof = {day: profile(g.get_group(day)) for day in days}
    rows=[]
    P=pd.DataFrame(prof,index=["poc","vah","val"]).T.sort_index()

    for k in range(3, len(days)-1):
        day=days[k]; sub=g.get_group(day)
        poc,vah,val=P.loc[day,["poc","vah","val"]]
        p1,p2,p3 = P["poc"].iloc[k-3:k].astype(float).values
        if any(pd.isna(x) for x in (poc,vah,val,p1,p2,p3)): continue
        migration = 1 if poc>p2>p1 else (-1 if poc<p2<p1 else 0)   # 3-session rising/falling POC
        if not migration: continue
        c,o,h,l,vw,atr=(sub[k] for k in ("close","open","high","low","vwap","atr"))
        for i in range(6,len(sub)-HOLD-1):
            if pd.isna(vw.iloc[i]): continue
            # pullback to value with reclaim (entry with control confirmation)
            if migration==1 and l.iloc[i]<=vw.iloc[i]*1.002 and c.iloc[i]>o.iloc[i] and c.iloc[i]>vw.iloc[i]:
                direc=1
            elif migration==-1 and h.iloc[i]>=vw.iloc[i]*0.998 and c.iloc[i]<o.iloc[i] and c.iloc[i]<vw.iloc[i]:
                direc=-1
            else: continue
            entry=c.iloc[i]; risk=atr.iloc[i]
            if risk<=0: continue
            for rr in (1,2):
                tp=entry+rr*risk if direc==1 else entry-rr*risk
                sl=entry-risk if direc==1 else entry+risk
                res=0.0
                for m in range(i+1,min(i+HOLD,len(sub))):
                    if direc==1:
                        if l.iloc[m]<=sl: res=-1;break
                        if h.iloc[m]>=tp: res=rr;break
                    else:
                        if h.iloc[m]>=sl: res=-1;break
                        if l.iloc[m]<=tp: res=rr;break
                rows.append({"mig":migration,"rr":rr,"res":res})

    r=pd.DataFrame(rows)
    if r.empty: print("koi signal nahi"); return
    print("VALUE MIGRATION drift on Nifty 15m (5y)\n")
    print(f"{'Setup':22s} {'n':>6s} {'win%':>6s} {'avgR':>7s}")
    for mig,label in ((1,"POC rising -> LONG"),(-1,"POC falling -> SHORT")):
        for rr in (1,2):
            sub=r[(r.mig==mig)&(r.rr==rr)]
            if sub.empty: continue
            print(f"{label+' '+str(rr)+'R':22s} {len(sub):6d} {(sub.res>0).mean()*100:6.1f} {sub.res.mean():+7.3f}")


if __name__=="__main__":
    main()
