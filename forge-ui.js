(() => {
  'use strict';

  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const state = { data: {files:[], issues:[], graph:{nodes:[],edges:[]}, history:[]}, mode:'all', fx:true, hot:false, minimap:false, selected:null, positions:{}, drag:null, renderQueued:false };

  function text(id, value) { const el=$(id); if(el) el.textContent=String(value ?? ''); }
  function html(id, value) { const el=$(id); if(el) el.innerHTML=value; }
  function showError(title, detail) {
    console.error('[FORGE]', title, detail);
    let box=$('forgeError');
    if(!box){ box=document.createElement('div'); box.id='forgeError'; box.style.cssText='position:fixed;right:16px;bottom:16px;z-index:9999;max-width:520px;padding:14px 16px;border:1px solid #ff526f;background:#180810ee;color:#ffd9df;font:11px Consolas,monospace;box-shadow:0 0 35px #000'; document.body.appendChild(box); }
    box.innerHTML='<b style="color:#ff7d91">FORGE UI ERROR</b><div style="margin-top:6px">'+esc(title)+'</div><small style="display:block;margin-top:5px;color:#ffb6c1">'+esc(detail)+'</small>';
  }

  async function api(path) {
    const response=await fetch(path+(path.includes('?')?'&':'?')+'_='+Date.now(),{cache:'no-store'});
    const data=await response.json().catch(()=>({error:'Invalid server response'}));
    if(!response.ok || data.error) throw new Error(data.error || ('HTTP '+response.status));
    return data;
  }

  function issueCard(x){
    const sev=String(x.severity||'LOW').toLowerCase();
    return '<div class="issue"><i class="'+sev+'"></i><div><b>'+esc(x.title||x.type||'Finding')+'</b><small>'+esc(x.file||'PROJECT')+(x.line?' : LINE '+x.line:'')+'</small><p>'+esc(x.message||'')+'</p></div><em class="'+sev+'">'+sev.toUpperCase()+'</em></div>';
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

  async function openFile(path){
    try{
      const x=await api('/api/file?path='+encodeURIComponent(path));
      text('codeTitle',x.path); text('codeLang',x.language);
      const lines=String(x.content||'').split(/\r?\n/);
      html('code',lines.map((line,i)=>'<span class="ln">'+String(i+1).padStart(4,' ')+'</span>'+esc(line)).join('\n'));
      switchTab('explorer');
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
    const svg=$('graphSvg'); if(!svg)return;
    const graph=state.data.graph||{};
    const nodes=(graph.nodes||[]).filter(n=>n.kind!=='folder');

    // Keep every detected connection visible. Layout is layered; density is
    // handled through spacing, curvature and styling rather than deleting data.
    const rawRanks=nodes.map(n=>Math.max(0,Number(n.rank)||0));
    const rawMax=Math.max(0,...rawRanks);
    const layerCount=Math.min(6,Math.max(2,new Set(rawRanks).size));
    nodes.forEach(n=>{n.visualLayer=rawMax===0?0:Math.min(layerCount-1,Math.round((Number(n.rank)||0)/rawMax*(layerCount-1)));});

    const byLayer=new Map();
    nodes.forEach(n=>{
      if(!byLayer.has(n.visualLayer))byLayer.set(n.visualLayer,[]);
      byLayer.get(n.visualLayer).push(n);
    });
    [...byLayer.values()].forEach(arr=>arr.sort((x,y)=>{
      const dy=(Number(y.degree)||0)-(Number(x.degree)||0);
      return dy||String(x.label||'').localeCompare(String(y.label||''));
    }));

    const left=95,right=1105,top=78,bottom=622;
    for(let layer=0;layer<layerCount;layer++){
      const arr=byLayer.get(layer)||[];
      const x=layerCount===1?600:left+(layer/Math.max(1,layerCount-1))*(right-left);
      const gap=(bottom-top)/Math.max(1,arr.length-1);
      arr.forEach((n,i)=>{state.positions[n.id]={x,y:arr.length===1?350:top+i*gap};});
    }

    const by=Object.fromEntries(nodes.map(n=>[n.id,n]));
    const visibleEdges=(graph.edges||[]).filter(edgeVisible).filter(e=>by[e.source]&&by[e.target]&&e.kind!=='contains');

    text('graphInfo',nodes.length+' NODES / '+visibleEdges.length+' LINKS');
    text('hudNodes',String(nodes.length).padStart(2,'0'));
    text('hudEdges',String(visibleEdges.length).padStart(2,'0'));
    text('hudDepth',String(layerCount).padStart(2,'0'));
    text('hudMode',state.mode.toUpperCase());

    const defs='<defs>'+
      '<marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="3" markerHeight="3" orient="auto"><path d="M0 0L10 5L0 10z" fill="#ccefff"/></marker>'+
      '</defs>';

    const labels=['INPUT','HIDDEN 1','HIDDEN 2','HIDDEN 3','HIDDEN 4','OUTPUT'];
    const guides=Array.from({length:layerCount},(_,layer)=>{
      const arr=byLayer.get(layer)||[];
      const x=arr.length?state.positions[arr[0].id].x:(left+(layer/Math.max(1,layerCount-1))*(right-left));
      return '<line class="layerGuide" x1="'+x+'" y1="42" x2="'+x+'" y2="658"/>'+
             '<text class="layerLabel" x="'+x+'" y="27">'+esc(labels[layer]||('LAYER '+(layer+1)))+'</text>';
    }).join('');

    const paths=visibleEdges.map((e,i)=>{
      const s=by[e.source],t=by[e.target],p=state.positions[s.id],q=state.positions[t.id];
      const same=s.visualLayer===t.visualLayer;
      const dist=Math.abs(q.y-p.y);
      const curve=same?18:Math.max(18,Math.min(70,dist*.10));
      const dir=q.x>=p.x?1:-1;
      const c1x=p.x+(q.x-p.x)*.35;
      const c2x=p.x+(q.x-p.x)*.65;
      const d='M'+p.x+','+p.y+' C'+c1x+','+(p.y+curve*dir*.15)+' '+c2x+','+(q.y-curve*dir*.15)+' '+q.x+','+q.y;
      return '<path class="edge '+esc(e.kind)+' edge-'+(i%7)+'" d="'+d+'" marker-end="url(#arrow)"/>'+
             '<path class="stream stream-'+(i%5)+'" d="'+d+'" style="animation-delay:-'+((i%17)*.09)+'s;display:'+(state.fx?'block':'none')+'"/>';
    }).join('');

    const maxDegree=Math.max(0,...nodes.map(n=>Number(n.degree)||0));
    const ns=nodes.map(n=>{
      const p=state.positions[n.id],degree=Number(n.degree||0),hot=state.hot&&degree===maxDegree&&degree>0;
      const radius=n.role==='entrypoint'?10:7;
      return '<g class="node '+esc(String(n.role||'module').toLowerCase())+' '+(hot?'hot ':'')+(state.selected===n.id?'selected':'')+'" transform="translate('+p.x+' '+p.y+')" data-id="'+esc(n.id)+'">'+
        '<circle class="halo" r="'+(hot?22:15)+'"/>'+
        '<circle class="core" r="'+radius+'"/>'+
        '<circle class="ring" r="'+(hot?28:12)+'"/>'+
        '<text class="name" y="22">'+esc(String(n.label||'').length>19?String(n.label).slice(0,18)+'…':n.label)+'</text>'+
        '<text class="type" y="32">'+esc(String(n.role||n.language||'MODULE').toUpperCase())+'</text>'+
        '</g>';
    }).join('');

    svg.innerHTML=defs+'<g class="layerGuides">'+guides+'</g><g class="actualEdges">'+paths+'</g>'+ns;
    bindNodes();
  }

  function bindNodes(){
    document.querySelectorAll('#graphSvg .node').forEach(el=>{
      el.addEventListener('mouseenter',e=>showTip(e,el.dataset.id));
      el.addEventListener('mouseleave',hideTip);
      el.addEventListener('click',e=>{e.stopPropagation();state.selected=el.dataset.id;renderGraph();});
      el.addEventListener('dblclick',e=>{e.stopPropagation();const n=(state.data.graph.nodes||[]).find(x=>x.id===el.dataset.id);if(n?.kind==='file')openFile(n.path);});
      el.addEventListener('mousedown',e=>{
        e.stopPropagation();
        const n=(state.data.graph.nodes||[]).find(x=>x.id===el.dataset.id);
        if(n)state.drag={n,ox:e.clientX,oy:e.clientY,sx:state.positions[n.id].x,sy:state.positions[n.id].y};
      });
    });
  }

  function showTip(e,id){
    const n=(state.data.graph.nodes||[]).find(x=>x.id===id); if(!n)return;
    const tip=$('graphTip'); if(!tip)return;
    tip.style.display='block'; tip.innerHTML='<b>'+esc(n.label)+'</b><span>'+esc(n.path)+'</span><span>'+esc(n.language||'FOLDER')+' • '+esc(n.lines||0)+' lines • '+esc(n.degree||0)+' links</span>';
    const r=$('graphbox').getBoundingClientRect(); tip.style.left=Math.max(8,Math.min(e.clientX-r.left+16,r.width-240))+'px'; tip.style.top=Math.max(8,Math.min(e.clientY-r.top+16,r.height-100))+'px';
  }
  function hideTip(){const el=$('graphTip');if(el)el.style.display='none';}
  function centerGraph(){state.positions={};renderGraph();}
  function focusHot(){state.hot=!state.hot;renderGraph();}
  function toggleFX(){state.fx=!state.fx;text('fxBtn','FX '+(state.fx?'ON':'OFF'));renderGraph();}
  function toggleMinimap(){state.minimap=!state.minimap;text('miniBtn','MINIMAP '+(state.minimap?'ON':'OFF'));showError('MINIMAP',state.minimap?'Telemetry overlay enabled.':'Telemetry overlay disabled.');setTimeout(()=>{$('forgeError')?.remove();},1100);}

  async function refresh(){
    try{
      const d=await api('/api/state'); state.data=d;
      text('project',d.project);text('watch',d.watching?'WATCHING':'STOPPED');text('scan','#'+String(d.scan||0).padStart(3,'0'));text('ms',(d.duration_ms||0)+' ms');
      const s=d.stats||{},sum=d.summary||{}; text('files',s.files||0);text('sfiles',s.files||0);text('lines',Number(s.lines||0).toLocaleString());text('functions',s.functions||0);text('classes',s.classes||0);text('imports',s.imports||0);text('total',sum.total||0);text('health',d.health??100);text('gapcount',String((d.shortages||[]).length).padStart(2,'0'));text('bugcount',String((d.bugs||[]).length).padStart(2,'0'));text('sev',(sum.critical||0)+' CRITICAL / '+(sum.high||0)+' HIGH');text('arch','ARCHITECTURE: '+(d.dna?.architecture||'—'));
      html('gaps',(d.shortages||[]).length?d.shortages.map(issueCard).join(''):'<div class="empty">✓ NO ROOT PROBLEMS DETECTED</div>');
      html('bugs',(d.bugs||[]).length?d.bugs.map(issueCard).join(''):'<div class="empty">✓ NO ANOMALIES DETECTED</div>');
      html('activity',(d.activity||[]).map(x=>'<div>› '+esc(x)+'</div>').join('')||'<div class="empty">Waiting for telemetry...</div>');
      renderDNA();renderFiles();renderSecurity();renderHistory();renderGraph();
      if(d.error)showError('Backend scan error',d.error);
    }catch(e){text('watch','OFFLINE');showError('Cannot reach Forge server',e.message);}
  }

  function init(){
    document.querySelectorAll('.nav').forEach(b=>b.addEventListener('click',()=>switchTab(b.dataset.tab)));
    $('fileFilter')?.addEventListener('input',renderFiles);
    $('filesTree')?.addEventListener('click',e=>{const b=e.target.closest('[data-open-file]');if(b)openFile(decodeURIComponent(b.dataset.openFile));});
    $('searchBtn')?.addEventListener('click',doSearch);
    $('query')?.addEventListener('keydown',e=>{if(e.key==='Enter')doSearch();});
    $('results')?.addEventListener('click',e=>{const el=e.target.closest('[data-search-file]');if(el)openFile(decodeURIComponent(el.dataset.searchFile));});
    document.querySelectorAll('.graph-controls [data-mode]').forEach(b=>b.addEventListener('click',()=>{state.mode=b.dataset.mode;document.querySelectorAll('.graph-controls [data-mode]').forEach(x=>x.classList.toggle('active',x===b));renderGraph();}));
    $('hotBtn')?.addEventListener('click',focusHot); $('centerBtn')?.addEventListener('click',centerGraph); $('fxBtn')?.addEventListener('click',toggleFX); $('miniBtn')?.addEventListener('click',toggleMinimap);
    $('graphSvg')?.addEventListener('mousemove',e=>{
      if(!state.drag)return;
      const r=$('graphbox').getBoundingClientRect();
      const dx=(e.clientX-state.drag.ox)/r.width*1200,dy=(e.clientY-state.drag.oy)/r.height*700;
      state.positions[state.drag.n.id]={x:Math.max(20,Math.min(1180,state.drag.sx+dx)),y:Math.max(20,Math.min(680,state.drag.sy+dy))};
      queueGraphRender();
    });
    window.addEventListener('mouseup',()=>state.drag=null);
    $('graphSvg')?.addEventListener('click',()=>{state.selected=null;renderGraph();});
    window.addEventListener('keydown',e=>{
      if(e.ctrlKey&&e.key.toLowerCase()==='k'){e.preventDefault();switchTab('search');$('query')?.focus();}
      if(e.key==='Escape'){state.selected=null;renderGraph();}
    });
    window.addEventListener('error',e=>showError('JavaScript error',e.message||'Unknown error'));
    window.addEventListener('unhandledrejection',e=>showError('Promise error',e.reason?.message||String(e.reason||'Unknown rejection')));
    refresh();setInterval(refresh,1200);
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();