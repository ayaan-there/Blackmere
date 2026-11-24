"""Backtest 3 described strategies on Nifty 5/15/60-min data.

Where source data is missing, proxies are used and stated explicitly:
  - Gold/QQQ-specific, footprint delta, gamma, heatmap -> NOT available; mapped to
    Nifty multi-timeframe structure / volume-profile / swing levels.
  - Volume is 0 in index data -> bar-range activity proxy is used.

Win = forward move in the intended direction exceeds threshold before the
opposite threshold (simplified fixed-horizon hit, 5-min equivalent).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

TH = 0.10  # percent move threshold for a "win" at horizon


def fwd(df, horizon):
    c = df["close"].to_numpy()
    day = df["timestamp"].dt.date.to_numpy()
    f = (c[min(horizon, len(c) - 1):] / c[:len(c) - min(horizon, len(c) - 1)] - 1) * 100
    f = np.concatenate([f, np.full(min(horizon, len(c)-1), np.nan)])
    same = np.concatenate([day[min(horizon, len(c)-1):] == day[:len(c)-min(horizon, len(c)-1)],
                           np.full(min(horizon, len(c)-1), False)])
    return f, same


def report(name, mask, f, same, n_total):
    a = (mask.fillna(False).to_numpy() if hasattr(mask, "fillna") else np.asarray(mask)) & same
    sel = f[a]
    if len(sel) == 0:
        print(f"{name:34s} n=0")
        return
    wins = (sel > TH).sum()
    losses = (sel < -TH).sum()
    print(f"{name:34s} n={len(sel):5d} win={wins/len(sel)*100:5.1f}% "
          f"loss={losses/len(sel)*100:5.1f}% avg={np.nanmean(sel):+.3f}% "
          f"({wins/len(sel)*100:.1f}% vs base {(f[same]>TH).mean()*100:.1f}%)")


def ema(s, n): return s.ewm(span=n, adjust=False).mean()


def main():
    d5 = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    d15 = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=15))
    d60 = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=60))

    # align 60m / 15m trend to 5m bars via asof-style forward-fill on timestamp
    t60 = pd.Series(np.where(d60.ema9 > d60.ema21, 1,
                             np.where(d60.ema9 < d60.ema21, -1, 0)).astype(float),
                    index=d60["timestamp"])
    t15 = pd.Series((d15.ema9 > d15.ema21).astype(float), index=d15["timestamp"])
    d5["trend60"] = t60.reindex(d5["timestamp"], method="ffill").fillna(0).astype(int).values
    d5["ema15up"] = t15.reindex(d5["timestamp"], method="ffill").fillna(False).astype(bool).values

    f5, same5 = fwd(d5, 15)   # ~75 min horizon (15 x 5-min bars)
    c, o, h, l = (d5[k] for k in ("close", "open", "high", "low"))
    body = (c - o).abs()
    rng = (h - l).replace(0, np.nan)
    bull_eng = ((c > o) & (c.shift(1) < o.shift(1)) &
                (c > o.shift(1)) & (o < c.shift(1)))
    bear_eng = ((c < o) & (c.shift(1) > o.shift(1)) &
                (o > c.shift(1)) & (c < o.shift(1)))

    print("==== 1. Iman ICC (HTF trend + correction + continuation) ====")
    # long: 60m up, 15m pullback below ema9, then engulfing continuation
    pull_up = (d5.trend60 == 1) & (c < d5.ema9)
    cont_up = (bull_eng & (c > d5.ema9))
    pull_dn = (d5.trend60 == -1) & (c > d5.ema9)
    cont_dn = (bear_eng & (c < d5.ema9))
    report("ICC long (H1 up + pullback + bull engulf)", pull_up.shift(1).fillna(False) & cont_up, f5, same5, len(d5))
    report("ICC short (H1 down + pullback + bear engulf)", pull_dn.shift(1).fillna(False) & cont_dn, -f5, same5, len(d5))
    report("ICC loose (H1 trend + any engulf in trend)",
           ((d5.trend60 == 1) & bull_eng) | ((d5.trend60 == -1) & bear_eng),
           np.where(d5.trend60.to_numpy() == 1, f5, -f5), same5, len(d5))

    print("\n==== 2. Ellie Order Flow / Auction (volume profile POC/VAH/VAL) ====")
    # vectorised POC/VA over trailing ~1 day using close buckets and volume proxy
    vol = d5["volume"].fillna(0).to_numpy()
    cl = c.to_numpy()
    tick = 50.0
    bucket = (cl / tick).round() * tick
    poc = pd.Series(bucket).rolling(76).apply(
        lambda x: pd.Series(x).value_counts().idxmax(), raw=False).values
    val = pd.Series(np.where(cl < poc, bucket, np.nan)).rolling(76).min().values
    vah = pd.Series(np.where(cl > poc, bucket, np.nan)).rolling(76).max().values
    poc_s, val_s, vah_s = pd.Series(poc).ffill(), pd.Series(val).ffill(), pd.Series(vah).ffill()
    d5["poc"], d5["val"], d5["vah"] = poc_s, val_s, vah_s
    failed_low = (l <= val_s) & (c > val_s)   # push below VAL then back inside
    failed_high = (h >= vah_s) & (c < vah_s)
    report("Failed auction at VAL -> long", failed_low, f5, same5, len(d5))
    report("Failed auction at VAH -> short", failed_high, -f5, same5, len(d5))
    near_poc = ((c - poc_s).abs() < 100)
    report("POC touch (mean reversion, either way)", near_poc, f5, same5, len(d5))

    print("\n==== 3. Sed two-model (1:1 / structure sweep / BE after 1:1) ====")
    hi20 = h.rolling(20).max().shift(1)
    lo20 = l.rolling(20).min().shift(1)
    sweep_hi = (h > hi20) & (c < hi20)   # high sweep rejection -> short
    sweep_lo = (l < lo20) & (c > lo20)   # low sweep rejection -> long
    REPORT = 2 * 0.10  # 1:1 with 0.1% stop -> 0.2% target (TH)
    # win at 1:1 horizon ~ 10 bars if +REPORT reached before -0.1
    f10, same10 = fwd(d5, 10)
    report("Sweep low + reversal -> long (1:1)", sweep_lo, f10, same10, len(d5))
    report("Sweep high + reversal -> short (1:1)", sweep_hi, -f10, same10, len(d5))
    # consolidation breakout proxy
    narrow = ((h - l).rolling(10).mean() < (h - l).rolling(50).mean())
    brk = (c > hi20.shift(1)) & narrow.shift(1).fillna(False)
    report("Tight range breakout -> long (1:1)", brk, f10, same10, len(d5))
    print(f"\nBase rate at 15-bar horizon: {(f5[same5]>TH).mean()*100:.1f}% up, "
          f"{(f5[same5]<-TH).mean()*100:.1f}% down")


if __name__ == "__main__":
    main()
