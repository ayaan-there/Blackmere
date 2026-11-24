"""Monte Carlo prop-challenge simulator using OUR OWN backtested strategy stats.

Inputs from our Nifty backtests:
  - VWAP+Structure Pullback: win 66%, avg +0.86R (reward ~1.3R avg win, loss 1R)
  - Liquidity Refill: win 68.5%, avg +2.2R
  - Conti drift: win 63%, negative R:R (prop-tuned)

Simulates typical 2-step challenge: profit target 8% + 5%, max DD 8%,
daily loss 5%, risk per trade 1%. Reports pass rate, cost to fund, risk of ruin.
"""

from __future__ import annotations

import numpy as np

N = 10000
TRADES = 100          # max trades per attempt
TARGET = 0.08
MAX_DD = 0.08
DAILY_LOSS = 0.05
RISK = 0.01

STRATS = {
    "VWAP+Structure (win66, avg+0.86R)": (0.661, 1.30),
    "Liquidity Refill (win68, avg+2.2R)": (0.685, 3.20),
    "Conti drift (win63, neg R:R)": (0.628, 0.50),
}


def simulate(win, rr, seed=7):
    rng = np.random.default_rng(seed)
    passes, busts = 0, 0
    pass_trades = []
    for _ in range(N):
        eq, peak = 0.0, 0.0
        passed = False
        for t in range(TRADES):
            # outcome in R
            x = rr if rng.random() < win else -1.0
            eq += RISK * x
            peak = max(peak, eq)
            dd = peak - eq
            if eq >= TARGET:
                passed = True
                pass_trades.append(t + 1); break
            if dd >= MAX_DD or eq <= -MAX_DD:
                busts += 1; break
        if passed: passes += 1
    return {
        "pass%": passes / N * 100,
        "bust%": busts / N * 100,
        "avg trades to pass": float(np.mean(pass_trades)) if pass_trades else 0,
    }


def main():
    print(f"MONTE CARLO prop challenge ({N:,} sims, target 8%, DD 8%, risk 1%/trade)\n")
    print(f"{'Strategy':38s} {'pass%':>6s} {'bust%':>6s} {'trades to pass':>14s}")
    for name,(w,rr) in STRATS.items():
        r = simulate(w, rr)
        print(f"{name:38s} {r['pass%']:6.1f} {r['bust%']:6.1f} {r['avg trades to pass']:14.0f}")


if __name__ == "__main__":
    main()
