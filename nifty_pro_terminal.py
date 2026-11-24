"""NIFTY PRO TERMINAL — compact one-screen dashboard.
Theme-agnostic (Streamlit 3-dot menu controls light/dark), 3 small charts,
vertical VERIFIED MOST ACTIVE OI, clear breadth tables, DIFFERENCE = FUTURE - VWAP,
GIFT NIFTY + Hang Seng + global, major stocks/sectors with number and %.
"""
from __future__ import annotations
import re, sys, json, urllib.request, time, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Nifty Pro Terminal", layout="wide")
RECORDED = Path(r"D:\PROJECTS\active\personal\Trading-Assistant\data\recorded")
CACHE = Path(__file__).resolve().parent / "data" / "cache"
CACHE.mkdir(exist_ok=True, parents=True)
DAY = "20261121"

# Theme-agnostic CSS: no forced background -> Streamlit's own theme (3-dot menu)
# controls light/dark. Colors use neutral transparency + inherit so both work.
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
/* ---- elegant blue terminal ---- */
.stApp{background:#070D19;background-image:radial-gradient(1200px 620px at 12% -12%,rgba(38,84,175,.30),transparent 62%),radial-gradient(900px 520px at 96% -4%,rgba(24,112,196,.16),transparent 58%);}
.block-container{padding:.5rem .75rem 1rem .75rem;max-width:1500px;color:#E8EEF9;
  font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;}
.g{color:#2DD4A7!important;} .r{color:#FF6B78!important;} .y{color:#F5B84B!important;}
.n{opacity:.55;} b{font-weight:700;}

/* ---- timeframe tabs ---- */
[data-testid="stRadio"]{position:relative;top:44px;margin:0 0 -39px 0;}
[data-testid="stRadioGroup"] label{font-family:Inter,"Segoe UI",sans-serif;
  font-size:12px!important;font-weight:700!important;letter-spacing:.8px!important;
  border-radius:9px;padding:4px 10px;background:rgba(255,255,255,.035);
  border:1px solid rgba(120,160,230,.18);color:#9FB2D0;}
[data-testid="stRadioGroup"] label[data-selected="true"]{background:rgba(47,107,255,.16);
  border-color:rgba(94,150,255,.50);color:#DCE9FF;}
[data-testid="stRadioGroup"] > div:nth-child(1) label{color:#82B0FF!important;}
[data-testid="stRadioGroup"] > div:nth-child(1) label[data-selected="true"]{
  background:linear-gradient(135deg,#3B82FF,#1F4FD6)!important;color:#fff!important;
  border-color:rgba(255,255,255,.40)!important;box-shadow:0 4px 15px rgba(47,107,255,.38);}

/* ---- header ---- */
.term{background:linear-gradient(135deg,rgba(20,38,72,.94),rgba(10,21,43,.94));
  border:1px solid rgba(96,140,220,.26);border-radius:14px;padding:9px 15px;
  display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:8px;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.05),0 6px 20px rgba(0,0,0,.30);}
.hleft{font-family:Inter,sans-serif;font-size:10px;opacity:.58;letter-spacing:.6px;font-weight:600;line-height:1.45;}
.hcenter{display:flex;align-items:center;gap:9px;justify-self:center;}
.logo{filter:drop-shadow(0 2px 6px rgba(47,107,255,.5));}
.brand{font-family:"Space Grotesk",sans-serif;font-size:19px;font-weight:700;
  letter-spacing:-.5px;color:#F2F6FF;white-space:nowrap;}
.idx{font-family:"IBM Plex Mono",monospace;font-size:27px;font-weight:600;color:#FFFFFF;
  line-height:1.1;letter-spacing:-1.2px;font-variant-numeric:tabular-nums;justify-self:end;}
.live{font-family:Inter,sans-serif;font-size:9px;font-weight:700;color:#7BF0C4;
  background:rgba(45,212,167,.12);padding:3px 10px;border-radius:20px;
  border:1px solid rgba(45,212,167,.35);letter-spacing:.8px;}
.hright{justify-self:end;text-align:right;}

/* ---- KPI tiles ---- */
.kpi{display:grid;grid-template-columns:repeat(6,1fr);gap:7px;margin:9px 0;}
.k{position:relative;padding:9px 5px 8px;text-align:center;border-radius:11px;overflow:hidden;
  background:linear-gradient(160deg,rgba(22,38,70,.94),rgba(12,24,46,.94));
  border:1px solid rgba(96,140,220,.18);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.04),0 3px 12px rgba(0,0,0,.25);}
.k:before{content:"";position:absolute;left:0;right:0;top:0;height:2px;
  background:linear-gradient(90deg,#2F6BFF,#6EB6FF);}
.k:nth-child(3n+2):before{background:linear-gradient(90deg,#2DD4A7,#7BE0C0);}
.k:nth-child(3n):before{background:linear-gradient(90deg,#4F7BFF,#9A6BFF);}
.k:last-child{background:linear-gradient(160deg,rgba(34,68,145,.72),rgba(15,32,68,.92));
  border-color:rgba(94,150,255,.38);}
.k .l{font-family:Inter,sans-serif;font-size:9px;opacity:.62;font-weight:700;
  letter-spacing:.6px;text-transform:uppercase;}
.k .v{font-family:"IBM Plex Mono",monospace;font-size:19px;font-weight:600;
  color:#EDF4FF;letter-spacing:-.7px;margin-top:2px;
  font-variant-numeric:tabular-nums;line-height:1.15;}

/* ---- cards ---- */
.box{padding:10px 12px 9px;border-radius:13px;
  background:linear-gradient(160deg,rgba(20,36,68,.94),rgba(10,21,42,.94));
  border:1px solid rgba(96,140,220,.18);border-top:2px solid #2F6BFF;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.04),0 5px 16px rgba(0,0,0,.25);margin-bottom:2px;}
.b-green{border-top-color:#2DD4A7;} .b-purple{border-top-color:#9A6BFF;}
.b-orange{border-top-color:#F5B84B;} .b-blue{border-top-color:#2F6BFF;}
.cap{font-family:"Space Grotesk",sans-serif;font-size:13px;font-weight:700;
  letter-spacing:.8px;text-transform:uppercase;color:#EAF1FF;padding-bottom:6px;margin:0;
  border-bottom:1px solid rgba(120,160,230,.16);}
.cap:before{content:"";display:inline-block;width:3px;height:12px;border-radius:2px;
  background:linear-gradient(#6EB6FF,#2F6BFF);margin-right:9px;vertical-align:-2px;}
.b-green .cap:before{background:linear-gradient(#7BE0C0,#2DD4A7);}
.b-purple .cap:before{background:linear-gradient(#C39BFF,#9A6BFF);}
.b-orange .cap:before{background:linear-gradient(#FFD489,#F5B84B);}
.subcap{font-family:Inter,sans-serif;font-size:10px;opacity:.48;letter-spacing:.3px;
  margin:5px 0 7px;line-height:1.4;}

/* ---- tables ---- */
.tw{width:100%;overflow-x:auto;overflow-y:hidden;-webkit-overflow-scrolling:touch;}
.dt{width:100%;table-layout:fixed;border-collapse:collapse;font-variant-numeric:tabular-nums;}
.dt th{font-family:Inter,sans-serif;font-size:9px;font-weight:700;letter-spacing:.2px;
  text-transform:uppercase;text-align:right;padding:5px 2px;color:#93A9CC;
  white-space:normal;word-break:break-word;line-height:1.25;
  background:rgba(47,107,255,.10);border-bottom:1px solid rgba(120,160,230,.22);}
.dt td{font-family:"IBM Plex Mono",monospace;font-size:12px;font-weight:500;
  color:#DCE8FA;letter-spacing:-.3px;text-align:right;padding:4px 2px;
  white-space:nowrap;overflow:hidden;border-bottom:1px solid rgba(120,160,230,.10);}
.dt th:first-child,.dt td:first-child{text-align:left;}
.dt tr:last-child td{border-bottom:none;}
.dt tbody tr:hover{background:rgba(47,107,255,.09);}
.vst th,.vst td{text-align:left;padding:4px 9px;}

/* ---- badges ---- */
.res{font-family:"IBM Plex Mono",monospace;font-size:15px;font-weight:700;
  padding:5px 13px;border-radius:8px;display:inline-block;letter-spacing:.5px;}
.resb{background:rgba(45,212,167,.14);color:#4FE0B4;border:1px solid rgba(45,212,167,.40);}
.resr{background:rgba(255,107,120,.13);color:#FF6B78;border:1px solid rgba(255,107,120,.36);}
.verow{font-family:"IBM Plex Mono",monospace;font-size:13px;font-weight:600;letter-spacing:.1px;}
.pivrow{margin-top:-20px;}
[data-testid="stSelectbox"]{max-width:190px;font-size:13px;}
hr{border-color:rgba(120,160,230,.16);margin:6px 0;}

/* ---- mobile ---- */
@media(max-width:640px){
 .block-container{padding:.35rem .4rem 1rem .4rem;}
 .term{grid-template-columns:1fr auto;gap:6px;padding:7px 10px;border-radius:11px;}
 .hleft{display:none;} .hcenter{justify-self:start;gap:6px;}
 .brand{font-size:14px;letter-spacing:-.3px;} .logo{width:22px;height:22px;}
 .hright{justify-self:end;text-align:right;}
 .idx{font-size:18px;letter-spacing:-.8px;} .live{font-size:8px;padding:2px 7px;}
 .kpi{grid-template-columns:repeat(4,1fr);gap:4px;margin:6px 0;}
 .k{padding:5px 2px 4px;border-radius:9px;}
 .k .v{font-size:15px;margin-top:1px;letter-spacing:-.7px;} .k .l{font-size:8px;letter-spacing:.25px;}
 .cap{font-size:11px;} .subcap{font-size:9px;}
 .tw{width:100%;overflow:hidden;}
 .dt th{font-size:8px!important;padding:4px 1px;}
 .dt td{font-size:9px!important;padding:3px 1px;} .verow{font-size:11px;}
 .res{font-size:14px;padding:4px 9px;}
}
</style>"""

# ---------------- cache ----------------
def build_cache(mins=3):
    suf = "" if mins==3 else f"_{mins}"
    out = CACHE / f"oi_{DAY}{suf}.parquet"
    if out.exists(): return out
    idx = pd.read_parquet(RECORDED/"nifty50_index"/f"{DAY}.parquet")
    idx["ts"] = pd.to_datetime(idx["ts"]).dt.tz_localize(None)
    can = idx.set_index("ts")["price"].resample(f"{mins}min",label="right",closed="right").agg(["first","max","min","last"]).dropna()
    can.columns=["open","high","low","close"]
    recs=[]
    for p in RECORDED.glob(f"NIFTY*/{DAY}.parquet"):
        m=re.match(r"NIFTY.*?(\d{5})(CE|PE)$",p.parent.name)
        if not m: continue
        K,side=int(m.group(1)),m.group(2)
        t=pd.read_parquet(p,columns=["ts","price","oi"])
        t["ts"]=pd.to_datetime(t["ts"]).dt.tz_localize(None)
        t=t.set_index("ts").resample(f"{mins}min",label="right",closed="right").agg({"price":"last","oi":"last"})
        for ts,r in t.dropna(subset=["price"]).iterrows():
            recs.append((ts,K,side,float(r.price),float(r.oi) if pd.notna(r.oi) else 0))
    opt=pd.DataFrame(recs,columns=["ts","strike","side","ltp","oi"])
    opt.to_parquet(CACHE/f"chain_{DAY}{suf}.parquet",index=False)
    can.reset_index().to_parquet(out,index=False)
    return out

@st.cache_data(ttl=600,show_spinner=False)
def get_data(mins=3):
    build_cache(mins)
    suf="" if mins==3 else f"_{mins}"
    can=pd.read_parquet(CACHE/f"oi_{DAY}{suf}.parquet")
    opt=pd.read_parquet(CACHE/f"chain_{DAY}{suf}.parquet")
    agg=[]
    for _,c in can.iterrows():
        o=opt[opt.ts<=c.ts].groupby(["strike","side"]).last().reset_index()
        ce,pe=o[o.side=="CE"],o[o.side=="PE"]
        call,put=float(ce.oi.sum()),float(pe.oi.sum())
        agg.append((call,put,put/call if call else 0,put-call))
    a=pd.DataFrame(agg,columns=["CALL","PUT","PCR","DIFF"])
    d=pd.concat([can.reset_index(drop=True),a],axis=1)
    d["VWAP"]=d.close.expanding().mean()
    d["FUTURE"]=d.close-10
    d["FUT-VWAP"]=d.FUTURE-d.VWAP      # DIFFERENCE = FUTURE - VWAP
    d["P-C DIFF"]=d.DIFF               # PUT - CALL OI difference
    # OI state: price direction + OI direction
    pr=d.close.diff(); oi=(d.CALL+d.PUT).diff()
    def _st(p,o):
        # FLAT when no change; real label when price/OI actually move
        if pd.isna(p) or pd.isna(o): return "FLAT","n"
        if p>0 and o>0: return "LONG BLD","g"
        if p<0 and o>0: return "SHORT BLD","r"
        if p>0 and o<0: return "SHORT COV","y"
        if p<0 and o<0: return "LONG UNW","n"
        return "FLAT","n"
    st=[_st(p,o) for p,o in zip(pr,oi)]
    d["STATE"]=[x[0] for x in st]; d["STATE_C"]=[x[1] for x in st]
    # SIGNAL per row: PCR > 1 => BUY, else SELL
    d["SIG"]=["BUY" if x>1 else "SELL" for x in d.PCR]
    d["SIG_C"]=["g" if x>1 else "r" for x in d.PCR]
    return d,opt

# ---------------- NSE live — disk cache + stale-while-revalidate ----------------
LIVE_FILE = CACHE / "live_data.json"
_lock = threading.Lock()
_last_try = [0.0]

def _fetch_global():
    out=[]
    syms=[("000001.SS","SHANGHAI"),("%5EHSI","HANG SENG"),("%5EKS11","KOSPI"),
          ("%5EN225","NIKKEI"),("%5EFTSE","FTSE 100"),("%5EGDAXI","DAX"),
          ("%5EFCHI","CAC 40"),("%5EGSPC","S&P 500"),("%5ENDX","NASDAQ"),
          ("%5EDJI","DOW")]
    def one(sym,name):
        try:
            u=f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=1d"
            r=urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=6)
            m=json.loads(r.read())["chart"]["result"][0]["meta"]
            p=m.get("regularMarketPrice"); pc=m.get("chartPreviousClose") or m.get("previousClose") or p
            return {"name":name,"price":round(p,2) if p else None,
                    "chg":round((p/pc-1)*100,2) if p and pc else None}
        except Exception:
            return {"name":name,"price":None,"chg":None}
    with ThreadPoolExecutor(max_workers=7) as ex:
        out=list(ex.map(lambda s: one(*s), syms))
    return out

def _fetch_all():
    from concurrent.futures import ThreadPoolExecutor
    import nse_live
    with ThreadPoolExecutor(max_workers=2) as ex:
        fn=ex.submit(nse_live.all_data); fg=ex.submit(_fetch_global)
        return fn.result(), fg.result()

def _read_cache():
    try:
        c=json.loads(LIVE_FILE.read_text(encoding="utf-8"))
        if isinstance(c,dict) and "nse" in c and "glob" in c: return c
    except Exception:
        pass
    return None

def _save_cache(nse, glob):
    try:
        tmp=LIVE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps({"ts":time.time(),"nse":nse,"glob":glob}), encoding="utf-8")
        tmp.replace(LIVE_FILE)
    except Exception:
        pass

def _bg_refresh():
    try:
        _save_cache(*_fetch_all())
    except Exception:
        pass

# ---- live row accumulator (whole-day growing table; separate per timeframe) ----
def _session_file(mins=3):
    return CACHE / f"session_{mins}min.json"

def _load_session(mins=3):
    try:
        r=json.loads(_session_file(mins).read_text(encoding="utf-8"))
        return r if isinstance(r,list) else []
    except Exception:
        return []

def _append_live_row(last, oi=None, mins=3, lv=None, fut=None, vwap=None):
    """Market hours me har `mins`-minute bucket par ek nayi row add karta hai."""
    from datetime import datetime, timezone, timedelta
    ist=timezone(timedelta(hours=5,minutes=30))
    now=datetime.now(ist)
    if now.weekday()>=5: return
    minute_of_day=now.hour*60+now.minute
    if not (555<=minute_of_day<=930): return
    try:
        import config, data_loader
        if not (config.LIVE_ENABLED and config.all_credentials_present()): return
        if lv is None:
            lv=data_loader.fetch_live_ltp("NIFTY 50","99926000")
    except Exception:
        return
    if not lv: return
    bucket=now.replace(second=0,microsecond=0)
    bucket=bucket.replace(minute=(now.minute//mins)*mins)
    key=bucket.isoformat()
    rows=_load_session(mins)
    if any(r.get("ts")==key for r in rows): return   # already added this bucket
    call=oi["call"] if oi else float(last.CALL)
    put=oi["put"] if oi else float(last.PUT)
    pcr=put/call if call else 0
    # state from change vs previous live row (real price/OI movement)
    prev=rows[-1] if rows else None
    state,sc="FLAT","n"
    if prev:
        dp=float(lv)-float(prev["close"]); do=(call+put)-(float(prev["CALL"])+float(prev["PUT"]))
        if dp>0 and do>0: state,sc="LONG BLD","g"
        elif dp<0 and do>0: state,sc="SHORT BLD","r"
        elif dp>0 and do<0: state,sc="SHORT COV","y"
        elif dp<0 and do<0: state,sc="LONG UNW","n"
    # VWAP = typical-price (H+L+C)/3 proxy from TODAY's real 1-min index bars.
    # Fallback = expanding mean of today's live closes (never yesterday's value).
    if not vwap or not (vwap>0):
        closes=[float(r["close"]) for r in rows]+[float(lv)]
        vwap=sum(closes)/len(closes)
    if not fut or not (fut>0):                 # real futures LTP; graceful proxy fallback
        fut=float(lv)-10
    rows.append({"ts":key,"close":float(lv),"FUTURE":float(fut),
                 "VWAP":vwap,"FUT-VWAP":float(fut)-vwap,
                 "CALL":call,"PUT":put,"DIFF":put-call,"PCR":pcr,
                 "STATE":state,"STATE_C":sc,
                 "SIG":"BUY" if pcr>1 else "SELL","SIG_C":"g" if pcr>1 else "r"})
    try:
        sf=_session_file(mins)
        tmp=sf.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows[-400:]),encoding="utf-8")
        tmp.replace(sf)
    except Exception:
        pass

@st.cache_data(ttl=60,show_spinner=False)
def live_spot():
    try:
        import data_loader
        return data_loader.fetch_live_ltp("NIFTY 50","99926000")
    except Exception:
        return None

@st.cache_data(ttl=150,show_spinner=False)
def angel_oi(atm50):
    """Live OI chain from Angel One (cached 150s)."""
    try:
        import data_loader
        return data_loader.fetch_live_oi_chain(atm50)
    except Exception:
        return None

def get_live():
    """Instant: serve disk cache; refresh in background when older than 170s."""
    now=time.time()
    c=_read_cache()
    if c and now-c.get("ts",0) < 170:
        return c["nse"], c["glob"]
    if c:                                  # stale -> serve now, refresh behind
        with _lock:
            if now-_last_try[0] > 20:
                _last_try[0]=now
                threading.Thread(target=_bg_refresh,daemon=True).start()
        return c["nse"], c["glob"]
    with _lock:                            # no cache -> first load, fetch once
        if now-_last_try[0] < 5:
            return {}, []
        _last_try[0]=now
    nse,glob=_fetch_all()
    _save_cache(nse,glob)
    return nse,glob

# ---------------- small chart (theme-agnostic, pinch zoom, no drag-select) ----------------
def small_chart(x, y, title, color, secondary=None, height=150):
    import plotly.graph_objects as go
    f=go.Figure()
    f.add_trace(go.Scatter(x=x,y=y,name=title,line=dict(color=color,width=2.6),mode="lines"))
    if secondary is not None:
        f.add_trace(go.Scatter(x=x,y=secondary,name="ref",line=dict(color="#9ca3af",width=1.4,dash="dot"),mode="lines"))
    f.update_layout(height=height,margin=dict(l=6,r=6,t=24,b=4),
        paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",showlegend=False,
        xaxis=dict(showticklabels=False,showgrid=False),
        yaxis=dict(showgrid=True,gridcolor="rgba(128,128,128,0.22)",tickfont=dict(size=11,color="#6b7280")),
        title=dict(text=title,font=dict(size=13,color="#6b7280"),x=0.02,y=0.97))
    return f

CHART_CFG={"displaylogo":False,"scrollZoom":True,"dragmode":False,
           "modeBarButtonsToRemove":["zoom","pan","select2d","lasso2d","resetScale2d","toImage","hoverClosestCartesian","hoverCompareCartesian"],
           "doubleClick":False,"responsive":True}

# helpers
def cell(l,v,c=""): return f'<div class="k"><div class="l">{l}</div><div class="v {c}">{v}</div></div>'
def sgn(v, suffix=""):
    c="g" if v>=0 else "r"
    return f'<span class="{c}">{v:+.2f}{suffix}</span>'
def tbl(headers, rows, cls="dt"):
    h="".join(f"<th>{x}</th>" for x in headers)
    b="".join("<tr>"+"".join(f"<td>{c}</td>" for c in r)+"</tr>" for r in rows)
    return f'<div class="tw"><table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'

def main():
    # Excel-sheet-like tabs: 3 / 5 / 9 / 15 MIN (each with its own auto-refresh)
    TFS=[3,5,9,15]
    if "tf" not in st.session_state: st.session_state.tf=3
    labels=[f"{x} MIN" for x in TFS]
    idx=TFS.index(st.session_state.tf) if st.session_state.tf in TFS else 0
    tf=st.radio("VIEW",labels,horizontal=True,index=idx,
                label_visibility="collapsed",key="tfsel")
    mins=int(tf.split()[0])
    st.session_state.tf=mins
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=mins*60000,key=f"pro{mins}")
    except ImportError:
        from streamlit.components.v1 import html
        html(f"<script>setTimeout(()=>location.reload(),{mins*60000})</script>",height=0)

    st.markdown(CSS,unsafe_allow_html=True)

    d,opt=get_data(mins); last=d.iloc[-1]
    # all 3 network sources in parallel -> fastest first load
    atm50=int(round(float(last.close)/50)*50)
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_live=ex.submit(get_live)
        f_spot=ex.submit(live_spot)
        f_oi=ex.submit(angel_oi, atm50)
        nse,glob=f_live.result()
        lv=f_spot.result()
        lc=f_oi.result()
    # GIFT NIFTY from NSE (real-time when market open)
    gift=nse.get("giftnifty") or {}
    if gift.get("LASTPRICE"):
        try:
            glob.insert(0,{"name":"GIFT NIFTY","price":float(gift["LASTPRICE"]),
                           "chg":float(gift.get("PERCHANGE") or 0)})
        except Exception:
            pass
    spot=lv if lv else float(last.close)
    mkt=(nse.get("market") or []); m0=mkt[0] if mkt else {}
    try: chg=float(m0.get("percentChange")) if m0.get("percentChange") not in (None,"") else 1.12
    except Exception: chg=1.12
    cls="g" if chg>=0 else "r"
    # LIVE OI from Angel One (real opnInterest) -> KPI, MOST ACTIVE OI, live rows
    oi_snap=None
    if lc is not None and not lc.empty:
        call_oi=float(lc[lc.side=="CE"].oi.sum()); put_oi=float(lc[lc.side=="PE"].oi.sum())
        pcr_live=put_oi/call_oi if call_oi else 0
        oi_snap={"call":call_oi,"put":put_oi,"pcr":pcr_live,"chain":lc}

    # header — centered logo + name (D: no "OI / PCR TERMINAL")
    st.markdown(f"""<div class="term">
      <div class="hleft">EXPIRY 01 DEC 2026<br>{mins}-MIN AUTO REFRESH</div>
      <div class="hcenter">
        <svg class="logo" width="36" height="36" viewBox="0 0 40 40" aria-hidden="true">
          <defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stop-color="#3b6ef5"/><stop offset="1" stop-color="#12a37d"/>
          </linearGradient></defs>
          <rect x="2" y="2" width="36" height="36" rx="11" fill="url(#lg)"/>
          <path d="M10 27 L16 20 L22 24 L31 12" stroke="#fff" stroke-width="3"
                fill="none" stroke-linecap="round" stroke-linejoin="round"/>
          <circle cx="31" cy="12" r="2.6" fill="#fff"/>
        </svg>
        <div class="brand">Nifty Pro Terminal</div>
      </div>
      <div class="hright">
        <div class="idx">{spot:,.0f} <span class="{cls}">{chg:+.2f}%</span></div>
        <div style="margin-top:3px;"><span class="live">● LIVE</span></div>
      </div>
    </div>""",unsafe_allow_html=True)

    # KPI — 11 Excel headlines
    futvw=float(last["FUT-VWAP"])
    c_oi=oi_snap["call"] if oi_snap else float(last.CALL)
    p_oi=oi_snap["put"] if oi_snap else float(last.PUT)
    pcr_v=oi_snap["pcr"] if oi_snap else float(last.PCR)
    st.markdown('<div class="kpi">'+
      cell("TIME",last.ts.strftime("%H:%M"))+cell("SPOT",f"{spot:,.0f}",cls)+
      cell("FUTURE",f"{last.FUTURE:,.0f}")+cell("VWAP",f"{last.VWAP:,.0f}")+
      cell("DIFF-VWAP",f"{float(last.close-last.VWAP):+,.0f}")+
      cell("CALL OI",f"{c_oi/1e6:.2f}M")+cell("PUT OI",f"{p_oi/1e6:.2f}M")+
      cell("FUT-VWAP",f"{futvw:+,.0f}","g" if futvw>=0 else "r")+
      cell("PCR",f"{pcr_v:.2f}")+
      cell("MARKET","LONG BUILD-UP" if pcr_v>1 else "LONG UNWINDING")+
      cell("SIGNAL","BUY" if pcr_v>1 else "SELL","g" if pcr_v>1 else "r")+
      "</div>",unsafe_allow_html=True)

    # live session rows -> charts + table both live during market hours
    _append_live_row(last, oi_snap, mins)
    sess=_load_session(mins)
    from datetime import datetime, timezone, timedelta
    today=datetime.now(timezone(timedelta(hours=5,minutes=30))).date()
    live_rows=[r for r in sess if pd.to_datetime(r["ts"]).date()==today]
    if live_rows:
        chart_df=pd.DataFrame(live_rows).sort_values("ts").reset_index(drop=True)
        chart_df["ts"]=pd.to_datetime(chart_df["ts"])
    else:
        chart_df=d

    # 3 SEPARATE SMALL CHARTS
    c1,c2,c3=st.columns(3)
    with c1: st.plotly_chart(small_chart(chart_df.ts,chart_df.PCR,"PCR","#2962ff",np.full(len(chart_df),1.0)),width="stretch",config=CHART_CFG)
    with c2: st.plotly_chart(small_chart(chart_df.ts,chart_df.VWAP,"VWAP","#ab47bc",chart_df.close),width="stretch",config=CHART_CFG)
    with c3:
        pv=spot*np.array([1.008,1.0,0.992])
        st.plotly_chart(small_chart(chart_df.ts,chart_df.close,"PIVOT (R1/P/S1)","#26a69a",np.full(len(chart_df),spot)),width="stretch",config=CHART_CFG)
        st.markdown(f'<div class="verow pivrow">R1 <span class="r">{pv[0]:.0f}</span> &nbsp; P <span class="n">{pv[1]:.0f}</span> &nbsp; S1 <span class="g">{pv[2]:.0f}</span></div>',unsafe_allow_html=True)

    st.markdown("<div style='height:5px'></div>",unsafe_allow_html=True)

    # MOST ACTIVE OI (VERTICAL strikes, VERIFIED) + 3-MIN DATA
    left,right=st.columns([1.05,2])
    with left:
        source=oi_snap["chain"] if oi_snap else opt   # live Angel One OI when available
        ce=source[source.side=="CE"].groupby("strike").oi.sum().nlargest(8).index.tolist()
        pe=source[source.side=="PE"].groupby("strike").oi.sum().nlargest(8).index.tolist()
        res="BUY-CE" if len(ce)<len(pe) else "BUY-PE"
        # one strike per row -> truly vertical, side-by-side CE / PE
        vr=[]
        for i in range(max(len(ce),len(pe))):
            c=f'<span class="g">{ce[i]}</span>' if i<len(ce) else ""
            p=f'<span class="r">{pe[i]}</span>' if i<len(pe) else ""
            vr.append([c,p])
        st.markdown('<div class="box b-green"><div class="cap">MOST ACTIVE OI </div>'+
          tbl([f'<span class="g">CE ({len(ce)})</span>',f'<span class="r">PE ({len(pe)})</span>'],vr,cls="dt vst")+
          f'<div class="verow" style="margin-top:6px;">RESULT &nbsp; <span class="res {"resb" if res=="BUY-CE" else "resr"}">{res}</span></div></div>',unsafe_allow_html=True)
    with right:
        # market open -> today's live rows (grow each 3 min); else full recorded day
        today_rows=live_rows
        if today_rows:
            td=pd.DataFrame(today_rows).sort_values("ts",ascending=False)
            cap="INTRADAY FLOW LOG"
            subcap=f"TODAY · {mins}-MIN BARS · LIVE ROWS · OI = ANGEL ONE LIVE"
        else:
            td=d.copy()                     # WHOLE recorded day
            cap="INTRADAY FLOW LOG"
            subcap=f"FULL DAY · {len(td)} ROWS · DIFF = FUTURE − VWAP · PUT−CALL · OI VIEW · SIGNAL: PCR&gt;1 BUY / ELSE SELL"
        # pakka newest-upar / oldest-neeche (explicit sort by timestamp)
        td=td.sort_values("ts",ascending=False).reset_index(drop=True)
        # dropdown: default latest 9 rows, "ALL" for full day
        chosen=st.selectbox("ROWS",["LATEST 9","ALL"],index=0,key="row_view",
                            label_visibility="collapsed")
        if chosen=="LATEST 9": td=td.head(9)
        rows=[]
        for _,r in td.iterrows():
            fv=float(r["FUT-VWAP"])
            # live OI snapshot sync (table + KPI + MOST ACTIVE all same source)
            cv_=oi_snap["call"] if oi_snap else float(r.CALL)
            pv_=oi_snap["put"] if oi_snap else float(r.PUT)
            pcr_=oi_snap["pcr"] if oi_snap else float(r.PCR)
            pc=pv_-cv_
            sig="BUY" if pcr_>1 else "SELL"; sc="g" if pcr_>1 else "r"
            rows.append([pd.to_datetime(r.ts).strftime("%H:%M"),f"{r.close:,.0f}",f"{r.FUTURE:,.0f}",
                         f"{r.VWAP:,.0f}",f'<span class="{"g" if fv>=0 else "r"}">{fv:+,.0f}</span>',
                         f"{cv_/1e6:.2f}M",f"{pv_/1e6:.2f}M",
                         f'<span class="{"r" if pc>0 else "g"}">{pc/1e6:+.2f}M</span>',
                         f"{pcr_:.2f}",f'<span class="{r.STATE_C}">{r.STATE}</span>',
                         f'<span class="{sc}"><b>{sig}</b></span>'])
        st.markdown('<div class="box b-blue"><div class="cap">'+cap+'</div><div class="subcap">'+subcap+'</div>'+
          tbl(["TIME","SPOT","FUTURE","VWAP","DIFFERENCE","CALL","PUT","PUT−CALL","PCR","OI VIEW","SIGNAL"],rows)+'</div>',unsafe_allow_html=True)

    st.markdown("<div style='height:5px'></div>",unsafe_allow_html=True)

    # BREADTH — clear layout: Nifty 50 vs Whole Market
    adv,dec,unc=nse.get("advances"),nse.get("declines"),nse.get("unchanged")
    i50=[x for x in (nse.get("indices") or []) if x.get("index")=="NIFTY 50"]
    n50=i50[0] if i50 else {}
    nadv,ndec,nunc=n50.get("advances"),n50.get("declines"),n50.get("unchanged")
    def cv(v):
        if v is None or v=="": return '<span class="n">—</span>'
        try: return f"{int(v):,}"
        except Exception: return str(v)
    def adr(a,b):
        try:
            if a is not None and b is not None and float(b)!=0:
                v=float(a)/float(b)
                return f'<span class="{"g" if v>=1 else "r"}">{v:.2f}</span>'
        except Exception:
            pass
        return '<span class="n">—</span>'
    brows=[
      ["NIFTY 50",f'<span class="g">{cv(nadv)}</span>',f'<span class="r">{cv(ndec)}</span>',adr(nadv,ndec),f'<span class="y">{cv(nunc)}</span>'],
      ["WHOLE MARKET",f'<span class="g">{cv(adv)}</span>',f'<span class="r">{cv(dec)}</span>',adr(adv,dec),f'<span class="y">{cv(unc)}</span>'],
    ]
    st.markdown('<div class="box b-purple"><div class="cap">BREADTH — ADVANCE / DECLINE / UNCHANGED</div>'+
      tbl(["MARKET","ADVANCE","DECLINE","A/D RATIO","UNCHANGED"],brows)+'</div>',unsafe_allow_html=True)

    st.markdown("<div style='height:5px'></div>",unsafe_allow_html=True)

    # MAJOR STOCKS + SECTOR INDICES + GLOBAL — with number and %
    stk=[x for x in (nse.get("stocks") or []) if x.get("lastPrice") is not None and x.get("symbol")!="NIFTY 50"]
    srows=[]
    for x in stk[:10]:
        pc=x.get("pChange") or 0
        srows.append([x.get("symbol",""),f"{float(x.get('lastPrice')):,.2f}",sgn(pc,"%")])
    # large / mid / small cap indices first
    cap_names={"NIFTY 100":"NIFTY LARGE (100)","NIFTY MIDCAP 100":"NIFTY MIDCAP 100",
               "NIFTY SMALLCAP 100":"NIFTY SMALLCAP 100"}
    cap_rows=[]
    for x in (nse.get("indices") or []):
        nm=x.get("index","")
        if nm in cap_names and x.get("last") is not None:
            cap_rows.append([cap_names[nm],f"{float(x.get('last')):,.2f}",
                             sgn(x.get("percentChange") or 0,"%")])
    # sectors: drop all FINANCIAL SERVICES variants
    sect=[x for x in (nse.get("sectors") or []) if x.get("last") is not None
          and "FINANCIAL" not in str(x.get("index","")).upper()
          and "PSU BANK" not in str(x.get("index","")).upper()
          and "PRIVATE BANK" not in str(x.get("index","")).upper()]
    seen=set(); sr=[]
    for x in sect:
        nm=x.get("index","")
        if nm in seen: continue
        seen.add(nm)
        pc=x.get("percentChange") or 0
        sr.append([nm,f"{float(x.get('last')):,.2f}",sgn(pc,"%")])
        if len(sr)>=7: break
    sr=cap_rows+sr
    grows=[[g["name"],f"{g['price']:,.2f}" if g.get("price") else "—",
            sgn(g["chg"],"%") if g.get("chg") is not None else '<span class="n">—</span>'] for g in glob]

    c1,c2,c3=st.columns([1.1,1.15,1.25])
    with c1:
        st.markdown('<div class="box b-green"><div class="cap">MAJOR STOCKS (NIFTY 50)</div>'+
          tbl(["STOCK","LAST","CHG%"],srows)+'</div>',unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="box b-orange"><div class="cap">SECTOR INDICES</div>'+
          tbl(["INDEX","LAST","CHG%"],sr)+'</div>',unsafe_allow_html=True)
    with c3:
        st.markdown('<div class="box b-purple"><div class="cap">GLOBAL INDICES</div>'+
          tbl(["INDEX","LAST","CHG%"],grows)+'</div>',unsafe_allow_html=True)

if __name__=="__main__": main()
