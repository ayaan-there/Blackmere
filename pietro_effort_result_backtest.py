"""Pietro-style Bias / Zones / Effort-vs-Result adapted to Nifty 5-min.

Bias  : trend = 2 body-closes beyond prior body+wicks (structure) OR shifting VAs;
        else range (avoid buying top / shorting bottom).
Zones : value area edges (VAH/VAL) + high-volume nodes (proxy for delta nodes).
Trigger: 'effort vs result' = large range candle with small body (absorption),
        then next candle close confirms reversal (or continuation in trend).
Missing (no data): DeepDOM heatmap, gamma, COT, big trades, effort indicator.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

MAX_HOLD = 16
TICK = 50.0


def prof(sub):
    b = (sub["close"] / TICK).round() * TICK
    v = sub["volume"].fillna(0).to_numpy()
    va = pd.DataFrame({"b": b.to_numpy(), "v": v}).groupby("b")["v"].sum().sort_values(ascending=False)
    if va.empty: return np.nan, np.nan, np.nan, np.nan
    poc = float(va.index[0]); total, acc, chosen = va.sum(), 0.0, [poc]
    for p, q in va.items():
        if acc >= 0.70*total: break
        chosen.append(float(p)); acc += float(q)
    return poc, max(chosen), min(chosen), float(va.iloc[0])


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    d["day"] = d["timestamp"].dt.date
    g = d.groupby("day")
    daily = pd.DataFrame({"C": g.close.last(), "O": g.open.first(),
                          "H": g.high.max(), "L": g.low.min()})
    # structural trend: body close beyond prior body+wicks twice
    up1 = daily.C > daily.H.shift(1)
    dn1 = daily.C < daily.L.shift(1)
    daily["trend"] = np.where(up1 & up1.shift(1).fillna(False).astype(bool), 1,
                       np.where(dn1 & dn1.shift(1).fillna(False).astype(bool), -1, 0))
    daily["trend"] = daily["trend"].ffill().fillna(0)
    d["trend"] = d["day"].map(daily["trend"]).fillna(0)

    days = sorted(g.groups.keys())
    prev = {}
    for k, day in enumerate(days):
        if k: prev[day] = prof(g.get_group(days[k-1]))
    P = pd.DataFrame(prev, index=["poc","vah","val","hv"]).T
    for col in ("poc","vah","val","hv"):
        d[col] = d["day"].map(P[col])

    c,o,h,l = (d[k].to_numpy() for k in ("close","open","high","low"))
    rng = h-l
    body = np.abs(c-o)
    effort = pd.Series(rng).rolling(20).mean().shift(1).to_numpy()
    rows = []
    n = len(d)
    for i in range(120, n-MAX_HOLD-2):
        poc, vah, val, hv = (d[k].iloc[i] for k in ("poc","vah","val","hv"))
        if any(pd.isna(x) for x in (poc, vah, val)): continue
        tr = d["trend"].iloc[i]
        price = c[i]
        # effort vs result: big range, small body
        absorption = (rng[i] > 1.3*effort[i]) and (body[i] < 0.35*rng[i])
        if not absorption: continue
        direction = 0
        if tr == 0:  # range: fade extremes (but not middle)
            if abs(price - val) < 0.5*(vah-val) and l[i] <= val*1.002 and c[i] > o[i]:
                direction = 1
            elif abs(price - vah) < 0.5*(vah-val) and h[i] >= vah*0.998 and c[i] < o[i]:
                direction = -1
        else: # trend: continuation with trend at VAH/VAL zone
            if tr == 1 and price > val and c[i] > o[i]: direction = 1
            elif tr == -1 and price < vah and c[i] < o[i]: direction = -1
        if not direction: continue
        # next candle close confirms
        j = i+1
        if j>=n or d["day"].iloc[j]!=d["day"].iloc[i]: continue
        if not ((c[j]>o[j]) if direction==1 else (c[j]<o[j])): continue
        entry = c[j]
        stop = (l[i]-0.1*rng[i]) if direction==1 else (h[i]+0.1*rng[i])
        risk = abs(entry-stop)
        if risk<=0: continue
        target = entry + 2*risk if direction==1 else entry - 2*risk
        pnl,res = np.nan,"TIME"
        for m in range(j, min(j+MAX_HOLD,n)):
            if d["day"].iloc[m]!=d["day"].iloc[i]: break
            if direction==1:
                if l[m]<=stop: pnl,res=-risk,"SL"; break
                if h[m]>=target: pnl,res=2*risk,"T"; break
            else:
                if h[m]>=stop: pnl,res=-risk,"SL"; break
                if l[m]<=target: pnl,res=2*risk,"T"; break
        if np.isnan(pnl): pnl=(c[min(j+MAX_HOLD,n)-1]-entry)*direction
        rows.append({"regime":"trend" if tr else "range",
                     "dir":"LONG" if direction==1 else "SHORT",
                     "pnl":pnl,"r":pnl/risk,"res":res})
    r=pd.DataFrame(rows)
    if r.empty: print("koi signal nahi"); return
    print("PIETRO effort-vs-result on Nifty 5m (5 yrs, 2R)\n")
    print(f"{'Setup':16s} {'n':>5s} {'Win%':>6s} {'AvgR':>7s} {'T%':>5s} {'SL%':>6s}")
    for name,sub in [("Range-fade",r[r.regime=="range"]),("Trend-cont.",r[r.regime=="trend"]),
                     ("LONG",r[r.dir=="LONG"]),("SHORT",r[r.dir=="SHORT"]),("ALL",r)]:
        if sub.empty: continue
        print(f"{name:16s} {len(sub):5d} {(sub.pnl>0).mean()*100:6.1f} "
              f"{sub.r.mean():+7.3f} {(sub.res=='T').mean()*100:5.1f} {(sub.res=='SL').mean()*100:6.1f}")


if __name__ == "__main__":
    main()
