(() => {
  'use strict';

  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const state = { data: {files:[], issues:[], graph:{nodes:[],edges:[]}, history:[]}, mode:'all', fx:true, hot:false, minimap:false, selected:null, focused:null, positions:{}, drag:null, renderQueued:false, serverOffline:false, lastErrorKey:'' };

  function text(id, value) { const el=$(id); if(el) el.textContent=String(value ?? ''); }
  function html(id, value) { const el=$(id); if(el) el.innerHTML=value; }
  function clearError(){
    const box=$('codeflowError');
    if(box)box.remove();
    state.serverOffline=false;
    state.lastErrorKey='';
  }

  function showError(title, detail){
    const key=String(title)+'|'+String(detail||'');
    if(key===state.lastErrorKey)return;
    state.lastErrorKey=key;
    state.serverOffline=title==='Cannot reach CodeFlow server';
    console.error('[CODEFLOW]',title,detail);
    let box=$('codeflowError');
    if(!box){
      box=document.createElement('div');
      box.id='codeflowError';
      box.style.cssText='position:fixed;right:16px;bottom:16px;z-index:9999;max-width:520px;padding:14px 16px;border:1px solid #ff526f;background:#180810ee;color:#ffd9df;font:11px Consolas,monospace;box-shadow:0 0 35px #000;pointer-events:none';
      document.body.appendChild(box);
    }
    box.innerHTML='<b style="color:#ff7d91">'+esc(title)+'</b><div style="margin-top:6px">'+esc(detail||'')+'</div>'+
      '<small style="display:block;margin-top:5px;color:#ffb6c1">'+(state.serverOffline?'Waiting for the local CodeFlow server…':'')+'</small>';
  }

  async function api(path) {
    const response=await fetch(path+(path.includes('?')?'&':'?')+'_='+Date.now(),{cache:'no-store'});
    const data=await response.json().catch(()=>({error:'Invalid server response'}));
    if(!response.ok || data.error) throw new Error(data.error || ('HTTP '+response.status));
    clearError();
    return data;
  }

  function issueCard(x){
    const sev=String(x.severity||'LOW').toLowerCase();
    const file=String(x.file||'PROJECT');
    const line=Number(x.line)||0;
    const column=Number(x.column)||0;
    const location=line?'LINE '+line+(column?' • COL '+column:''):'NO SOURCE LOCATION';
    const target=file && file!=='PROJECT' && line? ' data-location-file="'+esc(encodeURIComponent(file))+'" data-location-line="'+line+'" data-location-column="'+column+'" tabindex="0" role="button" title="Open source at finding location"':'';
    return '<div class="issue issue-locatable"'+target+'><i class="'+sev+'"></i><div><b>'+esc(x.title||x.type||'Finding')+'</b><small class="issueLocation">'+esc(file)+' <strong>•</strong> '+esc(location)+'</small><p>'+esc(x.message||'')+'</p></div><em class="'+sev+'">'+sev.toUpperCase()+'</em></div>';
  }

  function renderDNA(){
    const dna=state.data.dna||{};
    const rows=[['COMPLEXITY',dna.complexity],['COUPLING',dna.coupling],['DUPLICATION',dna.duplication],['MAINTAINABILITY',dna.maintainability],['SECURITY',dna.security]];
    html('dna',rows.map(([k,v])=>'<div><small>'+k+'</small><b>'+Number(v??0)+'</b><span><i style="width:'+Math.max(0,Math.min(100,Number(v)||0))+'%"></i></span></div>').join('')+
      '<div class="languages"><small>LANGUAGE MATRIX</small><p>'+Object.entries(state.data.languages||{}).map(([k,v])=>'<b>'+esc(k)+'</b> '+esc(v)).join('　')+'</p></div>');
  }

  function icon(ext){ return ({'.py':'PY','.js':'JS','.jsx':'JS','.ts':'TS','.tsx':'TS','.java':'JV','.cpp':'C+','.c':'C','.cs':'C#','.go':'GO','.rs':'RS','.rb':'RB','.php':'PH','.html':'HT','.css':'CS','.sql':'DB'})[ext]||'<>'; }

  function renderFiles(){
    const filter=($('fileFilter')?.value||'').toLowerCase();
    const files=(state.data.files||[]).filter(f=>String(f.path).toLowerCase().includes(filter));
    html('filesTree',files.map(f=>'<button type="button" data-open-file="'+encodeURIComponent(f.path)+'"><span>'+icon(f.language)+'</span>'+esc(f.path)+'<em>'+esc(f.lines)+'</em></button>').join('')||'<div class="empty">NO MATCHING FILES</div>');
  }

  async function openFile(path, focusLine=0, focusColumn=0){
    try{
      hideTip();
      const x=await api('/api/file?path='+encodeURIComponent(path));
      text('codeTitle',x.path); text('codeLang',x.language);
      const lines=String(x.content||'').split(/\r?\n/);
      html('code',lines.map((line,i)=>{
        const active=Number(focusLine)===i+1;
        const cls=active?'codeLine activeSourceLine':'codeLine';
        return '<span class="'+cls+'" data-line="'+(i+1)+'"><span class="ln">'+String(i+1).padStart(4,' ')+'</span>'+esc(line)+'</span>';
      }).join('\n'));
      switchTab('explorer');
      if(focusLine){
        requestAnimationFrame(()=>{
          const el=document.querySelector('#code .activeSourceLine');
          if(el){el.scrollIntoView({block:'center',behavior:'smooth'});}
          text('codeTitle',x.path+'  •  LINE '+focusLine+(focusColumn?' • COL '+focusColumn:''));
        });
      }
    }catch(e){showError('Could not open file',e.message);}
  }

  function renderSecurity(){
    const a=state.data.security||[];
    text('securityCount',a.length+' FINDINGS'); text('secScore',Math.max(0,Number(state.data.dna?.security??100)));
    html('securityList',a.length?a.map(issueCard).join(''):'<div class="empty">✓ NO HIGH-RISK SECURITY SIGNALS</div>');
  }

  async function doSearch(){
    const q=($('query')?.value||'').trim(); if(!q)return;
    html('results','<div class="empty">SCANNING PROJECT...</div>');
    try{
      const x=await api('/api/search?q='+encodeURIComponent(q));
      html('results',(x.results||[]).map(a=>'<div class="result" data-search-file="'+encodeURIComponent(a.file)+'"><b>'+esc(a.file)+':'+esc(a.line)+'</b><p>'+esc(a.text)+'</p></div>').join('')||'<div class="empty">NO MATCHES</div>');
    }catch(e){showError('Search failed',e.message); html('results','<div class="empty">SEARCH ERROR</div>');}
  }

  function renderHistory(){
    const h=state.data.history||[];
    const points=h.length<2?'':h.map((x,i)=>`${40+i*920/Math.max(1,h.length-1)},${350-Number(x.health||0)*3}`).join(' ');
    html('historySvg','<path d="M40 50V350H960" stroke="#183b4d" fill="none"/><line x1="40" y1="200" x2="960" y2="200" stroke="#0d2a3a"/>'+(points?'<polyline fill="none" stroke="#58d8ff" stroke-width="3" points="'+points+'"/>':''));
    html('historyTable',h.slice().reverse().map(x=>'<div class="historyRow"><b>#'+esc(x.scan)+'</b><span>'+esc(x.time)+'</span><span>HEALTH '+esc(x.health)+' • ISSUES '+esc(x.issues)+'</span></div>').join('')||'<div class="empty">Waiting for scan history...</div>');
  }

  function switchTab(id){
    document.querySelectorAll('.tab').forEach(el=>el.classList.toggle('activeTab',el.id===id));
    document.querySelectorAll('.nav').forEach(el=>el.classList.toggle('active',el.dataset.tab===id));
    if(id==='graph') requestAnimationFrame(renderGraph);
  }

  function edgeVisible(e){ return state.mode==='all'||e.kind===state.mode; }

  function queueGraphRender(){
    if(state.renderQueued)return;
    state.renderQueued=true;
    requestAnimationFrame(()=>{state.renderQueued=false;renderGraph();});
  }

  function renderGraph(){
    hideTip();
    const svg=$('graphSvg'); if(!svg)return;
    const graph=state.data.graph||{};
    let nodes=(graph.nodes||[]).filter(n=>n.kind!=='folder');
    const allEdges=(graph.edges||[]).filter(e=>e.kind!=='contains');

    if(state.focused){
      const nodeIds=new Set(nodes.map(n=>n.id));
      const adjacency=new Map();
      nodes.forEach(n=>adjacency.set(n.id,[]));
      allEdges.forEach(e=>{
        if(nodeIds.has(e.source)&&nodeIds.has(e.target)){adjacency.get(e.source).push(e.target);adjacency.get(e.target).push(e.source);}
      });
      const keep=new Set([state.focused]); const queue=[state.focused];
      while(queue.length){const id=queue.shift(); for(const next of adjacency.get(id)||[]){if(!keep.has(next)){keep.add(next);queue.push(next);}}}
      nodes=nodes.filter(n=>keep.has(n.id));
    }

    const by=Object.fromEntries(nodes.map(n=>[n.id,n]));
    const realEdges=allEdges.filter(e=>by[e.source]&&by[e.target]&&(state.focused?true:edgeVisible(e)));
    const focusNode=state.focused?by[state.focused]:null;

    if(focusNode){
      const incoming=nodes.map(n=>({n,d:0}));
      const distIn=new Map([[focusNode.id,0]]),distOut=new Map([[focusNode.id,0]]),inc=new Map(),out=new Map();
      nodes.forEach(n=>{inc.set(n.id,[]);out.set(n.id,[]);});
      realEdges.forEach(e=>{inc.get(e.target).push(e.source);out.get(e.source).push(e.target);});
      let q=[focusNode.id];
      while(q.length){const id=q.shift();for(const n of inc.get(id)){if(!distIn.has(n)){distIn.set(n,distIn.get(id)+1);q.push(n);}}}
      q=[focusNode.id];
      while(q.length){const id=q.shift();for(const n of out.get(id)){if(!distOut.has(n)){distOut.set(n,distOut.get(id)+1);q.push(n);}}}
      const left=new Map(),right=new Map();
      nodes.forEach(n=>{
        if(n.id===focusNode.id)return;
        const a=distIn.get(n.id),b=distOut.get(n.id);
        if(a!==undefined&&(b===undefined||a<=b)){if(!left.has(a))left.set(a,[]);left.get(a).push(n);}
        else if(b!==undefined){if(!right.has(b))right.set(b,[]);right.get(b).push(n);}
      });
      const columns=[...Array.from(left.keys()).sort((a,b)=>b-a).map(d=>({nodes:left.get(d)})),{nodes:[focusNode]},...Array.from(right.keys()).sort((a,b)=>a-b).map(d=>({nodes:right.get(d)}))];
      columns.forEach((col,ci)=>{const x=columns.length===1?600:55+ci/(columns.length-1)*1090;const arr=col.nodes;const gap=580/Math.max(1,arr.length-1);arr.forEach((n,i)=>{state.positions[n.id]={x,y:arr.length===1?350:60+i*gap};});});
      text('graphInfo',nodes.length+' NODES / '+realEdges.length+' FLOW LINKS');
      text('hudDepth',String(Math.max(distIn.size?Math.max(...distIn.values()):0,distOut.size?Math.max(...distOut.values()):0)).padStart(2,'0'));
      text('hudBlast',String(Math.max(0,nodes.length-1)).padStart(2,'0'));
    } else {
      const ranks=[...new Set(nodes.map(n=>Number(n.rank)||0))].sort((a,b)=>a-b);const maxRank=Math.max(0,...ranks);const layers=Math.max(1,ranks.length);const buckets=new Map(ranks.map(r=>[r,[]]));nodes.forEach(n=>buckets.get(Number(n.rank)||0).push(n));
      ranks.forEach((rank,li)=>{const arr=buckets.get(rank)||[];const x=layers===1?600:90+li/(layers-1)*1020;const gap=560/Math.max(1,arr.length-1);arr.forEach((n,i)=>{state.positions[n.id]={x,y:arr.length===1?350:70+i*gap};});});
      text('graphInfo',nodes.length+' NODES / '+realEdges.length+' FLOW LINKS');
      text('hudDepth',String(layers).padStart(2,'0'));text('hudBlast',String(state.data.intelligence?.impact?.blast_radius||0).padStart(2,'0'));
    }

    text('hudNodes',String(nodes.length).padStart(2,'0'));text('hudEdges',String(realEdges.length).padStart(2,'0'));text('hudMode',state.focused?'FOCUSED FLOW':'FULL NETWORK');
    const ns=Object.values(state.positions);
    const edgeMarkup=realEdges.map((e,i)=>{
      const a=state.positions[e.source],b=state.positions[e.target];if(!a||!b)return '';
      const dx=Math.abs(b.x-a.x),curve=Math.max(45,Math.min(160,dx*0.25));
      const d=`M ${a.x} ${a.y} C ${a.x+curve} ${a.y}, ${b.x-curve} ${b.y}, ${b.x} ${b.y}`;
      const kind=e.kind||'flow';
      return `<path class="edge ${esc(kind)}" d="${d}"/><path class="flow" d="${d}" style="animation-delay:${i*0.06}s"/>`;
    }).join('');
    const nodeMarkup=nodes.map(n=>{
      const p=state.positions[n.id]||{x:600,y:350};const sel=state.selected===n.id?' selected':'';const hot=state.hot&&state.focused&&n.id!==state.focused?' hot':'';
      return `<g class="node ${esc(n.role||'module')}${sel}${hot}" data-node="${esc(n.id)}" transform="translate(${p.x} ${p.y})"><circle r="20" class="core"></circle><circle r="25" class="halo"></circle><text y="5">${esc(String(n.label||'').slice(0,24))}</text><text class="type" y="34">${esc(n.role||n.language||'module')}</text></g>`;
    }).join('');
    svg.innerHTML=edgeMarkup+nodeMarkup;
    ns.forEach(()=>{});
  }

  function hideTip(){const tip=$('graphTip');if(tip)tip.style.display='none';}
  function showTip(ev,node){const tip=$('graphTip');if(!tip)return;tip.innerHTML='<b>'+esc(node.label||node.path||node.id)+'</b><span>'+esc(node.path||'')+'</span><span>'+esc(node.role||node.language||'module')+'</span>';tip.style.display='block';tip.style.left=Math.min(ev.offsetX+14,650)+'px';tip.style.top=Math.min(ev.offsetY+14,560)+'px';}

  async function refresh(){
    try{
      const data=await api('/api/state');state.data=data;
      text('watch',data.watching?'WATCHING':'IDLE');text('project',data.project);text('scan','#'+String(data.scan||0).padStart(3,'0'));text('ms',data.duration_ms);text('files',data.stats?.files||0);text('health',data.health||0);
      text('sfiles',data.stats?.files||0);text('lines',data.stats?.lines||0);text('functions',data.stats?.functions||0);text('classes',data.stats?.classes||0);text('imports',data.stats?.imports||0);text('total',data.summary?.total||0);text('sev',`${data.summary?.critical||0} CRITICAL / ${data.summary?.high||0} HIGH`);text('arch','ARCHITECTURE: '+(data.dna?.architecture||'—'));
      html('gaps',(data.shortages||[]).map(issueCard).join('')||'<div class="empty">✓ NO ROOT PROBLEMS</div>');html('bugs',(data.bugs||[]).map(issueCard).join('')||'<div class="empty">✓ NO BUGS / SMELLS</div>');text('gapcount',String((data.shortages||[]).length).padStart(2,'0'));text('bugcount',String((data.bugs||[]).length).padStart(2,'0'));
      html('activity',(data.activity||[]).map(x=>'<div>'+esc(x)+'</div>').join(''));renderDNA();renderFiles();renderSecurity();renderHistory();queueGraphRender();
    }catch(e){showError('Cannot reach CodeFlow server',e.message);}
  }

  document.addEventListener('click',ev=>{
    const nav=ev.target.closest('.nav');if(nav){switchTab(nav.dataset.tab);return;}
    const file=ev.target.closest('[data-open-file]');if(file){openFile(decodeURIComponent(file.dataset.openFile));return;}
    const result=ev.target.closest('[data-search-file]');if(result){openFile(decodeURIComponent(result.dataset.searchFile));return;}
    const located=ev.target.closest('[data-location-file]');if(located){openFile(decodeURIComponent(located.dataset.locationFile),Number(located.dataset.locationLine||0),Number(located.dataset.locationColumn||0));return;}
    const nodeEl=ev.target.closest('[data-node]');if(nodeEl){const id=nodeEl.dataset.node;state.selected=id;state.focused=id;queueGraphRender();return;}
    if(ev.target.matches('[data-mode]')){state.mode=ev.target.dataset.mode;state.focused=null;document.querySelectorAll('[data-mode]').forEach(x=>x.classList.toggle('active',x===ev.target));queueGraphRender();return;}
    if(ev.target.id==='centerBtn'){queueGraphRender();return;}
    if(ev.target.id==='hotBtn'){state.hot=!state.hot;ev.target.classList.toggle('active',state.hot);queueGraphRender();return;}
    if(ev.target.id==='impactBtn'){state.focused=null;state.hot=true;queueGraphRender();return;}
    if(ev.target.id==='xrayBtn'){state.mode='all';state.focused=null;queueGraphRender();return;}
    if(ev.target.id==='cyclesBtn'){state.hot=true;queueGraphRender();return;}
    if(ev.target.id==='deadBtn'){state.hot=true;queueGraphRender();return;}
  });
  $('searchBtn')?.addEventListener('click',doSearch);$('query')?.addEventListener('keydown',e=>{if(e.key==='Enter')doSearch();});$('fileFilter')?.addEventListener('input',renderFiles);
  $('graphSvg')?.addEventListener('mousemove',ev=>{const n=ev.target.closest?.('[data-node]');if(n){const node=(state.data.graph?.nodes||[]).find(x=>x.id===n.dataset.node);if(node)showTip(ev,node);}else hideTip();});
  $('graphSvg')?.addEventListener('mouseleave',hideTip);
  setInterval(refresh,1500);refresh();
})();
