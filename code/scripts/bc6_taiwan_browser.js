// BC6: Taiwan real-data base case.  Run in a browser tab opened at
//   https://api.cnyes.com/media/api/v1/newslist/category/tw_stock?limit=1
// (see bc6_taiwan_browser.md).  Output = summary statistics only.

// ---------------------------------------------------------------- 1. crawl cnyes tw_stock news, day by day
window.__cr = {items: [], dayTotals: {}, done: {}, errors: [], running: true, req: 0, bytes: 0, started: Date.now(), cur: null};
{
const BASE='https://api.cnyes.com/media/api/v1/newslist/category/tw_stock';
const TZ=8*3600;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function dayStart(ds){const [y,m,d]=ds.split('-').map(Number); return Date.UTC(y,m-1,d)/1000 - TZ;}
function days(a,b){const out=[]; let t=Date.UTC(...a.split('-').map((v,i)=>i==1?v-1:+v)); const e=Date.UTC(...b.split('-').map((v,i)=>i==1?v-1:+v)); while(t<=e){out.push(new Date(t).toISOString().slice(0,10)); t+=86400000;} return out;}
async function getJSON(url){
  for (let a=0;a<4;a++){
    try{ const r=await fetch(url); window.__cr.req++; const s=await r.text(); window.__cr.bytes+=s.length; if(r.ok) return JSON.parse(s); window.__cr.errors.push([url.slice(-60),'HTTP '+r.status]); }
    catch(e){ window.__cr.errors.push([url.slice(-60),String(e)]); }
    await sleep(8000*(a+1));
  }
  return null;
}
async function crawl(list, delay){
  for (const ds of list){
    if (window.__cr.done[ds]) continue;
    window.__cr.cur=ds;
    const s=dayStart(ds), e=s+86399; let page=1, last=1, got=0, total=null, ok=true;
    do {
      const j=await getJSON(`${BASE}?startAt=${s}&endAt=${e}&limit=30&page=${page}`);
      if(!j||!j.items){ ok=false; break; }
      const it=j.items; last=it.last_page||1; total=it.total;
      for (const x of (it.data||[])){ window.__cr.items.push([x.newsId, x.publishAt, (x.stock||[]).join(','), x.title||'', x.categoryName||'']); got++; }
      page++; await sleep(delay);
    } while(page<=last);
    window.__cr.dayTotals[ds]=[total, got];
    if (ok) window.__cr.done[ds]=true;
  }
  window.__cr.running=false; window.__cr.finished=Date.now();
}
crawl(days('2024-09-30','2026-09-30'), 700);
}

// ---------------------------------------------------------------- 2. prices: cnyes chart API (TWSE numbers) + US
window.__U = ['2330','2317','2454','2308','2382','2881','2891','2882','2412','3711','2303','2886','2884','2357','1216','2885','3231','2892','2345','6669'];
async function fetchPrices(){
  const syms = window.__U.map(c=>`TWS:${c}:STOCK`).concat(['TWS:TSE01:INDEX','TWS:0050:STOCK','GI:IXIC:INDEX','GI:SOX:INDEX','GI:DJI:INDEX','USS:TSM:STOCK','USS:NVDA:STOCK']);
  const from=Math.floor(Date.now()/1000), to=Math.floor(Date.UTC(2024,5,1)/1000);   // note: from > to
  window.__px = {};
  for (const s of syms){
    const r=await fetch(`https://ws.api.cnyes.com/ws/api/v1/charting/history?resolution=D&symbol=${encodeURIComponent(s)}&from=${from}&to=${to}`);
    const j=await r.json(); const d=j.data||{}; const n=(d.t||[]).length; const rows=[];
    for(let i=n-1;i>=0;i--){ rows.push({date:new Date(d.t[i]*1000).toISOString().slice(0,10), o:d.o[i], h:d.h[i], l:d.l[i], c:d.c[i], v:(d.v||[])[i]}); }
    window.__px[s]=rows; await new Promise(r=>setTimeout(r,500));
  }
}
// await fetchPrices();

// ---------------------------------------------------------------- 3. ex-dividend / split dates (from Yahoo events, 2026-10-19)
window.__EX = {"1216":["2024-08-01","2025-07-31","2026-07-30"],"2303":["2024-07-02","2025-06-24","2026-07-08"],"2308":["2024-06-18","2025-06-17","2026-06-17"],"2317":["2024-07-02","2025-07-02","2026-07-02"],"2330":["2024-06-13","2024-09-12","2024-12-12","2025-03-18","2025-06-12","2025-09-16","2025-12-11","2026-03-17","2026-06-11","2026-09-16"],"2345":["2024-07-31","2025-07-30","2026-07-30"],"2357":["2024-07-03","2025-06-26","2026-07-01"],"2382":["2025-06-30","2026-07-16"],"2412":["2024-07-04","2025-07-03","2026-07-09"],"2454":["2024-07-04","2025-01-02","2025-07-03","2026-01-06","2026-07-07"],"2881":["2024-07-19","2025-07-01","2026-07-01","2024-09-09","2025-09-25"],"2882":["2024-07-01","2025-06-30","2026-06-30"],"2884":["2024-07-26","2025-07-22","2026-07-01"],"2885":["2024-06-27","2025-07-01","2026-07-21","2024-08-12","2025-08-12","2026-08-18"],"2886":["2024-08-08","2025-08-07","2026-08-13"],"2891":["2024-07-15","2025-07-14","2026-07-13"],"2892":["2024-08-08","2025-08-07","2026-08-11"],"3231":["2024-06-25","2025-06-03","2026-07-08"],"3711":["2024-07-01","2025-07-02","2026-07-03"],"6669":["2024-06-11","2025-06-24","2026-06-22","2026-09-02"]};
window.__SPL = {"2881":[["2024-09-09",1050,1000],["2025-09-25",1025,1000]],"2884":[["2024-07-26",1020.0332,1000],["2025-07-22",1010.01514,1000]],"2885":[["2024-08-12",1020,1000],["2025-08-12",1030,1000],["2026-08-18",1040,1000]],"2886":[["2024-08-08",1030,1000]],"2892":[["2024-08-08",1030,1000],["2025-08-07",1025,1000]],"6669":[["2026-09-02",2982.7947,1000]]};

// ---------------------------------------------------------------- 4. build the (stock, trading day) table
window.__build = function(){
  const U=window.__U, px=window.__px, items=window.__cr.items, EX=window.__EX, SPL=window.__SPL;
  const cal=px['TWS:TSE01:INDEX'].map(r=>r.date); const K=cal.length;
  const t0=d=>{const [y,m,dd]=d.split('-').map(Number); return Date.UTC(y,m-1,dd)/1000;};
  const openT=cal.map(d=>t0(d)+3600), closeT=cal.map(d=>t0(d)+19800), lateT=cal.map(d=>t0(d)+2700);   // 09:00, 13:30, 08:45 Taipei
  const aligned=sym=>{const m=Object.fromEntries(px[sym].map(r=>[r.date,r])); return cal.map(d=>m[d]||null);};
  const lagMean=(arr,k,a,b)=>{let s=0,n=0; for(let j=k-b;j<=k-a;j++){ if(j>=0&&arr[j]!=null){s+=arr[j];n++;} } return n>=Math.ceil((b-a+1)/2)?s/n:null;};
  const us=sym=>{const rows=px[sym]; const m={}; for(let i=1;i<rows.length;i++){const a=rows[i-1],b=rows[i]; m[b.date]={ret:Math.log(b.c/a.c), rng:Math.log(Math.max(Math.log(b.h/b.l),1e-4)), gapd:(t0(b.date)-t0(a.date))/86400};} return m;};
  const IX=us('GI:IXIC:INDEX'), SOX=us('GI:SOX:INDEX'), TSM=us('USS:TSM:STOCK');
  const usDates=px['GI:IXIC:INDEX'].map(r=>r.date);
  const usFeat=new Array(K).fill(null);
  for(let k=1;k<K;k++){ const lo=cal[k-1], hi=cal[k]; const ds=usDates.filter(u=>u>=lo&&u<hi); if(!ds.length){usFeat[k]={n:0,ix:0,sox:0,tsm:0,tsmMiss:1,rngix:null,rngsox:null}; continue;}
    let ix=0,sox=0,tsm=0,miss=0; for(const u of ds){ ix+=IX[u]?IX[u].ret:0; sox+=SOX[u]?SOX[u].ret:0; if(TSM[u]&&TSM[u].gapd<=4) tsm+=TSM[u].ret; else miss=1; }
    const last=ds[ds.length-1]; usFeat[k]={n:ds.length, ix, sox, tsm, tsmMiss:miss, rngix:IX[last]?IX[last].rng:null, rngsox:SOX[last]?SOX[last].rng:null}; }
  const I=aligned('TWS:TSE01:INDEX'); const trI=new Array(K).fill(null), gapI=new Array(K).fill(null), ocI=new Array(K).fill(null);
  for(let k=1;k<K;k++){ const r=I[k],p=I[k-1]; if(r&&p){ trI[k]=Math.log(Math.max(Math.log(Math.max(r.h,p.c)/Math.min(r.l,p.c)),1e-3)); gapI[k]=Math.log(r.o/p.c); ocI[k]=Math.log(r.c/r.o);} }
  const Uset=new Set(U); const FLN=['rev','earn','div','analyst','react','corp','disp'];
  const FL={rev:/營收/, earn:/財報|EPS|每股純益|每股盈餘|獲利|法說|季報|年報|毛利率|營益率|淨利/, div:/股利|除息|除權|配息|殖利率|填息/, analyst:/目標價|評等|調升|調降|上修|下修|外資報告|看好|看淡/, react:/漲停|跌停|大漲|大跌|勁揚|重挫|走高|走低|翻紅|翻黑|收盤|收紅|收黑|漲幅|跌幅|創高|新高|新低|領漲|領跌|急漲|急跌|收漲|收跌|週漲|週跌|漲逾|跌逾|攻上|站上|跌破|失守|買超|賣超/, corp:/併購|收購|合併|訂單|擴產|投資|合作|設廠|建廠|增資|減資|庫藏股/, disp:/處置|注意股|警示/};
  const POS=/創新高|新高|成長|增加|優於預期|上修|調升|看好|大漲|漲停|利多|強勁|攀升|飆|旺|樂觀|突破/g, NEG=/衰退|減少|低於預期|下修|調降|看淡|大跌|跌停|利空|疲弱|重挫|虧損|下滑|跌破|悲觀|保守|下跌/g;
  const z=()=>new Array(K).fill(0);
  const cnt={}; for(const c of U){ cnt[c]={over:z(),sess:z(),late:z(),sent:z(),fl:Object.fromEntries(FLN.map(f=>[f,z()]))}; }
  const mkt={over:z(),sess:z(),late:z()};
  const seen=new Set(); const st={items:0,dup:0,over:0,sess:0,late:0,out:0,tagged:0,taggedU:0,taggedUover:0, tagsTotal:0};
  for(const it of items){ const [id,T,tags,title]=it; if(seen.has(id)){st.dup++; continue;} seen.add(id); st.items++;
    let lo=0,hi=K-1,j=K; while(lo<=hi){const mid=(lo+hi)>>1; if(closeT[mid]>T){j=mid;hi=mid-1;} else lo=mid+1;}
    if(j>=K){st.out++; continue;}
    const b=T>=openT[j]?'sess':(T>=lateT[j]?'late':'over'); st[b]++; mkt[b][j]++;
    const tg=tags?tags.split(','):[]; if(tg.length){st.tagged++; st.tagsTotal+=tg.length;}
    let hitU=false;
    for(const c of tg){ if(!Uset.has(c)) continue; hitU=true; cnt[c][b][j]++; if(b==='over'){ for(const f of FLN) if(FL[f].test(title)) cnt[c].fl[f][j]++; cnt[c].sent[j]+=(title.match(POS)||[]).length-(title.match(NEG)||[]).length; } }
    if(hitU){st.taggedU++; if(b==='over') st.taggedUover++;}
  }
  const rows=[]; const perStock={};
  for(const [ci,code] of U.entries()){
    const R=aligned(`TWS:${code}:STOCK`); const ex=new Set(EX[code]||[]); const V=R.map(r=>r&&r.v>0?r.v:null);
    for(const [sd,num,den] of (SPL[code]||[])){ const f=num/den; for(let k=0;k<K;k++) if(cal[k]<sd&&V[k]!=null) V[k]*=f; }
    const tr=z().map(()=>null), rng=z().map(()=>null), oc=z().map(()=>null), gap=z().map(()=>null), lv=z().map(()=>null), trRaw=z().map(()=>null);
    for(let k=1;k<K;k++){ const r=R[k],p=R[k-1]; if(!r) continue; rng[k]=Math.log(Math.max(Math.log(r.h/r.l),1e-3)); oc[k]=Math.log(r.c/r.o); if(V[k]!=null) lv[k]=Math.log(V[k]);
      if(p&&!ex.has(cal[k])){ const x=Math.log(Math.max(r.h,p.c)/Math.min(r.l,p.c)); trRaw[k]=x; tr[k]=Math.log(Math.max(x,1e-3)); gap[k]=Math.log(r.o/p.c);} }
    const abv=z().map(()=>null); for(let k=0;k<K;k++){ const m=lagMean(lv,k,1,20); if(lv[k]!=null&&m!=null) abv[k]=lv[k]-m; }
    let nNewsDays=0,nDays=0,sumOver=0;
    for(let k=23;k<K;k++){ const d=cal[k]; if(d<'2024-10-01'||d>'2026-09-30') continue;
      const C=cnt[code]; nDays++; if(C.over[k]>0) nNewsDays++; sumOver+=C.over[k];
      const hd=tr[k-1]!=null?tr[k-1]:lagMean(tr,k,1,2), hw=lagMean(tr,k,1,5), hm=lagMean(tr,k,1,22);
      const mk1=trI[k-1], mk5=lagMean(trI,k,1,5), u=usFeat[k];
      if(tr[k]==null||hd==null||hw==null||hm==null||mk1==null||mk5==null||!u||u.rngix==null||abv[k-1]==null||abv[k]==null) continue;
      const abv5=lagMean(abv,k,1,5);
      rows.push({code, ci, k, date:d, y_tr:tr[k], y_rng:rng[k], y_abv:abv[k], trRaw:trRaw[k], oc:oc[k], gap:gap[k],
        f:{hd,hw,hm,mk1,mk5,gapdays:(t0(cal[k])-t0(cal[k-1]))/86400, abv1:abv[k-1], abv5:abv5==null?0:abv5,
           usabsix:Math.abs(u.ix), usabssox:Math.abs(u.sox), usrngix:u.rngix, usrngsox:u.rngsox, usabstsm:Math.abs(u.tsm), ustsmmiss:u.tsmMiss, usn:u.n,
           usix:u.ix, ussox:u.sox, ustsm:u.tsm,
           l_over:Math.log1p(C.over[k]), any_over:C.over[k]>0?1:0, l_prev:Math.log1p(C.sess[k-1]), l_mover:Math.log1p(mkt.over[k]), l_mprev:Math.log1p(mkt.sess[k-1]),
           l_rev:Math.log1p(C.fl.rev[k]), l_earn:Math.log1p(C.fl.earn[k]), l_div:Math.log1p(C.fl.div[k]), l_analyst:Math.log1p(C.fl.analyst[k]), l_react:Math.log1p(C.fl.react[k]), l_corp:Math.log1p(C.fl.corp[k]), l_disp:Math.log1p(C.fl.disp[k]),
           sent:C.sent[k], l_sess:Math.log1p(C.sess[k])}});
    }
    perStock[code]={newsDayShare:+(nNewsDays/nDays).toFixed(3), meanOver:+(sumOver/nDays).toFixed(2)};
  }
  const idx=[]; for(let k=23;k<K;k++){ const d=cal[k]; if(d<'2024-10-01'||d>'2026-09-30') continue; const u=usFeat[k]; if(gapI[k]==null||ocI[k]==null||!u) continue; idx.push({date:d, gap:gapI[k], oc:ocI[k], usix:u.ix, ussox:u.sox, ustsm:u.tsm, ustsmmiss:u.tsmMiss, l_mover:Math.log1p(mkt.over[k])}); }
  window.__ds={rows, idx, st, perStock, cal};
  return {nRows:rows.length, nIdx:idx.length, st};
};

// ---------------------------------------------------------------- 5. fixed-split models (train 2024-10..2025-06, val 2025-07..09, test 2025-10..2026-09)
window.__models = function(opts={}){
  const {rows, idx}=window.__ds; const U=window.__U;
  const TRAIN_END='2025-06-30', VAL_END='2025-09-30';
  const split=d=> d<=TRAIN_END?0:(d<=VAL_END?1:2);
  let seed=12345; const rnd=()=>{seed|=0; seed=seed+0x6D2B79F5|0; let t=Math.imul(seed^seed>>>15,1|seed); t=t+Math.imul(t^t>>>7,61|t)^t; return ((t^t>>>14)>>>0)/4294967296;};
  function solve(A,b){ const n=b.length; const M=A.map((r,i)=>[...r,b[i]]);
    for(let c=0;c<n;c++){ let p=c; for(let r=c+1;r<n;r++) if(Math.abs(M[r][c])>Math.abs(M[p][c])) p=r; const tmp=M[c]; M[c]=M[p]; M[p]=tmp; const d=M[c][c]; if(Math.abs(d)<1e-12) continue;
      for(let r=0;r<n;r++){ if(r===c) continue; const f=M[r][c]/d; if(f===0) continue; const Mr=M[r], Mc=M[c]; for(let k=c;k<=n;k++) Mr[k]-=f*Mc[k]; } }
    return M.map((r,i)=>Math.abs(r[i])<1e-12?0:r[n]/r[i]); }
  function design(cols, fitMask){ // standardized cols + stock dummies (unpenalized)
    const n=rows.length, p=cols.length; const mu=new Array(p).fill(0), sd=new Array(p).fill(0); let nf=0;
    for(let i=0;i<n;i++) if(fitMask[i]){ nf++; for(let a=0;a<p;a++) mu[a]+=rows[i].f[cols[a]]; }
    for(let a=0;a<p;a++) mu[a]/=nf;
    for(let i=0;i<n;i++) if(fitMask[i]) for(let a=0;a<p;a++){ const v=rows[i].f[cols[a]]-mu[a]; sd[a]+=v*v; }
    for(let a=0;a<p;a++) sd[a]=Math.sqrt(sd[a]/nf)||1;
    const X=rows.map(r=>{ const x=new Float64Array(p+U.length); for(let a=0;a<p;a++) x[a]=(r.f[cols[a]]-mu[a])/sd[a]; x[p+r.ci]=1; return x;});
    return {X, p};
  }
  function ridge(X,y,mask,alpha,p){ const q=X[0].length; const A=Array.from({length:q},()=>new Float64Array(q)); const b=new Float64Array(q);
    for(let i=0;i<X.length;i++){ if(!mask[i]) continue; const x=X[i], yi=y[i]; for(let a=0;a<q;a++){ const xa=x[a]; if(xa===0) continue; b[a]+=xa*yi; const Aa=A[a]; for(let c=a;c<q;c++) Aa[c]+=xa*x[c]; } }
    for(let a=0;a<q;a++){ for(let c=0;c<a;c++) A[a][c]=A[c][a]; if(a<p) A[a][a]+=alpha; }
    return solve(A.map(r=>Array.from(r)), Array.from(b)); }
  const dot=(x,w)=>{let s=0; for(let a=0;a<w.length;a++) s+=x[a]*w[a]; return s;};
  const sp=rows.map(r=>split(r.date)); const trM=sp.map(s=>s===0), vaM=sp.map(s=>s===1), fitM=sp.map(s=>s<=1), teM=sp.map(s=>s===2);
  function fitPredict(cols, y){ const {X,p}=design(cols, fitM); let best=null, bestA=null;
    for(const a of [0.1,1,10,100,1000,10000]){ const w=ridge(X,y,trM,a,p); let s=0,n=0; for(let i=0;i<X.length;i++) if(vaM[i]){ const e=y[i]-dot(X[i],w); s+=e*e; n++; } const mse=s/n; if(best==null||mse<best){best=mse; bestA=a;} }
    const w=ridge(X,y,fitM,bestA,p); return {pred:X.map(x=>dot(x,w)), alpha:bestA}; }
  const teIdx=rows.map((r,i)=>i).filter(i=>teM[i]); const teDates=[...new Set(teIdx.map(i=>rows[i].date))].sort();
  const byDay={}; for(const i of teIdx){ (byDay[rows[i].date]=byDay[rows[i].date]||[]).push(i); }
  const stockMean=(y)=>{ const s=new Array(U.length).fill(0), n=new Array(U.length).fill(0); rows.forEach((r,i)=>{ if(fitM[i]){ s[r.ci]+=y[i]; n[r.ci]++; } }); return rows.map(r=>s[r.ci]/n[r.ci]); };
  function r2(y,pred,bench,list){ let a=0,b=0; for(const i of list){ a+=(y[i]-pred[i])**2; b+=(y[i]-bench[i])**2; } return 1-a/b; }
  function bootR2(y,preds,bench,reps=1000){ // per-day sums
    const D=teDates.map(d=>byDay[d]); const sse=preds.map(p=>D.map(L=>L.reduce((s,i)=>s+(y[i]-p[i])**2,0))); const sst=D.map(L=>L.reduce((s,i)=>s+(y[i]-bench[i])**2,0));
    const out=preds.map(()=>[]), dif=[];
    for(let r=0;r<reps;r++){ let t=0; const e=preds.map(()=>0); for(let j=0;j<D.length;j++){ const q=Math.floor(rnd()*D.length); t+=sst[q]; for(let m=0;m<preds.length;m++) e[m]+=sse[m][q]; } for(let m=0;m<preds.length;m++) out[m].push(1-e[m]/t); dif.push(e); }
    const ci=a=>{const s=[...a].sort((x,y)=>x-y); return [+s[Math.floor(0.025*s.length)].toFixed(4), +s[Math.floor(0.975*s.length)-1].toFixed(4)];};
    return {ci:out.map(ci), deltaCI:(a,b)=>ci(out[b].map((v,i)=>v-out[a][i]))}; }
  function auc(sc,lb){ const id=sc.map((s,i)=>i).sort((a,b)=>sc[a]-sc[b]); let i=0, sp=0, np=0, nn=0; while(i<id.length){ let j=i; while(j+1<id.length&&sc[id[j+1]]===sc[id[i]]) j++; const avg=(i+j)/2+1; for(let k=i;k<=j;k++){ if(lb[id[k]]){sp+=avg;np++;} else nn++; } i=j+1; } return (sp-np*(np+1)/2)/(np*nn); }
  function bootAUC(preds, lab, reps=300){ const D=teDates.map(d=>byDay[d]); const res=preds.map(()=>[]);
    for(let r=0;r<reps;r++){ const L=[]; for(let j=0;j<D.length;j++){ const q=Math.floor(rnd()*D.length); for(const i of D[q]) L.push(i); } for(let m=0;m<preds.length;m++) res[m].push(auc(L.map(i=>preds[m][i]), L.map(i=>lab[i]))); }
    const ci=a=>{const s=[...a].sort((x,y)=>x-y); return [+s[Math.floor(0.025*s.length)].toFixed(4), +s[Math.floor(0.975*s.length)-1].toFixed(4)];};
    return {ci:res.map(ci), delta:(a,b)=>ci(res[b].map((v,i)=>v-res[a][i]))}; }
  const F0=['hd','hw','hm'], F1=F0.concat(['mk1','mk5','gapdays','abv1','usabsix','usabssox','usrngix','usrngsox','usabstsm','ustsmmiss','usn']);
  const NEWS=['l_over','any_over','l_prev','l_mover','l_mprev'], FLAGS=['l_rev','l_earn','l_div','l_analyst','l_react','l_corp','l_disp'];
  const F2=F1.concat(NEWS), F3=F2.concat(FLAGS), FL=F2.concat(['l_sess']);
  const out={n:{rows:rows.length, test:teIdx.length, testDays:teDates.length, train:trM.filter(Boolean).length, val:vaM.filter(Boolean).length}};
  for(const tgt of ['y_tr','y_rng','y_abv']){
    const y=rows.map(r=>r[tgt]); const extra=tgt==='y_abv'?['abv5']:[];
    const specs=[['M0',F0],['M1',F1],['M2',F2],['M3',F3],['LEAK',FL]];
    const P=specs.map(([n,c])=>fitPredict(c.concat(extra), y));
    const bench=stockMean(y); const b=bootR2(y,P.map(p=>p.pred),bench, opts.reps||1000);
    const o={}; specs.forEach(([n],m)=>{ o[n]={r2:+r2(y,P[m].pred,bench,teIdx).toFixed(4), ci:b.ci[m], alpha:P[m].alpha}; });
    o.d_M1_M0={v:+(o.M1.r2-o.M0.r2).toFixed(4), ci:b.deltaCI(0,1)}; o.d_M2_M1={v:+(o.M2.r2-o.M1.r2).toFixed(4), ci:b.deltaCI(1,2)}; o.d_M3_M2={v:+(o.M3.r2-o.M2.r2).toFixed(4), ci:b.deltaCI(2,3)}; o.d_M3_M1={v:+(o.M3.r2-o.M1.r2).toFixed(4), ci:b.deltaCI(1,3)}; o.d_LEAK_M2={v:+(o.LEAK.r2-o.M2.r2).toFixed(4), ci:b.deltaCI(2,4)};
    if(tgt==='y_tr'){ const grp={none:[],any:[],earnrev:[]}; for(const i of teIdx){ const f=rows[i].f; if(!f.any_over) grp.none.push(i); else { grp.any.push(i); if(f.l_earn>0||f.l_rev>0) grp.earnrev.push(i);} }
      o.residual_by_news={}; for(const [g,L] of Object.entries(grp)){ const r1=L.reduce((s,i)=>s+(y[i]-P[1].pred[i]),0)/L.length, r3=L.reduce((s,i)=>s+(y[i]-P[3].pred[i]),0)/L.length; o.residual_by_news[g]={n:L.length, meanResid_M1:+r1.toFixed(4), meanResid_M3:+r3.toFixed(4)}; }
      const thr=U.map(()=>[]); rows.forEach((r,i)=>{ if(fitM[i]) thr[r.ci].push(r.trRaw); }); const q90=thr.map(a=>{const s=a.sort((x,y)=>x-y); return s[Math.floor(0.9*s.length)];});
      const lab=rows.map(r=>r.trRaw>=q90[r.ci]?1:0); const ba=bootAUC(P.map(p=>p.pred), lab, opts.repsAUC||300);
      o.big={rate_test:+(teIdx.reduce((s,i)=>s+lab[i],0)/teIdx.length).toFixed(4)}; specs.forEach(([n],m)=>{ o.big[n]={auc:+auc(teIdx.map(i=>P[m].pred[i]), teIdx.map(i=>lab[i])).toFixed(4), ci:ba.ci[m]}; });
      o.big.d_M2_M1=ba.delta(1,2); o.big.d_M3_M1=ba.delta(1,3);
    }
    out[tgt]=o;
  }
  { const keep=rows.map(r=>r.oc!==0); const y=rows.map(r=>r.oc>0?1:-1);
    const cols=F3.concat(['usix','ussox','ustsm','sent']); const {pred}=fitPredict(cols, y);
    const L=teIdx.filter(i=>keep[i]); const acc=L.filter(i=>Math.sign(pred[i])===y[i]).length/L.length; const up=L.filter(i=>y[i]>0).length/L.length;
    const fitUp=rows.filter((r,i)=>fitM[i]&&keep[i]&&r.oc>0).length/rows.filter((r,i)=>fitM[i]&&keep[i]).length;
    const D=teDates.map(d=>byDay[d].filter(i=>keep[i])); const accs=[]; for(let r=0;r<1000;r++){ let a=0,n=0; for(let j=0;j<D.length;j++){ const q=Math.floor(rnd()*D.length); for(const i of D[q]){ n++; if(Math.sign(pred[i])===y[i]) a++; } } accs.push(a/n); } accs.sort((a,b)=>a-b);
    out.direction={acc:+acc.toFixed(4), ci:[+accs[25].toFixed(4), +accs[974].toFixed(4)], test_share_up:+up.toFixed(4), fit_share_up:+fitUp.toFixed(4), auc:+auc(L.map(i=>pred[i]), L.map(i=>y[i]>0?1:0)).toFixed(4)}; }
  { const sp2=idx.map(r=>split(r.date)); const fit=sp2.map(s=>s<=1), te=sp2.map(s=>s===2);
    const ols=(ycol)=>{ const cols=['usix','ussox','ustsm']; const X=idx.map(r=>[1,...cols.map(c=>r[c])]); const y=idx.map(r=>r[ycol]); const q=X[0].length; const A=Array.from({length:q},()=>new Array(q).fill(0)), b=new Array(q).fill(0);
      X.forEach((x,i)=>{ if(!fit[i]) return; for(let a=0;a<q;a++){ b[a]+=x[a]*y[i]; for(let c=0;c<q;c++) A[a][c]+=x[a]*x[c]; } }); const w=solve(A,b);
      const ym=y.filter((v,i)=>fit[i]).reduce((s,v)=>s+v,0)/fit.filter(Boolean).length; let sse=0,sst=0,hit=0,n=0; X.forEach((x,i)=>{ if(!te[i]) return; const p=dot(x,w); sse+=(y[i]-p)**2; sst+=(y[i]-ym)**2; n++; if(Math.sign(p)===Math.sign(y[i])) hit++; });
      return {r2:+(1-sse/sst).toFixed(4), dirAcc:+(hit/n).toFixed(4), n, coef:w.map(v=>+v.toFixed(4))}; };
    out.taiex={gap:ols('gap'), oc:ols('oc')}; }
  return out;
};

// ---------------------------------------------------------------- 6. walk-forward (monthly refit), within-stock R2
window.__wf = function(opts={}){
  const {rows}=window.__ds; const U=window.__U;
  let seed=777; const rnd=()=>{seed|=0; seed=seed+0x6D2B79F5|0; let t=Math.imul(seed^seed>>>15,1|seed); t=t+Math.imul(t^t>>>7,61|t)^t; return ((t^t>>>14)>>>0)/4294967296;};
  function solve(A,b){ const n=b.length; const M=A.map((r,i)=>[...r,b[i]]);
    for(let c=0;c<n;c++){ let p=c; for(let r=c+1;r<n;r++) if(Math.abs(M[r][c])>Math.abs(M[p][c])) p=r; const tmp=M[c]; M[c]=M[p]; M[p]=tmp; const d=M[c][c]; if(Math.abs(d)<1e-12) continue;
      for(let r=0;r<n;r++){ if(r===c) continue; const f=M[r][c]/d; if(f===0) continue; const Mr=M[r], Mc=M[c]; for(let k=c;k<=n;k++) Mr[k]-=f*Mc[k]; } }
    return M.map((r,i)=>Math.abs(r[i])<1e-12?0:r[n]/r[i]); }
  const dot=(x,w)=>{let s=0; for(let a=0;a<w.length;a++) s+=x[a]*w[a]; return s;};
  function fitPred(cols, y, fitMask, predMask, alpha){
    const n=rows.length, p=cols.length; const mu=new Array(p).fill(0), sd=new Array(p).fill(0); let nf=0;
    for(let i=0;i<n;i++) if(fitMask[i]){ nf++; for(let a=0;a<p;a++) mu[a]+=rows[i].f[cols[a]]; } for(let a=0;a<p;a++) mu[a]/=nf;
    for(let i=0;i<n;i++) if(fitMask[i]) for(let a=0;a<p;a++){ const v=rows[i].f[cols[a]]-mu[a]; sd[a]+=v*v; } for(let a=0;a<p;a++) sd[a]=Math.sqrt(sd[a]/nf)||1;
    const q=p+U.length; const A=Array.from({length:q},()=>new Float64Array(q)); const b=new Float64Array(q);
    const xs=i=>{ const x=new Float64Array(q); for(let a=0;a<p;a++) x[a]=(rows[i].f[cols[a]]-mu[a])/sd[a]; x[p+rows[i].ci]=1; return x; };
    for(let i=0;i<n;i++){ if(!fitMask[i]) continue; const x=xs(i), yi=y[i]; for(let a=0;a<q;a++){ const xa=x[a]; if(xa===0) continue; b[a]+=xa*yi; for(let c=a;c<q;c++) A[a][c]+=xa*x[c]; } }
    for(let a=0;a<q;a++){ for(let c=0;c<a;c++) A[a][c]=A[c][a]; if(a<p) A[a][a]+=alpha; }
    const w=solve(A.map(r=>Array.from(r)), Array.from(b)); const out={}; for(let i=0;i<n;i++) if(predMask[i]) out[i]=dot(xs(i),w); return out; }
  const F0=['hd','hw','hm'], F1=F0.concat(['mk1','mk5','gapdays','abv1','usabsix','usabssox','usrngix','usrngsox','usabstsm','ustsmmiss','usn']);
  const F2s=F1.concat(['l_over','any_over','l_prev']), F2=F2s.concat(['l_mover','l_mprev']), F3=F2.concat(['l_rev','l_earn','l_div','l_analyst','l_react','l_corp','l_disp']);
  const specs=[['M0',F0],['M1',F1],['M2s',F2s],['M2',F2],['M3',F3]]; const alpha=opts.alpha||10;
  const y=rows.map(r=>r.y_tr);
  const months=[...new Set(rows.filter(r=>r.date>'2025-09-30').map(r=>r.date.slice(0,7)))].sort();
  const pred=specs.map(()=>({}));
  for(const m of months){ const fitM=rows.map(r=>r.date< m+'-01'), prM=rows.map(r=>r.date.slice(0,7)===m);
    specs.forEach(([n,c],j)=>{ Object.assign(pred[j], fitPred(c,y,fitM,prM,alpha)); }); }
  const te=Object.keys(pred[0]).map(Number); const byDay={}; for(const i of te) (byDay[rows[i].date]=byDay[rows[i].date]||[]).push(i); const days=Object.keys(byDay).sort(); const D=days.map(d=>byDay[d]);
  const ym=te.reduce((s,i)=>s+y[i],0)/te.length; const sm=new Array(U.length).fill(0), sn=new Array(U.length).fill(0); for(const i of te){ sm[rows[i].ci]+=y[i]; sn[rows[i].ci]++; } const smean=sm.map((v,k)=>v/sn[k]);
  const sse=specs.map((_,j)=>D.map(L=>L.reduce((s,i)=>s+(y[i]-pred[j][i])**2,0))); const sst=D.map(L=>L.reduce((s,i)=>s+(y[i]-(opts.within?smean[rows[i].ci]:ym))**2,0));
  const R2=j=>1-sse[j].reduce((a,b)=>a+b,0)/sst.reduce((a,b)=>a+b,0);
  const boots=specs.map(()=>[]); for(let r=0;r<(opts.reps||1000);r++){ let t=0; const e=specs.map(()=>0); for(let k=0;k<D.length;k++){ const q=Math.floor(rnd()*D.length); t+=sst[q]; for(let j=0;j<specs.length;j++) e[j]+=sse[j][q]; } for(let j=0;j<specs.length;j++) boots[j].push(1-e[j]/t); }
  const ci=a=>{const s=[...a].sort((x,y)=>x-y); return [+s[Math.floor(0.025*s.length)].toFixed(4), +s[Math.floor(0.975*s.length)-1].toFixed(4)];};
  const out={note:'walk-forward, expanding window, monthly refit, alpha='+alpha+'; R2 benchmark = '+(opts.within?"each stock's own TEST-period mean (within-stock)":'pooled TEST-period mean'), nTest:te.length, nDays:days.length, months:months.length};
  specs.forEach(([n],j)=>{ out[n]={r2:+R2(j).toFixed(4), ci:ci(boots[j])}; });
  const idx=Object.fromEntries(specs.map(([n],j)=>[n,j]));
  for(const [a,b] of [['M0','M1'],['M1','M2s'],['M1','M2'],['M2','M3'],['M1','M3']]){ const ja=idx[a], jb=idx[b]; out[`d_${b}_${a}`]={v:+(R2(jb)-R2(ja)).toFixed(4), ci:ci(boots[jb].map((v,i)=>v-boots[ja][i]))}; }
  const corr=j=>{ const p=te.map(i=>pred[j][i]), o=te.map(i=>y[i]); const mp=p.reduce((s,v)=>s+v,0)/p.length, mo=o.reduce((s,v)=>s+v,0)/o.length; let sxy=0,sxx=0,syy=0; for(let k=0;k<p.length;k++){ sxy+=(p[k]-mp)*(o[k]-mo); sxx+=(p[k]-mp)**2; syy+=(o[k]-mo)**2; } return +(sxy/Math.sqrt(sxx*syy)).toFixed(4); };
  out.corr=Object.fromEntries(specs.map(([n],j)=>[n,corr(j)]));
  return out;
};

// ---------------------------------------------------------------- 7. where does news help? (walk-forward, event subsets)
window.__subset = function(opts={}){
  const {rows}=window.__ds; const U=window.__U; const alpha=opts.alpha||10;
  let seed=4242; const rnd=()=>{seed|=0; seed=seed+0x6D2B79F5|0; let t=Math.imul(seed^seed>>>15,1|seed); t=t+Math.imul(t^t>>>7,61|t)^t; return ((t^t>>>14)>>>0)/4294967296;};
  function solve(A,b){ const n=b.length; const M=A.map((r,i)=>[...r,b[i]]); for(let c=0;c<n;c++){ let p=c; for(let r=c+1;r<n;r++) if(Math.abs(M[r][c])>Math.abs(M[p][c])) p=r; const tmp=M[c]; M[c]=M[p]; M[p]=tmp; const d=M[c][c]; if(Math.abs(d)<1e-12) continue; for(let r=0;r<n;r++){ if(r===c) continue; const f=M[r][c]/d; if(f===0) continue; const Mr=M[r], Mc=M[c]; for(let k=c;k<=n;k++) Mr[k]-=f*Mc[k]; } } return M.map((r,i)=>Math.abs(r[i])<1e-12?0:r[n]/r[i]); }
  function fitPred(cols, y, fitMask, predMask){ const n=rows.length, p=cols.length; const mu=new Array(p).fill(0), sd=new Array(p).fill(0); let nf=0;
    for(let i=0;i<n;i++) if(fitMask[i]){ nf++; for(let a=0;a<p;a++) mu[a]+=rows[i].f[cols[a]]; } for(let a=0;a<p;a++) mu[a]/=nf;
    for(let i=0;i<n;i++) if(fitMask[i]) for(let a=0;a<p;a++){ const v=rows[i].f[cols[a]]-mu[a]; sd[a]+=v*v; } for(let a=0;a<p;a++) sd[a]=Math.sqrt(sd[a]/nf)||1;
    const q=p+U.length; const A=Array.from({length:q},()=>new Float64Array(q)); const b=new Float64Array(q); const xs=i=>{ const x=new Float64Array(q); for(let a=0;a<p;a++) x[a]=(rows[i].f[cols[a]]-mu[a])/sd[a]; x[p+rows[i].ci]=1; return x; };
    for(let i=0;i<n;i++){ if(!fitMask[i]) continue; const x=xs(i), yi=y[i]; for(let a=0;a<q;a++){ const xa=x[a]; if(xa===0) continue; b[a]+=xa*yi; for(let c=a;c<q;c++) A[a][c]+=xa*x[c]; } }
    for(let a=0;a<q;a++){ for(let c=0;c<a;c++) A[a][c]=A[c][a]; if(a<p) A[a][a]+=alpha; } const w=solve(A.map(r=>Array.from(r)), Array.from(b)); const out={}; for(let i=0;i<n;i++) if(predMask[i]){ const x=xs(i); let s=0; for(let a=0;a<q;a++) s+=x[a]*w[a]; out[i]=s; } return out; }
  const F1=['hd','hw','hm','mk1','mk5','gapdays','abv1','usabsix','usabssox','usrngix','usrngsox','usabstsm','ustsmmiss','usn'];
  const specs=[['M1',F1],['M1e',F1.concat(['l_earn','l_rev'])],['M3',F1.concat(['l_over','any_over','l_prev','l_mover','l_mprev','l_rev','l_earn','l_div','l_analyst','l_react','l_corp','l_disp'])]];
  const y=rows.map(r=>r.y_tr); const months=[...new Set(rows.filter(r=>r.date>'2025-09-30').map(r=>r.date.slice(0,7)))].sort();
  const P=specs.map(()=>({})); for(const m of months){ const fitM=rows.map(r=>r.date< m+'-01'), prM=rows.map(r=>r.date.slice(0,7)===m); specs.forEach(([n,c],j)=>Object.assign(P[j], fitPred(c,y,fitM,prM))); }
  const te=Object.keys(P[0]).map(Number);
  const sm={}, sn={}; for(const i of te){ const c=rows[i].ci; sm[c]=(sm[c]||0)+y[i]; sn[c]=(sn[c]||0)+1; } const smean=i=>sm[rows[i].ci]/sn[rows[i].ci];
  const groups={all:te, noNews:te.filter(i=>!rows[i].f.any_over), anyNews:te.filter(i=>rows[i].f.any_over), earnRev:te.filter(i=>rows[i].f.l_earn>0||rows[i].f.l_rev>0), otherNews:te.filter(i=>rows[i].f.any_over && !(rows[i].f.l_earn>0||rows[i].f.l_rev>0))};
  const out={note:'walk-forward monthly refit; residual = actual - predicted log TR; excessPct = exp(mean residual)-1', alpha};
  for(const [g,L] of Object.entries(groups)){ const o={n:L.length};
    specs.forEach(([n],j)=>{ const res=L.map(i=>y[i]-P[j][i]); const mr=res.reduce((s,v)=>s+v,0)/L.length; const sse=res.reduce((s,v)=>s+v*v,0), sst=L.reduce((s,i)=>s+(y[i]-smean(i))**2,0); o[n]={meanResid:+mr.toFixed(4), excessPct:+(100*(Math.exp(mr)-1)).toFixed(1), r2within:+(1-sse/sst).toFixed(4)}; });
    const byDay={}; for(const i of L) (byDay[rows[i].date]=byDay[rows[i].date]||[]).push(i); const D=Object.values(byDay);
    const d1=D.map(Li=>Li.reduce((s,i)=>s+(y[i]-P[0][i])**2,0)), d2=D.map(Li=>Li.reduce((s,i)=>s+(y[i]-P[1][i])**2,0)), dt=D.map(Li=>Li.reduce((s,i)=>s+(y[i]-smean(i))**2,0));
    const bs=[]; for(let r=0;r<1000;r++){ let a=0,b=0,t=0; for(let k=0;k<D.length;k++){ const q=Math.floor(rnd()*D.length); a+=d1[q]; b+=d2[q]; t+=dt[q]; } bs.push((a-b)/t); } bs.sort((x,y)=>x-y);
    o.dR2_M1e_M1={v:+(o.M1e.r2within-o.M1.r2within).toFixed(4), ci:[+bs[25].toFixed(4), +bs[974].toFixed(4)]};
    out[g]=o; }
  return out;
};

// ---------------------------------------------------------------- 8. descriptive statistics, level shift, ADR -> 2330
// (the "extra" block in results/bc6_taiwan.json; run after __build)
window.__extra = function(){
  const {rows, st, perStock}=window.__ds; const U=window.__U;
  const split=d=> d<='2025-06-30'?0:(d<='2025-09-30'?1:2);
  const mean=a=>a.length?a.reduce((s,v)=>s+v,0)/a.length:null;
  const med=a=>{ if(!a.length) return null; const s=[...a].sort((x,y)=>x-y); return s[Math.floor(s.length/2)]; };
  // descriptive: daily true range (in %) by news status, whole sample and test only
  const grp=(L)=>{ const g={none:[],any:[],earnOrRev:[],react:[]}; for(const r of L){ const f=r.f; if(!f.any_over) g.none.push(r.trRaw); else { g.any.push(r.trRaw); if(f.l_earn>0||f.l_rev>0) g.earnOrRev.push(r.trRaw); if(f.l_react>0) g.react.push(r.trRaw); } }
    return Object.fromEntries(Object.entries(g).map(([k,v])=>[k,{n:v.length, meanTRpct:v.length?+(100*mean(v)).toFixed(3):null, medianTRpct:v.length?+(100*med(v)).toFixed(3):null}])); };
  const test=rows.filter(r=>split(r.date)===2), fit=rows.filter(r=>split(r.date)<=1);
  // per-stock level shift between fit and test (non-stationarity)
  const lvl={}; for(const c of U){ const a=fit.filter(r=>r.code===c).map(r=>r.trRaw), b=test.filter(r=>r.code===c).map(r=>r.trRaw); lvl[c]=[+(100*mean(a)).toFixed(2), +(100*mean(b)).toFixed(2)]; }
  // 2330 vs TSM ADR overnight return
  const t2330=rows.filter(r=>r.code==='2330' && r.f.ustsmmiss===0 && r.gap!=null);
  const fitR=t2330.filter(r=>split(r.date)<=1), teR=t2330.filter(r=>split(r.date)===2);
  const ols1=(L,xk,yk)=>{ const xm=mean(L.map(r=>r.f[xk])), ym=mean(L.map(r=>r[yk])); let sxy=0,sxx=0; for(const r of L){ sxy+=(r.f[xk]-xm)*(r[yk]-ym); sxx+=(r.f[xk]-xm)**2; } const b=sxy/sxx; return {a:ym-b*xm, b}; };
  const evalTe=(m,L,xk,yk,ymFit)=>{ let sse=0,sst=0,hit=0; for(const r of L){ const p=m.a+m.b*r.f[xk]; sse+=(r[yk]-p)**2; sst+=(r[yk]-ymFit)**2; if(Math.sign(p)===Math.sign(r[yk])) hit++; } return {r2:+(1-sse/sst).toFixed(4), dirAcc:+(hit/L.length).toFixed(4), n:L.length, slope:+m.b.toFixed(3)}; };
  const mg=ols1(fitR,'ustsm','gap'), mo=ols1(fitR,'ustsm','oc');
  const adr={gap:evalTe(mg,teR,'ustsm','gap',mean(fitR.map(r=>r.gap))), oc:evalTe(mo,teR,'ustsm','oc',mean(fitR.map(r=>r.oc)))};
  return {descriptive_all:grp(rows), descriptive_test:grp(test), levelShift_fit_vs_test_meanTRpct:lvl, adr2330:adr, perStock, st};
};

// ---------------------------------------------------------------- 9. how BC6 was run
// await fetchPrices();  (after the crawl has finished)
// __build(); __models(); __wf({within:true}); __subset(); __extra();
// Universe 2 (mid-coverage): 40 non-ETF codes not in U1 whose overnight-news share in 2024-10..2025-09 was 10-60%,
// top 40 by that share (list in results/bc6_taiwan.json); fetch their prices the same way, add their ex-dates to
// __EX/__SPL, set window.__U to the new list and rerun __build/__models/__wf/__subset/__extra.
