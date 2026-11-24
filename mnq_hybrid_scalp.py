"""Hybrid scalp adapted to Nifty 5-min.

LONG: limit at prev close - 3.1*ATR(14); entry when lower wick clips band;
      TP 2*ATR(prev), SL 1.5*ATR(prev), static distances. Skip opening bar.
SHORT: shooting-star-like candle (upper wick >= 2*body, lower wick <= 0.1*upper);
       enter at next bar open; exit at close of next bar (1-bar hold).
       Upgrade: only when prior daily candle was red.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    c, o, h, l, atr = (d[k].to_numpy() for k in ("close", "open", "high", "low", "atr"))
    days = d["timestamp"].dt.date.to_numpy()
    hm = d["timestamp"].dt.hour * 60 + d["timestamp"].dt.minute
    n = len(d)

    # ---------- LONG: ATR band reversal ----------
    rows_l = []
    for i in range(30, n - 8):
        if hm[i] <= 9 * 60 + 15: continue          # skip opening candle
        if days[i] != days[i - 1] and i > 0: continue
        a = atr[i - 1]                              # static ATR from prior bar
        band = c[i - 1] - 3.1 * a
        if l[i] <= band and c[i] > l[i]:             # wick clips band, close up
            entry = band
            tp, sl = entry + 2 * a, entry - 1.5 * a
            pnl = np.nan
            for m in range(i, min(i + 8, n)):
                if days[m] != days[i]: break
                if l[m] <= sl: pnl = -1.5 * a; break
                if h[m] >= tp: pnl = 2 * a; break
            if np.isnan(pnl): pnl = c[min(i + 8, n) - 1] - entry
            rows_l.append(pnl)

    # ---------- SHORT: upper-wick + 1-bar exit ----------
    body = np.abs(c - o)
    upw = h - np.maximum(o, c)
    loww = np.minimum(o, c) - l
    sig = (upw >= 2 * body) & (body > 0) & (loww <= 0.1 * upw) & (c < o)
    # prior daily red flag
    dg = d.groupby(d["timestamp"].dt.date)
    dclose = dg.close.last()
    dred = (dclose < dclose.shift(1))
    d["dred"] = d["timestamp"].dt.date.map(dred).astype(bool)

    rows_s = []
    for i in range(30, n - 3):
        if not sig[i]: continue
        if days[i + 1] != days[i]: continue
        entry = o[i + 1]
        exitp = c[i + 1]                            # 1-bar hold
        pnl = (entry - exitp)
        rows_s.append({"pnl": pnl, "dred": bool(d["dred"].iloc[i])})

    la = pd.Series(rows_l); sa = pd.DataFrame(rows_s)
    print("HYBRID SCALP on Nifty 5m (5y)\n")
    print(f"LONG  ATR-band reversal : n={len(la):5d} win={(la>0).mean()*100:5.1f}% "
          f"avg={la.mean():+6.2f} pts")
    if len(sa):
        print(f"SHORT upper-wick 1-bar   : n={len(sa):5d} win={(sa.pnl>0).mean()*100:5.1f}% "
              f"avg={sa.pnl.mean():+6.2f} pts")
        for flag, sub in sa.groupby("dred"):
            print(f"   prior daily {'RED' if flag else 'GREEN'}: n={len(sub):5d} "
                  f"win={(sub.pnl>0).mean()*100:5.1f}% avg={sub.pnl.mean():+6.2f}")


if __name__ == "__main__":
    main()
