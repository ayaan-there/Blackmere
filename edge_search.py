"""Search for a REAL edge: signals whose hit-rate beats base rate on BOTH
train (first 70% time) and test (last 30% time). No market-profile loop here
(vectorised) so ~90k bars run in seconds.

Usage: python edge_search.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

TH = 0.10  # percent move threshold


def main():
    df = engine.add_indicators(data_loader.load_data(last_days=None, minutes=5))
    c, h, l, o, v = (df[k] for k in ("close", "high", "low", "open", "volume"))
    n = len(df)

    f5 = (c.shift(-5) / c - 1) * 100
    f15 = (c.shift(-15) / c - 1) * 100
    day = df["timestamp"].dt.date
    same5 = day.shift(-5).eq(day).fillna(False)
    same15 = day.shift(-15).eq(day).fillna(False)
    rng = (h - l)
    atr = df["atr"]
    hr = df["timestamp"].dt.hour + df["timestamp"].dt.minute / 60
    qlo, qhi = atr.div(c).quantile(0.4), atr.div(c).quantile(0.6)
    ahead10 = h.rolling(10).max().shift(1)
    ahead20 = h.rolling(20).max().shift(1)
    low10 = l.rolling(10).min().shift(1)

    L = {  # long candidates
        "ema_up": df.ema9 > df.ema21,
        "above_vwap": c > df.vwap,
        "brk20": c > ahead20,
        "brk10": c > ahead10,
        "brk10+ema": (c > ahead10) & (df.ema9 > df.ema21) & (c > df.vwap),
        "brk20+ema": (c > ahead20) & (df.ema9 > df.ema21) & (c > df.vwap),
        "bullbar+above": (c > o) & (c > df.vwap) & (df.ema9 > df.ema21),
        "bull_engulf": df.pattern.eq("BULL ENGULFING"),
        "bull_maru": df.pattern.eq("BULL MARUBOZU"),
        "hammer": df.pattern.eq("HAMMER"),
        "rsi_pullback": (df.rsi > 45) & (df.rsi < 60) & (c > df.vwap),
        "rsi_oversold_bounce": (df.rsi < 35) & (c > o),
        "lowvol_breakout": (c > ahead10) & (atr.div(c) < qlo),
        "highvol_breakout": (c > ahead10) & (atr.div(c) > qhi),
        "hv_brk+vwap": (c > ahead10) & (atr.div(c) > qhi) & (c > df.vwap),
        "hv_brk+bull": (c > ahead10) & (atr.div(c) > qhi) & (c > o),
        "hv_brk+rsi50": (c > ahead10) & (atr.div(c) > qhi) & (df.rsi > 50),
        "hv_brk+morning": (c > ahead10) & (atr.div(c) > qhi) & (hr < 11),
        "hv_brk+afternoon": (c > ahead10) & (atr.div(c) > qhi) & (hr >= 14),
        "hv_brk20": (c > ahead20) & (atr.div(c) > qhi),
        "narrow_then_up": (rng < 0.5 * atr).shift(1).fillna(False) & (c > o),
        "morning_up": (hr < 11) & (c > df.vwap) & (df.ema9 > df.ema21),
        "afternoon_up": (hr >= 14) & (hr <= 15) & (c > df.vwap) & (df.ema9 > df.ema21),
        "afternoon_up_brk": (hr >= 14) & (hr <= 15) & (c > df.vwap)
                            & (df.ema9 > df.ema21) & (c > ahead10),
        "afternoon_up_strong": (hr >= 14) & (hr <= 15) & (c > df.vwap)
                               & (df.ema9 > df.ema21) & (df.rsi > 55),
        "far_above_vwap": ((c - df.vwap) / atr > 0.7) & (df.ema9 > df.ema21),
        "bounce_vwap": ((c - df.vwap).abs() < 0.3 * atr) & (c > o) & (df.ema9 > df.ema21),
    }
    S = {  # short candidates
        "ema_dn": df.ema9 < df.ema21,
        "below_vwap": c < df.vwap,
        "brk_dn20": c < low10.shift(0) if False else c < l.rolling(20).min().shift(1),
        "brk_dn10": c < low10,
        "brk_dn10+ema": (c < low10) & (df.ema9 < df.ema21) & (c < df.vwap),
        "bearbar+below": (c < o) & (c < df.vwap) & (df.ema9 < df.ema21),
        "bear_engulf": df.pattern.eq("BEAR ENGULFING"),
        "bear_maru": df.pattern.eq("BEAR MARUBOZU"),
        "shooting_star": df.pattern.eq("SHOOTING STAR"),
        "rsi_overbought_fade": (df.rsi > 65) & (c < o),
        "morning_dn": (hr < 11) & (c < df.vwap) & (df.ema9 < df.ema21),
        "afternoon_dn": (hr >= 14) & (c < df.vwap) & (df.ema9 < df.ema21),
    }
    cut = int(n * 0.7)

    def stats(mask, fwd, same):
        a = (mask.fillna(False) & same).to_numpy()
        y = fwd.to_numpy()
        out = []
        for name, sl in (("train", slice(0, cut)), ("test", slice(cut, n - 16))):
            sel = y[a][sl] if False else y[sl][a[sl]]
            out.append((int(len(sel)), round(float((sel > TH).mean() * 100), 1)
                        if len(sel) else 0.0,
                        round(float(sel.mean()), 3) if len(sel) else 0.0))
        return out

    fu, fd = f15[same15], (-f15)[same15]
    bc = int(same15.iloc[:cut].sum())
    base_up = [(int((fu.iloc[:cut] > TH).sum()),
                round(float((fu.iloc[:cut] > TH).mean() * 100), 1),
                round(float(fu.iloc[:cut].mean()), 3)),
               (int((fu.iloc[cut:] > TH).sum()),
                round(float((fu.iloc[cut:] > TH).mean() * 100), 1),
                round(float(fu.iloc[cut:].mean()), 3))]
    base_dn = [(int((fd.iloc[:cut] > TH).sum()),
                round(float((fd.iloc[:cut] > TH).mean() * 100), 1),
                round(float(fd.iloc[:cut].mean()), 3)),
               (int((fd.iloc[cut:] > TH).sum()),
                round(float((fd.iloc[cut:] > TH).mean() * 100), 1),
                round(float(fd.iloc[cut:].mean()), 3))]
    print(f"same-day 15-bar bars: train={bc:,} test={int(same15.iloc[cut:].sum()):,}")
    print(f"bars={n:,} train={cut:,} test={n-cut:,} threshold=+/-{TH}% at 15 bars")
    print(f"BASE up  train/test: {base_up}")
    print(f"BASE down train/test: {base_dn}\n")

    for label, sigs, fwd in (("LONG", L, f15), ("SHORT", S, -f15)):
        res = []
        for name, mask in sigs.items():
            tr, te = stats(mask, fwd, same15)
            res.append((name, tr, te))
        res.sort(key=lambda x: -(x[1][1] - (base_up if label == "LONG" else base_dn)[0][1]))
        print(f"===== {label} top by train hit-rate (train n,hit,mean / test n,hit,mean) =====")
        for name, tr, te in res[:12]:
            print(f"{name:24s} {tr} | {te}")
        print()


if __name__ == "__main__":
    main()
