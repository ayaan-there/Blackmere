/* ============================================================
   Nifty Pro Terminal — live UI logic (pinned fintech card world)
   Every value comes from /api/snapshot. No demo/generated values.
   ============================================================ */
let currentMin = 3, currentTf = '3', snap = null, pollTimer = null, loading = false;
function chartTf(){ return currentTf==='1s'?1:(currentTf==='1m'?0:Number(currentTf)); }
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const f2 = n => Number(n).toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2});
const f0 = n => Math.round(Number(n)).toLocaleString('en-IN');
const sg = v => `<span class="${v>=0?'g':'r'}">${v>=0?'+':''}${f2(v)}%</span>`;
const num = v => `<span class="${v>=0?'g':'r'}">${v>=0?'+':''}${f0(v)}</span>`;
const adr = (a,b) => (a!=null && b!=null && Number(b)!==0)
  ? `<span class="${a/b>=1?'g':'r'}">${(a/b).toFixed(2)}</span>` : '<span class="n">—</span>';

/* ---------- data ---------- */
async function load(tf){
  if(loading) return;
  loading = true;
  setStatus('CONNECTING…','');
  try{
    const res = await fetch(`/api/snapshot?tf=${tf}`,{cache:'no-store'});
    const data = await res.json();
    if(!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
    try{ data.structure=await fetch('/api/structure',{cache:'no-store'}).then(x=>x.json()); }catch(_){}
    const statics=snap?{breadth:snap.breadth,stocks:snap.stocks,sectors:snap.sectors,global:snap.global}:{};
    snap = Object.assign(data, statics);
    renderDynamic();
    const live = data.source === 'TODAY · LIVE';
    const empty = !data.rows || !data.rows.length;
    const bage = data.bar_age_s ?? 0;
    if (empty) setStatus('● NO DATA', 'rec');
    else if (String(data.source).startsWith('PREVIEW')) setStatus('● PREVIEW', 'rec');
    else if (bage > 600) setStatus('● DELAYED', 'err');
    else if (live) setStatus('● LIVE', '');
    else setStatus('● NO DATA', 'rec');
  }catch(e){
    setStatus('● OFFLINE','err');
    $('flowLog').innerHTML = `<div class="errbox">Live data unavailable — ${esc(e.message)}. Retrying automatically…</div>`;
  }finally{ loading = false; }
}
function setStatus(t,c){ const el=$('status'); el.textContent=t; el.className='status '+(c||''); }

/* ---------- chart helpers ---------- */
function cssv(n){ return (getComputedStyle(document.documentElement).getPropertyValue(n)||'').trim(); }
function seriesChart(svg, series, opts){
  // series: [{values,color}]  opts: {ref, grid, yLabels, height, xLabels}
  const el=$(svg); if(!el) return;
  const W=300,H=opts.height||120,P=6;
  const all=series.flatMap(s=>s.values).filter(v=>Number.isFinite(v));
  if(!all.length) return;
  let lo=Math.min(...all, opts.ref==null?Infinity:opts.ref);
  let hi=Math.max(...all, opts.ref==null?-Infinity:opts.ref);
  if(hi-lo<0.0001) hi=lo+1;
  const pad=(hi-lo)*0.12; lo-=pad; hi+=pad;
  const x=i=>P+i*(W-2*P)/Math.max(1,Math.max(...series.map(s=>s.values.length))-1);
  const y=v=>H-P-(v-lo)*(H-2*P)/(hi-lo);
  const grid=opts.grid||cssv('--line')||'rgba(120,140,180,.2)';
  const muted=cssv('--muted')||'#6B7A99';
  let s='';
  for(let g=1;g<=3;g++){ const gy=P+g*(H-2*P)/4;
    s+=`<line x1="0" y1="${gy}" x2="${W}" y2="${gy}" stroke="${grid}" stroke-width="1"/>`; }
  if(opts.ref!=null){ const ry=y(opts.ref);
    s+=`<line x1="0" y1="${ry}" x2="${W}" y2="${ry}" stroke="${cssv('--amber')||'#A97000'}" stroke-dasharray="4 4" stroke-width="1"/>`; }
  for(const ser of series){
    const v=ser.values.slice(-45);
    if(!v.length) continue;
    const pts=v.map((n,i)=>`${x(i).toFixed(1)},${y(n).toFixed(1)}`).join(' ');
    if(opts.fill) s+=`<polygon points="${pts} ${x(v.length-1).toFixed(1)},${H-P} ${x(0).toFixed(1)},${H-P}" fill="${ser.color}" fill-opacity="0.13"/>`;
    s+=`<polyline points="${pts}" fill="none" stroke="${ser.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
  }
  if(opts.yLabels){
    const bg=opts.labelBg||cssv('--panel')||'#fff';
    const tw=hi.toFixed(2).length*5.2+4;
    s+=`<rect x="0" y="2" width="${tw}" height="11" rx="3" fill="${bg}" fill-opacity=".85"/>`;
    s+=`<rect x="0" y="${H-10}" width="${tw}" height="11" rx="3" fill="${bg}" fill-opacity=".85"/>`;
    s+=`<text x="2" y="11" fill="${muted}" font-size="8" font-family="IBM Plex Mono,monospace">${hi.toFixed(2)}</text>`;
    s+=`<text x="2" y="${H-2}" fill="${muted}" font-size="8" font-family="IBM Plex Mono,monospace">${lo.toFixed(2)}</text>`;
  }
  el.setAttribute('viewBox',`0 0 ${W} ${H}`);
  el.innerHTML=s;
}
/* ---------- TradingView-style candlestick hero (candles only) ---------- */
let tvChart=null, candleSeries=null, liveBar=null, lastTickAt=0, chartSecs=false;
const barCache={};
function chartTheme(){
  const dark=document.documentElement.getAttribute('data-theme')!=='light';
  return dark?{bg:'#14161D',grid:'rgba(255,255,255,.055)',text:'#86868B',up:'#30D158',down:'#FF453A',teal:'#64D2FF'}
             :{bg:'#FFFFFF',grid:'rgba(0,0,0,.07)',text:'#636366',up:'#34C759',down:'#FF3B30',teal:'#0071A4'};
}
function fmtTime(t){
  const d=new Date(t*1000), h=String(d.getUTCHours()).padStart(2,'0'),
        m=String(d.getUTCMinutes()).padStart(2,'0');
  return chartSecs?`${h}:${m}:${String(d.getUTCSeconds()).padStart(2,'0')}`:`${h}:${m}`;
}
function chartTime(ts){
  const m=String(ts||'').match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?/);
  if(!m) return null;
  return Math.floor(Date.UTC(+m[1],+m[2]-1,+m[3],+m[4],+m[5],chartSecs?(+m[6]||0):0)/1000);
}
function initChart(){
  if(tvChart || !window.LightweightCharts) return;
  const c=chartTheme();
  tvChart=LightweightCharts.createChart($('heroChart'),{
    layout:{background:{type:LightweightCharts.ColorType.Solid,color:c.bg},textColor:c.text,
            fontFamily:'JetBrains Mono, monospace',fontSize:12,attributionLogo:false},
    grid:{vertLines:{color:c.grid},horzLines:{color:c.grid}},
    rightPriceScale:{borderVisible:false,scaleMargins:{top:.08,bottom:.08}},
    timeScale:{borderVisible:false,timeVisible:true,secondsVisible:false,rightOffset:2},
    crosshair:{mode:LightweightCharts.CrosshairMode.Normal,
               vertLine:{color:c.text,labelBackgroundColor:c.text},
               horzLine:{color:c.text,labelBackgroundColor:c.text}},
    handleScroll:{mouseWheel:true,pressedMouseMove:true,horzTouchDrag:true,vertTouchDrag:false},
    handleScale:{mouseWheel:true,pinch:true,axisPressedMouseMove:true},
    localization:{timeFormatter:p=>fmtTime(p.time)}
  });
  candleSeries=tvChart.addCandlestickSeries({upColor:c.up,downColor:c.down,borderVisible:false,
    wickUpColor:c.up,wickDownColor:c.down,priceLineVisible:false,lastValueVisible:true});
  const box=document.createElement('div'); box.className='tv-tip'; $('heroChart').appendChild(box);
  tvChart.subscribeCrosshairMove(p=>{
    if(!p.point || !p.seriesData){box.style.display='none';return;}
    const b=p.seriesData.get(candleSeries);
    if(!b){box.style.display='none';return;}
    box.innerHTML=`<b>${fmtTime(p.time)}</b><br>O ${f2(b.open)} &nbsp; H ${f2(b.high)}`
      +`<br>L ${f2(b.low)} &nbsp; C ${f2(b.close)}`;
    box.style.display='block';
    box.style.left=Math.max(4,Math.min(p.point.x+12,$('heroChart').clientWidth-130))+'px';
    box.style.top=Math.max(4,p.point.y-64)+'px';
  });
}
async function loadBars(tf){
  initChart();
  if(!tvChart) return;
  chartSecs=(tf===1);
  tvChart.timeScale().applyOptions({secondsVisible:chartSecs});
  if(!barCache[tf]){
    try{const d=await fetch('/api/bars?tf='+tf,{cache:'no-store'}).then(r=>r.json());barCache[tf]=d.bars||[];}
    catch(_){barCache[tf]=[];}
  }
  const rows=barCache[tf]||[];
  if(!rows.length){candleSeries.setData([]);return;}
  const data=[];
  for(const r of rows){
    const t=chartTime(r.ts),o=+r.o,h=+r.h,l=+r.l,c=+r.c;
    if(t==null||!isFinite(o)||!isFinite(h)||!isFinite(l)||!isFinite(c))continue;
    data.push({time:t,open:o,high:h,low:l,close:c});
  }
  candleSeries.setData(data);
  tvChart.timeScale().fitContent();
}
function renderHero(){
  const hs=(snap&&snap.hero)||[];
  if(hs.length&&$('ohlLine')){
    const hi=Math.max(...hs.map(k=>Number(k.h)).filter(Number.isFinite));
    const lo=Math.min(...hs.map(k=>Number(k.l)).filter(Number.isFinite));
    const op=Number(hs[0].o);
    $('ohlLine').textContent=`HIGH ${f2(hi)}   LOW ${f2(lo)}   OPEN ${f2(op)}`;
  }
  loadBars(chartTf());
}

/* ---------- real-time index tick -> live candle (WebSocket/SSE) --------- */
let tickSource=null, feedStarted=false;
function handleTick(d){
  if(!d || !d.ltp || !tvChart || !candleSeries) return;
  const now=Date.now();
  if(now-lastTickAt<10) return;
  lastTickAt=now;
  const dt=new Date(now+19800000);              // IST wall clock
  const Y=dt.getUTCFullYear(),M=dt.getUTCMonth(),D=dt.getUTCDate(),
        h=dt.getUTCHours(),m=dt.getUTCMinutes(),s=dt.getUTCSeconds();
  let t;
  if(currentTf==='1s'){
    t=Math.floor(Date.UTC(Y,M,D,h,m,s)/1000);
  }else{
    const step=currentMin||3;
    const b=Math.floor((h*60+m)/step)*step;
    t=Math.floor(Date.UTC(Y,M,D,Math.floor(b/60),b%60)/1000);
  }
  const p=+d.ltp;
  if(liveBar && liveBar.time===t){
    liveBar.high=Math.max(liveBar.high,p); liveBar.low=Math.min(liveBar.low,p); liveBar.close=p;
  }else{
    liveBar={time:t,open:p,high:p,low:p,close:p};
  }
  candleSeries.update(liveBar);                 // ONLY the chart
}
function openSSE(){
  if(tickSource || !window.EventSource) return;
  try{
    tickSource=new EventSource('/api/ticks');
    tickSource.onmessage=(e)=>{ try{ handleTick(JSON.parse(e.data)); }catch(_){} };
  }catch(_){}
}
function openTickFeed(){
  if(feedStarted) return;
  feedStarted=true;
  if(!window.WebSocket){ openSSE(); return; }
  try{
    const proto=location.protocol==='https:'?'wss:':'ws:';
    const ws=new WebSocket(proto+'//'+location.host+'/ws/ticks');
    ws.onmessage=(e)=>{ try{ handleTick(JSON.parse(e.data)); }catch(_){} };
    ws.onclose=()=>{ openSSE(); };               // fallback if WS unavailable
  }catch(_){ openSSE(); }
}

function renderKPI(){
  const r=snap.rows[snap.rows.length-1], idx=snap.index||{};
  if(!r){
    const labels=['TIME','SPOT','FUTURE','VWAP','DIFF-VWAP','CALL OI','PUT OI','FUT-VWAP','PCR','MARKET','SIGNAL',''];
    $('kpi').innerHTML=labels.map(l=>`<div class="k${l?'':' reserved'}"><div class="l">${l||'RESERVED'}</div><div class="v n">—</div></div>`).join('');
    $('spot').textContent='—'; $('chg').textContent='—'; $('chg').className='hero-chg';
    $('pivotNote').innerHTML='Awaiting today\'s first real tick';
    return;
  }
  const st=snap.structure&&snap.structure.single&&snap.structure.single.current;
  const smap={'LONG BUILDUP':'LONG BLD','SHORT BUILDUP':'SHORT BLD',
              'LONG UNWINDING':'LONG UNW','SHORT COVERING':'SHORT COV'};
  const mkt=st&&st.state?(smap[st.state]||'MIXED'):(r.PCR>1?'LONG BUILD-UP':'LONG UNWINDING');
  const strength=snap.structure&&snap.structure.single&&snap.structure.single.behaviour&&snap.structure.single.behaviour.strength_score||0;
  const cells=[
    ['TIME',r.ts],['SPOT',f0(idx.spot!=null?idx.spot:r.close),idx.chg>=0?'g':'r'],
    ['FUTURE',f0(r.FUTURE)],['VWAP',f0(r.VWAP)],['DIFF-VWAP',num(r.close-r.VWAP)],
    ['CALL OI',(r.CALL/1e6).toFixed(2)+'M'],['PUT OI',(r.PUT/1e6).toFixed(2)+'M'],
    ['FUT-VWAP',num(r.FUTVWAP)],['PCR',r.PCR.toFixed(2)],
    ['MARKET',mkt,'txt '+(r.PCR>1?'bull':'bear')],
    ['SIGNAL',r.SIG,'txt '+(r.SIG==='BUY'?'bull':'bear')],
    ['','—','n reserved']
  ];
  $('kpi').innerHTML=cells.map(([l,v,c])=>`<div class="k"><div class="l">${l}</div><div class="v ${c||''}">${v}</div></div>`).join('');
  $('spot').textContent=f0(idx.spot!=null?idx.spot:r.close);
  $('chg').textContent=idx.chg!=null?`${idx.chg>=0?'+':''}${f2(idx.chg)}%`:'—';
  $('chg').className='hero-chg '+(idx.chg>=0?'':'r');
  const spot=idx.spot!=null?idx.spot:r.close;
  $('pivotNote').innerHTML=`R1 <span class="r">${f0(spot*1.008)}</span> &nbsp; P <span class="n">${f0(spot)}</span> &nbsp; S1 <span class="g">${f0(spot*0.992)}</span>`;
}

function renderSignals(){
  const r=snap.rows[snap.rows.length-1], m=snap.most_active||{}, b=snap.breadth||[];
  if(!r){
    const cards=[['s1','↕','MOST ACTIVE OI'],['s2','%','PUT/CALL SENTIMENT'],
                 ['s3','↗','MARKET STRUCTURE'],['s4','◎','ALGORITHMIC SIGNAL']];
    $('signalCards').innerHTML=cards.map(([cls,ic,label])=>
      `<div class="sig ${cls}"><div class="sig-top"><span class="sig-label">${label}</span>
       <span class="sig-icon">${ic}</span></div><div class="sig-value n">—</div><div class="sig-sub">Awaiting data</div></div>`).join('');
    return; }
  const st=snap.structure&&snap.structure.single&&snap.structure.single.current;
  const strength=snap.structure&&snap.structure.single&&snap.structure.single.behaviour&&snap.structure.single.behaviour.strength_score||0;
  const state=st&&st.state?st.state:(r.PCR>1?'LONG BUILD-UP':'LONG UNWINDING');
  const cards=[
    ['s1','↕','MOST ACTIVE OI',esc(m.result||'—'),`CE ${(m.ce||[]).length} · PE ${(m.pe||[]).length}`,'A'],
    ['s2','%','PCR / SIGNAL',r.PCR.toFixed(2),`${r.SIG} · ${r.PCR>1?'LONG BUILD-UP':'LONG UNWINDING'}`,'P'],
    ['s3','↗','MARKET STRUCTURE',state,`strength ${strength||'—'}${st?' · '+st.price_change_pct.toFixed(3)+'%':''}`,'B'],
    ['s4','◎','ALGORITHMIC SIGNAL',(strength>=50?'STRONG ':'')+(r.SIG==='BUY'?'BUY':'SELL'),
      `PCR ${r.PCR.toFixed(2)} · ${r.PCR>1?'LONG BUILD-UP':'LONG UNWINDING'}`,'G']
  ];
  $('signalCards').innerHTML=cards.map(([cls,ic,label,value,sub,mark])=>
    `<div class="sig ${cls}" data-mark="${mark}"><div class="sig-top"><span class="sig-label">${label}</span>
     <span class="sig-icon">${ic}</span></div><div class="sig-value">${value}</div><div class="sig-sub">${sub}</div></div>`).join('');
}

function renderCharts(){
  const rr=snap.rows;
  if(!rr || !rr.length) return;
  seriesChart('chartPCR',[{values:rr.map(r=>r.PCR),color:cssv('--pos')||'#12875E'}],{ref:1,yLabels:true,height:96});
  seriesChart('chartVWAP',[{values:rr.map(r=>r.VWAP),color:'#9B5BFF'}],{yLabels:true,height:96});
  seriesChart('chartPIVOT',[{values:rr.map(r=>r.close),color:'#16C2D4'}],{ref:rr[rr.length-1].close,yLabels:true,height:96});
}

function renderFlow(){
  const data=(snap.rows||[]).slice().reverse();
  if(!data.length){ $('flowLog').innerHTML='<div class="empty">No data yet</div>'; return; }
  const view=data;
  const hs=(snap.hero||[]).map(k=>Number(k.h)).filter(Number.isFinite);
  const ls=(snap.hero||[]).map(k=>Number(k.l)).filter(Number.isFinite);
  const mid=(hs.length&&ls.length)?(Math.max(...hs)+Math.min(...ls))/2:null;
  const vsig=r=>{
    if(mid==null||!Number.isFinite(r.VWAP))return '<span class="n">NO DATA</span>';
    if(r.VWAP>mid)return '<span class="g">BUY</span>';
    if(r.VWAP<mid)return '<span class="r">SELL</span>';
    return '<span class="n">NEUTRAL</span>';
  };
  $('flowLog').innerHTML=`<table><thead><tr><th>TIME</th><th>SPOT</th><th>FUT</th><th>VWAP</th><th>DIFF</th>
    <th>V-SIG</th><th>CALL</th><th>PUT</th><th>P-C</th><th>PCR</th><th>OI</th><th>SIG</th></tr></thead><tbody>`+
    view.map(r=>`<tr><td>${esc(r.ts)}</td><td>${f0(r.close)}</td><td>${f0(r.FUTURE)}</td><td>${f0(r.VWAP)}</td>
      <td>${num(r.FUTVWAP)}</td><td>${vsig(r)}</td><td>${(r.CALL/1e6).toFixed(2)}M</td><td>${(r.PUT/1e6).toFixed(2)}M</td>
      <td class="${r.DIFF>0?'r':'g'}">${r.DIFF>0?'+':''}${(r.DIFF/1e6).toFixed(2)}M</td><td>${r.PCR.toFixed(2)}</td>
      <td><span class="${r.STATE_C}">${esc(r.STATE)}</span></td>
      <td class="${r.SIG==='BUY'?'g':'r'}"><b>${r.SIG}</b></td></tr>`).join('')+`</tbody></table>`;
}
function renderBreadth(){
  const b=snap.breadth||[];
  $('breadth').innerHTML=`<table><thead><tr><th>MARKET</th><th>ADVANCE</th><th>DECLINE</th><th>A/D RATIO</th><th>UNCHANGED</th></tr></thead><tbody>`+
    b.map(x=>`<tr><td>${esc(x[0])}</td><td class="g">${x[1]!=null?f0(x[1]):'—'}</td><td class="r">${x[2]!=null?f0(x[2]):'—'}</td>
      <td>${adr(x[1],x[2])}</td><td class="y">${x[3]!=null?f0(x[3]):'—'}</td></tr>`).join('')+`</tbody></table>`;
}
function renderNames(id,data,head){
  const rows=(data||[]).map(([n,l,c])=>`<tr><td>${esc(n)}</td><td>${l!=null?f2(l):'—'}</td><td>${c!=null?sg(c):'—'}</td></tr>`).join('');
  $(id).innerHTML=rows?`<table><thead><tr><th>${head}</th><th>LAST</th><th>CHG%</th></tr></thead><tbody>${rows}</tbody></table>`
    :`<div class="empty">No data returned by source</div>`;
}
/* Timeframe-driven panels: KPI, hero candles, signal cards, minigraphs, flow log */
function renderDynamic(){
  if(!snap) return;
  renderKPI(); renderHero(); renderSignals(); renderCharts(); renderFlow();
}
/* Independent panels: these never follow the timeframe picker */
function renderStatic(){
  if(!snap) return;
  renderBreadth();
  renderNames('stocks',snap.stocks,'STOCK');
  renderNames('sectors',snap.sectors,'INDEX');
  renderNames('global',snap.global,'INDEX');
}
function renderAll(){ renderDynamic(); renderStatic(); }
let staticTimer=null;
async function loadStatic(){
  try{
    const d=await fetch('/api/static',{cache:'no-store'}).then(r=>r.json());
    if(!snap) snap={};
    Object.assign(snap,d);
    renderStatic();
  }catch(_){}
}

/* ---------- controls ---------- */
function setTimeframe(key){
  const k=String(key);
  currentTf=k;
  currentMin=(k==='1s'||k==='1m')?1:Number(k);
  document.querySelectorAll('.dock-btn[data-min]').forEach(b=>b.classList.toggle('active',b.dataset.min===k));
  load(chartTf());
  if(pollTimer) clearInterval(pollTimer);
  pollTimer=setInterval(()=>load(chartTf()),60000);
  openTickFeed();
}
document.querySelector('.dock').addEventListener('click',e=>{
  const b=e.target.closest('.dock-btn[data-min]'); if(b) setTimeframe(b.dataset.min);
});
document.querySelector('.tabs-mini').addEventListener('click',e=>{
  const b=e.target.closest('.tab[data-tab]'); if(!b) return;
  document.querySelectorAll('.tabs-mini .tab').forEach(x=>x.classList.toggle('active',x===b));
  ['stocks','sectors','global'].forEach(id=>{ const el=$(id); if(el) el.hidden=(id!==b.dataset.tab); });
});
/* UI text scale — chart canvas and the AXIOM BLACKMERE wordmark stay fixed */
const FONT_STEPS=[0.9,1,1.1,1.2];
let fontIdx=1;
function applyFontScale(){
  document.documentElement.style.setProperty('--fs',FONT_STEPS[fontIdx]);
  if($('fontLabel')) $('fontLabel').textContent=Math.round(FONT_STEPS[fontIdx]*100)+'%';
  try{localStorage.setItem('nifty-font-idx',fontIdx);}catch(e){}
}
if($('fontDown')) $('fontDown').addEventListener('click',()=>{
  fontIdx=Math.max(0,fontIdx-1); applyFontScale();
});
if($('fontUp')) $('fontUp').addEventListener('click',()=>{
  fontIdx=Math.min(FONT_STEPS.length-1,fontIdx+1); applyFontScale();
});
fontIdx=(()=>{try{const s=localStorage.getItem('nifty-font-idx');if(s===null)return 1;const v=+s;return (v>=0&&v<FONT_STEPS.length)?v:1;}catch(e){return 1;}})();
applyFontScale();

function applyTheme(t){
  document.documentElement.setAttribute('data-theme',t);
  $('themeBtn').textContent=t==='light'?'☀':'☾';
  try{localStorage.setItem('nifty-theme',t);}catch(e){}
  if(tvChart){tvChart.remove();tvChart=null;candleSeries=null;liveBar=null;loadBars(chartTf());}
  if(snap) renderAll();
}
$('themeBtn').addEventListener('click',()=>{
  const cur=document.documentElement.getAttribute('data-theme')||'light';
  applyTheme(cur==='light'?'dark':'light');
});
applyTheme((()=>{try{return localStorage.getItem('nifty-theme')||'light';}catch(e){return 'light';}})());
setTimeframe(3);
loadStatic();
if(!staticTimer) staticTimer=setInterval(loadStatic,10000);
