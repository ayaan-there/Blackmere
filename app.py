"""Nifty 50 Price-Action Dashboard (decision support, NOT a prediction engine).

Run:  streamlit run app.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import streamlit as st

import config
import data_loader
import engine

st.set_page_config(page_title="Nifty Price Action Dashboard", layout="wide")

DISCLAIMER = (
    "⚠️ **Educational decision-support tool — financial advice nahi.** "
    "Koi bhi 5/15-min direction guarantee nahi karta. Yahan '*IF trigger THEN plan*' "
    "milti hai. Final decision aur risk aapka hi hai."
)


# ------------------------------------------------------------- auto refresh
def setup_autorefresh(seconds: int):
    try:
        from streamlit_autorefresh import st_autorefresh

        st_autorefresh(interval=seconds * 1000, key="nifty_refresh")
    except ImportError:
        from streamlit.components.v1 import html

        html(
            f"<script>setTimeout(()=>window.location.reload(),{seconds * 1000});"
            "</script>",
            height=0,
        )


def beep():
    from streamlit.components.v1 import html

    html(
        "<script>try{var c=new (window.AudioContext||window.webkitAudioContext)();"
        "var o=c.createOscillator(),g=c.createGain();o.connect(g);g.connect(c.destination);"
        "o.frequency.value=880;o.type='square';g.gain.value=0.08;o.start();"
        "o.stop(c.currentTime+0.18);}catch(e){}</script>",
        height=0,
    )


# ------------------------------------------------------------------ sidebar
def sidebar():
    st.sidebar.title("⚙️ Settings")
    st.sidebar.caption("Live feed ke liye env vars + LIVE_ENABLED=True karein.")
    st.sidebar.number_input("Strike step", 25, 200, config.STRIKE_STEP, 25, key="step")
    st.sidebar.number_input("Expiry weekday (0=Mon…1=Tue)", 0, 4,
                            config.EXPIRY_WEEKDAY, 1, key="wd")
    st.sidebar.number_input("Risk per trade (₹ premium)", 5, 200,
                            config.DEFAULT_RISK_RS, 5, key="risk")
    st.sidebar.number_input("Risk : Reward", 1.0, 5.0, config.RISK_REWARD,
                            0.5, key="rr")
    st.sidebar.number_input("Refresh (sec)", 5, 300, config.REFRESH_SECONDS,
                            5, key="refresh")
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Books → signals**")
    st.sidebar.markdown(
        "- Al Brooks → trend bar / breakout / HH-HL\n"
        "- J. Dalton → POC / VAH / VAL\n"
        "- Bulkowski → swing support/resistance\n"
        "- R. Miner → confluence scoring"
    )
    cfg_ok = config.all_credentials_present()
    st.sidebar.info(
        "Angel One creds: " + ("✅mil gaye" if cfg_ok else "❌env me nahi mile")
    )


# -------------------------------------------------------------------- cards
def scenario_card(sc, spot):
    if sc is None:
        return
    active = "ACTIVE" in sc.status
    color = "🟢" if active else "🟡"
    st.markdown(
        f"""
        <div style="border:1px solid {'#2ca02c' if active else '#d9a400'};
                    border-radius:10px;padding:14px;margin-bottom:8px;">
          <h3 style="margin:0;">{color} {sc.option} &nbsp;|&nbsp; {sc.action}</h3>
          <p style="margin:4px 0;color:{'#2ca02c' if active else '#b8860b'};">
             <b>{sc.status}</b></p>
          <table style="width:100%;font-size:15px;">
            <tr><td>Trigger (spot)</td><td><b>{sc.trigger:.2f}</b></td></tr>
            <tr><td>Entry (premium)</td><td><b>₹{sc.entry:.2f}</b></td></tr>
            <tr><td>Stop-loss</td><td><b style="color:#d62728;">₹{sc.sl:.2f}</b></td></tr>
            <tr><td>Target (1:{sc.rr:g})</td><td><b style="color:#2ca02c;">₹{sc.target:.2f}</b></td></tr>
            <tr><td>Risk / Reward</td><td>₹{sc.risk:.2f} / ₹{sc.reward:.2f}</td></tr>
            <tr><td>Expiry</td><td>{sc.expiry}</td></tr>
            <tr><td>Premium source</td><td>{sc.premium_source}</td></tr>
          </table>
          <p style="font-size:13px;color:#888;">{sc.note}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def one_line_plan(plan):
    """The single IF-THEN line the user actually wants (no 5/15 confusion)."""
    st.markdown(
        f"""
        <div style="border-left:5px solid #1f77b4;background:#f0f6ff;
                    padding:14px;border-radius:8px;">
          <h3 style="margin:0 0 8px 0;">15-MIN PLAN &nbsp;(primary timeframe)</h3>
          <p style="margin:4px 0;font-size:16px;">
            ⬆️ Agar Nifty <b>{plan.resistance:.2f}</b> cross kare →
            <b>{plan.bull.option} @ ₹{plan.bull.entry:.2f}</b>,
            SL <b style="color:#d62728;">₹{plan.bull.sl:.2f}</b>,
            Target <b style="color:#2ca02c;">₹{plan.bull.target:.2f}</b>
          </p>
          <p style="margin:4px 0;font-size:16px;">
            ⬇️ Agar Nifty <b>{plan.support:.2f}</b> toot jaye →
            <b>{plan.bear.option} @ ₹{plan.bear.entry:.2f}</b>,
            SL <b style="color:#d62728;">₹{plan.bear.sl:.2f}</b>,
            Target <b style="color:#2ca02c;">₹{plan.bear.target:.2f}</b>
          </p>
          <p style="margin:8px 0 0 0;font-size:13px;color:#666;">
            Expiry {plan.expiry} &nbsp;|&nbsp; Lot {config.LOT_SIZE} &nbsp;|&nbsp;
            Risk ₹{plan.bull.risk:.0f} : Reward ₹{plan.bull.reward:.0f} (1:{plan.bull.rr:g})
            &nbsp;|&nbsp; Bias {plan.bias} {plan.score}/100
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Trigger + candle confirmation (engulfing/marubozu) ke baad hi entry. "
               "Premium estimate hai — live option chain se replace karein.")


def projection_block(plan, minutes):
    lo, hi = plan.proj5 if minutes == 5 else plan.proj15
    st.info(
        f"**{minutes}-min ATR-based expected range:** {lo:.2f} – {hi:.2f}  "
        f"(spot {plan.spot:.2f})\n\n"
        f"**Bias:** {plan.bias} (score {plan.score}/100, {plan.confidence} confidence)\n\n"
        f"**Key trigger levels:**\n"
        f"- ⬆️ Upar cross {plan.resistance:.2f} → **CE scenario** "
        f"({plan.bull.option} @ ₹{plan.bull.entry:.2f})\n"
        f"- ⬇️ Neeche break {plan.support:.2f} → **PE scenario** "
        f"({plan.bear.option} @ ₹{plan.bear.entry:.2f})\n\n"
        f"*Ye range 'kahan ja sakta hai' batati hai, 'kahan jayega' nahi.*"
    )


# --------------------------------------------------------- candles + stats
def render_patterns(plan):
    st.subheader("🕯️ Current candle pattern")
    st.info(
        f"**Last 5-min candle:** {plan.pattern}\n\n"
        f"**Pichhle 6 candles (newest → oldest):** "
        f"{' → '.join(plan.recent_patterns)}"
    )
    st.subheader("Aage kya pattern dekhna hai (confirmation)")
    st.caption(
        "Main agli candle **predict nahi** kar sakta. Yeh list batati hai ki "
        "kaunsa pattern ban gaya to kaunsa scenario confirm hoga."
    )
    for w in plan.watch_patterns:
        st.markdown(
            f"- **{w['pattern']}** @ `{w['at']}` → _{w['means']}_"
        )
    st.warning(
        "⚠️ Doji / Spinning Top ka matlab **indecision** hai — wahan trade nahi, "
        "aglim candle ka close wait karein. Marubozu/Engulfing **banne ke baad** "
        "hi trigger maan na, pehle nahi."
    )


def render_backtest():
    import json

    path = Path(__file__).resolve().parent / "data" / "backtest_report.json"
    if not path.exists():
        st.info("Backtest report nahi mila. `python backtest.py` chalao.")
        return
    r = json.loads(path.read_text(encoding="utf-8"))
    meta = r["meta"]
    st.subheader("📊 Kitne percent sure? — aapke hi data par backtest")
    st.caption(
        f"{meta['bars']:,} five-min bars | {meta['signals_sampled']:,} sampled signals | "
        f"threshold = +{meta['threshold_pct']}% move. {meta['note']}"
    )
    b = r["bias"]
    rows = [
        {"Setup": "BULLISH score → up in 5 bars",
         "Signals": b["BULLISH"]["up_5"]["n"],
         "Hit %": b["BULLISH"]["up_5"]["hit_pct"],
         "Avg move %": b["BULLISH"]["up_5"]["mean_pct"]},
        {"Setup": "BULLISH score → up in 15 bars",
         "Signals": b["BULLISH"]["up_15"]["n"],
         "Hit %": b["BULLISH"]["up_15"]["hit_pct"],
         "Avg move %": b["BULLISH"]["up_15"]["mean_pct"]},
        {"Setup": "BEARISH score → down in 5 bars",
         "Signals": b["BEARISH"]["down_5"]["n"],
         "Hit %": b["BEARISH"]["down_5"]["hit_pct"],
         "Avg move %": b["BEARISH"]["down_5"]["mean_pct"]},
        {"Setup": "BEARISH score → down in 15 bars",
         "Signals": b["BEARISH"]["down_15"]["n"],
         "Hit %": b["BEARISH"]["down_15"]["hit_pct"],
         "Avg move %": b["BEARISH"]["down_15"]["mean_pct"]},
        {"Setup": "BASE RATE → any up move in 5 bars",
         "Signals": meta["bars"], "Hit %": 20.1, "Avg move %": 0.0005},
        {"Setup": "BASE RATE → any up move in 15 bars",
         "Signals": meta["bars"], "Hit %": 32.0, "Avg move %": None},
    ]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    st.error(
        "**Seedha jawab:** bullish signal ke baad up move 19.7% — base rate 20.1% se "
        "bhi kam. Bearish 22.9% vs base 20.8%, matlab ~2% ka marginal edge, "
        "aur average move 0.005% (costs nikal diye to zero). "
        "**Is score ka predictive edge nahi hai.** Isse prediction ke liye nahi, "
        "sirf discipline + risk tracking ke liye use karein."
    )
    st.markdown("**Candle patterns — observed 5-bar up rate (aapka data):**")
    pat_rows = [
        {"Pattern": k, "n": v["n"],
         "Up in 5 %": v["up_5"]["hit_pct"],
         "Down in 5 %": v["down_5"]["hit_pct"]}
        for k, v in r["patterns"].items()
    ]
    st.dataframe(pd.DataFrame(pat_rows), width="stretch", hide_index=True)
    st.caption(
        "In numbers se bhi koi pattern reliable edge nahi dikhata. Pattern batata hai "
        "ki **abhi kya chal raha hai**, aage kya hoga yeh nahi."
    )


# ------------------------------------------------------- option-chain tab
def render_option_chain_backtest():
    import json

    path = Path(__file__).resolve().parent / "data" / "option_chain_backtest.json"
    if not path.exists():
        st.info("Option-chain backtest report nahi mila. `python option_chain_backtest.py` chalao.")
        return
    r = json.loads(path.read_text(encoding="utf-8"))
    st.caption(
        f"Real recorded option ticks | Day: **{r['day']}** | Expiry: {r['expiry']} | "
        f"{r['strikes']} strikes, {r['option_files']} files | "
        f"Pivot source: {r['pivot_source']}"
    )
    st.error(
        "⚠️ **Sirf 1 din ka data hai** (19 Nov 2026) aur 18 Nov missing hone ki wajah se "
        "pivot 13 Nov se liye gaye hain. Isliye ye result **statistically meaningful nahi** — "
        "sirf real option prices par strategy ka demonstration hai."
    )

    for key, title in (("pivot_variant", "A. Pivot + 3 green candles (aapki strategy)"),
                       ("oi_levels_variant", "B. OI-based support/resistance + 3 candles")):
        v = r[key]
        st.subheader(title)
        if not v["signals"]:
            st.info("Is din koi signal nahi bana.")
            continue
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Signals", v["signals"])
        c2.metric("Win %", f"{v['win_pct']}%")
        c3.metric("Avg P&L", f"₹{v['avg_pnl']:.2f}")
        c4.metric("Total P&L", f"₹{v['total_pnl']:.2f}")
        st.dataframe(pd.DataFrame(v["trades"]), width="stretch", hide_index=True)
        st.caption(f"Target hits: {v['target_hits']} | SL hits: {v['sl_hits']}")

    if r.get("oi_levels_sample"):
        with st.expander("OI-derived levels (sample)"):
            st.dataframe(pd.DataFrame(r["oi_levels_sample"]), width="stretch", hide_index=True)
    if r.get("chain_10am"):
        with st.expander("Option chain snapshot @ 10:00 (top OI)"):
            ch = pd.DataFrame(r["chain_10am"]).sort_values("oi", ascending=False).head(12)
            st.dataframe(ch, width="stretch", hide_index=True)


# ------------------------------------------------------------------- charts
def draw_chart(df, plan):

    df = engine.add_indicators(df)
    try:
        import plotly.graph_objects as go

        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=df["timestamp"], open=df["open"], high=df["high"],
            low=df["low"], close=df["close"], name="Nifty"))
        fig.add_trace(go.Scatter(x=df["timestamp"], y=df["ema9"],
                                 line=dict(color="#1f77b4", width=1), name="EMA9"))
        fig.add_trace(go.Scatter(x=df["timestamp"], y=df["ema21"],
                                 line=dict(color="#ff7f0e", width=1), name="EMA21"))
        fig.add_trace(go.Scatter(x=df["timestamp"], y=df["vwap"],
                                 line=dict(color="#9467bd", width=1), name="VWAP"))
        for lvl, name, col in [(plan.resistance, "Resistance/VAH", "#2ca02c"),
                               (plan.support, "Support/VAL", "#d62728"),
                               (plan.poc, "POC", "#888888")]:
            fig.add_hline(y=lvl, line_dash="dash", line_color=col,
                          annotation_text=name)
        fig.update_layout(height=460, xaxis_rangeslider_visible=False,
                          template="plotly_dark", margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig, width="stretch")
    except ImportError:
        st.line_chart(df.set_index("timestamp")[["close", "ema9", "ema21", "vwap"]])


# -------------------------------------------------------------- trade tracker
def trade_tracker(df, plan):
    st.markdown("### 🧾 Paper-trade tracker (1:2 alert system)")
    st.caption("Real order nahi lagata — sirf alert deta hai. Premium approx = BS delta se.")
    with st.form("trade_form"):
        col1, col2, col3 = st.columns(3)
        side = col1.selectbox("Side", ["CE", "PE"])
        entry = col2.number_input("Entry premium ₹", 1.0, 1000.0,
                                  float(plan.bull.entry if side == "CE"
                                        else plan.bear.entry), 0.5)
        cols = st.columns(3)
        sl = cols[0].number_input("SL ₹", 0.5, 1000.0,
                                  float(max(1, entry - config.DEFAULT_RISK_RS)), 0.5)
        tgt = cols[1].number_input("Target ₹", 1.0, 2000.0,
                                   float(entry + config.RISK_REWARD *
                                         config.DEFAULT_RISK_RS), 0.5)
        start = cols[2].form_submit_button("Track this trade")

    if start:
        st.session_state.trade = {
            "side": side, "entry": entry, "sl": sl, "target": tgt,
            "entry_spot": plan.spot,
        }
        st.toast(f"Tracking {side} @ ₹{entry} | SL ₹{sl} | Target ₹{tgt}")

    trade = st.session_state.get("trade")
    if not trade:
        st.info("Upar se trade select karke 'Track this trade' dabao.")
        return

    cur = engine.premium_from_spot(
        trade["entry"], trade["entry_spot"], plan.spot,
        plan.bull.strike, plan.days / 365, plan.vol, trade["side"],
    )
    pnl = round(cur - trade["entry"], 2)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Current premium (approx)", f"₹{cur:.2f}")
    c2.metric("P&L / lot", f"₹{pnl * config.LOT_SIZE:.0f}", delta=f"₹{pnl:.2f}/pt")
    c3.metric("SL", f"₹{trade['sl']:.2f}")
    c4.metric("Target", f"₹{trade['target']:.2f}")

    if cur <= trade["sl"]:
        st.error(f"🚨 **SL HIT — EXIT {trade['side']} NOW** (approx ₹{cur:.2f} ≤ ₹{trade['sl']:.2f})")
        beep()
    elif cur >= trade["target"]:
        st.success(f"🎯 **TARGET HIT — book profit** (approx ₹{cur:.2f} ≥ ₹{trade['target']:.2f})")
        beep()
    elif abs(cur - trade["sl"]) <= 5:
        st.warning(f"⚠️ SL ke paas hai — {cur:.2f}, SL {trade['sl']:.2f}. Ready reho.")
        beep()
    else:
        st.write(f"Trade chal raha hai. Spot {plan.spot:.2f}, entry spot {trade['entry_spot']:.2f}.")

    if st.button("Clear trade"):
        del st.session_state.trade
        st.rerun()


# ---------------------------------------------------------------------- main
def main():
    sidebar()
    setup_autorefresh(int(st.session_state.get("refresh", config.REFRESH_SECONDS)))

    st.title("📈 Nifty 50 — Price Action Dashboard")
    st.caption(DISCLAIMER)

    files = data_loader.list_parquet(config.LOAD_LAST_DAYS)
    if not files:
        st.error("Parquet data nahi mila: `data/raw/nifty50_index/1m/`")
        st.stop()

    try:
        raw = data_loader.load_data()
        plan = engine.build_plan(raw)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Data/engine error: {exc}")
        st.stop()

    last_bar = pd.Timestamp(plan.date).date()
    if (pd.Timestamp.now().date() - last_bar).days > 4:
        st.warning(
            f"⚠️ Data **{last_bar}** tak ka hai — aaj ke live market ke liye stale ho "
            "sakta hai. Live feed chalao ya nayi parquet files daalo."
        )

    live = data_loader.fetch_live_ltp()
    if live:
        plan.spot = round(live, 2)
        st.toast(f"Live LTP: {live}")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Spot", f"{plan.spot:.2f}")
    m2.metric("Bias", plan.bias, delta=f"{plan.score}/100")
    m3.metric("Confidence", plan.confidence)
    m4.metric("Expiry", plan.expiry)
    m5.metric("Realised Vol", f"{plan.vol:.1%}")

    st.markdown(f"**Source:** parquet 1m → 5m ({len(files)} din) &nbsp;|&nbsp; "
                f"**Last bar:** {plan.date} &nbsp;|&nbsp; VWAP {plan.vwap:.2f} "
                f"&nbsp;|&nbsp; ATR(5m) {plan.atr5:.2f} &nbsp;|&nbsp; "
                f"POC {plan.poc:.2f} &nbsp;|&nbsp; **Lot** {config.LOT_SIZE}")

    tplan, tcandle, toption, tchart, tdata = st.tabs(
        ["⏱️ 15-MIN PLAN (PRIMARY)", "🕯️ CANDLE + SURETY",
         "🔗 OPTION CHAIN BACKTEST", "📊 CHART + PLAN", "📋 TRADE + DATA"]
    )
    with tplan:
        one_line_plan(plan)
        projection_block(plan, 15)
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Bullish plan")
            scenario_card(plan.bull, plan.spot)
        with c2:
            st.subheader("Bearish plan")
            scenario_card(plan.bear, plan.spot)
    with tcandle:
        render_patterns(plan)
        st.markdown("---")
        render_backtest()
    with toption:
        render_option_chain_backtest()
    with tchart:
        draw_chart(raw, plan)
        st.subheader("Bias reasons (confluence)")
        for r in plan.reasons:
            st.write("- " + r)
    with tdata:
        trade_tracker(raw, plan)
        with st.expander("Processed data (last 40 bars)"):
            st.dataframe(engine.add_indicators(raw).tail(40), width="stretch")


if __name__ == "__main__":
    main()
