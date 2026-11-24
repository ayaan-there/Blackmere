"""Andrea's 2 strategies adapted to Nifty:

A) Morning futures: value-to-value reversal / breakout using VAH/VAL + volume.
B) Afternoon 0DTE naked put selling (~10-13 delta OTM), hold to expiry.

Missing -> proxied: GEX, footprint, speed of tape, option block trades.
Index has no real volume -> bar-range proxy. 0DTE put tested on recorded option
chain ticks (19 Nov, 1 Dec expiry) where available, else Black-Scholes estimate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

MAX_HOLD = 24
TICK = 50.0


def prof(sub):
    b = (sub["close"] / TICK).round() * TICK
    v = sub["volume"].fillna(0).to_numpy()
    va = pd.DataFrame({"b": b.to_numpy(), "v": v}).groupby("b")["v"].sum().sort_values(ascending=False)
    if va.empty: return np.nan, np.nan, np.nan
    poc = float(va.index[0]); total, acc, chosen = va.sum(), 0.0, [poc]
    for p, q in va.items():
        if acc >= 0.70*total: break
        chosen.append(float(p)); acc += float(q)
    return poc, max(chosen), min(chosen)


def strategy_a(d):
    g = d.groupby("day"); days = sorted(g.groups.keys()); prev = {}
    for k, day in enumerate(days):
        if k: prev[day] = prof(g.get_group(days[k-1]))
    P = pd.DataFrame(prev, index=["poc","vah","val"]).T
    for col in ("poc","vah","val"): d[col] = d["day"].map(P[col])
    c,o,h,l = (d[k].to_numpy() for k in ("close","open","high","low"))
    rng = h-l
    surge = pd.Series(rng).rolling(20).mean().shift(1).to_numpy()
    rows=[]; n=len(d)
    for i in range(120, n-MAX_HOLD-2):
        poc,vah,val = (d[k].iloc[i] for k in ("poc","vah","val"))
        if any(pd.isna(x) for x in (poc,vah,val)): continue
        direction=0; mode=""
        if c[i]>vah and c[i-1]<=vah and rng[i]>surge[i] and c[i]>o[i]:
            direction,mode=1,"breakout"      # VAH breakout with volume
        elif c[i]<val and c[i-1]>=val and rng[i]>surge[i] and c[i]<o[i]:
            direction,mode=-1,"breakout"
        elif l[i]<val and c[i]>val and c[i]<o[i]:
            direction,mode=1,"reversal"      # failed auction at VAL -> long
        elif h[i]>vah and c[i]<vah and c[i]>o[i]:
            direction,mode=-1,"reversal"     # failed auction at VAH -> short
        if not direction: continue
        entry=c[i]
        stop=(l[i]-0.1*rng[i]) if direction==1 else (h[i]+0.1*rng[i])
        risk=abs(entry-stop)
        if risk<=0: continue
        # target other side of value area (value-to-value)
        target = vah if (direction==1 and vah>entry+risk) else (val if direction==-1 and val<entry-risk else entry+2*risk*direction)
        pnl,res=np.nan,"TIME"
        for m in range(i+1,min(i+MAX_HOLD,n)):
            if d["day"].iloc[m]!=d["day"].iloc[i]: break
            if direction==1:
                if l[m]<=stop: pnl,res=-risk,"SL"; break
                if h[m]>=target: pnl,res=abs(target-entry),"T"; break
            else:
                if h[m]>=stop: pnl,res=-risk,"SL"; break
                if l[m]<=target: pnl,res=abs(target-entry),"T"; break
        if np.isnan(pnl): pnl=(c[min(i+MAX_HOLD,n)-1]-entry)*direction
        rows.append({"mode":mode,"dir":"LONG" if direction==1 else "SHORT","pnl":pnl,"r":pnl/risk,"res":res})
    return pd.DataFrame(rows)


def strategy_b():
    """0DTE OTM put selling proxy on recorded option ticks (19 Nov only).
    Sell ~10-13 delta OTM PE ~2-3 hrs before close, hold to end of day.
    Win = option expires/last price < entry premium (keeps premium).
    """
    import re
    from pathlib import Path
    REC = Path(r"D:\PROJECTS\active\personal\Trading-Assistant\data\recorded")
    idx = data_loader.resample(data_loader._normalise(
        pd.read_parquet(Path(r"D:\PROJECTS\active\personal\Trading-Assistant\data\recorded_core_bars\nifty50_index\20261119.parquet"))), 5)
    t12 = idx[idx["timestamp"].dt.hour == 12]
    spot12 = float(t12["close"].iloc[0]) if len(t12) else float(idx["close"].iloc[len(idx)//2])
    rows=[]
    for p in REC.glob("NIFTY*PE/*.parquet"):
        K = int(re.match(r"NIFTY.*?(\d{5})PE$",p.parent.name).group(1))
        if not (spot12 - 350 <= K <= spot12 - 100):   # OTM put ~1-1.5% below spot
            continue
        t = pd.read_parquet(p, columns=["ts","price"])
        t["ts"]=pd.to_datetime(t["ts"]).dt.tz_localize(None)
        t=t.set_index("ts").sort_index()
        after = t[t.index.hour>=12]
        if after.empty: continue
        entry=float(after.iloc[0]["price"]); last=float(after.iloc[-1]["price"])
        rows.append({"strike":K,"entry":round(entry,2),"last":round(last,2),
                     "pnl":round(entry-last,2)})
    print(f"[0DTE] spot@12 = {spot12:.1f}, OTM PE candidates={len(rows)}")
    return pd.DataFrame(rows)


def show(title, r, keys=()):
    if r.empty: print(f"{title}: koi trade nahi"); return
    print(f"\n=== {title} (n={len(r)}) ===")
    for key in keys:
        for val, sub in r.groupby(key):
            if sub.empty: continue
            print(f"  {str(val):12s} n={len(sub):5d} win={(sub.pnl>0).mean()*100:5.1f}% avgR={sub.r.mean() if 'r' in sub else sub.pnl.mean():+7.3f}")
    print(f"  ALL          n={len(r):5d} win={(r.pnl>0).mean()*100:5.1f}% avgR={r['r'].mean() if 'r' in r else r.pnl.mean():+7.3f}")


if __name__ == "__main__":
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    d["day"] = d["timestamp"].dt.date
    show("A) Morning value-to-value (Nifty 5m, 5y)", strategy_a(d), keys=("mode","dir"))
    show("B) 0DTE OTM put selling (recorded 19 Nov)", strategy_b())
