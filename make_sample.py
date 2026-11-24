"""Generate a clearly-labelled SYNTHETIC sample CSV so the UI can be tested.
Delete/replace with real data. NEVER trade on this.
"""

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(7)
start = datetime(2026, 11, 20, 9, 15)
bars = []
price = 24180.0
t = start
for i in range(156):  # ~2 sessions of 5-min bars
    drift = 1.2 if i < 70 else (-1.0 if i > 100 else 0.2)
    ret = rng.normal(drift, 9.0)
    o = price
    c = price + ret
    h = max(o, c) + abs(rng.normal(0, 4))
    l = min(o, c) - abs(rng.normal(0, 4))
    v = int(rng.integers(40000, 160000))
    bars.append((t, o, h, l, c, v, 0))
    price = c
    t += timedelta(minutes=5)
    if t.hour == 15 and t.minute >= 30:
        t = datetime(t.year, t.month, t.day + 1, 9, 15)

df = pd.DataFrame(bars, columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
path = Path(__file__).resolve().parent / "data" / "SAMPLE_nifty_5min.csv"
path.parent.mkdir(exist_ok=True)
df.to_csv(path, index=False)
print(f"wrote {path} ({len(df)} bars) - SYNTHETIC, do not trade on this")
