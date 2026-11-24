"""Build fast-loading cached parquet for 5m and 15m (index + BEES).
Run ONCE. Dashboard then loads a single fast file instead of 1232 small ones.
"""

from pathlib import Path
import pandas as pd
import config
import data_loader
import engine

OUT = config.DATA_DIR / "cache"
OUT.mkdir(exist_ok=True)


def build(kind, tf):
    p = config.DATA_DIR / "raw" / kind / "1m"
    chunks = [data_loader._normalise(pd.read_parquet(f)) for f in sorted(p.rglob("*.parquet"))]
    df = engine.add_indicators(data_loader.resample(pd.concat(chunks, ignore_index=True), tf))
    out = OUT / f"{kind}_{tf}m.parquet"
    df.to_parquet(out, index=False)
    print(f"{out.name}: {len(df):,} rows")


if __name__ == "__main__":
    for kind in ("nifty50_index", "nifty50_etf"):
        for tf in (5, 15):
            build(kind, tf)
    print("cache ready")
