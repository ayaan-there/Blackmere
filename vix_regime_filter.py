"""Manuel's VIX regime idea applied to our best strategy:
Do trades perform better when India VIX is CALM/FALLING vs SPIKING/HIGH?

VIX 1m data merged with Nifty 5m signals of VWAP+Structure Pullback.
Regimes tested:
  - VIX level (low < median, high >= median)
  - VIX change over last 1h (rising vs falling)
  - combination
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

HOLD = 16


def load_vix():
    files = sorted((data_loader.Path(config.RAW_DIR).parent / "india_vix" / "1m").rglob("*.parquet")) \
            if False else sorted(__import__("config").DATA_DIR.joinpath("raw","india_vix","1m").rglob("*.parquet"))
    chunks=[data_loader._normalise(pd.read_parquet(f)) for f in files]
    v=pd.concat(chunks,ignore_index=True)
    v["ts"]=v["timestamp"]
    return v[["ts","close"]].rename(columns={"close":"vix"})


def main():
    import config
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    vix = load_vix()
    d = pd.merge_asof(d.sort_values("timestamp"), vix.sort_values("ts"),
                      left_on="timestamp", right_on="ts", direction="backward")
    d["vix_chg"] = d["vix"] - d["vix"].shift(12)   # ~1h change in 5m bars

    c,o,h,l,vw,vxa,atr,vx = (d[k].to_numpy() for k in
                            ("close","open","high","low","vwap","ema21","atr","vix"))
    days=d["timestamp"].dt.date.to_numpy(); n=len(d)
    med=np.nanmedian(vx)
    rows=[]
    for i in range(120,n-HOLD-2):
        if any(pd.isna(x) for x in (vw[i],vxa[i],vx[i],d["vix_chg"].iloc[i])): continue
        hi5=d["ema9"].iloc[i]
        hh=h[i-1]>h[i-5]; hl=l[i-1]>l[i-5]
        lh=h[i-1]<h[i-5]; ll=l[i-1]<l[i-5]
        direc=0
        if c[i]>vw[i] and hh and hl and abs(l[i]-vw[i])<=0.5*atr[i] and c[i]>o[i] and c[i]>vw[i]: direc=1
        elif c[i]<vw[i] and lh and ll and abs(h[i]-vw[i])<=0.5*atr[i] and c[i]<o[i] and c[i]<vw[i]: direc=-1
        if not direc: continue
        entry=vw[i]; risk=abs(c[i]-entry)+atr[i]*0.5
        if risk<=0: continue
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
        lvl = "highVIX" if vx[i]>=med else "lowVIX"
        chg = "VIXrising" if d["vix_chg"].iloc[i]>0 else "VIXfalling"
        rows.append({"lvl":lvl,"chg":chg,"res":res})

    r=pd.DataFrame(rows)
    if r.empty: print("koi signal nahi / VIX merge fail"); return
    print(f"VIX median = {med:.1f}, total signals = {len(r)}\n")
    for col in ("lvl","chg"):
        print(f"--- by {col} ---")
        for k,sub in r.groupby(col):
            print(f"  {k:12s} n={len(sub):5d} win={(sub.res>0).mean()*100:5.1f}% avgR={sub.res.mean():+.3f}")
    print("--- by level x change ---")
    for k,sub in r.groupby(["lvl","chg"]):
        print(f"  {str(k):28s} n={len(sub):5d} win={(sub.res>0).mean()*100:5.1f}% avgR={sub.res.mean():+.3f}")


if __name__=="__main__":
    main()
