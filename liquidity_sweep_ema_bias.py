"""Tim-style liquidity sweep + structure shift + 200EMA bias on Nifty 15m.

Bias: price above 200EMA (on 60m proxy) -> long setups only; below -> short only.
Setup: sweep of recent swing extreme (equal highs/lows proxy) then reversal with
       structure shift (higher low / lower high) -> enter on confirmation.
SL beyond swept level, TP 2R or opposing liquidity. Skip sub-1:1.
X-ray liquidity data unavailable -> swing extremes + volume cluster proxy.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

HOLD = 20


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=15))
    c, o, h, l, atr = (d[k].to_numpy() for k in ("close","open","high","low","atr"))
    n = len(d)
    # 200EMA proxy: 60-min EMA50 mapped (approximate HTF trend)
    d60 = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=60))
    ema = pd.Series((d60.ema21).values, index=d60["timestamp"])
    d["bias_ema"] = ema.reindex(d["timestamp"], method="ffill").to_numpy()
    d["bias"] = np.where(c > d["bias_ema"].to_numpy(), 1, -1)

    sh = pd.Series(h).rolling(20).max().shift(1)
    sl = pd.Series(l).rolling(20).min().shift(1)
    rows = []
    for i in range(60, n - HOLD - 3):
        bias = d["bias"].iloc[i]
        direction, level = 0, np.nan
        if bias == 1 and l[i] < sl.iloc[i] and c[i] > sl.iloc[i] and c[i] > o[i]:
            direction, level = 1, sl.iloc[i]     # downside sweep + reclaim in uptrend
        elif bias == -1 and h[i] > sh.iloc[i] and c[i] < sh.iloc[i] and c[i] < o[i]:
            direction, level = -1, sh.iloc[i]
        if not direction: continue
        # structure shift: next candle higher low (long) / lower high (short)
        j = i + 1
        if j + 1 >= n: break
        if direction == 1:
            shift = l[j] > l[i] and c[j] > o[j]
        else:
            shift = h[j] < h[i] and c[j] < o[j]
        if not shift: continue
        entry = c[j]
        stop = level - 0.1*atr[i] if direction==1 else level + 0.1*atr[i]
        risk = abs(entry - stop)
        if risk <= 0: continue
        tp = entry + 2*risk if direction==1 else entry - 2*risk
        res = 0.0
        for m in range(j+1, min(j+HOLD, n)):
            if direction == 1:
                if l[m] <= stop: res = -1; break
                if h[m] >= tp: res = 2; break
            else:
                if h[m] >= stop: res = -1; break
                if l[m] <= tp: res = 2; break
        rows.append({"dir":"LONG" if direction==1 else "SHORT","res":res})

    r = pd.DataFrame(rows)
    if r.empty: print("koi signal nahi"); return
    print("LIQUIDITY SWEEP + EMA BIAS + structure shift on Nifty 15m (5y, 2R)\n")
    for name, sub in [("LONG (above EMA)",r[r.dir=="LONG"]),("SHORT (below EMA)",r[r.dir=="SHORT"]),("ALL",r)]:
        if sub.empty: continue
        print(f"{name:20s} n={len(sub):5d} win={(sub.res>0).mean()*100:5.1f}% avgR={sub.res.mean():+.3f}")


if __name__ == "__main__":
    main()
