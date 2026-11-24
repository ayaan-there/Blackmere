"""Calendar seasonality on Nifty 50 daily returns (2021-2026).

Tests:
 1) Payday model: long 11th/12th -> exit 18th (time-based, no SL/TP).
 2) Day-of-week returns.
 3) Month-of-year returns.
 4) Robustness: neighboring entry/exit dates (heat map style).
In-sample (2021-2023) vs out-of-sample (2024-2026).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader


def daily():
    d = data_loader.load_data(last_days=10**6, minutes=5)
    g = d.groupby(d["timestamp"].dt.date)
    x = pd.DataFrame({"C": g.close.last(), "O": g.open.first()})
    x.index = pd.to_datetime(x.index)
    x["ret"] = x.C.pct_change() * 100
    x["dow"] = x.index.dayofweek
    x["dom"] = x.index.day
    x["mon"] = x.index.month
    return x


def window_ret(x, start_dom, end_dom):
    """Compound return from close on start_dom to close on end_dom each month."""
    outs = []
    for (y, m), sub in x.groupby([x.index.year, x.index.month]):
        s = sub[sub.dom >= start_dom]
        e = sub[sub.dom <= end_dom]
        if s.empty or e.empty: continue
        a, b = s.iloc[0], e.iloc[-1]
        if b.name <= a.name: continue
        outs.append({"year": y, "month": m,
                     "ret": (b.C / a.C - 1) * 100,
                     "days": len(sub[(sub.dom>=start_dom)&(sub.dom<=end_dom)])})
    return pd.DataFrame(outs)


def show(name, df):
    if df.empty: return
    pos = (df.ret > 0).mean() * 100
    print(f"{name:28s} n={len(df):3d} win={pos:5.1f}% mean={df.ret.mean():+6.2f}% "
          f"median={df.ret.median():+6.2f}%")


def main():
    x = daily()
    print(f"Nifty daily data: {x.index[0].date()} -> {x.index[-1].date()} ({len(x)} sessions)\n")

    print("=== 1) PAYDAY MODEL (long 11th/12th -> exit 18th) ===")
    for s in (11, 12, 13):
        for e in (17, 18, 19):
            w = window_ret(x, s, e)
            show(f"  long {s}th -> exit {e}th", w)

    print("\n=== 2) IN-SAMPLE vs OUT-OF-SAMPLE (12th -> 18th) ===")
    w = window_ret(x, 12, 18)
    for label, part in [("IS 2021-2023", w[w.year<=2023]), ("OOS 2024-2026", w[w.year>=2024])]:
        show(label, part)

    print("\n=== 3) DAY OF WEEK (avg daily return) ===")
    for dow, sub in x.groupby("dow"):
        names = ["Mon","Tue","Wed","Thu","Fri"]
        print(f"  {names[dow]:4s} n={len(sub):4d} win={(sub.ret>0).mean()*100:5.1f}% "
              f"mean={sub.ret.mean():+.3f}% median={sub.ret.median():+.3f}%")

    print("\n=== 4) MONTH OF YEAR (avg daily return) ===")
    for mon, sub in x.groupby("mon"):
        print(f"  M{mon:02d}  n={len(sub):4d} win={(sub.ret>0).mean()*100:5.1f}% "
              f"mean={sub.ret.mean():+.3f}%")


if __name__ == "__main__":
    main()
