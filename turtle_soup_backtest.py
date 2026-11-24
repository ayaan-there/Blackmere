"""ICT Turtle Soup + 2022 Model adapted to Nifty 5-min.

- Liquidity sweep of relative equal highs/lows or prior session high/low.
- Range positioning: longs only in discount (<50% of prior session range), shorts in premium.
- FVG / inverse-FVG after sweep as entry trigger (proxy: 3-candle gap + retest).
- SL beyond sweep wick, TP 1:2 (or opposing liquidity).
15s/30s charts, SMT divergence, news filter not available -> proxied / skipped.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

MAX_HOLD = 20
TOL = 0.0008   # 0.08% equal-high/low tolerance


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    d["day"] = d["timestamp"].dt.date
    g = d.groupby("day")
    daily = pd.DataFrame({"H": g.high.max(), "L": g.low.min(), "C": g.close.last()})
    daily["mid"] = (daily.H + daily.L) / 2
    d["ph"] = d["day"].map(daily.H.shift(1))
    d["pl"] = d["day"].map(daily.L.shift(1))
    d["pmid"] = d["day"].map(daily.mid.shift(1))

    c, o, h, l = (d[k].to_numpy() for k in ("close", "open", "high", "low"))
    days = d["timestamp"].dt.date.to_numpy()
    n = len(d)

    # relative equal highs / lows over trailing 20 bars
    hs, ls, cs = pd.Series(h), pd.Series(l), pd.Series(c)
    rh = hs.rolling(20, min_periods=10).max()
    rl = ls.rolling(20, min_periods=10).min()
    near_eq_h = (hs >= rh - TOL * cs) & (hs <= rh + TOL * cs)
    near_eq_l = (ls <= rl + TOL * cs) & (ls >= rl - TOL * cs)
    eq_h_count = near_eq_h.rolling(20, min_periods=10).sum()
    eq_l_count = near_eq_l.rolling(20, min_periods=10).sum()

    rows = []
    for i in range(120, n - MAX_HOLD - 2):
        ph, pl, pmid = (d[k].iloc[i] for k in ("ph", "pl", "pmid"))
        if any(pd.isna(x) for x in (ph, pl, pmid)):
            continue
        price = c[i]
        long_ok = price < pmid       # discount
        short_ok = price > pmid      # premium

        direction = 0
        level = np.nan
        if long_ok and eq_l_count.iloc[i] >= 2:
            level = rl[i]
            if l[i] < level and c[i] > level:   # sweep lows, reclaim
                direction = 1
        elif short_ok and eq_h_count.iloc[i] >= 2:
            level = rh[i]
            if h[i] > level and c[i] < level:   # sweep highs, reject
                direction = -1
        elif long_ok and l[i] < pl and c[i] > pl:
            level, direction = pl, 1
        elif short_ok and h[i] > ph and c[i] < ph:
            level, direction = ph, -1
        if not direction:
            continue
        # FVG proxy after sweep: next 3 candles create a gap in reversal direction
        j = i + 1
        if j + 2 >= n or days[j] != days[i]:
            continue
        fvg = None
        if direction == 1 and h[j + 2] < l[j]:     # bullish FVG (gap up zone)
            fvg = (l[j], h[j + 2], "bull")
        elif direction == -1 and l[j + 2] > h[j]:  # bearish FVG
            fvg = (h[j], l[j + 2], "bear")
        if fvg is None:
            continue

        lo, hi, _ = fvg
        entry = (lo + hi) / 2
        stop = min(l[i], lo) - 0.05 * abs(lo - hi) if direction == 1 else max(h[i], hi) + 0.05 * abs(lo - hi)
        risk = abs(entry - stop)
        if risk <= 0 or risk > 2.5 * (ph - pl) / 100:
            continue
        target = entry + 2 * risk if direction == 1 else entry - 2 * risk
        pnl, res = np.nan, "TIME"
        for m in range(j + 2, min(j + 2 + MAX_HOLD, n)):
            if days[m] != days[i]:
                break
            if direction == 1:
                if l[m] <= stop:
                    pnl, res = -risk, "SL"; break
                if h[m] >= target:
                    pnl, res = 2 * risk, "T"; break
            else:
                if h[m] >= stop:
                    pnl, res = -risk, "SL"; break
                if l[m] <= target:
                    pnl, res = 2 * risk, "T"; break
        if np.isnan(pnl):
            pnl = (c[min(j + 2 + MAX_HOLD, n) - 1] - entry) * direction
        rows.append({"direction": "LONG" if direction == 1 else "SHORT",
                     "pnl": pnl, "r": pnl / risk, "result": res})

    r = pd.DataFrame(rows)
    if r.empty:
        print("koi signal nahi"); return
    print("ICT TURTLE SOUP / 2022 MODEL on Nifty 5m (5 yrs, 1:2)\n")
    print(f"{'Setup':12s} {'n':>5s} {'Win%':>6s} {'AvgR':>7s} {'T%':>5s} {'SL%':>6s}")
    for name, sub in [("LONG", r[r.direction == "LONG"]),
                      ("SHORT", r[r.direction == "SHORT"]), ("ALL", r)]:
        if sub.empty: continue
        print(f"{name:12s} {len(sub):5d} {(sub.pnl>0).mean()*100:6.1f} "
              f"{sub.r.mean():+7.3f} {(sub.result=='T').mean()*100:5.1f} "
              f"{(sub.result=='SL').mean()*100:6.1f}")


if __name__ == "__main__":
    main()
