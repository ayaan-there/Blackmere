"""70%-claim strategy adapted to Nifty 5-min.

Bias  : weekly trend + prior daily candle + pre-session H4 candle alignment.
Zones : S/R at candle BODIES (not wicks), clean ranges only.
Entry : consolidation -> small breakout candle (<50% of range) -> next candle
        makes opposing wick (liquidity grab) then breaks breakout high/low.
Risk  : SL behind breakout candle; TP at 1:1 or next major body level.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine

MAX_HOLD = 12


def main():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    d["day"] = d["timestamp"].dt.date
    g = d.groupby("day")

    daily = pd.DataFrame({"C": g.close.last(), "O": g.open.first(),
                          "H": g.high.max(), "L": g.low.min()})
    daily["dir"] = np.sign(daily.C - daily.O)
    # weekly trend from daily
    daily["wk_up"] = daily.C > daily.C.rolling(5).mean().shift(0)
    daily["wk_ema"] = daily.C.ewm(span=20).mean()
    daily["wk_trend"] = np.where(daily.C > daily.wk_ema, 1,
                          np.where(daily.C < daily.wk_ema, -1, 0))
    # pre-session H4 proxy = last 60-min bar direction of prior day
    d60 = data_loader.load_data(last_days=10**6, minutes=60)
    d60["dir"] = np.sign(d60.close - d60.open)
    d60["day"] = d60["timestamp"].dt.date
    last_h4 = d60.groupby("day")["dir"].last()
    daily["h4dir"] = last_h4.reindex(daily.index).fillna(0)

    bias = {}
    for i, day in enumerate(daily.index):
        if i == 0: continue
        wt = daily.wk_trend.iloc[i]
        dd = daily["dir"].iloc[i - 1]
        h4 = daily.h4dir.iloc[i - 1]
        if wt != 0 and (dd == wt or h4 == wt):
            bias[day] = wt
        elif wt == 0:
            bias[day] = dd if dd == h4 else 0
        else:
            bias[day] = 0
    d["bias"] = d["day"].map(bias).fillna(0)

    # body-based levels from prior day
    body_hi = d[["open", "close"]].assign(day=d["day"]).groupby("day").max().max(axis=1)
    body_lo = d[["open", "close"]].assign(day=d["day"]).groupby("day").min().min(axis=1)
    prior = pd.DataFrame({"bh": body_hi.shift(1), "bl": body_lo.shift(1),
                          "ph": daily.H.shift(1), "pl": daily.L.shift(1)})
    d["bh"] = d["day"].map(prior.bh)
    d["bl"] = d["day"].map(prior.bl)
    d["ph"] = d["day"].map(prior.ph)
    d["pl"] = d["day"].map(prior.pl)

    c, o, h, l = (d[k].to_numpy() for k in ("close", "open", "high", "low"))
    rng = (h - l)
    days = d["timestamp"].dt.date.to_numpy()
    n = len(d)
    cons = pd.Series(rng).rolling(6).max().shift(1).to_numpy()   # recent range
    atr = d["atr"].to_numpy()

    rows = []
    for i in range(90, n - MAX_HOLD - 2):
        b = d["bias"].iloc[i]
        bh, bl, ph, pl = (d[k].iloc[i] for k in ("bh", "bl", "ph", "pl"))
        if any(pd.isna(x) for x in (bh, bl, ph, pl)):
            continue
        if days[i] == days[i - 1] and days[i] != days[i + 1] and i + 1 >= n:
            continue
        # consolidation: last 6 bars tight
        if not (0 < cons[i] < 1.5 * atr[i]):
            continue
        # breakout candle i: body < 50% of recent range, close outside body level
        body = abs(c[i] - o[i])
        if body >= 0.5 * cons[i]:
            continue
        up = c[i] > o[i]
        dn = c[i] < o[i]
        if not (up or dn):
            continue
        if b == 1 and not (c[i] > min(bh, ph)):
            continue
        if b == -1 and not (c[i] < max(bl, pl)):
            continue
        if b == 0:
            continue  # mixed bias: skip directional breakouts

        direction = 1 if up else -1
        # next candle j: opposing wick (liquidity grab) then break of breakout high/low
        j = i + 1
        if j >= n or days[j] != days[i]:
            continue
        grab = ((h[j] > h[i] or l[j] < l[i]) and
                ((h[i] - c[j]) > 0.3 * (h[j] - l[j]) if direction == -1 else
                 (c[j] - l[i]) > 0.3 * (h[j] - l[j])))
        if not grab:
            continue

        for k in range(j, min(j + 4, n - MAX_HOLD)):
            if days[k] != days[i]:
                break
            trig = (h[k] > h[i]) if direction == 1 else (l[k] < l[i])
            if not trig:
                continue
            entry = h[i] if direction == 1 else l[i]
            stop = l[i] - 0.1 * (h[i] - l[i]) if direction == 1 else h[i] + 0.1 * (h[i] - l[i])
            risk = abs(entry - stop)
            if risk <= 0 or risk > cons[i]:
                break
            tgt1 = entry + risk if direction == 1 else entry - risk
            # next major level as alternative target
            major = ph if direction == 1 else pl
            target = min(tgt1, major) if (direction == 1 and major > entry) else (
                      max(tgt1, major) if (direction == -1 and major < entry) else tgt1)
            if abs(target - entry) < risk:
                target = tgt1
            pnl, res = np.nan, "TIME"
            for m in range(k, min(k + MAX_HOLD, n)):
                if days[m] != days[i]:
                    break
                if direction == 1:
                    if l[m] <= stop:
                        pnl, res = -risk, "SL"; break
                    if h[m] >= target:
                        pnl, res = abs(target - entry), "T"; break
                else:
                    if h[m] >= stop:
                        pnl, res = -risk, "SL"; break
                    if l[m] <= target:
                        pnl, res = abs(target - entry), "T"; break
            if np.isnan(pnl):
                pnl = (c[min(k + MAX_HOLD, n) - 1] - entry) * direction
            rows.append({"direction": "LONG" if direction == 1 else "SHORT",
                         "pnl": pnl, "r": pnl / risk, "result": res})
            break

    r = pd.DataFrame(rows)
    if r.empty:
        print("koi signal nahi"); return
    print("BODY LEVELS + LIQUIDITY GRAB on Nifty 5m (5 yrs)\n")
    print(f"{'Setup':14s} {'n':>5s} {'Win%':>6s} {'AvgR':>7s} {'T%':>5s} {'SL%':>6s}")
    for name, sub in [("LONG", r[r.direction == "LONG"]),
                      ("SHORT", r[r.direction == "SHORT"]), ("ALL", r)]:
        if sub.empty: continue
        print(f"{name:14s} {len(sub):5d} {(sub.pnl>0).mean()*100:6.1f} "
              f"{sub.r.mean():+7.3f} {(sub.result=='T').mean()*100:5.1f} "
              f"{(sub.result=='SL').mean()*100:6.1f}")


if __name__ == "__main__":
    main()
