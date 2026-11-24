"""WALK-FORWARD PAPER RUN — exact dashboard rules, BEFORE building dashboard.

BEES   : 5y, 15m, VWAP+Structure signal, close-based SL (wick ignored), trail exit.
OPTIONS: recorded tick data (19 & 21 Nov), 5m, ATM CE/PE, entry at signal bar
         option LTP, SL Rs20 close-based, Target A Rs40 / Target B trail.
"""

from __future__ import annotations

import glob
import re
from pathlib import Path

import numpy as np
import pandas as pd

import config
import data_loader
import engine

RECORDED = Path(r"D:\PROJECTS\active\personal\Trading-Assistant\data\recorded")
CORE = Path(r"D:\PROJECTS\active\personal\Trading-Assistant\data\recorded_core_bars")


def signals(d):
    c,o,h,l,vw,atr=(d[k].to_numpy() for k in ("close","open","high","low","vwap","atr"))
    out=[]
    for i in range(120,len(d)-3):
        if pd.isna(vw[i]) or pd.isna(atr[i]): continue
        hh=h[i-1]>h[i-3]; hl=l[i-1]>l[i-3]; lh=h[i-1]<h[i-3]; ll=l[i-1]<l[i-3]
        if c[i]>vw[i] and hh and hl and abs(l[i]-vw[i])<=0.5*atr[i] and c[i]>o[i]:
            out.append((i,1))
        elif c[i]<vw[i] and lh and ll and abs(h[i]-vw[i])<=0.5*atr[i] and c[i]<o[i]:
            out.append((i,-1))
    return out


def bees_run():
    p=config.DATA_DIR/"raw"/"nifty50_etf"/"1m"
    chunks=[data_loader._normalise(pd.read_parquet(f)) for f in sorted(p.rglob("*.parquet"))]
    d=engine.add_indicators(data_loader.resample(pd.concat(chunks,ignore_index=True),15))
    c,o,h,l,vw,atr=(d[k].to_numpy() for k in ("close","open","high","low","vwap","atr"))
    days=d["timestamp"].dt.date.to_numpy()
    trades=[]
    for i,direc in signals(d):
        if i+1>=len(d) or days[i+1]!=days[i]: continue
        entry=o[i+1]; risk=atr[i]
        if risk<=0: continue
        sl=entry-risk; tp=entry+2*risk
        res=None; mode="TIME"
        for m in range(i+1,min(i+16,len(d))):
            if days[m]!=days[i]: break
            # close-based stop (wick ignored); target touches on high/low
            if (c[m]<=sl if direc==1 else c[m]>=sl): res=-1; mode="SL"; break
            if (h[m]>=tp if direc==1 else l[m]<=tp): res=2; mode="T"; break
        if res is None:
            res=(c[min(i+16,len(d))-1]-entry)*direc/risk; mode="TIME"
        trades.append(res)
    s=pd.Series(trades)
    print("BEES (5y, 15m, VWAP+Structure, close-SL, 2R):")
    print(f"  trades={len(s)} win={(s>0).mean()*100:.1f}% avgR={s.mean():+.3f} "
          f"SL={sum(1 for x in s if x==-1)/len(s)*100:.1f}% T={sum(1 for x in s if x==2)/len(s)*100:.1f}%")


def options_run():
    # option ticks by (day, strike, side)
    opt={}
    for f in RECORDED.glob("NIFTY*/*.parquet"):
        day=f.stem
        m=re.match(r"NIFTY.*?(\d{5})(CE|PE)$",f.parent.name)
        if not m: continue
        K,side=int(m.group(1)),m.group(2)
        t=pd.read_parquet(f,columns=["ts","price"])
        t["ts"]=pd.to_datetime(t["ts"]).dt.tz_localize(None)
        t=t.set_index("ts").sort_index()
        bar=t.resample("5min",label="left",closed="left")["price"].agg(["first","max","min","last"]).dropna()
        opt[(day,K,side)]=bar
    days=sorted(set(k[0] for k in opt))
    print(f"\nOPTIONS (recorded {len(days)} days: {days}):")

    trades=[]
    for day in days:
        idxpath=CORE/"nifty50_index"/f"{day}.parquet"
        if not idxpath.exists():
            print(f"  index missing for {day}"); continue
        idx=engine.add_indicators(data_loader.resample(
            data_loader._normalise(pd.read_parquet(idxpath)),5))
        for i,direc in signals(idx):
            t0=idx["timestamp"].iloc[i].floor("5min")
            spot=idx["close"].iloc[i]
            K=int(round(spot/50)*50)
            side="CE" if direc==1 else "PE"
            bar=opt.get((day,K,side))
            if bar is None or t0 not in bar.index:
                # try nearest available strike
                cand=[(kk[1],bar2) for kk,bar2 in opt.items()
                      if kk[0]==day and kk[2]==side and t0 in bar2.index]
                if not cand: continue
                K,bar=min(cand,key=lambda x:abs(x[0]-spot))
            entry=float(bar.loc[t0,"last"])
            if entry<=0: continue
            sl, tgt = entry-20, entry+40
            res=None; mode="TIME"
            ts=list(bar.index)
            pos=ts.index(t0)
            for k in range(pos+1,min(pos+9,len(ts))):
                hi,lo,cl=bar.iloc[k][["max","min","last"]]
                if cl<=sl: res=-20; mode="SL"; break   # close-based SL
                if hi>=tgt: res=40; mode="T"; break     # target touches on high
            if res is None and pos+8<len(ts): res=float(bar.iloc[pos+8]["last"])-entry
            if res is None: continue
            trades.append({"day":day,"time":str(t0),"option":str(K)+side,
                           "entry":round(entry,2),"result":mode,"pnl":round(res,2)})
    if not trades:
        print("  koi option signal nahi mila"); return
    df=pd.DataFrame(trades,columns=["day","time","option","entry","result","pnl"])
    print(df.to_string(index=False))
    print(f"  trades={len(df)} win={(df.pnl>0).mean()*100:.1f}% total=Rs{df.pnl.sum():.0f}")


if __name__=="__main__":
    bees_run()
    options_run()
