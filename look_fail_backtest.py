"""Look Above & Fail / Look Below & Fail (Balanced Range Model) on Nifty 5-min.

Adapted: 2-min -> 5-min, RTH -> NSE 09:15-15:30, big trades/delta -> not
available (volume proxy used). Developing volume profile recomputed hourly.

Long  = Look BELOW and FAIL: push below VAL, snap back inside VAL.
Short = Look ABOVE and FAIL: push above VAH, snap back inside VAH.
T1 = POC (SL -> BE), Final = opposite value area edge. Min 2R to final.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

TICK = 50.0
MAX_HOLD = 48
START = pd.Timestamp("09:45").time()   # skip first 30 min (09:15-09:45)


def prof(sub: pd.DataFrame):
    b = (sub["close"] / TICK).round() * TICK
    v = sub["volume"].fillna(0).to_numpy()
    va = pd.DataFrame({"b": b.to_numpy(), "v": v}).groupby("b")["v"].sum().sort_values(ascending=False)
    if va.empty:
        return np.nan, np.nan, np.nan
    poc = float(va.index[0])
    total, acc, chosen = va.sum(), 0.0, [poc]
    for price, q in va.items():
        if acc >= 0.70 * total:
            break
        chosen.append(float(price))
        acc += float(q)
    return poc, max(chosen), min(chosen)


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    d["day"] = d["timestamp"].dt.date
    d["tm"] = d["timestamp"].dt.time

    g = d.groupby("day")
    daily = pd.DataFrame({"C": g.close.last(), "H": g.high.max(), "L": g.low.min()})
    e20, e50 = daily.C.ewm(span=20).mean(), daily.C.ewm(span=50).mean()
    daily["bal"] = ~(((daily.C > e20) & (e20 > e50)) | ((daily.C < e20) & (e20 < e50)))
    d["bal"] = d["day"].map(daily["bal"]).fillna(True)

    # hourly developing profile -> forward fill within day
    levels = {}
    for day, sub in g:
        marks = [t for t in (pd.Timestamp("10:00").time(), pd.Timestamp("11:00").time(),
                             pd.Timestamp("12:00").time(), pd.Timestamp("13:00").time(),
                             pd.Timestamp("14:00").time())]
        cur = np.full(3, np.nan)
        idxs = sub.index
        for i in idxs:
            if sub.at[i, "tm"] in marks:
                cur = np.array(prof(sub.loc[idxs[0]:i]), dtype=float)
            levels[i] = cur.copy()
    L = pd.DataFrame.from_dict(levels, orient="index", columns=["poc", "vah", "val"])
    d[["poc", "vah", "val"]] = L.reindex(d.index)

    c, h, l = (d[k] for k in ("close", "high", "low"))
    rows = []
    for i in range(80, len(d) - MAX_HOLD - 1):
        if not d["bal"].iloc[i] or d["tm"].iloc[i] < START:
            continue
        poc, vah, val = (d[k].iloc[i] for k in ("poc", "vah", "val"))
        if any(pd.isna(x) for x in (poc, vah, val)):
            continue
        day = d["day"].iloc[i]
        if i == 0 or d["day"].iloc[i - 1] != day:
            continue

        sig = None
        # Long: prior bar closed below VAL, now reclaims it
        if c.iloc[i - 1] < val and c.iloc[i] > val:
            sig = (1, val, poc, vah)
        # Short: prior bar closed above VAH, now back inside
        elif c.iloc[i - 1] > vah and c.iloc[i] < vah:
            sig = (-1, vah, poc, val)
        if sig is None:
            continue
        direction, level, t1, t2 = sig
        swing = l.iloc[i - 1] if direction == 1 else h.iloc[i - 1]
        stop = swing - 0.2 * abs(level - swing) if direction == 1 else swing + 0.2 * abs(level - swing)
        entry = float(c.iloc[i])
        risk = abs(entry - stop)
        if risk <= 0:
            continue
        r2 = abs(t2 - entry) >= 2 * risk          # 2R to final target
        r1 = abs(t1 - entry) >= 1 * risk
        if not r1:
            continue

        res1, res2 = "TIME", "TIME"
        for j in range(i + 1, min(i + MAX_HOLD, len(d))):
            if d["day"].iloc[j] != day:
                break
            if direction == 1:
                if l.iloc[j] <= stop:
                    res1 = res2 = "SL"; break
                if res1 == "TIME" and h.iloc[j] >= t1:
                    res1 = "T1"
                if h.iloc[j] >= t2:
                    res2 = "FINAL"; break
            else:
                if h.iloc[j] >= stop:
                    res1 = res2 = "SL"; break
                if res1 == "TIME" and l.iloc[j] <= t1:
                    res1 = "T1"
                if l.iloc[j] <= t2:
                    res2 = "FINAL"; break
        rows.append({"side": "LONG" if direction == 1 else "SHORT",
                     "r2": r2, "t1": res1, "final": res2, "risk": round(risk, 1)})

    r = pd.DataFrame(rows)
    if r.empty:
        print("koi signal nahi"); return
    print("LOOK ABOVE/BELOW & FAIL on Nifty 5m (5 yrs, balanced only)\n")
    print(f"{'Setup':22s} {'n':>5s} {'T1 hit%':>8s} {'Final%':>7s} {'SL%':>6s}")
    for name, sub in [("LONG - below VAL fail", r[r.side == "LONG"]),
                      ("SHORT - above VAH fail", r[r.side == "SHORT"]),
                      ("2R-eligible only", r[r.r2]),
                      ("ALL", r)]:
        if sub.empty: continue
        print(f"{name:22s} {len(sub):5d} {(sub.t1!='TIME').mean()*100:8.1f} "
              f"{(sub.final=='FINAL').mean()*100:7.1f} {(sub.final=='SL').mean()*100:6.1f}")


if __name__ == "__main__":
    main()
