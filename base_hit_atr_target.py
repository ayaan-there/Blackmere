"""Role-reversal breakout + retest with 30% daily-ATR 'base hit' target and
early cut (no follow-through -> exit early instead of full stop).

Nifty 5m. Compare: fixed full stop vs early cut; 30% daily ATR target vs 2R.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

HOLD = 16


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    d["day"] = d["timestamp"].dt.date
    g = d.groupby("day")
    daily_atr = pd.concat([g.high.max()-g.low.min(),
                           (g.high.max()-g.close.last()).abs()],axis=1).max(axis=1).ewm(alpha=1/14).mean()
    d["datr"] = d["day"].map(daily_atr.shift(1))
    c,o,h,l,atr = (d[k].to_numpy() for k in ("close","open","high","low","atr"))
    days = d["timestamp"].dt.date.to_numpy()
    n = len(d)
    sh = pd.Series(h).rolling(20).max().shift(1)
    sl = pd.Series(l).rolling(20).min().shift(1)
    rows = []
    for i in range(60, n-HOLD-2):
        r = sh.iloc[i]-sl.iloc[i]
        if pd.isna(d["datr"].iloc[i]) or r<=0: continue
        # breakout of 20-bar high then retest from above (role reversal)
        if c[i] > sh.iloc[i-1] and l[i] <= sh.iloc[i-1]*1.001 and c[i] > o[i]:
            direc, level = 1, sh.iloc[i-1]
        elif c[i] < sl.iloc[i-1] and h[i] >= sl.iloc[i-1]*0.999 and c[i] < o[i]:
            direc, level = -1, sl.iloc[i-1]
        else: continue
        entry = c[i]
        stop = level - 0.15*r if direc==1 else level + 0.15*r
        risk = abs(entry-stop)
        if risk<=0: continue
        tgt_atr = 0.30*d["datr"].iloc[i]
        tgt_2r = 2*risk
        for mode in ("2R","30pctATR"):
            tp = entry + (tgt_2r if mode=="2R" else tgt_atr) if direc==1 else entry - (tgt_2r if mode=="2R" else tgt_atr)
            if abs(tp-entry) < 0.5*risk: continue
            # full stop vs early cut (exit if 2 bars no follow-through)
            for cut in (False, True):
                res = 0.0
                stall = 0
                for m in range(i+1, min(i+HOLD,n)):
                    if days[m]!=days[i]: break
                    if direc==1:
                        if l[m]<=stop: res=-1; break
                        if h[m]>=tp: res=(tp-entry)/risk; break
                        stall = stall+1 if c[m]<=entry else 0
                    else:
                        if h[m]>=stop: res=-1; break
                        if l[m]<=tp: res=(entry-tp)/risk; break
                        stall = stall+1 if c[m]>=entry else 0
                    if cut and stall>=2: res=(c[m]-entry)*direc/risk; break
                rows.append({"mode":mode,"cut":cut,"res":res})
    r=pd.DataFrame(rows)
    if r.empty: print("koi signal nahi"); return
    print("ROLE-REVERSAL + 30%ATR base-hit target (Nifty 5m, 5y)\n")
    for (mode,cut),sub in r.groupby(["mode","cut"]):
        print(f"{mode:10s} early-cut={str(cut):5s} n={len(sub):5d} win={(sub.res>0).mean()*100:5.1f}% avgR={sub.res.mean():+.3f}")


if __name__=="__main__":
    main()
