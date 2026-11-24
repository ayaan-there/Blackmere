"""User's pivot+3-candle setup with FIXED 1:2 in option-premium rupees.

SL = entry premium - 20, Target = entry premium + 40.
Premium simulated with Black-Scholes (ITM strike, realised vol, next-Tuesday expiry)
because option-chain history is not available. Index data only.

Also reports MFE (max favourable excursion) before an SL hit:
"target tak jaakar kitni baar SL laga" -> premium +30/+35 ke baad SL.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

import data_loader
import engine
from pivot_strategy_backtest import pivots

SL_RS, TARGET_RS, MAX_HOLD = 20.0, 40.0, 30


def next_tuesday(d: date) -> date:
    delta = (1 - d.weekday()) % 7
    if delta == 0:
        delta = 7
    return d + timedelta(days=delta)


def signals(df: pd.DataFrame):
    df = pivots(df).reset_index(drop=True)
    c, o, h, l = (df[k].to_numpy() for k in ("close", "open", "high", "low"))
    lv_arr = df[["S2", "S1", "P", "R1", "R2"]].to_numpy()
    out = []
    i = 0
    while i < len(df) - 4:
        lv = lv_arr[i]
        if np.isnan(lv).any():
            i += 1
            continue
        direction = 0
        crossed = None
        for L in lv:
            if c[i - 1] <= L < c[i]:
                direction, crossed = 1, L
            elif c[i - 1] >= L > c[i]:
                direction, crossed = -1, L
        if not direction:
            i += 1
            continue
        ok = all((c[i + k] > o[i + k]) if direction == 1
                 else (c[i + k] < o[i + k]) for k in (1, 2, 3))
        if not ok:
            i += 1
            continue
        out.append((i + 3, direction, crossed))
        i += 4
    return df, out


def main():
    raw = data_loader.load_data(last_days=10 ** 6, minutes=5)
    df, sigs = signals(raw)
    c, h, l = (df[k].to_numpy() for k in ("close", "high", "low"))
    days = df["timestamp"].dt.date.to_numpy()
    close_s = df["close"]

    rows = []
    for e, direction, _ in sigs:
        spot = c[e]
        K = int(np.floor(spot / 50) * 50) if direction == 1 else int(np.ceil(spot / 50) * 50)
        T = max((next_tuesday(days[e]) - days[e]).days, 0.5) / 365
        sigma = engine.realised_vol(close_s.iloc[max(0, e - 60):e], 5)
        kind = "CE" if direction == 1 else "PE"
        entry = engine.bs_price(spot, K, T, sigma, kind=kind)
        sl, target = entry - SL_RS, entry + TARGET_RS
        if sl < 1:
            continue

        mfe, result, exitp, bars = 0.0, "TIME", entry, 0
        for j in range(e, min(e + MAX_HOLD, len(df))):
            if days[j] != days[e]:
                break
            if direction == 1:
                fav = engine.bs_price(h[j], K, T, sigma, kind="CE")
                adv = engine.bs_price(l[j], K, T, sigma, kind="CE")
                mfe = max(mfe, fav - entry)
                if adv <= sl:
                    result, exitp, bars = "SL", sl, j - e
                    break
                if fav >= target:
                    result, exitp, bars = "TARGET", target, j - e
                    break
            else:
                fav = engine.bs_price(l[j], K, T, sigma, kind="PE")
                adv = engine.bs_price(h[j], K, T, sigma, kind="PE")
                mfe = max(mfe, fav - entry)
                if adv <= sl:
                    result, exitp, bars = "SL", sl, j - e
                    break
                if fav >= target:
                    result, exitp, bars = "TARGET", target, j - e
                    break
            bars = j - e
        if result == "TIME":
            exitp = engine.bs_price(c[min(e + MAX_HOLD, len(df)) - 1], K, T, sigma, kind=kind)
        rows.append({"t": df["timestamp"].iloc[e], "side": kind, "result": result,
                     "pnl": exitp - entry, "mfe": mfe, "bars": bars})

    r = pd.DataFrame(rows)
    r = r.sort_values("t").reset_index(drop=True)
    mid = int(len(r) * 0.7)
    print(f"signals={len(r)}  SL=₹{SL_RS:.0f}  target=₹{TARGET_RS:.0f}  hold<={MAX_HOLD} bars")
    for name, part in (("ALL", r), ("TRAIN", r.iloc[:mid]), ("TEST", r.iloc[mid:])):
        wins = part.pnl > 0
        gp, gl = part.loc[wins, "pnl"].sum(), -part.loc[~wins, "pnl"].sum()
        print(f"{name:5s} n={len(part):4d} win={wins.mean()*100:5.1f}% "
              f"avgPnL=₹{part.pnl.mean():+6.2f} PF={gp/gl if gl else np.inf:.2f} "
              f"target={(part.result=='TARGET').mean()*100:4.1f}% "
              f"SL={(part.result=='SL').mean()*100:4.1f}%")

    sls = r[r.result == "SL"]
    print(f"\nSL hue = {len(sls)} ({len(sls)/len(r)*100:.1f}% of all trades)")
    for th in (10, 20, 25, 30, 35):
        n = int((sls.mfe >= th).sum())
        print(f"  SL se pehle ₹+{th} ya zyada gaye: {n:3d} ({n/len(sls)*100:4.1f}% SLs, {n/len(r)*100:4.1f}% all)")
    near = int(((sls.mfe >= 30) | (sls.mfe >= 25)).sum())
    print(f"\n'₹25-35 tak jaakar SL' approx: {sls[(sls.mfe>=25)].shape[0]} trades")
    print("\nMFE distribution of SL trades:")
    print(sls.mfe.describe(percentiles=[.25, .5, .75, .9]).round(1).to_string())


if __name__ == "__main__":
    main()
