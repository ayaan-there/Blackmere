"""Backtest the pivot + 3-green-candle strategy on REAL recorded option-chain ticks.

Source: D:\\PROJECTS\\active\\personal\\Trading-Assistant\\data\\recorded
  - per-strike tick parquet (price, bid, ask, oi, iv) for 2026-11-19
  - Nifty index 5-min bars come from our own raw parquet (same date + prev day for pivots)

Rules: pivot cross + 3 green candles -> buy ITM CE (3 red -> ITM PE).
       SL = entry premium - 20, Target = entry premium + 40. No trail, no early exit.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

import config
import data_loader
from no_target_trail_backtest import make_signals

RECORDED = Path(r"D:\PROJECTS\active\personal\Trading-Assistant\data\recorded")
CORE = Path(r"D:\PROJECTS\active\personal\Trading-Assistant\data\recorded_core_bars")
OUT = Path(__file__).resolve().parent / "data" / "option_chain_backtest.json"
DAY = "2026-11-19"
PIVOT_DAY = "2026-11-13"   # last available session before 19 Nov (data gap)


def load_index(day: str) -> pd.DataFrame:
    p = CORE / "nifty50_index" / f"{day.replace('-', '')}.parquet"
    if not p.exists():
        p = Path(config.RAW_DIR) / f"{day[:4]}" / f"{day.replace('-', '')}.parquet"
    if not p.exists():
        return pd.DataFrame()
    return data_loader.resample(data_loader._normalise(pd.read_parquet(p)), 5)


def load_options(day: str) -> dict:
    out = {}
    for p in RECORDED.glob(f"*/{day.replace('-', '')}.parquet"):
        m = re.match(r"NIFTY.*?(\d{5})(CE|PE)$", p.parent.name)
        if not m:
            continue
        strike, side = int(m.group(1)), m.group(2)
        t = pd.read_parquet(p, columns=["ts", "price", "bid", "ask", "oi", "iv"])
        t["ts"] = pd.to_datetime(t["ts"], utc=False).dt.tz_localize(None)
        t = t.set_index("ts").sort_index()
        agg = t.resample("5min", label="left", closed="left").agg(
            {"price": ["first", "max", "min", "last"],
             "bid": "mean", "ask": "mean", "oi": "last", "iv": "mean"})
        agg.columns = ["o", "h", "l", "c", "bid", "ask", "oi", "iv"]
        agg = agg.dropna(subset=["c"])
        out[(strike, side)] = agg
    return out


def run_oi_variant(idx: pd.DataFrame, opts: dict, strikes: list) -> tuple:
    """Support/resistance from live option-chain OI instead of stale pivots."""
    c, o = idx["close"].to_numpy(), idx["open"].to_numpy()
    sigs, levels_log = [], []
    for i in range(1, len(idx) - 4):
        if str(idx["timestamp"].iloc[i].date()) != DAY:
            continue
        t = idx["timestamp"].iloc[i].floor("5min")
        spot = c[i]
        put_oi = {K: float(opts[(K, "PE")].loc[t, "oi"])
                  for K in strikes if t in opts[(K, "PE")].index
                  and not pd.isna(opts[(K, "PE")].loc[t, "oi"])}
        call_oi = {K: float(opts[(K, "CE")].loc[t, "oi"])
                   for K in strikes if t in opts[(K, "CE")].index
                   and not pd.isna(opts[(K, "CE")].loc[t, "oi"])}
        if not put_oi or not call_oi:
            continue
        below = [K for K in put_oi if K < spot]
        above = [K for K in call_oi if K > spot]
        if not below or not above:
            continue
        sup = max(below, key=lambda K: put_oi[K])
        res = min(above, key=lambda K: call_oi[K])
        levels_log.append({"time": str(idx["timestamp"].iloc[i]), "support": sup,
                           "resistance": res, "spot": round(float(spot), 2)})
        direction = 0
        if c[i - 1] <= sup < c[i]:
            direction = 1
        elif c[i - 1] >= res > c[i]:
            direction = -1
        elif c[i] > res and c[i - 1] <= res:
            direction = 1
        elif c[i] < sup and c[i - 1] >= sup:
            direction = -1
        if not direction:
            continue
        ok = all((c[i + k] > o[i + k]) if direction == 1 else (c[i + k] < o[i + k])
                 for k in (1, 2, 3))
        if ok:
            sigs.append((i + 3, direction))
    return idx, sigs, levels_log


def execute_trades(df, sigs, opts, strikes):
    rows = []
    for e, direction in sigs:
        if str(df["timestamp"].iloc[e].date()) != DAY:
            continue
        spot = df["close"].iloc[e]
        if direction == 1:
            K = max((s for s in strikes if s <= spot), default=None)
        else:
            K = min((s for s in strikes if s >= spot), default=None)
        if K is None:
            continue
        side = "CE" if direction == 1 else "PE"
        bar = opts[(K, side)]
        t0 = df["timestamp"].iloc[e].floor("5min")
        if t0 not in bar.index or np.isnan(bar.loc[t0, "c"]):
            continue
        entry = float(bar.loc[t0, "c"])
        sl, target = entry - 20, entry + 40
        result, exitp = "TIME", entry
        for j in range(e + 1, min(e + 31, len(df))):
            tt = df["timestamp"].iloc[j].floor("5min")
            if tt not in bar.index:
                continue
            hi, lo = float(bar.loc[tt, "h"]), float(bar.loc[tt, "l"])
            if direction == 1:
                if lo <= sl:
                    result, exitp = "SL", sl
                    break
                if hi >= target:
                    result, exitp = "TARGET", target
                    break
            else:
                if hi >= sl:
                    result, exitp = "SL", sl
                    break
                if lo <= target:
                    result, exitp = "TARGET", target
                    break
        rows.append({"time": str(df["timestamp"].iloc[e]), "side": side,
                     "strike": K, "spot": round(float(spot), 2),
                     "entry": round(entry, 2), "sl": round(sl, 2),
                     "target": round(target, 2), "exit": round(exitp, 2),
                     "result": result, "pnl": round(exitp - entry, 2)})
    return rows


def stats(rows):
    r = pd.DataFrame(rows)
    wins = int((r.pnl > 0).sum()) if len(r) else 0
    return {
        "signals": len(r), "wins": wins,
        "win_pct": round(wins / len(r) * 100, 1) if len(r) else 0,
        "avg_pnl": round(float(r.pnl.mean()), 2) if len(r) else 0,
        "total_pnl": round(float(r.pnl.sum()), 2) if len(r) else 0,
        "target_hits": int((r.result == "TARGET").sum()) if len(r) else 0,
        "sl_hits": int((r.result == "SL").sum()) if len(r) else 0,
        "trades": rows,
    }


def main():
    idx = pd.concat([load_index(PIVOT_DAY), load_index(DAY)], ignore_index=True)
    if idx.empty:
        raise ValueError("Index parquet for pivot source / 19 Nov not found.")
    opts = load_options(DAY)
    if not opts:
        raise ValueError(f"No option parquet found in {RECORDED}")

    strikes = sorted({k[0] for k in opts})
    context = []

    df1, sigs1 = make_signals(idx, 3)
    pivot_stats = stats(execute_trades(df1, sigs1, opts, strikes))

    df2, sigs2, levels = run_oi_variant(idx, opts, strikes)
    oi_stats = stats(execute_trades(df2, sigs2, opts, strikes))

    # Chain context at 10:00 for the dashboard
    t_ref = pd.Timestamp(f"{DAY} 10:00")
    for (K, side), b in opts.items():
        if t_ref in b.index:
            context.append({"strike": K, "side": side,
                            "oi": int(b.loc[t_ref, "oi"] or 0),
                            "iv": None if pd.isna(b.loc[t_ref, "iv"]) else round(float(b.loc[t_ref, "iv"]), 2),
                            "price": round(float(b.loc[t_ref, "c"]), 2)})

    summary = {
        "day": DAY, "expiry": "01-DEC-2026",
        "pivot_source": f"{PIVOT_DAY} (last available session before 19 Nov; 18 Nov data missing)",
        "strikes": len(strikes), "option_files": len(opts),
        "pivot_variant": pivot_stats,
        "oi_levels_variant": oi_stats,
        "oi_levels_sample": levels[:12],
        "chain_10am": context,
    }
    OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items()
                      if k not in ("trades", "chain_10am")}, indent=2))
    print("pivot trades:", pivot_stats["trades"])
    print("oi-level trades:", oi_stats["trades"])


if __name__ == "__main__":
    main()
