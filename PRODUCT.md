# Product — AXIOM BLACKMERE (HTML surface)

## Truth
- Intraday Nifty 50 option/price decision terminal for CALL/PUT planning.
- Fixed rules: SL ₹20, target ₹40; signal convention PCR > 1 → BUY, else SELL.
- Timeframes 3 / 5 / 9 / 15 minutes; each bar is real market data.
- Live sources: Angel One (spot LTP + option-chain open interest), NSE (breadth,
  stocks, sectors, GIFT NIFTY), Yahoo (global indices), recorded candles when
  the market is closed. No synthetic, invented, or illustrative numbers.

## Audience & scene
- Active intraday trader checking a phone in market hours, often one-handed,
  needing the signal and the numbers in seconds.

## Surface
- Standalone HTML/CSS/JS dashboard served at `/` by `web/api_server.py`.
- `/api/snapshot?tf=3|5|9|15` is the only data channel.

## Non-negotiables
- Every displayed number originates from `/api/snapshot`.
- Show honest source state: LIVE / RECORDED / OFFLINE.
- Keep every existing information section: KPI, hero chart, three detail charts,
  MOST ACTIVE OI, intraday flow log, breadth, major stocks, sectors, globals.
- Light and dark modes must both be legible.
