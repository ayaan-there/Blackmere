"""Generate Angel One refresh token from .env (API key + client code + PIN + TOTP).
Saves ANGEL_REFRESH_TOKEN to .env for live feed.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import pyotp

BASE = Path(__file__).resolve().parent
ENV = BASE / ".env"
load_dotenv(ENV)

api_key = os.getenv("ANGEL_API_KEY", "")
client_id = os.getenv("ANGEL_CLIENT_CODE", "") or os.getenv("ANGEL_CLIENT_ID", "")
pin = os.getenv("ANGEL_PIN", "") or os.getenv("ANGEL_PASSWORD", "")
secret = os.getenv("ANGEL_TOTP_SECRET", "")

if not all([api_key, client_id, pin, secret]):
    raise SystemExit("creds missing in .env")

try:
    from SmartApi import SmartConnect
    totp = pyotp.TOTP(secret).now()
    obj = SmartConnect(api_key=api_key)
    data = obj.generateSession(client_id, pin, totp)
    print("status:", data.get("status"))
    if data.get("status"):
        rt = data["data"]["refreshToken"]
        print("refresh token generated, len:", len(rt))
        # save to .env (replace if exists)
        lines = ENV.read_text(encoding="utf-8").splitlines()
        out, done = [], False
        for line in lines:
            if line.startswith("ANGEL_REFRESH_TOKEN="):
                out.append(f"ANGEL_REFRESH_TOKEN={rt}")
                done = True
            else:
                out.append(line)
        if not done:
            out.append(f"ANGEL_REFRESH_TOKEN={rt}")
        ENV.write_text("\n".join(out) + "\n", encoding="utf-8")
        print("saved to .env")
    else:
        print("message:", data.get("message"))
except Exception as e:
    print("ERROR:", type(e).__name__, e)
