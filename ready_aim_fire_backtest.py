"""Ready-Aim-Fire strategy adapted to Nifty 50 (Indian market).

Ready  : daily regime = BALANCE vs TREND (EMA20/50 + structure).
Aim    : prior-day VPOC/VAH/VAL, PDH/PDL, session VWAP, 15-day composite HVNs.
Fire   : 5-min rejection candle (absorption proxy) + break / break-&-retest entry.
         Stop beyond wick/level; target next opposing level; min 1:1 R:R.

Not available -> proxied: footprint/delta, intra-candle VPOC, GEX/options walls,
Globex session. Index volume=0 -> bar-range volume proxy.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

TICK = 50.0
MAX_HOLD = 48  # 5-min bars same day


def profile(day_df: pd.DataFrame):
    buckets = (day_df["close"] / TICK).round() * TICK
    vol = day_df["volume"].fillna(0).to_numpy()
    va = pd.DataFrame({"b": buckets.to_numpy(), "v": vol}).groupby("b")["v"].sum().sort_values(ascending=False)
    if va.empty:
        return np.nan, np.nan, np.nan, {}
    poc = float(va.index[0])
    total, acc, chosen = va.sum(), 0.0, [poc]
    for price, q in va.items():
        if acc >= 0.70 * total:
            break
        chosen.append(float(price))
        acc += float(q)
    return poc, max(chosen), min(chosen), va.to_dict()


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    d["day"] = d["timestamp"].dt.date

    # ---------- READY: daily regime ----------
    g = d.groupby("day")
    daily = pd.DataFrame({"H": g.high.max(), "L": g.low.min(), "C": g.close.last()})
    daily["e20"] = daily.C.ewm(span=20, adjust=False).mean()
    daily["e50"] = daily.C.ewm(span=50, adjust=False).mean()
    daily["tr"] = pd.concat([daily.H - daily.L,
                             (daily.H - daily.C.shift()).abs(),
                             (daily.L - daily.C.shift()).abs()], axis=1).max(axis=1)
    daily["atr"] = daily.tr.ewm(alpha=1/14, adjust=False).mean()
    daily["regime"] = np.where(daily.C > daily.e20, 1,
                        np.where(daily.C < daily.e20, -1, 0))
    up = (daily.C > daily.e20) & (daily.e20 > daily.e50)
    dn = (daily.C < daily.e20) & (daily.e20 < daily.e50)
    daily["regime"] = np.where(up, 1, np.where(dn, -1, 0))
    d["regime"] = d["day"].map(daily["regime"]).ffill().fillna(0).astype(int)

    # ---------- AIM: prior-day levels ----------
    days_sorted = sorted(d["day"].unique())
    prof = {day: profile(sub) for day, sub in g}
    hv = {day: dict(v[3]) for day, v in prof.items()}
    hv_df = pd.DataFrame(hv).T.fillna(0)
    hv_roll = hv_df.rolling(15, min_periods=5).sum()
    hvn_top = {day: sorted(hv_roll.loc[day].nlargest(3).index) if day in hv_roll.index else []
               for day in days_sorted}

    lvl = {}
    for i, day in enumerate(days_sorted):
        if i == 0:
            continue
        prev = days_sorted[i - 1]
        poc, vah, val, _ = prof[prev]
        lvl[day] = {"poc": poc, "vah": vah, "val": val,
                    "pdh": daily.loc[prev, "H"], "pdl": daily.loc[prev, "L"],
                    "hvn": hvn_top.get(prev, [])}
    d["daystr"] = d["day"].astype(str)
    lvldf = pd.DataFrame(lvl).T
    lvldf.index = lvldf.index.astype(str)
    for col in ("poc", "vah", "val", "pdh", "pdl"):
        d[col] = d["daystr"].map(lvldf[col]).astype(float)

    c, o, h, l = (d[k] for k in ("close", "open", "high", "low"))
    rng = (h - l).replace(0, np.nan)
    body = (c - o).abs()
    # absorption/rejection proxies on 5-min candle
    bull_pin = ((l - np.minimum(o, c)) >= 2 * body) & (c > o)
    bear_pin = ((np.maximum(o, c) - h) >= 2 * body) & (c < o)
    engulf_up = (c > o) & (c.shift(1) < o.shift(1)) & (c > o.shift(1))
    engulf_dn = (c < o) & (c.shift(1) > o.shift(1)) & (c < o.shift(1))

    rows = []
    for i in range(80, len(d) - MAX_HOLD - 1):
        day = d["day"].iloc[i]
        if day not in lvl:
            continue
        if i > 0 and d["day"].iloc[i - 1] != day:
            continue  # only first bar of day enters via levels (we still scan all below)
        li = lvl[day]
        poc, vah, val = li["poc"], li["vah"], li["val"]
        pdh, pdl = li["pdh"], li["pdl"]
        vwap = d["vwap"].iloc[i]
        atr = d["atr"].iloc[i]
        reg = d["regime"].iloc[i]
        if any(pd.isna(x) for x in (poc, vah, val, pdh, pdl, vwap, atr)):
            continue
        buf = 0.3 * atr
        price = c.iloc[i]

        sig = None
        # --- BALANCED: fade extremes at range low/high (VAL/PDL vs VAH/PDH)
        if reg == 0:
            if abs(price - min(val, pdl)) <= buf and (bull_pin.iloc[i] or engulf_up.iloc[i]):
                sig = (1, min(val, pdl), "balance-fade-low")
            elif abs(price - max(vah, pdh)) <= buf and (bear_pin.iloc[i] or engulf_dn.iloc[i]):
                sig = (-1, max(vah, pdh), "balance-fade-high")
        # --- TRENDING: with trend on pullback to VAH/VWAP/POC (long) or VAL/VWAP/POC (short)
        elif reg == 1:
            pull = min(x for x in (vah, vwap, poc) if x <= price + buf) if any(x <= price + buf for x in (vah, vwap, poc)) else None
            if pull is not None and abs(price - pull) <= buf and (bull_pin.iloc[i] or engulf_up.iloc[i]):
                sig = (1, pull, "trend-pullback-long")
            elif price > vah + buf and engulf_up.iloc[i]:
                sig = (1, vah, "trend-break-long")
        else:
            pull = max(x for x in (val, vwap, poc) if x >= price - buf) if any(x >= price - buf for x in (val, vwap, poc)) else None
            if pull is not None and abs(price - pull) <= buf and (bear_pin.iloc[i] or engulf_dn.iloc[i]):
                sig = (-1, pull, "trend-pullback-short")
            elif price < val - buf and engulf_dn.iloc[i]:
                sig = (-1, val, "trend-break-short")

        if sig is None:
            continue
        direction, level, kind = sig
        entry = float(price)
        stop = float(l.iloc[i] - buf) if direction == 1 else float(h.iloc[i] + buf)
        risk = abs(entry - stop)
        if risk <= 0:
            continue
        # next opposing area of interest
        ups = [x for x in (pdh, vah) + tuple(li["hvn"]) if x > entry + risk]
        dns = [x for x in (pdl, val) + tuple(li["hvn"]) if x < entry - risk]
        target = min(ups) if (direction == 1 and ups) else (max(dns) if (direction == -1 and dns) else np.nan)
        if np.isnan(target) or abs(target - entry) < risk:
            continue  # require >= 1:1
        # outcome same day
        result, exitp = "TIME", entry
        for j in range(i + 1, min(i + MAX_HOLD, len(d))):
            if d["day"].iloc[j] != day:
                break
            if direction == 1:
                if l.iloc[j] <= stop:
                    result, exitp = "SL", stop; break
                if h.iloc[j] >= target:
                    result, exitp = "TARGET", target; break
            else:
                if h.iloc[j] >= stop:
                    result, exitp = "SL", stop; break
                if l.iloc[j] <= target:
                    result, exitp = "TARGET", target; break
        if result == "TIME":
            exitp = float(c.iloc[j])
        rows.append({"kind": kind, "regime": reg, "result": result,
                     "pnl": (exitp - entry) * direction, "r": (exitp - entry) * direction / risk,
                     "time": str(d["timestamp"].iloc[i])})

    r = pd.DataFrame(rows)
    if r.empty:
        print("koi signal nahi")
        return
    print("READY-AIM-FIRE on Nifty 5m (5 years, 1:1 min)\n")
    print(f"{'Setup':28s} {'n':>5s} {'Win%':>6s} {'AvgR':>7s}")
    for k, sub in list(r.groupby("kind")) + [("ALL", r)]:
        wins = (sub.pnl > 0).mean() * 100
        print(f"{k:28s} {len(sub):5d} {wins:6.1f} {sub.r.mean():+7.3f}")
    print(f"\nSL hits: {(r.result=='SL').mean()*100:.1f}% | TARGET: {(r.result=='TARGET').mean()*100:.1f}%")


if __name__ == "__main__":
    main()
