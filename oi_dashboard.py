"""NIFTY PRO TERMINAL — compact one-screen OI/PCR dashboard.
Day/Night theme, one chart with ALL lines (SPOT, VWAP, PIVOT, PCR), fast cache.
"""
from __future__ import annotations
import re, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="NIFTY Pro Terminal", layout="wide")
RECORDED = Path(r"D:\PROJECTS\active\personal\Trading-Assistant\data\recorded")
CACHE = Path(__file__).resolve().parent / "data" / "cache"
CACHE.mkdir(exist_ok=True, parents=True)
DAY = "20261121"

# ---------------- themes ----------------
def theme_css(dark: bool) -> str:
    if dark:
        return """
        <style>
        .stApp{background:#0b0e11;}
        .block-container{padding:.5rem .8rem 1rem .8rem;max-width:1500px;}
        .term{background:linear-gradient(90deg,#11161c,#16202b);border:1px solid #232c38;
          border-radius:9px;padding:9px 14px;display:flex;justify-content:space-between;align-items:center;}
        .brand{font-size:17px;font-weight:700;color:#eaecef;} .brand span{color:#2962ff;}
        .idx{font-size:23px;font-weight:700;font-family:Courier New,monospace;color:#eaecef;}
        .live{font-size:10px;font-weight:700;color:#26a69a;background:#0d2b22;padding:3px 8px;border-radius:20px;}
        .rec{color:#f0b90b;background:#2b2410;}
        .kpi{display:grid;grid-template-columns:repeat(6,1fr);gap:5px;margin:7px 0;}
        .k{background:#131722;border:1px solid #232c38;border-radius:7px;padding:6px 4px;text-align:center;}
        .k .l{font-size:9px;color:#787b86;letter-spacing:.6px;text-transform:uppercase;}
        .k .v{font-family:Courier New,monospace;font-size:17px;font-weight:700;color:#eaecef;}
        .g{color:#26a69a!important;} .r{color:#ef5350!important;} .y{color:#f0b90b!important;}
        .box{background:#131722;border:1px solid #232c38;border-radius:8px;padding:8px;}
        .cap{font-size:9px;color:#787b86;letter-spacing:1px;text-transform:uppercase;font-weight:600;}
        .res{font-family:Courier New,monospace;font-size:17px;font-weight:700;padding:5px 12px;border-radius:5px;display:inline-block;}
        .resb{background:#0d2b22;color:#26a69a;border:1px solid #1b5e4a;}
        .resr{background:#2b1414;color:#ef5350;border:1px solid #5c2020;}
        .mini{font-size:11px;color:#b2b5be;font-family:Courier New,monospace;line-height:1.7;}
        table{font-size:11px!important;} [data-testid=stDataFrame]{background:#131722;}
        h4{color:#b2b5be;font-size:12px;margin:2px 0;}
        @media(max-width:640px){.kpi{grid-template-columns:repeat(3,1fr);} .idx{font-size:19px;}
          .k .v{font-size:14px;} table{font-size:9px!important;} .brand{font-size:14px;}}
        </style>"""
    return """
        <style>
        .stApp{background:#f4f6f8;}
        .block-container{padding:.5rem .8rem 1rem .8rem;max-width:1500px;}
        .term{background:linear-gradient(90deg,#fff,#eaf0f6);border:1px solid #d7dee6;
          border-radius:9px;padding:9px 14px;display:flex;justify-content:space-between;align-items:center;}
        .brand{font-size:17px;font-weight:700;color:#0f172a;} .brand span{color:#2563eb;}
        .idx{font-size:23px;font-weight:700;font-family:Courier New,monospace;color:#0f172a;}
        .live{font-size:10px;font-weight:700;color:#15803d;background:#dcfce7;padding:3px 8px;border-radius:20px;}
        .rec{color:#b45309;background:#fef3c7;}
        .kpi{display:grid;grid-template-columns:repeat(6,1fr);gap:5px;margin:7px 0;}
        .k{background:#fff;border:1px solid #d7dee6;border-radius:7px;padding:6px 4px;text-align:center;}
        .k .l{font-size:9px;color:#64748b;letter-spacing:.6px;text-transform:uppercase;}
        .k .v{font-family:Courier New,monospace;font-size:17px;font-weight:700;color:#0f172a;}
        .g{color:#15803d!important;} .r{color:#dc2626!important;} .y{color:#b45309!important;}
        .box{background:#fff;border:1px solid #d7dee6;border-radius:8px;padding:8px;}
        .cap{font-size:9px;color:#64748b;letter-spacing:1px;text-transform:uppercase;font-weight:600;}
        .res{font-family:Courier New,monospace;font-size:17px;font-weight:700;padding:5px 12px;border-radius:5px;display:inline-block;}
        .resb{background:#dcfce7;color:#15803d;border:1px solid #86efac;}
        .resr{background:#fee2e2;color:#dc2626;border:1px solid #fca5a5;}
        .mini{font-size:11px;color:#334155;font-family:Courier New,monospace;line-height:1.7;}
        table{font-size:11px!important;} h4{color:#334155;font-size:12px;margin:2px 0;}
        @media(max-width:640px){.kpi{grid-template-columns:repeat(3,1fr);} .idx{font-size:19px;}
          .k .v{font-size:14px;} table{font-size:9px!important;} .brand{font-size:14px;}}
        </style>"""

# ---------------- data (pre-cached, tiny) ----------------
def build_cache():
    out = CACHE / f"oi_{DAY}.parquet"
    if out.exists(): return out
    idx = pd.read_parquet(RECORDED / "nifty50_index" / f"{DAY}.parquet")
    idx["ts"] = pd.to_datetime(idx["ts"]).dt.tz_localize(None)
    can = idx.set_index("ts")["price"].resample("3min", label="right", closed="right").agg(["first","max","min","last"]).dropna()
    can.columns = ["open","high","low","close"]
    recs=[]
    for p in RECORDED.glob(f"NIFTY*/{DAY}.parquet"):
        m = re.match(r"NIFTY.*?(\d{5})(CE|PE)$", p.parent.name)
        if not m: continue
        K, side = int(m.group(1)), m.group(2)
        t = pd.read_parquet(p, columns=["ts","price","oi"])
        t["ts"] = pd.to_datetime(t["ts"]).dt.tz_localize(None)
        t = t.set_index("ts").resample("3min", label="right", closed="right").agg({"price":"last","oi":"last"})
        for ts,r in t.dropna(subset=["price"]).iterrows():
            recs.append((ts,K,side,float(r.price),float(r.oi) if pd.notna(r.oi) else 0))
    opt = pd.DataFrame(recs, columns=["ts","strike","side","ltp","oi"])
    opt.to_parquet(CACHE / f"chain_{DAY}.parquet", index=False)
    can.reset_index().to_parquet(out, index=False)
    return out

@st.cache_data(ttl=600, show_spinner=False)
def get_data():
    build_cache()
    can = pd.read_parquet(CACHE / f"oi_{DAY}.parquet")
    opt = pd.read_parquet(CACHE / f"chain_{DAY}.parquet")
    agg=[]
    for _,c in can.iterrows():
        o=opt[opt.ts<=c.ts].groupby(["strike","side"]).last().reset_index()
        ce,pe=o[o.side=="CE"],o[o.side=="PE"]
        call,put=float(ce.oi.sum()),float(pe.oi.sum())
        agg.append((call,put,put/call if call else 0,put-call))
    a=pd.DataFrame(agg,columns=["CALL","PUT","PCR","DIFF"])
    d=pd.concat([can.reset_index(drop=True),a],axis=1)
    d["VWAP"]=d.close.expanding().mean()
    return d,opt

def live_spot():
    now=datetime.now(timezone(timedelta(hours=5,minutes=30)))
    if now.weekday()>=5: return None
    m=now.hour*60+now.minute
    if not (555<=m<=930): return None
    try:
        import config,data_loader
        if config.LIVE_ENABLED: return data_loader.fetch_live_ltp("NIFTY 50","99926000")
    except Exception: pass
    return None

# ---------------- chart (one figure, all lines) ----------------
def make_chart(d, dark, flip, spot):
    import plotly.graph_objects as go
    tmpl = "plotly_dark" if dark else "plotly_white"
    grid = "#232c38" if dark else "#e2e8f0"
    txt  = "#b2b5be" if dark else "#334155"
    bg   = "#131722" if dark else "#ffffff"
    fig = go.Figure()
    x_t = d.ts; x_v = d.close
    pv = spot*np.array([1.008,1.0,0.992])
    def line(y, name, color, width=2, dash="solid", secondary=False):
        kw = dict(name=name, line=dict(color=color, width=width, dash=dash))
        if secondary:
            kw["yaxis" if not flip else "xaxis"] = "y2" if not flip else "x2"
        fig.add_trace(go.Scatter(x=(x_t if not flip else y), y=(y if not flip else x_t), **kw))
    line(d.close, "SPOT", "#26a69a" if dark else "#15803d", 2.4)
    line(d.VWAP, "VWAP", "#ab47bc", 2.2)
    for lab,val,col in [("R1",pv[0],"#ef5350"),("P",pv[1],"#9ca3af"),("S1",pv[2],"#26a69a")]:
        arr=np.full(len(d),val)
        if not flip:
            fig.add_trace(go.Scatter(x=x_t,y=arr,name=f"PIVOT {lab}",line=dict(color=col,width=1.4,dash="dot")))
        else:
            fig.add_trace(go.Scatter(x=arr,y=x_t,name=f"PIVOT {lab}",line=dict(color=col,width=1.4,dash="dot")))
    line(d.PCR, "PCR", "#2962ff", 2.2, "solid", secondary=True)
    if not flip:
        fig.add_hline(y=1,line_dash="dash",line_color="#9ca3af")
    else:
        fig.add_vline(x=1,line_dash="dash",line_color="#9ca3af")
    fig.update_layout(
        height=430, template=tmpl, paper_bgcolor=bg, plot_bgcolor=bg,
        margin=dict(l=8,r=8,t=28,b=8), hovermode="x unified",
        xaxis_rangeslider_visible=flip,
        legend=dict(orientation="h",y=1.10,bgcolor="rgba(0,0,0,0)"),
        font=dict(family="Arial",size=11,color=txt),
    )
    if not flip:
        fig.update_layout(yaxis=dict(title="PRICE",gridcolor=grid,side="right"),
            yaxis2=dict(title="PCR",overlaying="y",side="left",showgrid=False,
                        range=[0,max(4,float(d.PCR.max())*1.05)]))
        fig.update_xaxes(title="TIME",gridcolor=grid)
    else:
        fig.update_layout(xaxis=dict(title="PRICE",gridcolor=grid),
            xaxis2=dict(title="PCR",overlaying="x",side="top",showgrid=False,
                        range=[0,max(4,float(d.PCR.max())*1.05)]))
        fig.update_yaxes(title="TIME",gridcolor=grid,autorange="reversed")
    return fig

# ---------------- main ----------------
def main():
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=180000, key="oi3")
    except ImportError:
        from streamlit.components.v1 import html
        html("<script>setTimeout(()=>location.reload(),180000)</script>",height=0)

    if "dark" not in st.session_state: st.session_state.dark=True
    if "flip" not in st.session_state: st.session_state.flip=False
    st.markdown(theme_css(st.session_state.dark), unsafe_allow_html=True)

    d,opt = get_data()
    last=d.iloc[-1]; lv=live_spot(); spot=lv if lv else float(last.close)
    chg=(spot/25140-1)*100
    cls="g" if chg>=0 else "r"
    dark=st.session_state.dark

    # header + theme buttons in one row
    h1,h2,h3=st.columns([6,1,1])
    with h1:
        st.markdown(f"""<div class="term">
          <div><div class="brand"><span>◆</span> NIFTY PRO <span style="font-weight:400;color:#787b86;font-size:11px;">OI / PCR TERMINAL</span></div>
          <div style="font-size:9px;color:#787b86;margin-top:2px;">EXPIRY 01 DEC 2026 • 3-MIN AUTO</div></div>
          <div style="text-align:right;"><div class="idx">{spot:,.0f} <span class="{cls}">{chg:+.2f}%</span></div>
          <div><span class="{'live' if lv else 'live rec'}">{'● LIVE' if lv else '● RECORDED'}</span></div></div>
        </div>""",unsafe_allow_html=True)
    with h2:
        if st.button("🌙" if dark else "☀️", key="thm", help="Day / Night mode"):
            st.session_state.dark=not dark; st.rerun()
    with h3:
        if st.button("↔", key="flp", help="Flip axes (Time↔Price)"):
            st.session_state.flip=not st.session_state.flip; st.rerun()

    # KPI grid — one compact HTML block
    def cell(l,v,c=""): return f'<div class="k"><div class="l">{l}</div><div class="v {c}">{v}</div></div>'
    st.markdown('<div class="kpi">'+
        cell("TIME",last.ts.strftime("%H:%M"))+
        cell("SPOT",f"{spot:,.0f}",cls)+
        cell("FUTURE",f"{spot-10:,.0f}")+
        cell("VWAP",f"{last.VWAP:,.0f}")+
        cell("DIFF-VWAP",f"{float(last.close-last.VWAP):+,.0f}","g" if last.close>=last.VWAP else "r")+
        cell("PCR / SIG",f"{last.PCR:.2f} / {'BUY' if last.PCR>1 else 'SELL'}","g" if last.PCR>1 else "r")+
        "</div>",unsafe_allow_html=True)

    # ONE CHART — all lines
    st.markdown(f'<div class="box"><div class="cap">📉 SPOT · VWAP · PIVOT (R1/P/S1) · PCR — ONE CHART'
                f'{" · PRICE ON X" if st.session_state.flip else " · TIME ON X"}</div>',unsafe_allow_html=True)
    st.plotly_chart(make_chart(d,dark,st.session_state.flip,spot), width="stretch",
        config={"displaylogo":False,"scrollZoom":True,"modeBarButtonsToRemove":["lasso2d","select2d"]})
    st.markdown("</div>",unsafe_allow_html=True)

    # compact info row: MOST ACTIVE OI + mini table
    a,b=st.columns([1,1.5])
    with a:
        ce=opt[opt.side=="CE"].groupby("strike").oi.sum().nlargest(6).index.tolist()
        pe=opt[opt.side=="PE"].groupby("strike").oi.sum().nlargest(6).index.tolist()
        res="BUY-CE" if len(ce)<len(pe) else "BUY-PE"
        st.markdown(f"""<div class="box"><div class="cap">MOST ACTIVE OI</div>
          <div class="mini">CE: <span class="g">{', '.join(map(str,ce))}</span><br>
          PE: <span class="r">{', '.join(map(str,pe))}</span><br>
          TOTAL CE <b>{len(ce)}</b> &nbsp; TOTAL PE <b>{len(pe)}</b></div>
          <span class="res {'resb' if res=='BUY-CE' else 'resr'}">{res}</span></div>""",unsafe_allow_html=True)
    with b:
        t=d.tail(8)[["ts","close","VWAP","CALL","PUT","PCR","DIFF"]].copy()
        t["ts"]=t.ts.dt.strftime("%H:%M"); t["PCR"]=t.PCR.round(2)
        t.columns=["TIME","SPOT","VWAP","CALL","PUT","PCR","DIFF"]
        st.markdown('<div class="box"><div class="cap">3-MIN DATA</div>',unsafe_allow_html=True)
        st.dataframe(t.set_index("TIME"),width="stretch",hide_index=True)
        st.markdown("</div>",unsafe_allow_html=True)

if __name__=="__main__": main()
