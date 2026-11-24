"""Liquidity Refill & Aggression (Philip) adapted to Nifty 5-min.

C1 = impulse candle after compression.
C2 = next candle: small counter-wick within top/bottom 15% of C1 range, flips bullish/bearish.
Entry = cross of C1 high/low on a later bar. SL = just beyond C2 wick.
Exit = max 3-4 bars, or earlier on opposite-direction close (imbalance faded).
No intra-bar seconds data -> C2 quick-dip flip proxied by wick position.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

MAX_HOLD = 4


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    c, o, h, l = (d[k].to_numpy() for k in ("close", "open", "high", "low"))
    rng = h - l
    days = d["timestamp"].dt.date.to_numpy()
    n = len(d)

    avg5 = pd.Series(rng).rolling(5).mean().shift(1).to_numpy()
    comp = pd.Series(rng).rolling(4).max().shift(1).to_numpy()   # prior compression
    impulse = (rng > 1.8 * avg5) & (rng > 1.3 * comp) & (avg5 > 0)
    body_up = c > o
    body_dn = c < o

    rows = []
    i = 6
    while i < n - MAX_HOLD - 1:
        if not impulse[i]:
            i += 1
            continue
        c1r = rng[i]
        if c1r <= 0:
            i += 1
            continue
        direction = 1 if body_up[i] else -1 if body_dn[i] else 0
        if direction == 0:
            i += 1
            continue
        # C2 = bar i+1: counter-move stays in top/bottom 15% of C1, then flips
        j = i + 1
        if j >= n:
            break
        up_zone = h[i] - 0.15 * c1r   # C2 low must stay above this (top 15%)
        dn_zone = l[i] + 0.15 * c1r   # C2 high must stay below this (bottom 15%)
        if direction == 1:
            ok = (l[j] >= up_zone) and (c[j] > o[j])
        else:
            ok = (h[j] <= dn_zone) and (c[j] < o[j])
        if not ok:
            i += 1
            continue

        c2low, c2high = l[j], h[j]
        for k in range(j + 1, min(j + 8, n - MAX_HOLD)):
            if days[k] != days[i]:
                break
            trig = (h[k] >= h[i]) if direction == 1 else (l[k] <= l[i])
            if not trig:
                continue
            entry = h[i] if direction == 1 else l[i]
            stop = c2low - 0.1 * c1r if direction == 1 else c2high + 0.1 * c1r
            risk = abs(entry - stop)
            if risk <= 0 or risk > 1.2 * c1r:   # wide wick ruins R:R -> skip
                break
            pnl, exit_k, exit_r = np.nan, k, None
            for m in range(k, min(k + MAX_HOLD, n)):
                if days[m] != days[i]:
                    break
                opposite = (c[m] < o[m]) if direction == 1 else (c[m] > o[m])
                hit_stop = (l[m] <= stop) if direction == 1 else (h[m] >= stop)
                if hit_stop:
                    pnl, exit_k = -risk, m; break
                if opposite:
                    pnl, exit_k = (c[m] - entry) * direction, m; break
                if m == min(k + MAX_HOLD, n) - 1:
                    pnl, exit_k = (c[m] - entry) * direction, m
            if np.isnan(pnl):
                pnl = (c[min(k + MAX_HOLD, n) - 1] - entry) * direction
            net = pnl - 2.0   # ~1 index point each way slippage/spread (option approx)
            rows.append({"side": "LONG" if direction == 1 else "SHORT",
                         "pnl": net, "r": net / risk,
                         "bars": exit_k - k, "risk": round(risk, 1)})
            break
        i = j + 1

    r = pd.DataFrame(rows)
    if r.empty:
        print("koi signal nahi"); return
    print("LIQUIDITY REFILL / AGGRESSION on Nifty 5m (5 yrs)\n")
    print(f"{'Setup':16s} {'n':>5s} {'Win%':>6s} {'AvgR':>7s} {'AvgBars':>8s}")
    for name, sub in [("LONG", r[r.side == "LONG"]),
                      ("SHORT", r[r.side == "SHORT"]), ("ALL", r)]:
        if sub.empty: continue
        print(f"{name:16s} {len(sub):5d} {(sub.pnl>0).mean()*100:6.1f} "
              f"{sub.r.mean():+7.3f} {sub.bars.mean():8.1f}")
    print(f"\nSL hits (loss): {(r.pnl<0).mean()*100:.1f}% | "
          f"mean holding {r.bars.mean():.1f} bars (~{r.bars.mean()*5:.0f} min)")


if __name__ == "__main__":
    main()
