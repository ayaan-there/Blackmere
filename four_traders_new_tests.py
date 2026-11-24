"""Two UNTESTED ideas from the 4-trader summary:
A) Henrik 'business zone' value-area: SECOND attempt into zone (not first).
B) Kristoff 'gap and go': open gap direction; breakout if momentum follows,
   else gap fill. Nifty has no overnight session -> prev close to 09:15 open gap.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

HOLD = 16
TICK = 50.0


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
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    d["day"]=d["timestamp"].dt.date
    g=d.groupby("day"); days=sorted(g.groups.keys())
    prof={day:profile(g.get_group(day)) for day in days}
    P=pd.DataFrame(prof,index=["vah","val"]).T.sort_index()
    d["pvah"]=d["day"].map(P["vah"].shift(1))
    d["pval"]=d["day"].map(P["val"].shift(1))
    c,o,h,l,atr=(d[k].to_numpy() for k in ("close","open","high","low","atr"))
    dd=d["timestamp"].dt.date.to_numpy(); n=len(d)

    # ---- A) second attempt into value-area zone ----
    rows_a=[]
    for i in range(60,n-HOLD-2):
        vah,val=d["pvah"].iloc[i],d["pval"].iloc[i]
        if pd.isna(vah) or pd.isna(val) or vah<=val: continue
        # count attempts (bar touching zone then leaving) in trailing window
        touch = ((l[i]<=val*1.001) | (h[i]>=vah*0.999))
        if not touch: continue
        # count prior touches in last 20 bars
        prior = (((pd.Series(l).shift(1).iloc[i-20:i] <= val*1.001) |
                  (pd.Series(h).shift(1).iloc[i-20:i] >= vah*0.999)).sum())
        if prior < 1: continue   # this is 2nd+ attempt
        if l[i]<=val*1.001 and c[i]>o[i]: direc=1      # failed push below VAL
        elif h[i]>=vah*0.999 and c[i]<o[i]: direc=-1   # failed push above VAH
        else: continue
        entry=c[i]; risk=atr[i]
        tp=entry+2*risk if direc==1 else entry-2*risk
        sl=entry-risk if direc==1 else entry+risk
        res=0.0
        for m in range(i+1,min(i+HOLD,n)):
            if dd[m]!=dd[i]: break
            if direc==1:
                if l[m]<=sl: res=-1;break
                if h[m]>=tp: res=2;break
            else:
                if h[m]>=sl: res=-1;break
                if l[m]<=tp: res=2;break
        rows_a.append(res)

    # ---- B) gap and go ----
    rows_b=[]
    for day,sub in g:
        if len(sub)<12: continue
        prev_close = P.index.get_loc(day)
        if prev_close==0: continue
        pd_close = float(d[d["day"]==days[prev_close-1]]["close"].iloc[-1])
        op = float(sub["open"].iloc[0])
        gap = (op/pd_close - 1)*100
        if abs(gap) < 0.05: continue      # no meaningful gap
        first = sub.iloc[0]
        a = float(first["atr"])
        if pd.isna(a) or a<=0: continue
        # go with gap on first-bar momentum; else fade (gap fill)
        if gap>0 and first.close>first.open: direc=1
        elif gap<0 and first.close<first.open: direc=-1
        else: direc = -1 if gap>0 else 1   # gap fill attempt
        entry=float(first.close)
        tp=entry+2*a if direc==1 else entry-2*a
        sl=entry-a if direc==1 else entry+a
        res=0.0
        for m in range(1,min(len(sub),HOLD)):
            row=sub.iloc[m]
            if direc==1:
                if row.low<=sl: res=-1;break
                if row.high>=tp: res=2;break
            else:
                if row.high>=sl: res=-1;break
                if row.low<=tp: res=2;break
        rows_b.append({"gap":gap,"go":direc==(1 if gap>0 else -1),"res":res})

    A=pd.Series(rows_a); B=pd.DataFrame(rows_b)
    print("A) HENRIK second-attempt value-area (2R):", end=" ")
    if len(A): print(f"n={len(A)} win={(A>0).mean()*100:.1f}% avgR={A.mean():+.3f}")
    else: print("koi signal nahi")
    print("B) KRISTOFF gap & go (2R):")
    if len(B):
        print(f"   ALL n={len(B)} win={(B.res>0).mean()*100:.1f}% avgR={B.res.mean():+.3f}")
        for go,sub in B.groupby("go"):
            print(f"   {'GO' if go else 'FILL':5s} n={len(sub):4d} win={(sub.res>0).mean()*100:5.1f}% avgR={sub.res.mean():+.3f}")
    else: print("   koi signal nahi")


if __name__=="__main__":
    main()
