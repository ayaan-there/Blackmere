"""Trailing SL variants on the user's pivot + 3-candle setup.
Premium simulated by Black-Scholes (no option-chain history available).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine
from premium_rr_backtest import next_tuesday, signals

SL_RS, TARGET_RS, MAX_HOLD = 20.0, 40.0, 30

VARIANTS = {
    "base_NO_trail": None,
    "BE_after_+10": ("be", 10, 0),
    "LOCK5_after_+15": ("lock", 15, 5),
    "LOCK10_after_+20": ("lock", 20, 10),
    "TRAIL10_after_+15": ("trail", 15, 10),
}


def main():
    raw = data_loader.load_data(last_days=10 ** 6, minutes=5)
    df, sigs = signals(raw)
    c, h, l = (df[k].to_numpy() for k in ("close", "high", "low"))
    days = df["timestamp"].dt.date.to_numpy()
    cs = df["close"]
    out = []

    for name, var in VARIANTS.items():
        rows = []
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
            mfe, result, exitp = 0.0, "TIME", entry
            for j in range(e, min(e + MAX_HOLD, len(df))):
                if days[j] != days[e]:
                    break
                if direction == 1:
                    fav = engine.bs_price(h[j], K, T, sigma, kind="CE")
                    adv = engine.bs_price(l[j], K, T, sigma, kind="CE")
                else:
                    fav = engine.bs_price(l[j], K, T, sigma, kind="PE")
                    adv = engine.bs_price(h[j], K, T, sigma, kind="PE")
                mfe = max(mfe, fav - entry)
                if var:
                    mode, trig, lock = var
                    if fav - entry >= trig:
                        if mode == "be":
                            sl = max(sl, entry)
                        elif mode == "lock":
                            sl = max(sl, entry + lock)
                        elif mode == "trail":
                            sl = max(sl, fav - lock)
                if adv <= sl:
                    result, exitp = "SL", sl
                    break
                if fav >= target:
                    result, exitp = "TARGET", target
                    break
            if result == "TIME":
                exitp = engine.bs_price(c[min(e + MAX_HOLD, len(df)) - 1], K, T, sigma, kind=kind)
            rows.append({"result": result, "pnl": exitp - entry, "mfe": mfe})
        out.append((name, pd.DataFrame(rows)))

    print("Variant            n    Win%   AvgPnL   PF    Target%  SL%   SL me +25 se upar")
    for name, r in out:
        wins = r.pnl > 0
        gp, gl = r.loc[wins, "pnl"].sum(), -r.loc[~wins, "pnl"].sum()
        sls = r[r.result == "SL"]
        near = int((sls.mfe >= 25).sum())
        print(f"{name:19s} {len(r):4d}  {wins.mean()*100:5.1f}  {r.pnl.mean():+7.2f}  "
              f"{gp/gl if gl else np.inf:4.2f}   {(r.result=='TARGET').mean()*100:5.1f}  "
              f"{(r.result=='SL').mean()*100:5.1f}   {near:3d}")


if __name__ == "__main__":
    main()
