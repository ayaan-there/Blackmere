# Data folder

Apni Nifty 50 candle CSV yahin daalo, e.g. `nifty_5min.csv`.

## Minimum columns (case-insensitive, extra columns OK)
| column | example |
|---|---|
| timestamp | `2026-11-20 09:15:00` (ya `20-11-2026 09:15` — dono attempt hote hain) |
| open | `24198.50` |
| high | `24210.00` |
| low | `24192.00` |
| close | `24205.50` |
| volume | `125000` (optional, 0 maan liya jayega) |
| oi | `...` (optional) |

## Notes
- `config.py` me `TIMEFRAME_MINUTES` apni CSV ke hisaab se set karein (1 ya 5).
- `SAMPLE_` se shuru hone wali file sirf demo hai — usse hata dena jab real data aaye.
- Engine kam se kam 20 candles maangta hai (20-bar swing support/resistance ke liye).
- Live Angel One feed ke liye CSV zaroori nahi, par backlog/indicators ke liye achha hai.
