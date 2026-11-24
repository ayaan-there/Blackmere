"""Henrik's two testable ideas on Nifty 5m:
A) Single-print repair: fast low-volume move leaves a thin price zone;
   price later returns to 'repair' it -> trade back through / continuation.
B) Speed-based choice at key VPOC/VA edge: fast+broad candle -> breakout;
   slow+small candle -> counter-trend fade. Compare both.
Volume proxy = bar range (index volume=0); no real delta/DOM.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

TICK = 50.0
HOLD = 16


def profile(sub):
    b=(sub["close"]/TICK).round()*TICK; v=sub["volume"].fillna(0).to_numpy()
    va=pd.DataFrame({"b":b.to_numpy(),"v":v}).groupby("b")["v"].sum().sort_values(ascending=False)
    if va.empty: return np.nan,np.nan,np.nan
    poc=float(va.index[0]); tot,acc,ch=va.sum(),0.0,[poc]
    for p,q in va.items():
        if acc>=0.7*tot: break
        ch.append(float(p)); acc+=float(q)
    return poc,max(ch),min(ch)


def outcome(d,i,direc,risk,tp_mult):
    c,h,l=(d[k].to_numpy() for k in ("close","high","low"))
    entry=c[i]; tp=entry+tp_mult*risk if direc==1 else entry-tp_mult*risk
    sl=entry-risk if direc==1 else entry+risk
    days=d["timestamp"].dt.date.to_numpy()
    for m in range(i+1,min(i+HOLD,len(d))):
        if days[m]!=days[i]: break
        if direc==1:
            if l[m]<=sl: return -1
            if h[m]>=tp: return tp_mult
        else:
            if h[m]>=sl: return -1
            if l[m]<=tp: return tp_mult
    return (c[min(i+HOLD,len(d))-1]-entry)*direc/risk


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    d["day"]=d["timestamp"].dt.date
    g=d.groupby("day"); days=sorted(g.groups.keys())
    pf={day:profile(g.get_group(day)) for day in days}
    P=pd.DataFrame(pf,index=["poc","vah","val"]).T.sort_index()
    d["poc"]=d["day"].map(P["poc"].shift(1)); d["vah"]=d["day"].map(P["vah"].shift(1))
    d["val"]=d["day"].map(P["val"].shift(1))
    c,o,h,l,atr=(d[k].to_numpy() for k in ("close","open","high","low","atr"))
    rng=h-l
    n=len(d)
    rows={"single_print":[],"speed_breakout":[],"speed_fade":[]}

    for i in range(80,n-HOLD-2):
        poc,vah,val=(d[k].iloc[i] for k in ("poc","vah","val"))
        if any(pd.isna(x) for x in (poc,vah,val)): continue
        risk=atr[i]
        if risk<=0: continue
        # A) single print = narrow quick move gap zone left behind ~10 bars ago
        j=i-10
        if j>0 and rng[j]>1.8*atr[j] and c[j]>o[j]:
            gap_lo=min(l[j],c[j-1]); gap_hi=max(h[j],c[j-1])
            if l[i]<=gap_hi and c[i]>gap_lo and c[i]>o[i]:  # return to repair, bounce
                rows["single_print"].append(outcome(d,i,1,risk,2))
        # B) at VPOC: fast broad candle -> breakout continuation; slow small -> fade
        if abs(c[i]-poc)<0.4*atr[i]:
            fast = rng[i]>1.2*atr[i] and abs(c[i]-o[i])>0.5*rng[i]
            slow = rng[i]<0.7*atr[i] and abs(c[i]-o[i])<0.3*rng[i]
            if fast:
                rows["speed_breakout"].append(outcome(d,i,1 if c[i]>o[i] else -1,risk,2))
            elif slow:
                rows["speed_fade"].append(outcome(d,i,-1 if c[i]>o[i] else 1,risk,2))

    print("HENrik single-print / speed-based ideas (Nifty 5m, 2R)\n")
    for k,v in rows.items():
        s=pd.Series(v)
        if len(s): print(f"{k:16s} n={len(s):5d} win={(s>0).mean()*100:5.1f}% avgR={s.mean():+.3f}")
        else: print(f"{k:16s} koi signal nahi")


if __name__=="__main__":
    main()
