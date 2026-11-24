"""MASTER REPORT: all strategies numbered + cross-instrument test.

Instruments : Nifty 50 index, Nifty BEES ETF (real parquet), Nifty options
              (only 2 recorded days -> labelled LIMITED).
Timeframes  : 5m and 15m.
Method      : unified signal->2R outcome runner; top strategies re-tested live
              from code, rest use already-run backtest results (documented).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import config
import data_loader
import engine

HOLD_F = 16
HOLD_T = 12


def load(kind, tf):
    p = config.DATA_DIR / "raw" / kind / "1m"
    chunks = [data_loader._normalise(pd.read_parquet(f))
              for f in sorted(p.rglob("*.parquet"))]
    return engine.add_indicators(data_loader.resample(pd.concat(chunks, ignore_index=True), tf))


def outcome(d, i, direc, risk, rr=2.0, hold=HOLD_F):
    c, h, l = (d[k].to_numpy() for k in ("close", "high", "low"))
    days = d["timestamp"].dt.date.to_numpy()
    entry = c[i]
    tp = entry + rr*risk if direc==1 else entry - rr*risk
    sl = entry - risk if direc==1 else entry + risk
    for m in range(i+1, min(i+hold, len(d))):
        if days[m] != days[i]: break
        if direc==1:
            if l[m]<=sl: return -1
            if h[m]>=tp: return rr
        else:
            if h[m]>=sl: return -1
            if l[m]<=tp: return rr
    return (c[min(i+hold,len(d))-1]-entry)*direc/risk


def strat_vwap_struct(d):
    c,o,h,l,vw,atr=(d[k].to_numpy() for k in ("close","open","high","low","vwap","atr"))
    sig=[]
    for i in range(120,len(d)-HOLD_F-2):
        if pd.isna(vw[i]) or pd.isna(atr[i]): continue
        hh=h[i-1]>h[i-3]; hl=l[i-1]>l[i-3]; lh=h[i-1]<h[i-3]; ll=l[i-1]<l[i-3]
        if c[i]>vw[i] and hh and hl and abs(l[i]-vw[i])<=0.5*atr[i] and c[i]>o[i]: sig.append((i,1))
        elif c[i]<vw[i] and lh and ll and abs(h[i]-vw[i])<=0.5*atr[i] and c[i]<o[i]: sig.append((i,-1))
    return sig

def strat_vwap_close_stop(d):
    # same signals, close-based SL (better variant)
    return strat_vwap_struct(d)

def strat_liquidity_refill(d):
    c,o,h,l,atr=(d[k].to_numpy() for k in ("close","open","high","low","atr"))
    rng=h-l; av=pd.Series(rng).rolling(5).mean().shift(1).to_numpy()
    comp=pd.Series(rng).rolling(4).max().shift(1).to_numpy()
    imp=(rng>1.8*av)&(rng>1.3*comp)&(av>0)
    sig=[]; i=6
    while i<len(d)-HOLD_F-1:
        if not imp[i]: i+=1; continue
        direc=1 if c[i]>o[i] else -1 if c[i]<o[i] else 0
        if not direc: i+=1; continue
        j=i+1; up=h[i]-0.15*rng[i]; dn=l[i]+0.15*rng[i]
        ok=(l[j]>=up and c[j]>o[j]) if direc==1 else (h[j]<=dn and c[j]<o[j])
        if not ok: i+=1; continue
        for k in range(j+1,min(j+8,len(d)-HOLD_F)):
            if (h[k]>=h[i]) if direc==1 else (l[k]<=l[i]):
                sig.append((k,direc)); break
        i=j+1
    return sig

def strat_pivot3(d):
    c,o,h,l,atr=(d[k].to_numpy() for k in ("close","open","high","low","atr"))
    g=d.groupby(d["timestamp"].dt.date)
    H=g.high.max().shift(1); L=g.low.min().shift(1); C=g.close.last().shift(1)
    day=d["timestamp"].dt.date
    P=(H+L+C)/3
    R1=2*P-L; S1=2*P-H
    d2=d.assign(P=P.reindex(day).values,R1=R1.reindex(day).values,S1=S1.reindex(day).values)
    sig=[]
    for i in range(80,len(d2)-HOLD_F-2):
        p,r1,s1=(d2[k].iloc[i] for k in ("P","R1","S1"))
        if any(pd.isna(x) for x in (p,r1,s1)): continue
        if c[i]>r1 and all(c[i-k]>o[i-k] for k in (1,2,3)): sig.append((i,1))
        elif c[i]<s1 and all(c[i-k]<o[i-k] for k in (1,2,3)): sig.append((i,-1))
    return sig

def strat_otf(d):
    c,h,l=(d[k].to_numpy() for k in ("close","high","low"))
    sig=[]
    for i in range(30,len(d)-HOLD_T-2):
        hh=h[i]>h[i-1] and l[i]>l[i-1] and c[i]>h[i-1]
        ll=h[i]<h[i-1] and l[i]<l[i-1] and c[i]<l[i-1]
        if hh: sig.append((i,1))
        elif ll: sig.append((i,-1))
    return sig

STRATS = {
  "VWAP+Structure Pullback": strat_vwap_struct,
  "Liquidity Refill C1+C2": strat_liquidity_refill,
  "Pivot+3 green candles": strat_pivot3,
  "One-Time Framing": strat_otf,
}

def run(d, sigfn, close_stop=False):
    sig = sigfn(d)
    if not sig: return 0, 0, 0
    a = d["atr"].to_numpy()
    res = []
    for i,direc in sig:
        risk = a[i]
        if pd.isna(risk) or risk<=0: continue
        if close_stop:
            c,h,l=(d[k].to_numpy() for k in ("close","high","low"))
            days=d["timestamp"].dt.date.to_numpy()
            entry=c[i]; tp=entry+2*risk if direc==1 else entry-2*risk
            sl=entry-risk if direc==1 else entry+risk
            out=0.0
            for m in range(i+1,min(i+HOLD_F,len(d))):
                if days[m]!=days[i]: break
                bad=(c[m]<=sl) if direc==1 else (c[m]>=sl)
                good=(h[m]>=tp) if direc==1 else (l[m]<=tp)
                if bad: out=-1;break
                if good: out=2;break
            if out==0: out=(c[min(i+HOLD_F,len(d))-1]-entry)*direc/risk
            res.append(out)
        else:
            res.append(outcome(d,i,direc,risk))
    s=pd.Series(res)
    return len(s), round((s>0).mean()*100,1), round(s.mean(),3)


def main():
    print("="*78)
    print("MASTER REPORT — numbered strategies x instrument x timeframe")
    print("="*78)
    # registry of all previously run backtests (Nifty index, best variant)
    REG = [
      (1,"VWAP first-touch scalp","price action",79.9,"tight-stop artifact"),
      (2,"Look Above/Below Fail→POC","reversal",81.8,"final target only 16%"),
      (3,"ATR-band dip LONG","reversal",80.1,"n=136, verify"),
      (4,"Liquidity Refill C1+C2","price action",68.5,"+2.2R"),
      (5,"Ben Vault Break","breakout",67.8,""),
      (6,"Payday 13th→17th (swing)","seasonality",67.8,"monthly"),
      (7,"VWAP+Structure Pullback","price action",66.1,"+0.86R"),
      (8,"Conti VWAP drift","price action",62.8,"negative R:R"),
      (9,"Hurst+AC breakout LONG","trend",57.0,""),
      (10,"OTF regime filter","trend",57.0,"5-day swing"),
      (11,"Body+Liquidity Grab","price action",56.4,""),
      (12,"Value migration 1R","trend",51.8,""),
      (13,"Turtle Soup sweep+reversal","reversal",51.4,""),
      (14,"Pietro trend continuation","trend",51.0,""),
      (15,"PBD breakout","breakout",48.1,"n=54"),
      (16,"OB sweep early","reversal",45.0,""),
      (17,"Low-Effort high-vol","breakout",45-48,""),
      (18,"Aapki Pivot+3green","breakout",43.1,""),
      (19,"Andrea VAH breakout","breakout",41.1,""),
      (20,"NR4 compression 60m","breakout",40.8,""),
      (21,"VAH/VAL breakout","breakout",41.1,""),
      (22,"ICC short","trend",33.4,"weak"),
      (23,"3-touch range","reversal",35.2,""),
      (24,"VWAP+21EMA pullback","price action",33.5,""),
      (25,"Forced participation","reversal",30.8,""),
      (26,"Gold-open impulse","reversal",30.7,""),
      (27,"Gap and go","breakout",29.5,""),
      (28,"Ellie VAL failed auction","reversal",34.4,""),
      (29,"OB sweep retest","reversal",33.9,""),
      (30,"Henrik single-print","reversal",39.2,""),
      (31,"CRT 3-candle","reversal",19.7,""),
      (32,"VWAP 2SD fade","reversal",25.6,""),
      (33,"Liquidity sweep+EMA","reversal",23.9,""),
      (34,"Tom three-in-line","breakout",24.1,""),
      (35,"Tom balance breakout","breakout",23.8,""),
      (36,"Macro FX framework","n/a","N/A","FX only, N/A"),
      (37,"Gamma/heatmap frameworks","n/a","N/A","data nahi"),
    ]
    print("\n--- NUMBERED REGISTRY (Nifty index, best variant so far) ---")
    for no,name,cat,win,note in REG:
        print(f"{no:2d}. {name:32s} {cat:12s} {str(win):6s}% {note}")

    print("\n--- CROSS-INSTRUMENT RE-TEST (top 4, 5m & 15m) ---")
    print(f"{'Strategy':26s} {'INDEX5m':>16s} {'INDEX15m':>16s} {'BEES5m':>16s} {'BEES15m':>16s}")
    idx5=load("nifty50_index",5); idx15=load("nifty50_index",15)
    bees5=load("nifty50_etf",5); bees15=load("nifty50_etf",15)
    for name,fn in STRATS.items():
        cells=[]
        for d in (idx5,idx15,bees5,bees15):
            n,w,e=run(d,fn)
            cells.append(f"{w}%/{n}")
        print(f"{name:26s} " + " ".join(f"{c:>16s}" for c in cells))
    print("\n(OPTIONS: only 2 recorded days -> separate limited test)")
    print("  CE/PE tick test on 19 & 21 Nov: pivot+3green gave 1 signal, target hit (+Rs40).")


if __name__=="__main__":
    main()
