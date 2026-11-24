"""User: SL Rs20, target Rs40, but exit early 'when the move looks tired'.
Tested mechanical proxies for 'tired move' vs simply holding to Rs40.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine
from premium_rr_backtest import signals, next_tuesday

SL_RS, TARGET_RS, MAX_HOLD = 20.0, 40.0, 30

VARIANTS = [
    "hold_to_40",
    "first_red_candle",
    "red_after_+10",
    "red_after_+20",
    "bearish_pattern",
    "rsi_extreme",
    "mfe20_then_red",
]


def main():
    raw = data_loader.load_data(last_days=10 ** 6, minutes=5)
    df, sigs = signals(raw)           # 3-green signals
    df = engine.add_indicators(df)
    c, o, h, l = (df[k].to_numpy() for k in ("close", "open", "high", "low"))
    days = df["timestamp"].dt.date.to_numpy()
    pat, rsi = df["pattern"].to_numpy(), df["rsi"].to_numpy()
    cs = df["close"]

    results = {v: [] for v in VARIANTS}
    for e, direction, _ in sigs:
        spot = c[e]
        K = int(np.floor(spot / 50) * 50) if direction == 1 else int(np.ceil(spot / 50) * 50)
        T = max((next_tuesday(days[e]) - days[e]).days, 0.5) / 365
        sigma = engine.realised_vol(cs.iloc[max(0, e - 60):e], 5)
        kind = "CE" if direction == 1 else "PE"
        entry = engine.bs_price(spot, K, T, sigma, kind=kind)
        sl, target = entry - SL_RS, entry + TARGET_RS
        if sl < 1:
            continue

        per = {v: None for v in VARIANTS}
        mfe = 0.0
        for j in range(e, min(e + MAX_HOLD, len(df))):
            if days[j] != days[e]:
                break
            good = engine.bs_price(h[j] if direction == 1 else l[j], K, T, sigma, kind=kind)
            bad = engine.bs_price(l[j] if direction == 1 else h[j], K, T, sigma, kind=kind)
            mfe = max(mfe, good - entry)
            if bad <= sl:
                for v in VARIANTS:
                    if per[v] is None:
                        per[v] = sl - entry
                break
            if good >= target:
                for v in VARIANTS:
                    if per[v] is None:
                        per[v] = TARGET_RS
                break

            opposite = (c[j] < o[j]) if direction == 1 else (c[j] > o[j])
            bearish = pat[j] in ("BEAR ENGULFING", "BEAR MARUBOZU", "SHOOTING STAR")
            bullish = pat[j] in ("BULL ENGULFING", "BULL MARUBOZU", "HAMMER")
            hot = (rsi[j] > 70) if direction == 1 else (rsi[j] < 30)
            cond = {
                "hold_to_40": False,
                "first_red_candle": opposite,
                "red_after_+10": opposite and mfe >= 10,
                "red_after_+20": opposite and mfe >= 20,
                "bearish_pattern": bearish if direction == 1 else bullish,
                "rsi_extreme": hot,
                "mfe20_then_red": opposite and mfe >= 20,
            }
            exit_p = engine.bs_price(c[j], K, T, sigma, kind=kind)
            for v, hit in cond.items():
                if hit and per[v] is None:
                    per[v] = exit_p - entry

        last_p = engine.bs_price(c[min(e + MAX_HOLD, len(df)) - 1], K, T, sigma, kind=kind)
        for v in VARIANTS:
            if per[v] is None:
                per[v] = last_p - entry
            results[v].append(per[v])

    print("Variant             n    Win%   AvgRs    PF")
    for v in VARIANTS:
        s = pd.Series(results[v])
        wins = s > 0
        gp, gl = s[wins].sum(), -s[~wins].sum()
        print(f"{v:19s} {len(s):4d}  {wins.mean()*100:5.1f}  {s.mean():+7.2f}  "
              f"{gp/gl if gl else np.inf:4.2f}")


if __name__ == "__main__":
    main()
