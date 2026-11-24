"""One-Time Framing (OTF) regime filter test on Nifty daily bars.

Strict OTF-up: HH + HL + close > prior candle's HIGH.
OTF-down: LL + LH + close < prior LOW. Else balance.

Tests:
 1) Forward return profile after OTF-up / OTF-down / balance (does regime predict?).
 2) Regime persistence (does 'imbalance' last?).
 3) Alignment proxy: daily OTF + weekly (5-day) OTF direction.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader


def main():
    d = data_loader.load_data(last_days=10**6, minutes=5)
    g = d.groupby(d["timestamp"].dt.date)
    x = pd.DataFrame({"O": g.open.first(), "H": g.high.max(),
                      "L": g.low.min(), "C": g.close.last()})
    x.index = pd.to_datetime(x.index)
    c, h, l = x.C, x.H, x.L
    otf_up = (h > h.shift(1)) & (l > l.shift(1)) & (c > h.shift(1))
    otf_dn = (h < h.shift(1)) & (l < l.shift(1)) & (c < l.shift(1))
    x["regime"] = np.where(otf_up, 1, np.where(otf_dn, -1, 0))
    x["regime"] = x["regime"].replace(0, np.nan).ffill().fillna(0).astype(int)
    x["chg"] = c.pct_change() * 100

    print("Regime distribution:")
    for r, n_ in x.regime.value_counts().items():
        print(f"  {'IMBAL-UP' if r==1 else 'IMBAL-DN' if r==-1 else 'BALANCE'}: {n_} days ({n_/len(x)*100:.0f}%)")

    print("\n=== 1) Forward daily return after regime (next 1/3/5/10 days) ===")
    for r, label in ((1,"IMBAL-UP"),(-1,"IMBAL-DN"),(0,"BALANCE")):
        idx = x.index[x.regime == r]
        print(f"  {label:9s} n={len(idx):4d}", end="")
        for k in (1,3,5,10):
            f = (x.C.shift(-k) / x.C - 1) * 100
            vals = f.reindex(idx).dropna()
            print(f"  +{k}d={vals.mean():+.2f}% (win {(vals>0).mean()*100:.0f}%)", end="")
        print()

    print("\n=== 2) Regime persistence (next day same regime) ===")
    same = x.regime == x.regime.shift(1)
    for r, label in ((1,"IMBAL-UP"),(-1,"IMBAL-DN"),(0,"BALANCE")):
        m = x.regime == r
        print(f"  {label:9s} persists {same[m].mean()*100:.0f}% of days")

    print("\n=== 3) Weekly (5-day) alignment on daily OTF ===")
    x["wk"] = x.C.rolling(5).apply(lambda a: 1 if a.iloc[-1] > a.iloc[0] else -1, raw=False)
    for r, label in ((1,"daily UP"),(-1,"daily DN")):
        for w, wl in ((1,"weekly UP"),(-1,"weekly DN")):
            m = (x.regime == r) & (x.wk == w)
            f = ((x.C.shift(-5)/x.C - 1)*100).reindex(x.index[m]).dropna()
            if len(f): print(f"  {label:10s} + {wl:10s}: n={len(f):4d} +5d={f.mean():+.2f}% win={(f>0).mean()*100:.0f}%")


if __name__ == "__main__":
    main()
