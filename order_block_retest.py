"""Order-block sweep + reclaim + retest confirmation on Nifty 15-min.

OB proxy: last opposite-direction candle before a structural break (body > wick).
Sweep: wick pushes beyond OB extreme, body closes back inside (no first-break gamble).
Retest: price comes back to the zone, then breaks in trade direction with
        confirming candle (not immediate recovery). SL beyond OB/sweep.
TP: opposing liquidity (prior high/low) or 2R. Compare 1st break vs retest entry.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

MAX_HOLD = 20


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=15))
    c, o, h, l = (d[k].to_numpy() for k in ("close", "open", "high", "low"))
    days = d["timestamp"].dt.date.to_numpy()
    n = len(d)
    body = np.abs(c - o)
    wick = np.maximum(h - np.maximum(o, c), np.minimum(o, c) - l)
    valid = body > wick

    rows = []
    i = 40
    while i < n - MAX_HOLD - 3:
        # find valid opposite candle (OB) in recent 10 bars
        ob = None
        for k in range(i - 10, i):
            if k <= 0: continue
            if valid[k] and c[k] < o[k]:   # bearish OB -> long setup
                ob = (k, l[k], h[k]); break
        if ob is None:
            i += 1; continue
        obk, oblo, obhi = ob
        # sweep of OB low with body closing back inside (long)
        swept = (l[i] < oblo) and (oblo < c[i] < obhi) and (c[i] > o[i])
        if not swept:
            i += 1; continue
        # EARLY entry = first break (for comparison)
        early_entry = c[i]
        early_sl = min(l[i], oblo) - 0.05 * (obhi - oblo)
        # RETEST entry: wait for price to come back to zone then break confirmation
        retest_entry = None
        for j in range(i + 1, min(i + 10, n)):
            if days[j] != days[i]: break
            if l[j] <= obhi and c[j] > o[j] and c[j] > early_entry:
                retest_entry = c[j]; break
        if retest_entry is None:
            i += 1; continue
        direction = 1

        def outcome(entry, sl):
            risk = entry - sl
            if risk <= 0: return None
            target = entry + 2 * risk
            for m in range(i + 1, min(i + MAX_HOLD, n)):
                if days[m] != days[i]: break
                if l[m] <= sl: return -risk
                if h[m] >= target: return 2 * risk
            return c[min(i + MAX_HOLD, n) - 1] - entry

        e_pnl = outcome(early_entry, early_sl)
        r_sl = min(l[i], oblo) - 0.05 * (obhi - oblo)
        r_pnl = outcome(retest_entry, r_sl)
        if e_pnl is not None and r_pnl is not None:
            rows.append({"early": e_pnl, "retest": r_pnl})
        i += 4

    r = pd.DataFrame(rows)
    if r.empty: print("koi signal nahi"); return
    print("ORDER BLOCK sweep + retest on Nifty 15m (5y, 2R)\n")
    for col in ("early", "retest"):
        s = r[col]
        print(f"{col:8s} n={len(s):5d} win={(s>0).mean()*100:5.1f}% avg={s.mean():+7.2f} pts")


if __name__ == "__main__":
    main()
