"""SIMPLE NIFTY DASHBOARD — pivot style + VWAP signal + candle chart + P&L.

Run: streamlit run simple_dashboard.py
Colors: green=buy/bullish, red=sell/bearish, yellow=wait, blue=info.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd
import streamlit as st

import config
import data_loader
import engine
from pivot_paper_run import load, pivots

st.set_page_config(page_title="Nifty Simple Dashboard", layout="wide")

GREEN = "#16a34a"; RED = "#dc2626"; BLUE = "#2563eb"; YELLOW = "#f59e0b"


def css():
    st.markdown("""
    <style>
    .big {font-size:18px;font-weight:bold;padding:12px;border-radius:10px;text-align:center;color:white;}
    .g{background:#16a34a;} .r{background:#dc2626;} .y{background:#f59e0b;} .b{background:#2563eb;}
    .box{border-radius:10px;padding:10px;margin:6px 0;border-left:5px solid #2563eb;background:#f8fafc;
         font-size:14px;overflow-wrap:anywhere;}
    .pnl-p{color:#16a34a;font-weight:bold;} .pnl-n{color:#dc2626;font-weight:bold;}
    h1,h2,h3 {margin-bottom:4px;}
    /* ---- mobile ---- */
    @media (max-width: 640px) {
      .big {font-size:14px !important;padding:9px !important;}
      [data-testid="stMetricValue"] {font-size:18px !important;}
      .box {font-size:13px !important;padding:8px !important;}
      .stDataFrame {font-size:11px !important;}
    }
    .block-container {padding-left:1rem;padding-right:1rem;}
    </style>""", unsafe_allow_html=True)


def top_banner(price, ce_trig, pe_trig, active):
    """Plain-language banner: which ZONE price is in + exactly what to do."""
    if price > ce_trig:
        if active == "CE":
            st.markdown(f'<div class="big g">🟢 AB CALL KHARIDO — Nifty {price:.0f}, R1 {ce_trig:.0f} cross + 3 green ban gayi</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="big y">🟠 CALL ZONE — Nifty {price:.0f} R1 {ce_trig:.0f} se upar hai. 3 green candle ka wait karein, phir CE kharido.</div>', unsafe_allow_html=True)
    elif price < pe_trig:
        if active == "PE":
            st.markdown(f'<div class="big r">🔴 AB PUT KHARIDO — Nifty {price:.0f}, S1 {pe_trig:.0f} toota + 3 red ban gayi</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="big y">🟠 PUT ZONE — Nifty {price:.0f} S1 {pe_trig:.0f} se neeche hai. 3 red candle ka wait karein, phir PE kharido.</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="big b">👉 Nifty ab {price:.0f} — dono level ke BEECH me hai. CALL {ce_trig:.0f} cross par | PUT {pe_trig:.0f} break par. Ab kuch mat karo.</div>', unsafe_allow_html=True)


def signal_box(sig, price, pv, risk=20):
    """Hamesha DO plan dikhao — buy kahan, sell kahan. Koi 'WAIT/Reason' nahi."""
    atm = int(round(price / 50) * 50)
    ce_active = sig == "CE"
    pe_active = sig == "PE"
    st.markdown(f"""
    <div class="box" style="border-color:{GREEN if ce_active else '#94a3b8'}">
      <b style="color:{GREEN}">{'🟢 AB LENO (ACTIVE)' if ce_active else '⬆️ CALL KA PLAN'}</b><br>
      <b style="font-size:18px;">Nifty {float(pv['R1'].iloc[-2]):.0f} UPAR CROSS KARE → {atm} CE kharido</b><br>
      Entry = option ka live LTP &nbsp;|&nbsp; SL <b style="color:{RED}">₹{risk}</b> &nbsp;|&nbsp;
      Target <b style="color:{GREEN}">₹{risk*2}</b> &nbsp;|&nbsp; Lot {config.LOT_SIZE}
    </div>
    <div class="box" style="border-color:{RED if pe_active else '#94a3b8'}">
      <b style="color:{RED}">{'🔴 AB LENO (ACTIVE)' if pe_active else '⬇️ PUT KA PLAN'}</b><br>
      <b style="font-size:18px;">Nifty {float(pv['S1'].iloc[-2]):.0f} NEECHE TOT JAYE → {atm} PE kharido</b><br>
      Entry = option ka live LTP &nbsp;|&nbsp; SL <b style="color:{RED}">₹{risk}</b> &nbsp;|&nbsp;
      Target <b style="color:{GREEN}">₹{risk*2}</b> &nbsp;|&nbsp; Lot {config.LOT_SIZE}
    </div>
    """, unsafe_allow_html=True)


def draw_chart(d, pv, n=120):
    """Professional candlestick: dark theme, rangeslider, smooth drag/scroll zoom."""
    sub = d.tail(n).copy()
    sub["P"] = pv["P"].tail(n).values
    sub["R1"] = pv["R1"].tail(n).values
    sub["S1"] = pv["S1"].tail(n).values
    try:
        import plotly.graph_objects as go

        f = go.Figure()
        f.add_trace(go.Candlestick(
            x=sub.timestamp, open=sub.open, high=sub.high, low=sub.low, close=sub.close,
            name="Nifty", increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
            increasing_fillcolor="#26a69a", decreasing_fillcolor="#ef5350"))
        # VWAP + only 3 pivot lines (clean, not cluttered)
        f.add_trace(go.Scatter(x=sub.timestamp, y=sub.vwap,
                               line=dict(color="#ab47bc", width=2), name="VWAP"))
        f.add_trace(go.Scatter(x=sub.timestamp, y=sub["P"],
                               line=dict(color="#90a4ae", width=1, dash="dash"), name="P"))
        f.add_trace(go.Scatter(x=sub.timestamp, y=sub["R1"],
                               line=dict(color="#ef5350", width=1.5, dash="dot"), name="R1 (SELL)"))
        f.add_trace(go.Scatter(x=sub.timestamp, y=sub["S1"],
                               line=dict(color="#26a69a", width=1.5, dash="dot"), name="S1 (BUY)"))

        f.update_layout(
            height=520, template="plotly_dark",
            xaxis_rangeslider_visible=True,          # bottom slider for quick scroll
            xaxis_rangeslider_thickness=0.07,
            dragmode="zoom",                          # drag to zoom like broker app
            hovermode="x",                            # vertical crosshair line (valid in plotly)
            margin=dict(l=10, r=10, t=10, b=10),
            legend=dict(orientation="h", y=1.02, x=0, bgcolor="rgba(0,0,0,0)"),
            xaxis=dict(showgrid=True, gridcolor="#263238", rangeslider=dict(visible=True)),
            yaxis=dict(showgrid=True, gridcolor="#263238", side="right"),
            font=dict(family="Arial", size=12),
        )
        st.plotly_chart(f, width="stretch",
                        config={"scrollZoom": True, "displaylogo": False,
                                "modeBarButtonsToRemove": ["lasso2d", "select2d"],
                                "responsive": True})
    except Exception as exc:
        st.warning(f"chart error: {exc}")
        st.line_chart(sub.set_index("timestamp")[["close", "vwap", "P", "R1", "S1"]])


def compute_signal(d, pv, lookback=3):
    c, o, h, l, vw, atr = (d[k].to_numpy() for k in ("close","open","high","low","vwap","atr"))
    P, R1, S1, R2, S2 = (pv[k].to_numpy() for k in ("P","R1","S1","R2","S2"))
    i = len(d) - 2
    if pd.isna(vw[i]) or pd.isna(P[i]): return "WAIT", "signal nahi"
    lb = lookback
    hh = h[i-1] > h[i-lb]; hl = l[i-1] > l[i-lb]
    lh = h[i-1] < h[i-lb]; ll = l[i-1] < l[i-lb]
    # manual pivot style: cross + 3 candles
    three_g = all(c[i-k] > o[i-k] for k in range(3))
    three_r = all(c[i-k] < o[i-k] for k in range(3))
    if c[i] > R1[i] and three_g and c[i] > vw[i]:
        return "CE", "Pivot R1 cross + 3 green + VWAP upar"
    if c[i] > P[i] and hh and hl and c[i] > vw[i]:
        return "CE", "VWAP upar + HH/HL"
    if c[i] < S1[i] and three_r and c[i] < vw[i]:
        return "PE", "Pivot S1 break + 3 red + VWAP neeche"
    if c[i] < P[i] and lh and ll and c[i] < vw[i]:
        return "PE", "VWAP neeche + LH/LL"
    return "WAIT", "abhi koi confirm signal nahi"


def pattern_panel(d):
    i = len(d) - 2
    row = d.iloc[i]
    pat = row.get("pattern", "N/A")
    st.markdown(f"""<div class="box">
    <b>🕯️ Last candle:</b> {pat} &nbsp;|&nbsp; EMA9 {row.ema9:.1f} &nbsp;|&nbsp;
    VWAP {row.vwap:.1f} &nbsp;|&nbsp; ATR {row.atr:.1f}<br>
    <small>⬆️ <b style="color:{GREEN}">Bull engulf / Marubozu</b> ban gaya to CE confirm |
    ⬇️ <b style="color:{RED}">Bear engulf / Marubozu</b> to PE confirm |
    <b style="color:#f59e0b">Doji</b> = wait karein.</small></div>""", unsafe_allow_html=True)


def auto_ltp(chain, spot, source):
    """Return (ltp_dict, source_label). Tries live feed first, then chain."""
    live = None
    if source == "🔴 Live (Angel One)":
        live = data_loader.fetch_live_chain(spot)
    if live is not None and not live.empty:
        return dict(zip(zip(live["strike"], live["side"]), live["ltp"])), "🔴 LIVE (Angel One)"
    if chain is not None and not chain.empty:
        return dict(zip(zip(chain["strike"], chain["side"]), chain["ltp"])), "🟡 Recorded 21 Nov"
    return {}, "⚪ manual"


def pnl_table(price, ltpmap, ltpsource):
    st.markdown("### 💰 My Trades (P&L) — LTP auto "
                f"<span style='font-size:13px;color:#666;'>({ltpsource})</span>",
                unsafe_allow_html=True)
    if "trades" not in st.session_state:
        st.session_state.trades = []
    c1, c2, c3, c4 = st.columns(4)
    side = c1.selectbox("Side", ["CE", "PE"], key="pside")
    atm = int(round(price / 50) * 50)
    default_ltp = float(ltpmap.get((atm, side), 100.0))
    entry = c2.number_input("Entry ₹", 1.0, 100000.0, default_ltp, 0.5, key="pentry")
    qty = c3.number_input("Qty (lots)", 1, 10, 1, 1, key="pqty")
    if c4.button("➕ Add", width="stretch"):
        st.session_state.trades.append({"side": side, "entry": entry, "qty": qty,
                                        "strike": atm})
    # manual override for live LTP (top-up if feed not available)
    live_override = st.number_input("Live LTP ₹ (auto aata hai, change karein to manual override)",
                                    0.0, 100000.0, 0.0, 0.5, key="plive")
    if st.session_state.trades:
        rows, total = [], 0.0
        for idx, t in enumerate(st.session_state.trades):
            live = live_override if live_override > 0 else float(
                ltpmap.get((t.get("strike", atm), t["side"]), t["entry"]))
            pnl = (live - t["entry"]) * (1 if t["side"] == "CE" else -1) * t["qty"] * config.LOT_SIZE
            total += pnl
            cls = "pnl-p" if pnl >= 0 else "pnl-n"
            rows.append({"#": idx+1, "Strike": t.get("strike", atm), "Side": t["side"],
                         "Entry": t["entry"], "LTP": round(live, 2), "Qty": t["qty"],
                         "P&L ₹": f'<span class="{cls}">{pnl:+.0f}</span>'})
        st.markdown(pd.DataFrame(rows).to_html(escape=False, index=False), unsafe_allow_html=True)
        col = GREEN if total >= 0 else RED
        st.markdown(f'<div class="big" style="background:{col}">TOTAL P&L ₹{total:+.0f}</div>',
                    unsafe_allow_html=True)
        if st.button("🗑️ Clear trades"):
            st.session_state.trades = []
            st.rerun()
    else:
        st.info("Upar se trade add karein — LTP apne aap aayega, P&L apne aap niklega.")


def expiry_selector(price):
    """Expiry dropdown for option trading."""
    st.markdown("### 📅 Option Expiry")
    c1, c2, c3 = st.columns(3)
    expiry = c1.selectbox("Expiry", ["23 Nov 2026 (Mon)", "24 Nov 2026 (Tue)",
                                      "1 Dec 2026 (Tue)", "29 Dec 2026 (Tue)"])
    lot = c2.number_input("Lot size", 1, 100, config.LOT_SIZE, 1)
    risk = c3.number_input("Risk ₹ (SL)", 5, 100, 20, 5)
    atm = int(round(price / 50) * 50)
    st.caption(f"Strike: **{atm} CE / {atm} PE** (ATM) | Target ₹{risk*2} (1:2) | Lot {lot}")
    return expiry, risk


def render_option_chain(spot_main=None):
    """Latest recorded chain (21 Nov) + a WORKED example trade in plain numbers."""
    from option_chain_panel import load_chain, atm_legs

    chain, spot, ts = load_chain("20261121")
    if chain.empty:
        st.info("Option chain data nahi mila.")
        return None
    atm, legs = atm_legs(chain, spot)

    st.markdown(f"### 🔗 Option Chain — **{pd.Timestamp(ts).date()}** | Spot **{spot:.0f}** | Expiry **1 Dec 2026**")

    # Pivot-style chain table: strikes around ATM, CE / PE side by side
    around = [k for k in sorted(chain.strike.unique()) if abs(k - atm) <= 250]
    rows = []
    for k in around:
        ce = chain[(chain.strike == k) & (chain.side == "CE")]
        pe = chain[(chain.strike == k) & (chain.side == "PE")]
        rows.append({
            "Strike": f"**{k}**" if k == atm else str(k),
            "CE ₹": float(ce.ltp.iloc[0]) if not ce.empty else None,
            "CE OI": int(ce.oi.iloc[0]) if not ce.empty else None,
            "PE ₹": float(pe.ltp.iloc[0]) if not pe.empty else None,
            "PE OI": int(pe.oi.iloc[0]) if not pe.empty else None,
        })
    st.dataframe(pd.DataFrame(rows).set_index("Strike"), width="stretch")

    # WORKED EXAMPLE — exactly one trade, fully explained
    st.markdown(f"""#### 📖 Example Trade — samajhne ke liye (real prices {pd.Timestamp(ts).date()})

**Maano abhi aapko CALL lena hai** (upar wala plan active ho gaya):

| Step | Kya karein | Number |
|---|---|---|
| 1 | Spot / ATM strike | {spot:.0f} → **{atm} CE** |
| 2 | Option ka live LTP (entry) | **₹{legs[0]['ltp']:.2f}** |
| 3 | Stop Loss (₹20 neeche) | **₹{legs[0]['sl']:.2f}** |
| 4 | Target (₹40 upar, 1:2) | **₹{legs[0]['target']:.2f}** |
| 5 | Lot size | {config.LOT_SIZE} |
| 6 | Max risk | ₹20 × {config.LOT_SIZE} = **₹{20*config.LOT_SIZE}** |
| 7 | Max profit | ₹40 × {config.LOT_SIZE} = **₹{40*config.LOT_SIZE}** |

*Agar 25150 CE ₹{legs[0]['ltp']:.2f} par kharidi, to ₹{legs[0]['sl']:.2f} par nikalna hai (loss ₹20/point) aur ₹{legs[0]['target']:.2f} par bechna hai (profit ₹40/point).*
""")
    if legs[1]:
        st.markdown(f"""**Ulti taraf (PUT)** — agar neeche jana hai: **{atm} PE** LTP ₹{legs[1]['ltp']:.2f},
        SL ₹{legs[1]['sl']:.2f}, Target ₹{legs[1]['target']:.2f}.""")
    st.caption(f"⚠️ Ye **{pd.Timestamp(ts).date()}** ka recorded data hai — live trade ke liye brokar app se LTP check karein.")
    return chain


@st.cache_data(show_spinner=False)
def load_fast(kind, tf):
    """Load ONE cached parquet (ms) instead of 1232 files."""
    p = config.DATA_DIR / "cache" / f"{kind}_{tf}m.parquet"
    if p.exists():
        return pd.read_parquet(p)
    # fallback (slow) if cache missing
    return load(kind)


def main():
    st.set_page_config(page_title="Nifty Simple Dashboard", layout="wide")
    # auto refresh every 30s so live LTP / prices update on their own
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=30 * 1000, key="nifty_auto_refresh")
    except ImportError:
        from streamlit.components.v1 import html
        html("<script>setTimeout(()=>window.location.reload(),30000);</script>", height=0)

    css()
    # ---- timeframe selector (top) ----
    tf = st.radio("⏱️ Timeframe", [5, 15], horizontal=True, index=1,
                  help="5m = jaldi signals (zyada noise) | 15m = stable")
    d = load_fast("nifty50_index", tf)
    pv = pivots(d)
    sig, why = compute_signal(d, pv, lookback=5 if tf == 5 else 3)
    price = float(d["close"].iloc[-2])
    r1 = float(pv["R1"].iloc[-2]); s1 = float(pv["S1"].iloc[-2])

    # ---------- SINGLE PAGE: details first, chart below (scroll down) ----------
    st.title("Nifty Dashboard — Pivot + VWAP")
    st.caption("Risk ₹20 | Target ₹40 (1:2) | colours: 🟢 buy  🔴 sell  🟠 wait | 👇 neeche scroll karein to chart milega")

    top_banner(price, r1, s1, sig)

    a, b, c, dd = st.columns(4)
    a.metric("Nifty ab", f"{price:.0f}")
    b.metric("BUY CE >", f"{r1:.0f}")
    c.metric("BUY PE <", f"{s1:.0f}")
    if price > r1:
        short = "AB CE" if sig == "CE" else "3 green wait"
    elif price < s1:
        short = "AB PE" if sig == "PE" else "3 red wait"
    else:
        short = "wait"
    dd.metric("Ab karo", short)

    expiry_selector(price)
    signal_box(sig, price, pv)
    pattern_panel(d)
    chain = render_option_chain()
    ltpsource = st.radio("LTP source", ["🟡 Recorded 21 Nov", "🔴 Live (Angel One)"],
                         horizontal=True, index=0,
                         help="Live tab tab chalega jab Angel One creds env me honge.")
    ltpmap, label = auto_ltp(chain, price, ltpsource)
    pnl_table(price, ltpmap, label)

    st.markdown("---")
    st.subheader("📈 Live Chart — scroll = zoom, drag = move (data 13 Nov tak)")
    draw_chart(d, pv)


if __name__ == "__main__":
    main()
