"""Two changes requested by user:
  1) Entry at 2nd green candle (instead of 3rd).
  2) NO fixed target - only trailing stop loss.

All pivot lines (S2,S1,P,R1,R2) are treated as possible support/resistance.
Premium simulated with Black-Scholes (no option-chain history).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine
from pivot_strategy_backtest import pivots
from premium_rr_backtest import next_tuesday

INIT_SL = 20.0
MAX_HOLD = 30


def make_signals(df: pd.DataFrame, confirm: int):
    df = pivots(df).reset_index(drop=True)
    c, o = df["close"].to_numpy(), df["open"].to_numpy()
    lv_arr = df[["S2", "S1", "P", "R1", "R2"]].to_numpy()
    out, i = [], 0
    while i < len(df) - confirm - 1:
        lv = lv_arr[i]
        if np.isnan(lv).any():
            i += 1
            continue
        direction = 0
        for L in lv:
            if c[i - 1] <= L < c[i]:
                direction = 1
            elif c[i - 1] >= L > c[i]:
                direction = -1
        if not direction:
            i += 1
            continue
        ok = all((c[i + k] > o[i + k]) if direction == 1
                 else (c[i + k] < o[i + k]) for k in range(1, confirm + 1))
        if not ok:
            i += 1
            continue
        out.append((i + confirm, direction))
        i += confirm + 1
    return df, out


def run(df, sigs, trail):
    c, h, l = (df[k].to_numpy() for k in ("close", "high", "low"))
    days = df["timestamp"].dt.date.to_numpy()
    cs = df["close"]
    rows = []
    for e, direction in sigs:
        spot = c[e]
        K = int(np.floor(spot / 50) * 50) if direction == 1 else int(np.ceil(spot / 50) * 50)
        T = max((next_tuesday(days[e]) - days[e]).days, 0.5) / 365
        sigma = engine.realised_vol(cs.iloc[max(0, e - 60):e], 5)
        kind = "CE" if direction == 1 else "PE"
        entry = engine.bs_price(spot, K, T, sigma, kind=kind)
        sl, fav = entry - INIT_SL, 0.0
        exitp, result, bars = entry, "TIME", 0
        for j in range(e, min(e + MAX_HOLD, len(df))):
            if days[j] != days[e]:
                break
            if direction == 1:
                good = engine.bs_price(h[j], K, T, sigma, kind="CE")
                bad = engine.bs_price(l[j], K, T, sigma, kind="CE")
            else:
                good = engine.bs_price(l[j], K, T, sigma, kind="PE")
                bad = engine.bs_price(h[j], K, T, sigma, kind="PE")
            fav = max(fav, good - entry)
            sl = max(sl, entry + fav - trail)  # trail only upward
            if bad <= sl:
                exitp, result, bars = sl, "TRAIL", j - e
                break
            bars = j - e
        if result == "TIME":
            exitp = engine.bs_price(c[min(e + MAX_HOLD, len(df)) - 1], K, T, sigma, kind=kind)
        rows.append({"pnl": exitp - entry, "mfe": fav, "bars": bars,
                     "result": result})
    return pd.DataFrame(rows)


def show(name, r):
    wins = r.pnl > 0
    gp, gl = r.loc[wins, "pnl"].sum(), -r.loc[~wins, "pnl"].sum()
    print(f"{name:24s} n={len(r):4d} win={wins.mean()*100:5.1f}% "
          f"avg=Rs{r.pnl.mean():+6.2f} PF={gp/gl if gl else np.inf:4.2f} "
          f"avgMFE=Rs{r.mfe.mean():5.1f} avgBars={r.bars.mean():4.1f}")


if __name__ == "__main__":
    raw = data_loader.load_data(last_days=10 ** 6, minutes=5)
    for confirm in (3, 2):
        df, sigs = make_signals(raw, confirm)
        for trail in (10.0, 15.0, 20.0):
            show(f"{confirm}green / trail Rs{int(trail)}", run(df, sigs, trail))
        print()
