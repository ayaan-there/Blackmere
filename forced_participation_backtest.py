"""Forced-participation / trapped-sellers long setup on Nifty 5-min.

Discount zone = swing-high-to-swing-low Fib retracements 0.705 / 0.788 / 0.886
(below value, i.e. deep pullback in a value-up structure).
Setup: aggressive selling into discount (big red candle/wick) with NO follow-through
       -> bullish flip/second failed seller -> long. SL beyond failed sellers.
Target swing point / 1.5-2R. Test with and without HTF value-up filter.
GEX/footprint/delta/bid-ask not available -> price-action proxies.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

HOLD = 20


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    c, o, h, l, atr = (d[k].to_numpy() for k in ("close","open","high","low","atr"))
    days = d["timestamp"].dt.date.to_numpy()
    n = len(d)
    rng = h - l
    body = np.abs(c - o)

    # value-up proxy: 60-min EMA rising + price structure
    d60 = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=60))
    up = pd.Series((d60.ema9 > d60.ema21).astype(float), index=d60["timestamp"])
    d["value_up"] = up.reindex(d["timestamp"], method="ffill").fillna(0).astype(bool).values

    swing_hi = pd.Series(h).rolling(40).max().shift(1)
    swing_lo = pd.Series(l).rolling(40).min().shift(1)
    rows = []
    for i in range(60, n - HOLD - 2):
        sh, sl_ = swing_hi.iloc[i], swing_lo.iloc[i]
        if pd.isna(sh) or pd.isna(sl_) or sh <= sl_: continue
        rng_sw = sh - sl_
        # discount zone: price between 70.5% and 88.6% retracement down from swing high
        r = (sh - c[i]) / rng_sw
        if not (0.70 <= r <= 0.89): continue
        # aggressive seller candle with long lower wick (selling into discount)
        lower_wick = np.minimum(o[i], c[i]) - l[i]
        seller_push = (c[i] < o[i]) and (lower_wick > 0.5 * body[i]) and (rng[i] > 1.1 * atr[i])
        if not seller_push: continue
        # failed selling / bullish flip next candle
        j = i + 1
        if j >= n or days[j] != days[i]: continue
        flip = (c[j] > o[j]) and (c[j] > c[i]) and (l[j] >= l[i] - 0.2*atr[i])
        if not flip: continue
        entry = c[j]
        stop = l[i] - 0.1 * atr[i]
        risk = entry - stop
        if risk <= 0: continue
        target_swing = sh
        for rr in (1.5, 2.0):
            tp = min(entry + rr*risk, target_swing) if target_swing > entry else entry + rr*risk
            if tp <= entry: continue
            res = 0.0
            for m in range(j+1, min(j+HOLD, n)):
                if days[m] != days[i]: break
                if l[m] <= stop: res = -1; break
                if h[m] >= tp: res = (tp-entry)/risk; break
            rows.append({"vu": bool(d["value_up"].iloc[i]), "rr": rr, "res": res})

    r = pd.DataFrame(rows)
    if r.empty: print("koi signal nahi"); return
    print("FORCED PARTICIPATION (discount failed-selling) on Nifty 5m (5y)\n")
    print(f"{'Setup':24s} {'n':>6s} {'win%':>6s} {'avgR':>7s}")
    for vu, lab in ((True,"value-UP filter ON"),(False,"no HTF filter")):
        for rr in (1.5,2.0):
            sub=r[(r.vu==vu)&(r.rr==rr)]
            if sub.empty: continue
            print(f"{lab+' '+str(rr)+'R':24s} {len(sub):6d} {(sub.res>0).mean()*100:6.1f} {sub.res.mean():+7.3f}")


if __name__ == "__main__":
    main()
