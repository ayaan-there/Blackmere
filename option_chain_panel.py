"""Option-chain snapshot + example trade helper for the dashboard."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

RECORDED = Path(r"D:\PROJECTS\active\personal\Trading-Assistant\data\recorded")


def load_chain(day: str = "20261121") -> tuple:
    """Return (chain_df, spot, last_ts) from recorded option ticks + index LTP."""
    idx = pd.read_parquet(RECORDED / "nifty50_index" / f"{day}.parquet")
    idx["ts"] = pd.to_datetime(idx["ts"]).dt.tz_localize(None)
    spot = float(idx["price"].dropna().iloc[-1])
    last_ts = idx["ts"].iloc[-1]

    rows = []
    for p in RECORDED.glob(f"NIFTY*/*.parquet"):
        if p.stem != day:
            continue
        m = re.match(r"NIFTY.*?(\d{5})(CE|PE)$", p.parent.name)
        if not m:
            continue
        K, side = int(m.group(1)), m.group(2)
        t = pd.read_parquet(p, columns=["ts", "price", "oi", "iv", "delta"])
        t["ts"] = pd.to_datetime(t["ts"]).dt.tz_localize(None)
        if t.empty:
            continue
        rows.append({"strike": K, "side": side, "ltp": round(float(t.price.iloc[-1]), 2),
                     "oi": int(t.oi.iloc[-1]) if pd.notna(t.oi.iloc[-1]) else 0,
                     "iv": round(float(t.iv.iloc[-1]), 1) if pd.notna(t.iv.iloc[-1]) else None,
                     "delta": round(float(t.delta.iloc[-1]), 2) if pd.notna(t.delta.iloc[-1]) else None})
    df = pd.DataFrame(rows)
    return df, spot, last_ts


def atm_legs(chain: pd.DataFrame, spot: float, risk: int = 20):
    """Pick ATM CE & PE with real LTP, compute SL/Target — the example trade."""
    strikes = sorted(chain.strike.unique())
    atm = min(strikes, key=lambda k: abs(k - spot))
    out = []
    for side in ("CE", "PE"):
        row = chain[(chain.strike == atm) & (chain.side == side)]
        if row.empty:
            continue
        ltp = float(row.ltp.iloc[0])
        sl = max(1.0, ltp - risk)
        tgt = ltp + 2 * risk
        out.append({"side": side, "strike": atm, "ltp": ltp,
                    "sl": round(sl, 2), "target": round(tgt, 2),
                    "risk": risk, "reward": 2 * risk})
    return atm, out
