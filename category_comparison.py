"""Synthesis: all prior Nifty backtests bucketed into the video's 5 categories.

Numbers are the observed win% from our 29 backtests (5y Nifty data). Categories:
 order flow = not testable (no delta/footprint/book data).
"""

# (strategy, category, win%, expectancy note)
DATA = [
 ("Liquidity Refill C1+C2", "price action", 68.5, "+2.2R"),
 ("Ben Vault Break", "price action", 67.8, "+4pts"),
 ("VWAP + Structure Pullback", "price action", 66.1, "+0.86R"),
 ("VWAP first-touch", "price action", 79.9, "tight-stop artifact"),
 ("Conti VWAP drift", "price action", 62.8, "neg R:R"),
 ("Body + Liquidity Grab", "price action", 56.4, "+0.14R"),
 ("OTF regime filter", "trend following", 57.0, "+5d swing"),
 ("Hurst+AC breakout LONG", "trend following", 57.0, "+0.12R"),
 ("Value migration 1R", "trend following", 51.8, "+0.1R"),
 ("Pietro trend continuation", "trend following", 51.0, "+0.28R"),
 ("Pivot + 3 green", "breakout", 43.1, "+3.9 premium"),
 ("NR4 compression 60m", "breakout", 40.8, "+0.23R"),
 ("VAH/VAL breakout", "breakout", 41.1, "+0.09R"),
 ("5-bar breakout", "breakout", 38.0, "~0"),
 ("Opening impulse", "breakout", 30.7, "neg"),
 ("CRT 3-candle", "reversal", 19.7, "neg"),
 ("OB sweep retest", "reversal", 33.9, "neg"),
 ("Forced participation", "reversal", 30.8, "neg"),
 ("3-touch range", "reversal", 35.2, "neg"),
 ("Look Fail final target", "reversal", 16.4, "neg"),
 ("VWAP 2SD fade", "reversal", 25.6, "neg"),
 ("Liquidity sweep+EMA", "reversal", 23.9, "neg"),
 ("Gold reopen analogue", "reversal", 30.7, "neg"),
]

from collections import defaultdict
import statistics as st

def main():
    by = defaultdict(list)
    for name, cat, win, exp in DATA:
        by[cat].append((name, win, exp))
    print("VIDEO RANK vs OUR NIFTY RESULTS (29 backtests, 5y)\n")
    print(f"{'Category':18s} {'video#':6s} {'tests':5s} {'avg win%':8s} {'best strategy'}")
    order = ["order flow","price action","trend following","breakout","reversal"]
    for rank, cat in enumerate(order, 1):
        arr = by.get(cat, [])
        if not arr:
            print(f"{cat:18s} #{rank:<5d} {'0':5s} {'N/A':8s} (no data - needs delta/footprint)")
            continue
        wins = [w for _,w,_ in arr]
        best = max(arr, key=lambda x:x[1])
        print(f"{cat:18s} #{rank:<5d} {len(arr):5d} {st.mean(wins):8.1f} {best[0]} ({best[1]:.1f}%)")

if __name__ == "__main__":
    main()
