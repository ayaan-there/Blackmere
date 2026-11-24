# Nifty 50 — Price Action Dashboard

## 🔴 LATEST UPDATE (real parquet data + backtest)

- Data source: `data/raw/nifty50_index/1m/**/*.parquet` (1,232 daily files, `ts` column,
  volume=0 → bar-range proxy). 1-min ko 5-min me resample hota hai.
- Config: `STRIKE_STEP=50`, `LOT_SIZE=65`, `EXPIRY_OVERRIDE=2026-11-23` (Monday).
- nayi files: `backtest.py` + `data/backtest_report.json`, `🕯️ CANDLE + SURETY` tab.
- **Backtest finding (aapke hi data par):** bullish score ke baad 5-bar me +0.1% upmove
  **19.7%** (base rate 20.1%), bearish **22.9%** vs base 20.8%. Average move ~0.005%.
  **Score ka predictive edge nahi hai.** Tool ka asli kaam: scenario planning + 1:2 risk
  tracking + jaldi SL alert — prediction nahi.

**Educational decision-support tool.** Ye 5/15-min "prediction" nahi deta — deta hai
**scenario plan** (`IF trigger → THEN trade`) with **1:2 risk:reward**, expiry aur strike.

> ⚠️ Koi bhi system 5/15-min ka direction guarantee nahi kar sakta. Final trade aur
> risk aapka hi hai. `SL HIT` alert aapko jaldi batata hai, par order khud nahi lagata.

## Chalu karna

```powershell
pip install -r requirements.txt
streamlit run app.py
```

Browser khul jayega. Pehle `SAMPLE_` data dikhega (synthetic) — apni CSV `data/` me
daalte hi real data use hoga.

## Aapke diye gaye rules kaise lage

Aapka example: Nifty ~24200, `24200 CE @ 80`, SL `60` (₹20 niche), Target `120` (₹40 upar).

Is dashboard me:
- ATM strike auto nikalta hai (`spot` ko `STRIKE_STEP` ka nearest multiple).
- Premium live option chain se (agar diya) ya **Black-Scholes + realised vol** se estimate.
- `SL = entry − RISK` (default ₹20), `Target = entry + 2 × RISK` (aapka 1:2).
- Expiry = agla configured weekday (default Tuesday — **NSE circular se verify karein**).
- Minimal jab bhi spot resistance cross kare → CE plan active; support toot jaye → PE plan.

## Kya kya hai

| File | Kaam |
|---|---|
| `app.py` | Streamlit UI, auto-refresh, 5/15 min tabs, trade tracker + alerts |
| `engine.py` | Indicators, Market Profile, confluence bias, scenario builder, option maths |
| `data_loader.py` | CSV auto-detect + Angel One LTP adapter |
| `config.py` | Strike step, expiry weekday, risk, R:R, refresh — sab yahin |
| `books/` | Al Brooks, Dalton, Bulkowski, Miner — methodologies (content copy nahi kiya) |

## Signals (books se, general concepts)

- **Al Brooks** — trend bar / doji / breakout / HH-HL structure
- **Dalton** — POC, VAH, VAL (value area)
- **Bulkowski** — 20-bar swing high/low = support/resistance
- **Miner** — 7 signals ka weighted confluence score (0–100)

Score >57 = BULLISH, <43 = BEARISH, beech me NEUTRAL. Score "guarantee" nahi,
sirf current setup ki quality batata hai.

## Live Angel One feed (optional)

```powershell
$env:ANGEL_API_KEY="..."
$env:ANGEL_CLIENT_ID="..."
$env:ANGEL_PASSWORD="..."
$env:ANGEL_TOTP="..."          # 32-char TOTP secret ya 6-digit code
$env:ANGEL_REFRESH_TOKEN="..."
```
Phir `config.py` me `LIVE_ENABLED = True`. (requirements me `smartapi-python`, `pyotp` uncomment karein.)

**Order placement nahi kiya jata** — sirf LTP + alerts. Agar aap chahein to alag se,
clear safety limits ke saath, order routing add kar sakte hain.

## Verify karein (main web search kar nahi paya — 402 quota)
- Nifty weekly expiry weekday (`EXPIRY_WEEKDAY`)
- Nifty strike interval (`STRIKE_STEP`)
- Lot size (`LOT_SIZE`)

Yeh teeno NSE circular / broker se confirm karke `config.py` me badlein.
