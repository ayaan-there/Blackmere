"""Backtest of the USER's exact pivot + 3-candle strategy.

Rules (as described):
  - Pivot levels P/S1/S2/R1/R2 from the previous day (standard pivots).
  - Price crosses a level, then prints 3 consecutive GREEN candles -> BUY ITM CE.
  - Target = next level above the entry, a few points below it.
  - Mirror for PUT.
  - SL is not specified by the user; two variants are tested:
      (a) low/high of the 3 confirmation candles +/- buffer
      (b) the crossed pivot level itself
  - Square off same day. Index move is used; option premium ≈ delta x index move.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

import data_loader

BUFFER = 5.0          # "thoda kuch points neeche/upar"
MAX_HOLD = 30         # 5-min bars (~2.5 hours)
CONFIRM = 3


@dataclass
class Trade:
    side: str
    entry: float
    sl: float
    target: float
    exit: float
    result: str
    bars: int
    r: float
    t: object


def pivots(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["day"] = df["timestamp"].dt.date
    g = df.groupby("day")
    daily = pd.DataFrame({"H": g["high"].max(), "L": g["low"].min(),
                          "C": g["close"].last()})
    p = (daily["H"] + daily["L"] + daily["C"]) / 3
    daily["P"] = p
    daily["R1"] = 2 * p - daily["L"]
    daily["S1"] = 2 * p - daily["H"]
    daily["R2"] = p + (daily["H"] - daily["L"])
    daily["S2"] = p - (daily["H"] - daily["L"])
    prev = daily.shift(1)
    for k in ("P", "R1", "S1", "R2", "S2"):
        df[k] = df["day"].map(prev[k])
    return df


def run(df: pd.DataFrame, sl_mode: str = "candles") -> list[Trade]:
    df = pivots(df).reset_index(drop=True)
    c, o, h, l = (df[k].to_numpy() for k in ("close", "open", "high", "low"))
    days = df["day"].to_numpy()
    levels = df[["S2", "S1", "P", "R1", "R2"]].to_numpy()
    n = len(df)
    trades: list[Trade] = []
    i = 0
    while i < n - CONFIRM - 1:
        lv = levels[i]
        if np.isnan(lv).any():
            i += 1
            continue
        # cross up / cross down on close
        crossed = None
        direction = 0
        for L in lv:
            if c[i - 1] <= L < c[i]:
                crossed, direction = L, 1
            elif c[i - 1] >= L > c[i]:
                crossed, direction = L, -1
        if direction == 0:
            i += 1
            continue

        greens = all(c[i + k] > o[i + k] for k in range(1, CONFIRM + 1))
        reds = all(c[i + k] < o[i + k] for k in range(1, CONFIRM + 1))
        if direction == 1 and not greens:
            i += 1
            continue
        if direction == -1 and not reds:
            i += 1
            continue

        e = i + CONFIRM
        entry = c[e]
        conf_low = min(l[i + k] for k in range(1, CONFIRM + 1))
        conf_high = max(h[i + k] for k in range(1, CONFIRM + 1))
        if direction == 1:
            above = sorted(x for x in lv if x > entry + BUFFER)
            if not above:
                i = e + 1
                continue
            target = above[0] - BUFFER
            sl = (conf_low - BUFFER) if sl_mode == "candles" else (crossed - BUFFER)
            if sl >= entry or target <= entry:
                i = e + 1
                continue
        else:
            below = sorted((x for x in lv if x < entry - BUFFER), reverse=True)
            if not below:
                i = e + 1
                continue
            target = below[0] + BUFFER
            sl = (conf_high + BUFFER) if sl_mode == "candles" else (crossed + BUFFER)
            if sl <= entry or target >= entry:
                i = e + 1
                continue

        outcome, exitp, bars = "OPEN", entry, 0
        risk = abs(entry - sl)
        for j in range(e, min(e + MAX_HOLD, n)):
            if days[j] != days[e]:
                break
            if direction == 1:
                if l[j] <= sl:
                    outcome, exitp, bars = "SL", sl, j - e
                    break
                if h[j] >= target:
                    outcome, exitp, bars = "TARGET", target, j - e
                    break
            else:
                if h[j] >= sl:
                    outcome, exitp, bars = "SL", sl, j - e
                    break
                if l[j] <= target:
                    outcome, exitp, bars = "TARGET", target, j - e
                    break
            bars = j - e
        if outcome == "OPEN":
            exitp, outcome = c[min(e + MAX_HOLD, n) - 1], "TIME"
        r = ((exitp - entry) / risk) * direction
        trades.append(Trade("CE" if direction == 1 else "PE", entry, sl, target,
                            exitp, outcome, bars, r, df["timestamp"].iloc[e]))
        i = e + bars + 1
    return trades


def report(trades: list[Trade], label: str):
    if not trades:
        print(f"{label}: koi trade nahi")
        return
    cut = pd.Timestamp(trades[-1].t).date()
    # time split by index of timestamp
    ordered = sorted(trades, key=lambda x: x.t)
    mid = int(len(ordered) * 0.7)
    for name, sel in (("ALL", ordered), ("TRAIN", ordered[:mid]),
                      ("TEST", ordered[mid:])):
        if not sel:
            continue
        wins = [t for t in sel if t.r > 0]
        gp = sum(t.r for t in wins)
        gl = -sum(t.r for t in sel if t.r <= 0)
        print(f"{label:22s} {name:5s} n={len(sel):4d} win={len(wins)/len(sel)*100:5.1f}% "
              f"avgR={np.mean([t.r for t in sel]):+.2f} PF={gp/gl if gl else np.inf:.2f} "
              f"target={sum(t.result=='TARGET' for t in sel)/len(sel)*100:4.1f}% "
              f"sl={sum(t.result=='SL' for t in sel)/len(sel)*100:4.1f}%")


if __name__ == "__main__":
    data = data_loader.load_data(last_days=10 ** 6, minutes=5)
    print(f"bars={len(data)}, {data.timestamp.iloc[0].date()} -> {data.timestamp.iloc[-1].date()}")
    for mode in ("candles", "pivot"):
        report(run(data, mode), f"SL={mode}")
