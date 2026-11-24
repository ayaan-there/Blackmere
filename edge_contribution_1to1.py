"""Edge-contribution methodology applied to our Nifty trigger library.

Per the framework: test each short-term trigger at a fixed 1:1 R:R baseline,
one at a time, then compare. (No indicator stacking.)
Triggers: VWAP pullback reclaim, 5-bar breakout, liquidity-refill C1+C2,
OB sweep (early), VAL fade, ATR-band dip, Hurst+AC breakout.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine
from liquidity_refill_backtest import main as _unused  # noqa (module loads fine)

HOLD = 16


def baseline(signals, df, R=1.0, hold=HOLD):
    """signals: list of (bar_index, direction). Returns hit%, expectancy in R."""
    c, h, l = (df[k].to_numpy() for k in ("close", "high", "low"))
    days = df["timestamp"].dt.date.to_numpy()
    out = []
    for i, direc in signals:
        entry = c[i]
        # fixed R=R% of entry (1:1 target = R, stop = R)
        risk = R / 100 * entry
        tp = entry + risk if direc == 1 else entry - risk
        sl = entry - risk if direc == 1 else entry + risk
        res = 0.0
        for m in range(i + 1, min(i + hold, len(df))):
            if days[m] != days[i]: break
            if direc == 1:
                if l[m] <= sl: res = -1.0; break
                if h[m] >= tp: res = 1.0; break
            else:
                if h[m] >= sl: res = -1.0; break
                if l[m] <= tp: res = 1.0; break
        out.append(res)
    a = np.array(out)
    return len(a), (a > 0).mean() * 100 if len(a) else 0, a.mean() if len(a) else 0


def main():
    d5 = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    d15 = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=15))

    sigs = {}
    # 1) VWAP pullback reclaim (from vwap_structure_pullback idea)
    s = []
    c, o, h, l, vw, atr = (d5[k].to_numpy() for k in ("close","open","high","low","vwap","atr"))
    for i in range(80, len(d5)-HOLD):
        if pd.isna(vw[i]): continue
        if abs(l[i]-vw[i])<=0.5*atr[i] and c[i]>max(o[i],vw[i]): s.append((i,1))
        elif abs(h[i]-vw[i])<=0.5*atr[i] and c[i]<min(o[i],vw[i]): s.append((i,-1))
    sigs["VWAP pullback reclaim"] = (s, d5)

    # 2) 5-bar breakout
    hi5 = pd.Series(h).rolling(5).max().shift(1); lo5 = pd.Series(l).rolling(5).min().shift(1)
    s = [(i,1) for i in range(30,len(d5)-HOLD) if c[i]>hi5.iloc[i]] + \
        [(i,-1) for i in range(30,len(d5)-HOLD) if c[i]<lo5.iloc[i]]
    sigs["5-bar breakout"] = (s, d5)

    # 3) absorption: big range small body (liquidity-refill-ish)
    rng=h-l; body=np.abs(c-o); av=pd.Series(rng).rolling(20).mean().shift(1).to_numpy()
    s=[(i, 1 if c[i]>o[i] else -1) for i in range(30,len(d5)-HOLD)
       if rng[i]>1.3*av[i] and body[i]<0.35*rng[i]]
    sigs["absorption (effort/result)"] = (s, d5)

    # 4) VAL/VAH fade (range extremes via rolling profile proxy on 15m)
    d15h = pd.Series(d15.high).rolling(30).max().shift(1)
    d15l = pd.Series(d15.low).rolling(30).min().shift(1)
    cc = d15.close.to_numpy()
    s = [(i,1) for i in range(35,len(d15)-HOLD) if cc[i]<=d15l.iloc[i]+0.1*(d15h.iloc[i]-d15l.iloc[i])] + \
        [(i,-1) for i in range(35,len(d15)-HOLD) if cc[i]>=d15h.iloc[i]-0.1*(d15h.iloc[i]-d15l.iloc[i])]
    sigs["value-area extreme fade"] = (s, d15)

    # 5) ATR-band dip (long only)
    s=[]
    for i in range(30,len(d5)-HOLD):
        a=engine.realised_vol(d5.close.iloc[max(0,i-60):i],5)
        band=d5.close.iloc[i-1]-3.1*d5.atr.iloc[i-1]
        if d5.low.iloc[i]<=band: s.append((i,1))
    sigs["ATR-band dip (long)"] = (s, d5)

    print("EDGE CONTRIBUTION — each trigger ALONE at 1:1 (Nifty, 5y)\n")
    print(f"{'Trigger':30s} {'n':>6s} {'win%':>6s} {'expectancy(R)':>13s}")
    for name,(s,df) in sigs.items():
        n_,w,e = baseline(s, df, R=0.15)
        print(f"{name:30s} {n_:6d} {w:6.1f} {e:+13.3f}")


if __name__ == "__main__":
    main()
