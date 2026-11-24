"""ICT Turtle Soup core simplified: liquidity sweep + instant reversal on Nifty 5m.

Long  = sweep of relative equal lows / prior session low in discount, close back inside.
Short = sweep of relative equal highs / prior session high in premium, close back inside.
Entry = next candle breaks sweep candle's high/low. SL beyond sweep wick. TP = 1:2.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

MAX_HOLD = 20
TOL = 0.001


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    d["day"] = d["timestamp"].dt.date
    g = d.groupby("day")
    daily = pd.DataFrame({"H": g.high.max(), "L": g.low.min()})
    daily["mid"] = (daily.H + daily.L) / 2
    d["ph"] = d["day"].map(daily.H.shift(1))
    d["pl"] = d["day"].map(daily.L.shift(1))
    d["pmid"] = d["day"].map(daily.mid.shift(1))

    c, o, h, l = (d[k].to_numpy() for k in ("close", "open", "high", "low"))
    rows = []
    n = len(d)
    for i in range(120, n - MAX_HOLD - 2):
        ph, pl, pmid = (d[k].iloc[i] for k in ("ph", "pl", "pmid"))
        if any(pd.isna(x) for x in (ph, pl, pmid)):
            continue
        direction, level = 0, np.nan
        # discount long: sweep prior session low, reject
        if c[i] < pmid and l[i] < pl and c[i] > pl:
            direction, level = 1, pl
        # premium short: sweep prior session high, reject
        elif c[i] > pmid and h[i] > ph and c[i] < ph:
            direction, level = -1, ph
        if not direction:
            continue
        # next 2 candles: entry when one breaks sweep candle high/low
        entry = None
        for k in range(i + 1, min(i + 4, n)):
            if d["day"].iloc[k] != d["day"].iloc[i]:
                break
            if direction == 1 and c[k] > h[i]:
                entry = h[i]; break
            if direction == -1 and c[k] < l[i]:
                entry = l[i]; break
        if entry is None:
            continue
        stop = (l[i] - 0.05 * (h[i] - l[i])) if direction == 1 else (h[i] + 0.05 * (h[i] - l[i]))
        risk = abs(entry - stop)
        if risk <= 0:
            continue
        tgt = entry + 2 * risk if direction == 1 else entry - 2 * risk
        pnl, res = np.nan, "TIME"
        for m in range(k, min(k + MAX_HOLD, n)):
            if d["day"].iloc[m] != d["day"].iloc[i]:
                break
            if direction == 1:
                if l[m] <= stop: pnl, res = -risk, "SL"; break
                if h[m] >= tgt: pnl, res = 2 * risk, "T"; break
            else:
                if h[m] >= stop: pnl, res = -risk, "SL"; break
                if l[m] <= tgt: pnl, res = 2 * risk, "T"; break
        if np.isnan(pnl):
            pnl = (c[min(k + MAX_HOLD, n) - 1] - entry) * direction
        rows.append({"dir": "LONG" if direction == 1 else "SHORT",
                     "pnl": pnl, "r": pnl / risk, "res": res})

    r = pd.DataFrame(rows)
    if r.empty:
        print("koi signal nahi"); return
    print("TURTLE SOUP core (sweep + reversal) on Nifty 5m, 1:2\n")
    print(f"{'Setup':10s} {'n':>5s} {'Win%':>6s} {'AvgR':>7s} {'T%':>5s} {'SL%':>6s}")
    for name, sub in [("LONG", r[r.dir == "LONG"]),
                      ("SHORT", r[r.dir == "SHORT"]), ("ALL", r)]:
        if sub.empty: continue
        print(f"{name:10s} {len(sub):5d} {(sub.pnl>0).mean()*100:6.1f} "
              f"{sub.r.mean():+7.3f} {(sub.res=='T').mean()*100:5.1f} "
              f"{(sub.res=='SL').mean()*100:6.1f}")


if __name__ == "__main__":
    main()
