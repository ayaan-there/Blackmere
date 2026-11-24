"""Price-action engine.

Methodologies implemented (all from the books in ./books, general concepts only):
  - Al Brooks, "Reading Price Charts Bar by Bar" -> trend bars / trading range /
    breakout / higher-highs-higher-lows classification.
  - James Dalton, "Mind Over Markets" -> Market Profile POC / VAH / VAL.
  - Thomas Bulkowski, "Encyclopedia of Chart Patterns" -> swing highs/lows as
    pattern-based support & resistance.
  - Robert Miner, "High Probability Trading Strategies" -> multi-signal
    confluence scoring instead of a single indicator.

Output is a SCENARIO PLAN (IF -> THEN), never a guaranteed direction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd

import config


# --------------------------------------------------------------- utilities
def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price(S: float, K: float, T: float, sigma: float,
             r: float = 0.07, kind: str = "CE") -> float:
    """Black-Scholes premium. sigma = annualised realised vol from the data."""
    T = max(T, 0.5 / 365)
    sigma = float(np.clip(sigma, 0.08, 0.90))
    S, K = max(S, 1.0), max(K, 1.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if kind.upper() == "CE":
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def realised_vol(close: pd.Series, timeframe_minutes: int, window: int = 60) -> float:
    ret = np.log(close / close.shift(1)).replace([np.inf, -np.inf], np.nan).dropna()
    if len(ret) < 5:
        return 0.15
    bars_per_year = 252 * max(1, 375 // max(timeframe_minutes, 1))
    return float(ret.tail(window).std() * math.sqrt(bars_per_year))


# -------------------------------------------------------------- indicators
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    c, h, l, o = df["close"], df["high"], df["low"], df["open"]
    v = df["volume"].fillna(0)

    df["ema9"] = c.ewm(span=9, adjust=False).mean()
    df["ema21"] = c.ewm(span=21, adjust=False).mean()

    tp = (h + l + c) / 3
    day = df["timestamp"].dt.date
    cum_tpvol = (tp * v).groupby(day).cumsum()
    cum_vol = v.groupby(day).cumsum().replace(0, np.nan)
    df["vwap"] = cum_tpvol / cum_vol

    prev = c.shift(1)
    tr = pd.concat([(h - l), (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()

    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi"] = (100 - 100 / (1 + rs)).fillna(50)

    df["swing_hi"] = h.rolling(20, min_periods=1).max().shift(1).fillna(h)
    df["swing_lo"] = l.rolling(20, min_periods=1).min().shift(1).fillna(l)

    rng = (h - l).replace(0, np.nan)
    body = (c - o).abs()
    df["bar"] = np.where(body / rng > 0.6,
                         np.where(c > o, "BULL", "BEAR"), "DOJI")

    # ---- Candle patterns (classic definitions; Bulkowski / candlestick canon)
    prev_c, prev_o = c.shift(1), o.shift(1)
    hi_body = pd.concat([o, c], axis=1).max(axis=1)
    lo_body = pd.concat([o, c], axis=1).min(axis=1)
    upper, lower = h - hi_body, lo_body - l
    bull_bar, bear_bar = c > o, c < o

    pattern = pd.Series("NORMAL", index=df.index)
    pattern[body <= 0.10 * rng] = "DOJI"
    pattern[(body >= 0.90 * rng) & bull_bar] = "BULL MARUBOZU"
    pattern[(body >= 0.90 * rng) & bear_bar] = "BEAR MARUBOZU"
    pattern[(bear_bar.shift(1) & bull_bar & (c > prev_o) & (o < prev_c))
            .fillna(False)] = "BULL ENGULFING"
    pattern[(bull_bar.shift(1) & bear_bar & (o > prev_c) & (c < prev_o))
            .fillna(False)] = "BEAR ENGULFING"
    pattern[((body > 0) & (lower >= 2 * body) & (upper <= 0.3 * body))
            .fillna(False)] = "HAMMER"
    pattern[((body > 0) & (upper >= 2 * body) & (lower <= 0.3 * body))
            .fillna(False)] = "SHOOTING STAR"
    pattern[((h < h.shift(1)) & (l > l.shift(1))).fillna(False)] = "INSIDE BAR"
    pattern[((body > 0.1 * rng) & (body <= 0.4 * rng))
            .fillna(False)] = "SPINNING TOP"
    df["pattern"] = pattern
    return df


def market_profile(df: pd.DataFrame, tick: float | None = None) -> dict:
    """Dalton-style POC / VAH / VAL from the most recent session's volume."""
    tick = tick or config.TICK_SIZE
    bars_per_day = max(1, 375 // max(config.TIMEFRAME_MINUTES, 1))
    session = df.tail(min(bars_per_day, len(df)))
    if session.empty:
        return {"poc": float(df["close"].iloc[-1]),
                "vah": float(df["close"].iloc[-1]),
                "val": float(df["close"].iloc[-1])}

    buckets = (session["close"] / tick).round() * tick
    vol = session.groupby(buckets)["volume"].sum().sort_values(ascending=False)
    if vol.empty:
        p = float(session["close"].iloc[-1])
        return {"poc": p, "vah": p, "val": p}

    poc = float(vol.index[0])
    total = float(vol.sum()) or 1.0
    chosen, acc = [poc], float(vol.iloc[0])
    for price, qty in vol.iloc[1:].items():
        if acc >= 0.70 * total:
            break
        chosen.append(float(price))
        acc += float(qty)
    return {"poc": poc, "vah": max(chosen), "val": min(chosen)}


# ------------------------------------------------------------- data models
@dataclass
class Scenario:
    side: str                       # CE / PE
    action: str = "BUY"
    strike: int = 0
    option: str = ""
    expiry: str = ""
    trigger: float = 0.0            # SPOT level that activates the scenario
    status: str = ""
    entry: float = 0.0              # premium
    sl: float = 0.0
    target: float = 0.0
    rr: float = 2.0
    premium_source: str = ""
    note: str = ""

    @property
    def risk(self) -> float:
        return round(self.entry - self.sl, 2)

    @property
    def reward(self) -> float:
        return round(self.target - self.entry, 2)


@dataclass
class Plan:
    spot: float
    date: str
    bias: str
    score: int
    confidence: str
    reasons: list = field(default_factory=list)
    support: float = 0.0
    resistance: float = 0.0
    vwap: float = 0.0
    vah: float = 0.0
    val: float = 0.0
    poc: float = 0.0
    atr5: float = 0.0
    vol: float = 0.0
    expiry: str = ""
    days: float = 0.0
    proj5: tuple = (0.0, 0.0)
    proj15: tuple = (0.0, 0.0)
    pattern: str = ""
    recent_patterns: list = field(default_factory=list)
    watch_patterns: list = field(default_factory=list)
    bull: Optional[Scenario] = None
    bear: Optional[Scenario] = None


# ------------------------------------------------------------------- bias
def compute_bias(df: pd.DataFrame, mp: dict) -> tuple:
    """Weighted confluence score. 50 = neutral, >57 bullish, <43 bearish."""
    last, prev = df.iloc[-1], df.iloc[-2] if len(df) > 1 else df.iloc[-1]
    score, why = 50, []

    def add(points: int, text: str):
        nonlocal score
        score += points
        why.append(f"{'+' if points > 0 else ''}{points}  {text}")

    if last["ema9"] > last["ema21"]:
        add(12, "EMA9 > EMA21 (short-term trend up)")
    else:
        add(-12, "EMA9 < EMA21 (short-term trend down)")

    if last["close"] > last["vwap"]:
        add(12, "Price above VWAP (buyers in control)")
    else:
        add(-12, "Price below VWAP (sellers in control)")

    if last["close"] > last["swing_hi"]:
        add(18, "Breakout above prior 20-bar high (Brooks)")
    elif last["close"] < last["swing_lo"]:
        add(-18, "Breakdown below prior 20-bar low (Brooks)")

    if last["close"] > mp["vah"]:
        add(10, "Above Value Area High (Dalton)")
    elif last["close"] < mp["val"]:
        add(-10, "Below Value Area Low (Dalton)")

    if last["bar"] == "BULL":
        add(8, "Last bar = bull trend bar")
    elif last["bar"] == "BEAR":
        add(-8, "Last bar = bear trend bar")

    if last["rsi"] > 55:
        add(8, "RSI > 55 (momentum positive)")
    elif last["rsi"] < 45:
        add(-8, "RSI < 45 (momentum negative)")

    tail = df.tail(6)
    if tail["high"].is_monotonic_increasing and tail["low"].is_monotonic_increasing:
        add(7, "Higher highs + higher lows (HH/HL structure)")
    elif tail["high"].is_monotonic_decreasing and tail["low"].is_monotonic_decreasing:
        add(-7, "Lower highs + lower lows (LH/LL structure)")

    score = int(np.clip(score, 0, 100))
    bias = "BULLISH" if score >= 57 else "BEARISH" if score <= 43 else "NEUTRAL"
    swing = abs(score - 50)
    conf = "HIGH" if swing > 20 else "MEDIUM" if swing >= 8 else "LOW"
    return score, bias, conf, why


# ------------------------------------------------------------ main builder
def build_plan(df: pd.DataFrame, premium_lookup: dict | None = None) -> Plan:
    """premium_lookup: {(strike, 'CE'|'PE'): premium} from a live option chain."""
    if df.empty or len(df) < 20:
        raise ValueError("Kam se kam 20 candles chahiye (20-bar swing levels ke liye).")

    df = add_indicators(df)
    mp = market_profile(df)
    last = df.iloc[-1]
    spot = float(last["close"])
    score, bias, conf, reasons = compute_bias(df, mp)

    atr5 = float(last["atr"]) * math.sqrt(max(config.TIMEFRAME_MINUTES, 1) / 5)
    sigma = realised_vol(df["close"], config.TIMEFRAME_MINUTES)
    expiry, days = config.days_to_expiry()
    T = days / 365

    step = config.STRIKE_STEP
    atm = int(round(spot / step) * step)
    risk = float(config.DEFAULT_RISK_RS)

    resistance = float(max(last["swing_hi"], mp["vah"]))
    support = float(min(last["swing_lo"], mp["val"]))

    def premium(kind: str) -> tuple:
        key = (atm, kind)
        if premium_lookup and key in premium_lookup:
            return float(premium_lookup[key]), "live option chain"
        return round(max(bs_price(spot, atm, T, sigma, kind=kind),
                         config.MIN_PREMIUM), 2), "BS estimate (realised vol)"

    ce_entry, ce_src = premium("CE")
    pe_entry, pe_src = premium("PE")

    bull = Scenario(
        side="CE", strike=atm,
        option=f"{config.SYMBOL} {atm} CE", expiry=str(expiry),
        trigger=round(resistance, 2),
        status="ACTIVE NOW ✅" if spot >= resistance
               else f"WAIT — spot must cross {resistance:.2f}",
        entry=ce_entry,
        sl=round(max(config.MIN_PREMIUM, ce_entry - risk), 2),
        target=round(ce_entry + config.RISK_REWARD * risk, 2),
        rr=config.RISK_REWARD, premium_source=ce_src,
        note="Bullish confluence: breakout above resistance/VAH. Trend bar + price>VWAP.",
    )
    bear = Scenario(
        side="PE", strike=atm,
        option=f"{config.SYMBOL} {atm} PE", expiry=str(expiry),
        trigger=round(support, 2),
        status="ACTIVE NOW ✅" if spot <= support
               else f"WAIT — spot must break {support:.2f}",
        entry=pe_entry,
        sl=round(max(config.MIN_PREMIUM, pe_entry - risk), 2),
        target=round(pe_entry + config.RISK_REWARD * risk, 2),
        rr=config.RISK_REWARD, premium_source=pe_src,
        note="Bearish confluence: breakdown below support/VAL. Bear bar + price<VWAP.",
    )

    proj5 = round(atr5 * 0.8, 2)
    proj15 = round(atr5 * math.sqrt(3) * 0.8, 2)

    if bias == "BULLISH":
        watch = [
            {"pattern": "BULL MARUBOZU / BULL ENGULFING / HAMMER",
             "at": f"cross {resistance:.2f}",
             "means": "CE scenario CONFIRM — entry plan active"},
            {"pattern": "DOJI / SPINNING TOP",
             "at": f"right at {resistance:.2f}",
             "means": "indecision — next candle close tak wait karein"},
        ]
    elif bias == "BEARISH":
        watch = [
            {"pattern": "BEAR MARUBOZU / BEAR ENGULFING / SHOOTING STAR",
             "at": f"break {support:.2f}",
             "means": "PE scenario CONFIRM — entry plan active"},
            {"pattern": "DOJI / SPINNING TOP",
             "at": f"right at {support:.2f}",
             "means": "indecision — next candle close tak wait karein"},
        ]
    else:
        watch = [
            {"pattern": "Any MARUBOZU / ENGULFING",
             "at": f"{support:.2f} – {resistance:.2f} range se breakout",
             "means": "direction confirm hone par corresponding scenario"},
            {"pattern": "DOJI",
             "at": "range ke beech me",
             "means": "noise — koi trade nahi"},
        ]

    return Plan(
        spot=round(spot, 2), date=str(df["timestamp"].iloc[-1]),
        bias=bias, score=score, confidence=conf, reasons=reasons,
        support=round(support, 2), resistance=round(resistance, 2),
        vwap=round(float(last["vwap"]), 2),
        vah=round(mp["vah"], 2), val=round(mp["val"], 2),
        poc=round(mp["poc"], 2), atr5=round(atr5, 2), vol=round(sigma, 3),
        expiry=str(expiry), days=days,
        proj5=(round(spot - proj5, 2), round(spot + proj5, 2)),
        proj15=(round(spot - proj15, 2), round(spot + proj15, 2)),
        pattern=str(last["pattern"]),
        recent_patterns=list(df["pattern"].tail(6)[::-1]),
        watch_patterns=watch,
        bull=bull, bear=bear,
    )


def premium_from_spot(entry_premium: float, entry_spot: float, spot: float,
                      strike: int, T: float, sigma: float, side: str) -> float:
    """Approximate current premium from spot move using Black-Scholes delta.
    Used only for the paper-trade alert tracker (not for order placement).
    """
    S = max(entry_spot, 1.0)
    sigma = float(np.clip(sigma, 0.08, 0.90))
    d1 = (math.log(S / max(strike, 1)) + (0.07 + 0.5 * sigma ** 2) * T) / (
        sigma * math.sqrt(max(T, 0.5 / 365))
    )
    delta = _norm_cdf(d1) if side == "CE" else _norm_cdf(d1) - 1
    est = entry_premium + delta * (spot - entry_spot)
    return round(max(est, config.MIN_PREMIUM), 2)
