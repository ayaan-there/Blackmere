"""Central configuration for the Nifty price-action dashboard.

Live-feed credentials come from environment variables, never from a file.
"""

import os
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# ---------------------------------------------------------------- data
USE_PARQUET = True
RAW_DIR = DATA_DIR / "raw" / "nifty50_index" / "1m"
RAW_TIMEFRAME_MINUTES = 1
TIMEFRAME_MINUTES = 5          # dashboard bar size (1-min raw is resampled to this)
LOAD_LAST_DAYS = 120           # dashboard ke liye utne din (fast)
TICK_SIZE = 0.5                # Market Profile price bucket

# ------------------------------------------------------------ instrument
SYMBOL = "NIFTY 50"
EXCHANGE = "NSE"
STRIKE_STEP = 50
LOT_SIZE = 65
EXPIRY_WEEKDAY = 1             # default: Tuesday (0=Mon,1=Tue,...)
EXPIRY_OVERRIDE = "2026-11-23"  # is hafte Monday 23 Nov — khali karein to weekday use hoga

# ----------------------------------------------------------------- risk
RISK_REWARD = 2.0
DEFAULT_RISK_RS = 20
MIN_PREMIUM = 1.0

# ----------------------------------------------------------- live feed
LIVE_ENABLED = True            # .env me creds + refresh token ready hain
REFRESH_SECONDS = 30

# ------------------------------------------- market structure engine
# Initial test values only — configurable, not universally optimal.
PRICE_THRESHOLD_PCT = 0.05
OI_THRESHOLD_PCT = 0.5
STRUCTURE_WINDOW = 30          # rolling observations
STRENGTH_LOOKBACK = 60         # volatility normalisation window
PERSISTENCE_K = 10             # recent observations for persistence/consistency
DOMINANT_MIN_SHARE = 0.25      # below this -> MIXED


def angel_credentials() -> dict:
    """Read creds from .env (python-dotenv auto-loaded by callers)."""
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
    return {
        # support BOTH naming styles
        "api_key": os.getenv("ANGEL_API_KEY", ""),
        "client_id": os.getenv("ANGEL_CLIENT_ID", "") or os.getenv("ANGEL_CLIENT_CODE", ""),
        "password": os.getenv("ANGEL_PASSWORD", "") or os.getenv("ANGEL_PIN", ""),
        "totp_secret": os.getenv("ANGEL_TOTP_SECRET", ""),
        "totp": os.getenv("ANGEL_TOTP", ""),
        "refresh_token": os.getenv("ANGEL_REFRESH_TOKEN", ""),
    }


def all_credentials_present() -> bool:
    c = angel_credentials()
    # need: api key, client id, password/pin, refresh token (TOTP secret optional after token)
    return bool(c["api_key"] and c["client_id"] and c["password"] and c["refresh_token"])


def days_to_expiry(today=None) -> tuple:
    """Return (expiry_date, calendar_days). Override first, then weekday."""
    today = today or date.today()
    if EXPIRY_OVERRIDE:
        expiry = date.fromisoformat(EXPIRY_OVERRIDE)
        return expiry, max((expiry - today).days, 0.5)
    delta = (EXPIRY_WEEKDAY - today.weekday()) % 7
    expiry = today + timedelta(days=delta)
    return expiry, max(delta, 0.5)
