"""Single production entrypoint (local dev and Render use the same path).

Starts the tick feed + refresh ticker and serves the dashboard on 0.0.0.0:$PORT.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import api_server  # noqa: E402


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8502"))
    print(f"[main] starting AXIOM BLACKMERE on 0.0.0.0:{port}", flush=True)
    api_server.start(port)
