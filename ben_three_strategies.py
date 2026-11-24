"""Ben's 3 strategies adapted to Nifty 50.

CT -> IST mapping: 12:00 AM CT = 10:30 AM IST; 8:30 AM CT = 7:00 PM IST (not NSE).
Since NSE cash session is 09:15-15:30 IST, US overnight/premarket levels don't exist.
Adaptation:
  S1 Vault Break     : 30-min bars, "midnight open" -> session 09:15 open proxy;
                        noise barrier = 30% of 15-day ATR(14) added to open;
                        VWAP session; window 10:00-14:30 IST; entry next bar open;
                        TP/SL converted from $ to points via Nifty/point value.
  S2 VWAP Pullback   : 5-min (1-min->5-min proxy), opening range 09:15-09:30,
                        VWAP touch + reclaim, ADX>20 flat/falling (proxy: +DI>-DI).
  S3 Overnight ORB   : 15-min, overnight -> prior day 15:00-15:30 range thirds;
                        opening range 09:15-09:30; bias by open third; ADX>20;
                        SL=30% 15d ATR, TP=3R, 1 trade/day.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
import engine


def adx(df, n=14):
    up, dn = df.high.diff(), -df.low.diff()
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = df.atr
    pdi = 100 * pd.Series(plus).ewm(alpha=1/n).mean() / tr
    mdi = 100 * pd.Series(minus).ewm(alpha=1/n).mean() / tr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1/n).mean().fillna(0), pdi.fillna(0), mdi.fillna(0)


def prep():
    d = engine.add_indicators(data_loader.load_data(last_days=10**6, minutes=5))
    d["day"] = d["timestamp"].dt.date
    d["adx"], d["pdi"], d["mdi"] = adx(d)
    g = d.groupby("day")
    daily = pd.DataFrame({"C": g.close.last(), "H": g.high.max(), "L": g.low.min(),
                          "O": g.open.first()})
    daily["atr"] = pd.concat([daily.H-daily.L, (daily.H-daily.C.shift()).abs(),
                              (daily.L-daily.C.shift()).abs()], axis=1).max(axis=1).ewm(alpha=1/14).mean()
    daily["atr15"] = daily["atr"].rolling(15).mean()
    d["open"] = d["day"].map(daily.O.shift(1))
    d["noise"] = 0.30 * d["day"].map(daily.atr15.shift(1))
    d["on_hi"] = d["day"].map(daily.H.shift(1))
    d["on_lo"] = d["day"].map(daily.L.shift(1))
    return d, daily


def strat1(d):
    # 30-min bars resampled
    d30 = data_loader.resample(data_loader.load_data(last_days=10**6, minutes=1), 30)
    d30 = engine.add_indicators(d30)
    d30["day"] = d30["timestamp"].dt.date
    d30["hm"] = d30["timestamp"].dt.hour*60 + d30["timestamp"].dt.minute
    g = d30.groupby("day")
    daily = pd.DataFrame({"H": g.high.max(), "L": g.low.min(), "O": g.open.first()})
    daily["atr"] = pd.concat([daily.H-daily.L, (daily.H-daily.O).abs()],axis=1).max(axis=1).ewm(alpha=1/14).mean()
    daily["atr15"] = daily["atr"].rolling(15).mean()
    d30["noise"] = 0.30*d30["day"].map(daily.atr15.shift(1))
    d30["sesopen"] = d30["day"].map(daily.O)
    rows=[]; n=len(d30)
    for i in range(30, n-3):
        if 10*60 <= d30["hm"].iloc[i] <= 14*60+30 and d30["hm"].iloc[i+1] <= 14*60+30:
            if (d30.close.iloc[i] > d30["sesopen"].iloc[i]+d30["noise"].iloc[i] and
                d30.close.iloc[i] > d30["vwap"].iloc[i]):
                entry=d30.open.iloc[i+1]
                # $800 TP / $1500 SL on NQ ~ 40pts/75pts scaled to Nifty by ~1/20
                tp=entry+40; sl=entry-75
                pnl=np.nan
                for m in range(i+1, min(i+10,n)):
                    if d30.low.iloc[m]<=sl: pnl=-75; break
                    if d30.high.iloc[m]>=tp: pnl=40; break
                if np.isnan(pnl): pnl=d30.close.iloc[min(i+10,n)-1]-entry
                rows.append(pnl)
    return pd.Series(rows)


def strat2(d):
    # opening range 09:15-09:30 on 5-min; pullback to vwap + reclaim + ADX gate
    d2=d.copy()
    g=d2.groupby("day")
    orng=g.apply(lambda x: x[x.timestamp.dt.time<=pd.Timestamp("09:30").time()]["high"].max())
    d2["orh"]=d2["day"].map(orng)
    rows=[]; n=len(d2)
    for i in range(30, n-3):
        if pd.isna(d2["orh"].iloc[i]): continue
        armed = d2.close.iloc[i-1] > d2["orh"].iloc[i]
        touch = d2.low.iloc[i] <= d2.vwap.iloc[i]
        reclaim = d2.close.iloc[i] > d2.vwap.iloc[i] and d2.close.iloc[i] > d2.open.iloc[i]
        adxv = d2.adx.iloc[i]
        adxflat = adxv > 20 and adxv <= d2.adx.iloc[i-1]
        if armed and touch and reclaim and adxflat:
            entry=d2.open.iloc[i+1]
            tp=d2.high.iloc[i-5:i+1].max(); sl=d2.low.iloc[i-20:i+1].min()
            if tp<=entry or sl>=entry: continue
            pnl=np.nan
            for m in range(i+1,min(i+12,n)):
                if d2.low.iloc[m]<=sl: pnl=sl-entry;break
                if d2.high.iloc[m]>=tp: pnl=tp-entry;break
            if np.isnan(pnl): pnl=d2.close.iloc[min(i+12,n)-1]-entry
            rows.append(pnl)
    return pd.Series(rows)


def strat3(d):
    # 15-min ORB with prior-day thirds + ADX>20
    d15=data_loader.resample(data_loader.load_data(last_days=10**6,minutes=1),15)
    d15=engine.add_indicators(d15)
    d15["day"]=d15["timestamp"].dt.date
    g=d15.groupby("day")
    daily=pd.DataFrame({"H":g.high.max(),"L":g.low.min(),"C":g.close.last()})
    daily["atr"]=pd.concat([daily.H-daily.L,(daily.H-daily.C.shift()).abs()],axis=1).max(axis=1).ewm(alpha=1/14).mean()
    daily["atr15"]=daily["atr"].rolling(15).mean()
    d15["on_hi"]=d15["day"].map(daily.H.shift(1)); d15["on_lo"]=d15["day"].map(daily.L.shift(1))
    d15["noise"]=0.30*d15["day"].map(daily.atr15.shift(1))
    d15["adx"],_,_=adx(d15)
    d15["hm"]=d15["timestamp"].dt.hour*60+d15["timestamp"].dt.minute
    rows=[]
    for day,sub in d15.groupby("day"):
        if len(sub)<6: continue
        on_hi,on_lo,noise=sub.on_hi.iloc[0],sub.on_lo.iloc[0],sub.noise.iloc[0]
        if any(pd.isna(x) for x in (on_hi,on_lo,noise)): continue
        range_=on_hi-on_lo
        first=sub.iloc[0]
        pos=(first.open-on_lo)/range_ if range_>0 else 0.5
        bias=1 if pos>0.66 else -1 if pos<0.34 else 0
        if not bias: continue
        orh,orl=first.high,first.low
        for k in range(1,len(sub)-1):
            if sub.adx.iloc[k]<=20: continue
            if bias==1 and sub.close.iloc[k]>orh: entry=sub.open.iloc[k+1]; sl=entry-noise; tp=entry+3*noise; break
            if bias==-1 and sub.close.iloc[k]<orl: entry=sub.open.iloc[k+1]; sl=entry+noise; tp=entry-3*noise; break
        else: continue
        pnl=np.nan
        for m in range(k+1,len(sub)):
            if bias==1:
                if sub.low.iloc[m]<=sl: pnl=-noise;break
                if sub.high.iloc[m]>=tp: pnl=3*noise;break
            else:
                if sub.high.iloc[m]>=sl: pnl=-noise;break
                if sub.low.iloc[m]<=tp: pnl=3*noise;break
        if np.isnan(pnl): pnl=sub.close.iloc[-1]-entry
        rows.append({"bias":"LONG" if bias==1 else "SHORT","pnl":pnl})
    return pd.DataFrame(rows)


def show(name, x):
    if len(x)==0: print(f"{name}: koi trade nahi"); return
    s=pd.Series(x) if not isinstance(x,pd.Series) else x
    pnl=s if isinstance(s,pd.Series) and s.name is None else (s.pnl if hasattr(s,'pnl') else s)
    print(f"{name:24s} n={len(pnl):5d} win={(pnl>0).mean()*100:5.1f}% avg={pnl.mean():+7.2f}")


if __name__=="__main__":
    d,_=prep()
    print("BEN STRATEGIES on Nifty (5y)\n")
    s1=strat1(d); show("1) Vault Break (30m)",s1)
    s2=strat2(d); show("2) VWAP Pullback+ADX",s2)
    s3=strat3(d)
    if len(s3):
        print(f"3) Overnight ORB (15m) n={len(s3)} win={(s3.pnl>0).mean()*100:.1f}% avg={s3.pnl.mean():+.2f}")
        for b,sub in s3.groupby("bias"):
            print(f"    {b:6s} n={len(sub):4d} win={(sub.pnl>0).mean()*100:5.1f}%")
    else: show("3) Overnight ORB",s3)
