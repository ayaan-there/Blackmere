"""Walk-forward base rates on the user's OWN parquet data.

Honest purpose: answer "how sure are you?" with observed frequencies, not
opinions. These are in-sample historical frequencies, NOT a forecast.
No costs/slippage, overlapping 5/15-bar windows, and regime changes apply.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import config
import data_loader
import engine

REPORT = Path(__file__).resolve().parent / "data" / "backtest_report.json"


def _rate(mask: pd.Series, fwd: pd.Series, threshold: float = 0.10) -> dict:
    """% of signals where forward move > +threshold% (or < -threshold%)."""
    sel = fwd[mask.fillna(False).values]
    if len(sel) == 0:
        return {"n": 0, "hit_pct": None, "mean_pct": None}
    return {
        "n": int(len(sel)),
        "hit_pct": round(float((sel > threshold).mean() * 100), 1),
        "mean_pct": round(float(sel.mean()), 3),
    }


def run(days: int = 300, step: int = 3) -> dict:
    df = data_loader.load_data(last_days=days, minutes=5)
    if len(df) < 200:
        raise ValueError("Backtest ke liye kam data hai.")
    df = engine.add_indicators(df)
    close = df["close"].to_numpy()
    n = len(df)
    lookback = max(1, 375 // config.TIMEFRAME_MINUTES)

    rows = []
    for i in range(lookback, n - 16, step):
        sub = df.iloc[i - lookback + 1: i + 1]
        mp = engine.market_profile(sub, config.TICK_SIZE)
        score, bias, conf, _ = engine.compute_bias(sub, mp)
        rows.append({
            "score": score, "bias": bias, "conf": conf,
            "pattern": df["pattern"].iloc[i],
            "f5": (close[i + 5] / close[i] - 1) * 100,
            "f15": (close[i + 15] / close[i] - 1) * 100,
        })

    r = pd.DataFrame(rows)
    bull = r["bias"] == "BULLISH"
    bear = r["bias"] == "BEARISH"
    high = r["conf"] == "HIGH"

    out = {
        "meta": {
            "bars": n, "signals_sampled": len(r),
            "days_loaded": days, "step": step,
            "bar_minutes": config.TIMEFRAME_MINUTES,
            "threshold_pct": 0.10,
            "note": "in-sample observed frequencies; costs/slippage excluded; "
                    "overlapping forward windows. Not a forecast.",
        },
        "bias": {
            "BULLISH": {"n": int(bull.sum()),
                        "up_5": _rate(bull, r["f5"]),
                        "up_15": _rate(bull, r["f15"])},
            "BEARISH": {"n": int(bear.sum()),
                        "down_5": _rate(bear, -r["f5"]),
                        "down_15": _rate(bear, -r["f15"])},
            "NEUTRAL": {"n": int((r["bias"] == "NEUTRAL").sum())},
        },
        "high_confidence": {
            "BULLISH": _rate(bull & high, r["f5"]),
            "BULLISH_15": _rate(bull & high, r["f15"]),
            "BEARISH": _rate(bear & high, -r["f5"]),
            "BEARISH_15": _rate(bear & high, -r["f15"]),
        },
        "patterns": {},
        "pattern_plus_bias": {},
    }

    for pat in ["BULL MARUBOZU", "BULL ENGULFING", "HAMMER",
                "DOJI", "SPINNING TOP", "BEAR MARUBOZU",
                "BEAR ENGULFING", "SHOOTING STAR", "INSIDE BAR", "NORMAL"]:
        m = r["pattern"] == pat
        if m.sum() >= 10:
            out["patterns"][pat] = {
                "n": int(m.sum()),
                "up_5": _rate(m, r["f5"]),
                "down_5": _rate(m, -r["f5"]),
                "up_15": _rate(m, r["f15"]),
            }
    for pat, bs in [("BULL MARUBOZU", bull), ("BULL ENGULFING", bull),
                    ("HAMMER", bull), ("BEAR MARUBOZU", bear),
                    ("BEAR ENGULFING", bear), ("SHOOTING STAR", bear)]:
        m = (r["pattern"] == pat) & bs
        if m.sum() >= 10:
            out["pattern_plus_bias"][f"{pat} + {('BULLISH' if bs.equals(bull) else 'BEARISH')}"] = {
                "n": int(m.sum()),
                "hit_5": _rate(m, r["f5"] if bs.equals(bull) else -r["f5"]),
            }

    REPORT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def _fmt(d: dict) -> str:
    if not d or d.get("n", 0) == 0:
        return "n/a"
    return f"n={d['n']}, hit={d.get('hit_pct', d.get('up_5', {}).get('hit_pct'))}%, mean={d.get('mean_pct')}%"


if __name__ == "__main__":
    res = run()
    print("=== BIAS BASE RATES (threshold +0.10% in 5/15 bars) ===")
    for k, v in res["bias"].items():
        print(k, v)
    print("\n=== HIGH-CONFIDENCE ===")
    for k, v in res["high_confidence"].items():
        print(k, v)
    print("\n=== CANDLE PATTERNS ===")
    for k, v in res["patterns"].items():
        print(k, v)
    print(f"\nreport -> {REPORT}")
