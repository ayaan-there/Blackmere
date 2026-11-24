"""Quantitative market-structure engine (pure, deterministic, auditable).

Classifies price/OI behaviour from real observations only. No intuition, no
probabilities, no trade instructions. All thresholds live in config.py.
"""
from __future__ import annotations

import math
import statistics
from collections import Counter

import config

STATES = ("LONG BUILDUP", "SHORT BUILDUP", "LONG UNWINDING", "SHORT COVERING")
NEUTRAL = "NEUTRAL / MIXED"


def _num(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except Exception:
        return None


def classify(price_prev, price_curr, oi_prev, oi_curr, ts=None, tf=None) -> dict:
    p0, p1, o0, o1 = map(_num, (price_prev, price_curr, oi_prev, oi_curr))
    out = {
        "observed": {"price_prev": p0, "price_current": p1,
                     "oi_prev": o0, "oi_current": o1, "timestamp": ts, "timeframe": tf},
        "data_quality": "OK", "state": None,
        "price_change_pct": None, "oi_change_pct": None,
        "abs_price_change": None, "abs_oi_change": None,
    }
    if None in (p0, p1, o0, o1) or p0 <= 0 or o0 <= 0:
        out["data_quality"] = "INSUFFICIENT"
        out["state"] = NEUTRAL
        return out
    if ts is None or tf is None:
        out["data_quality"] = "MISMATCH"

    dp = p1 - p0
    do = o1 - o0
    pp = dp / p0 * 100.0
    op = do / o0 * 100.0
    out.update(abs_price_change=dp, abs_oi_change=do,
               price_change_pct=pp, oi_change_pct=op)
    pt = config.PRICE_THRESHOLD_PCT
    ot = config.OI_THRESHOLD_PCT
    if pp > pt and op > ot:
        out["state"] = "LONG BUILDUP"
    elif pp < -pt and op > ot:
        out["state"] = "SHORT BUILDUP"
    elif pp < -pt and op < -ot:
        out["state"] = "LONG UNWINDING"
    elif pp > pt and op < -ot:
        out["state"] = "SHORT COVERING"
    else:
        out["state"] = NEUTRAL
    return out


def _series(observations: list) -> list:
    out = []
    for x in observations:
        r = classify(x.get("price_prev"), x.get("price"),
                     x.get("oi_prev"), x.get("oi"), x.get("ts"), x.get("tf"))
        if r["price_change_pct"] is not None:
            out.append(r)
    return out


def _strength(series: list) -> dict:
    if len(series) < 5:
        return {"score": None, "trend": "insufficient", "z_price": None, "z_oi": None,
                "persistence": None, "consistency": None}
    window = series[-config.STRENGTH_LOOKBACK:]
    pp = [x["price_change_pct"] for x in window]
    op = [x["oi_change_pct"] for x in window]
    sp = statistics.pstdev(pp) if len(pp) > 1 else 0.0
    so = statistics.pstdev(op) if len(op) > 1 else 0.0
    eps = 1e-9
    zp = series[-1]["price_change_pct"] / max(sp, eps)
    zo = series[-1]["oi_change_pct"] / max(so, eps)
    magnitude = math.sqrt((zp * zp + zo * zo) / 2)
    k = config.PERSISTENCE_K
    recent = series[-k:]
    same = sum(1 for x in recent if x["state"] == series[-1]["state"])
    persistence = same / len(recent)
    consistent = sum(1 for x in recent if x["state"] == series[-1]["state"]
                     and math.copysign(1, x["price_change_pct"]) == math.copysign(1, zp)
                     and math.copysign(1, x["oi_change_pct"]) == math.copysign(1, zo))
    consistency = consistent / len(recent)
    raw = magnitude * (0.5 + 0.5 * persistence) * (0.5 + 0.5 * consistency)
    score = 100.0 * math.tanh(raw / 3.0)
    prior = series[-6:-1]
    trend = "stable"
    if prior:
        avg = sum(x.get("_strength", score) for x in prior) / len(prior)
        if score - avg > 5:
            trend = "increasing"
        elif avg - score > 5:
            trend = "decreasing"
    return {"score": round(score, 2), "trend": trend,
            "z_price": round(zp, 3), "z_oi": round(zo, 3),
            "persistence": round(persistence, 3), "consistency": round(consistency, 3)}


def analyze(observations: list, tf: str = "30s") -> dict:
    """observations: [{ts, price, oi, price_prev, oi_prev, tf?}] chronological."""
    series = _series([dict(x, tf=x.get("tf") or tf) for x in observations])
    if not series:
        return {"data_quality": "INSUFFICIENT", "state": NEUTRAL,
                "interpretation": "No real price/OI observations available.",
                "uncertainty": "No classification performed."}
    current = series[-1]
    window = series[-config.STRUCTURE_WINDOW:]
    counts = Counter(x["state"] for x in window)
    total = len(window)
    distribution = {k: round(v / total * 100, 1) for k, v in counts.items()}
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    dominant = ranked[0][0] if ranked[0][1] / total >= config.DOMINANT_MIN_SHARE else "MIXED"
    persistence = 0
    for x in reversed(window):
        if x["state"] != current["state"]:
            break
        persistence += 1
    transitions = Counter()
    for a, b in zip(window, window[1:]):
        if a["state"] != b["state"]:
            transitions[f"{a['state']} -> {b['state']}"] += 1

    strength = _strength(series)
    for i, x in enumerate(series):
        s = _strength(series[:i + 1])
        x["_strength"] = s.get("score") or 0
    strength = _strength(series)

    return {
        "data_quality": current["data_quality"],
        "current": current,
        "behaviour": {
            "dominant_state": dominant,
            "distribution_pct": distribution,
            "persistence_observations": persistence,
            "transitions": dict(transitions),
            "strength_score": strength["score"],
            "strength_scale": "0-100 dimensionless heuristic, not a probability",
            "strength_trend": strength["trend"],
            "z_price": strength["z_price"], "z_oi": strength["z_oi"],
            "persistence_ratio": strength["persistence"],
            "consistency_ratio": strength["consistency"],
        },
        "interpretation": (
            f"Latest real price change {current['price_change_pct']:+.3f}% and OI change "
            f"{current['oi_change_pct']:+.3f}% classify as {current['state']}. "
            f"Over the last {total} observations the dominant state is {dominant}."
        ),
        "uncertainty": (
            "Classification reflects observed price and OI changes only. It does not "
            "predict direction, and a BUY/SELL instruction is never derived from it."
        ),
    }


def multi_timeframe(observations: list) -> dict:
    """Resample real observations; never mix intervals in one calculation."""
    out = {}
    for tf in (1, 5, 15, 30, 60):
        buckets = {}
        for x in observations:
            ts = str(x.get("ts", ""))
            if len(ts) < 16:
                continue
            hh, mm = int(ts[11:13]), int(ts[14:16])
            key = (hh * 60 + mm) // tf * tf
            buckets[key] = x
        seq = [buckets[k] for k in sorted(buckets)]
        out[f"{tf}m"] = analyze(seq, tf=f"{tf}m")
    out["1s"] = {"data_quality": "INSUFFICIENT_OI_RESOLUTION", "state": NEUTRAL,
                 "interpretation": "OI is sampled every 30s; a 1s price/OI pair does not exist.",
                 "uncertainty": "No 1s classification performed."}
    states = [v.get("state") for k, v in out.items() if k != "1s" and v.get("state")]
    tally = Counter(states)
    out["summary"] = {
        "agreement_pct": round(max(tally.values()) / len(states) * 100, 1) if states else None,
        "states": dict(tally),
        "conflicts": sorted(set(states)) if len(set(states)) > 1 else [],
    }
    return out
