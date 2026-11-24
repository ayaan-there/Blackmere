"""All strategies re-tested on BEES PROXY = Nifty 50 index / 100.

No options here: plain ETF buy/sell. SL/target in BEES rupees.
Index parquet is the only data available; BEES price is approximated as Nifty/100.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
from no_target_trail_backtest import make_signals

MAX_HOLD = 60  # 5-min bars (~5 hours, same-day exit)


def simulate(df, sigs, sl_rs, target_rs=None, trail_rs=None, early_rs=None):
    c = (df["close"] / 100).to_numpy()
    h = (df["high"] / 100).to_numpy()
    l = (df["low"] / 100).to_numpy()
    o = (df["open"] / 100).to_numpy()
    days = df["timestamp"].dt.date.to_numpy()
    rows = []
    for e, direction in sigs:
        entry = c[e]
        sl = entry - sl_rs if direction == 1 else entry + sl_rs
        target = (entry + target_rs) if (target_rs and direction == 1) else (
            (entry - target_rs) if target_rs else None)
        fav, exitp, result = 0.0, entry, "TIME"
        for j in range(e, min(e + MAX_HOLD, len(df))):
            if days[j] != days[e]:
                break
            bad = (entry - l[j]) if direction == 1 else (h[j] - entry)
            if direction == 1:
                fav = max(fav, h[j] - entry)
            else:
                fav = max(fav, entry - l[j])
            if trail_rs:
                if direction == 1:
                    sl = max(sl, h[j] - trail_rs)
                else:
                    sl = min(sl, l[j] + trail_rs)
            hit_sl = (l[j] <= sl) if direction == 1 else (h[j] >= sl)
            if hit_sl:
                exitp, result = sl, "SL"
                break
            if target is not None:
                hit_t = (h[j] >= target) if direction == 1 else (l[j] <= target)
                if hit_t:
                    exitp, result = target, "TARGET"
                    break
            if early_rs and fav >= early_rs:
                opposite = (c[j] < o[j]) if direction == 1 else (c[j] > o[j])
                if opposite:
                    exitp, result = c[j], "EARLY"
                    break
        if result == "TIME":
            exitp = c[min(e + MAX_HOLD, len(df)) - 1]
        pnl = (exitp - entry) * direction
        rows.append({"pnl": pnl, "result": result, "fav": fav})
    return pd.DataFrame(rows)


def show(name, r):
    wins = r.pnl > 0
    gp, gl = r.loc[wins, "pnl"].sum(), -r.loc[~wins, "pnl"].sum()
    print(f"{name:26s} n={len(r):4d} win={wins.mean()*100:5.1f}% "
          f"avg=Rs{r.pnl.mean():+5.2f} PF={gp/gl if gl else np.inf:4.2f} "
          f"T={(r.result=='TARGET').mean()*100:4.1f}% "
          f"SL={(r.result=='SL').mean()*100:4.1f}%")


if __name__ == "__main__":
    raw = data_loader.load_data(last_days=10 ** 6, minutes=5)
    print(f"BEES proxy = Nifty/100, bars={len(raw)}, last BEES ~{raw.close.iloc[-1]/100:.1f}\n")
    for confirm in (3, 2):
        df, sigs = make_signals(raw, confirm)
        print(f"--- {confirm} GREEN CANDLE ---")
        for sl, tg in ((0.5, 1.0), (1.0, 2.0), (1.5, 3.0)):
            show(f"{confirm}g SL{sl} T{tg}", simulate(df, sigs, sl, target_rs=tg))
        show(f"{confirm}g SL1 TRAIL1 (no target)",
             simulate(df, sigs, 1.0, trail_rs=1.0))
        show(f"{confirm}g SL1 T2 EARLY+0.5",
             simulate(df, sigs, 1.0, target_rs=2.0, early_rs=0.5))
        print()
