(() => {
  'use strict';

  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const state = { data: {files:[], issues:[], graph:{nodes:[],edges:[]}, history:[]}, mode:'all', fx:true, hot:false, minimap:false, selected:null, focused:null, positions:{}, drag:null, renderQueued:false, serverOffline:false, lastErrorKey:'' };

  function text(id, value) { const el=$(id); if(el) el.textContent=String(value ?? ''); }
  function html(id, value) { const el=$(id); if(el) el.innerHTML=value; }
  function clearError(){
    const box=$('forgeError');
    if(box)box.remove();
    state.serverOffline=false;
    state.lastErrorKey='';
  }

  function showError(title, detail){
    const key=String(title)+'|'+String(detail||'');
    if(key===state.lastErrorKey)return;
    state.lastErrorKey=key;
    state.serverOffline=title==='Cannot reach Forge server';
    console.error('[FORGE]',title,detail);
    let box=$('forgeError');
    if(!box){
      box=document.createElement('div');
      box.id='forgeError';
      box.style.cssText='position:fixed;right:16px;bottom:16px;z-index:9999;max-width:520px;padding:14px 16px;border:1px solid #ff526f;background:#180810ee;color:#ffd9df;font:11px Consolas,monospace;box-shadow:0 0 35px #000;pointer-events:none';
      document.body.appendChild(box);
    }
    box.innerHTML='<b style="color:#ff7d91">'+esc(title)+'</b><div style="margin-top:6px">'+esc(detail||'')+'</div>'+
      '<small style="display:block;margin-top:5px;color:#ffb6c1">'+(state.serverOffline?'Waiting for the local Forge server…':'')+'</small>';
  }

  async function api(path) {
    const response=await fetch(path+(path.includes('?')?'&':'?')+'_='+Date.now(),{cache:'no-store'});
    const data=await response.json().catch(()=>({error:'Invalid server response'}));
    if(!response.ok || data.error) throw new Error(data.error || ('HTTP '+response.status));
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
    const allNodes=(graph.nodes||[]).filter(n=>n.kind!=='folder');
    const allEdges=(graph.edges||[]).filter(e=>e.kind!=='contains');

    // FILE NETWORK FOCUS:
    // Focus on the selected file and recursively traverse every real
    // dependency path until each reachable branch ends. No artificial links.
    let nodes=allNodes;
    if(state.focused){
      const adjacency=new Map();
      allNodes.forEach(n=>adjacency.set(n.id,{in:new Set(),out:new Set()}));
      allEdges.forEach(e=>{
        if(adjacency.has(e.source)&&adjacency.has(e.target)){
          adjacency.get(e.source).out.add(e.target);
          adjacency.get(e.target).in.add(e.source);
        }
      });

      const keep=new Set([state.focused]);
      const queue=[state.focused];
      while(queue.length){
        const id=queue.shift();
        const links=adjacency.get(id);
        if(!links)continue;
        for(const next of [...links.in,...links.out]){
          if(!keep.has(next)){keep.add(next);queue.push(next);}
        }
      }
      nodes=allNodes.filter(n=>keep.has(n.id));
    }
    // Neural-network presentation.
    // Focus mode keeps the selected file as the core and renders its full
    // one-hop network with explicit source -> core -> destination flow.
    const by=Object.fromEntries(nodes.map(n=>[n.id,n]));
    const realEdges=(state.focused?allEdges:allEdges.filter(edgeVisible)).filter(e=>by[e.source]&&by[e.target]);

    let byLayer=new Map();
    let layerCount=6;

    if(state.focused){
      const focus=state.focused;
      const visibleSet=new Set(nodes.map(n=>n.id));
      const incoming=new Map(),outgoing=new Map();
      nodes.forEach(n=>{incoming.set(n.id,[]);outgoing.set(n.id,[]);});
      realEdges.forEach(e=>{
        if(!visibleSet.has(e.source)||!visibleSet.has(e.target))return;
        outgoing.get(e.source).push(e.target);
        incoming.get(e.target).push(e.source);
      });

      // Calculate minimum directed distance from the selected file in both
      // directions. Every reachable step gets its own visual layer.
      const inDist=new Map([[focus,0]]);
      const outDist=new Map([[focus,0]]);
      let q=[focus];
      while(q.length){
        const id=q.shift();
        for(const next of incoming.get(id)||[]){
          if(!inDist.has(next)){inDist.set(next,inDist.get(id)+1);q.push(next);}
        }
      }
      q=[focus];
      while(q.length){
        const id=q.shift();
        for(const next of outgoing.get(id)||[]){
          if(!outDist.has(next)){outDist.set(next,outDist.get(id)+1);q.push(next);}
        }
      }

      const leftGroups=new Map(),rightGroups=new Map();
      nodes.forEach(n=>{
        if(n.id===focus)return;
        if(inDist.has(n.id) && (!outDist.has(n.id) || inDist.get(n.id)<=outDist.get(n.id))){
          const d=inDist.get(n.id);
          if(!leftGroups.has(d))leftGroups.set(d,[]);
          leftGroups.get(d).push(n);
        }else if(outDist.has(n.id)){
          const d=outDist.get(n.id);
          if(!rightGroups.has(d))rightGroups.set(d,[]);
          rightGroups.get(d).push(n);
        }
      });

      // Adaptive full-canvas layout.
      // Two-sided networks keep the selected file near the center. For a
      // one-sided network, the selected file shifts toward the empty side so
      // the recursive chain uses the entire canvas instead of half the screen.
      const maxInbound=Math.max(0,...inDist.values());
      const maxOutbound=Math.max(0,...outDist.values());
      const hasInbound=leftDistances.length>0;
      const hasOutbound=rightDistances.length>0;

      let focusX=600;
      let columnXs=[];

      if(hasInbound && hasOutbound){
        const total=leftDistances.length+1+rightDistances.length;
        const step=1010/Math.max(1,total-1);
        columnXs=Array.from({length:total},(_,i)=>90+i*step);
      }else if(hasOutbound){
        const total=1+rightDistances.length;
        const step=1010/Math.max(1,total-1);
        columnXs=Array.from({length:total},(_,i)=>90+i*step);
      }else if(hasInbound){
        const total=leftDistances.length+1;
        const step=1010/Math.max(1,total-1);
        columnXs=Array.from({length:total},(_,i)=>90+i*step);
      }else{
        columnXs=[600];
      }

      let colIndex=0;
      leftDistances.forEach(()=>{colIndex++;});
      const focusIndex=hasInbound ? leftDistances.length : 0;
      focusX=columnXs[focusIndex] ?? 600;

      const placeColumn=(arr,x)=>{
        const sorted=arr.slice().sort((a,b)=>{
          const degree=(Number(b.degree)||0)-(Number(a.degree)||0);
          return degree||String(a.label||'').localeCompare(String(b.label||''));
        });
        const top=55,bottom=645,gap=(bottom-top)/Math.max(1,sorted.length-1);
        sorted.forEach((n,i)=>{
          state.positions[n.id]={x,y:sorted.length===1?350:top+i*gap};
        });
      };

      leftDistances.forEach((d,i)=>{
        const x=columnXs[i];
        placeColumn(leftGroups.get(d)||[],x);
      });
      placeColumn([by[focus]],focusX);

      const rightStart=focusIndex+1;
      rightDistances.forEach((d,i)=>{
        const x=columnXs[Math.min(columnXs.length-1,rightStart+i)];
        placeColumn(rightGroups.get(d)||[],x);
      });

      // Keep the recursive depth visible in the HUD.
      layerCount=Math.max(1,columnXs.length);
      text('graphInfo','FULL FILE NETWORK // '+nodes.length+' NODES // '+realEdges.length+' LINKS');
      text('hudDepth',String(Math.max(maxInbound,maxOutbound)).padStart(2,'0'));
      text('hudBlast',String(Math.max(0,nodes.length-1)).padStart(2,'0'));
      layerCount=columns.length;
      const incomingCount=realEdges.filter(e=>e.target===focus).length;
      const outgoingCount=realEdges.filter(e=>e.source===focus).length;
      const maxIn=Math.max(0,...[...inDist.values()]);
      const maxOut=Math.max(0,...[...outDist.values()]);
      text('graphInfo','FULL FILE NETWORK // '+nodes.length+' NODES // '+realEdges.length+' LINKS');
      text('hudDepth',String(Math.max(maxIn,maxOut)).padStart(2,'0'));
      text('hudBlast',String(Math.max(0,nodes.length-1)).padStart(2,'0'));
    } else {
      const rawRanks=nodes.map(n=>Math.max(0,Number(n.rank)||0));
      const rawMax=Math.max(0,...rawRanks);
      layerCount=Math.min(6,Math.max(2,new Set(rawRanks).size));
      nodes.forEach(n=>{n.visualLayer=rawMax===0?0:Math.min(layerCount-1,Math.round((Number(n.rank)||0)/rawMax*(layerCount-1)));});
      nodes.forEach(n=>{
        if(!byLayer.has(n.visualLayer))byLayer.set(n.visualLayer,[]);
        byLayer.get(n.visualLayer).push(n);
      });
      [...byLayer.values()].forEach(arr=>arr.sort((x,y)=>String(x.label||'').localeCompare(String(y.label||''))));
      const left=95,right=1105,top=72,bottom=628;
      for(let layer=0;layer<layerCount;layer++){
        const arr=byLayer.get(layer)||[];
        const x=layerCount===1?600:left+(layer/Math.max(1,layerCount-1))*(right-left);
        const gap=(bottom-top)/Math.max(1,arr.length-1);
        arr.forEach((n,i)=>{state.positions[n.id]={x,y:arr.length===1?350:top+i*gap};});
      }
      text('graphInfo',nodes.length+' NODES / '+realEdges.length+' DATA LINKS');
      text('hudDepth',String(layerCount).padStart(2,'0'));
      text('hudBlast',String(state.data.intelligence?.impact?.blast_radius||0).padStart(2,'0'));
    }

    text('hudNodes',String(nodes.length).padStart(2,'0'));
    text('hudEdges',String(realEdges.length).padStart(2,'0'));
    text('hudMode',state.focused?'FILE NETWORK':'FULL NETWORK');

    const defs='<defs>'+
      '<marker id="arrowIn" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto"><path d="M0 0L10 5L0 10z" fill="#65dfff"/></marker>'+
      '<marker id="arrowOut" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto"><path d="M0 0L10 5L0 10z" fill="#f2ffff"/></marker>'+
      '</defs>';

    const labels=state.focused?['SOURCE / INBOUND','TARGET FILE','DESTINATION / OUTBOUND']:['INPUT','HIDDEN 1','HIDDEN 2','HIDDEN 3','HIDDEN 4','OUTPUT'];
    const guideCount=state.focused?3:layerCount;
    const guides=Array.from({length:guideCount},(_,layer)=>{
      const arr=byLayer.get(layer)||[];
      const fallback=state.focused?[155,600,1045][layer]:95+(layer/Math.max(1,layerCount-1))*1010;
      const x=arr.length?state.positions[arr[0].id].x:fallback;
      return '<line class="layerGuide" x1="'+x+'" y1="38" x2="'+x+'" y2="662"/>'+
             '<text class="layerLabel" x="'+x+'" y="24">'+esc(labels[layer]||('LAYER '+(layer+1)))+'</text>';
    }).join('');

    // No synthetic edges: render only real analyzer-detected relationships.

    const real=realEdges.map((e,i)=>{
      const s=by[e.source],t=by[e.target],p=state.positions[s.id],q=state.positions[t.id];
      if(!p||!q)return '';
      const focusedIncoming=state.focused&&e.target===state.focused;
      const focusedOutgoing=state.focused&&e.source===state.focused;
      const bidirectional=state.focused&&focusedIncoming&&realEdges.some(x=>x.source===e.target&&x.target===e.source);
      const bend=state.focused?Math.max(12,Math.min(60,Math.abs(q.y-p.y)*.08)):Math.max(12,Math.min(55,Math.abs(q.y-p.y)*.06));
      const mid=(p.x+q.x)/2;
      const d='M'+p.x+','+p.y+' C'+mid+','+(p.y-bend)+' '+mid+','+(q.y+bend)+' '+q.x+','+q.y;
      const marker=focusedIncoming?'url(#arrowIn)':'url(#arrowOut)';
      const cls=(focusedIncoming?' inbound':focusedOutgoing?' outbound':'')+(bidirectional?' bidirectional':'');
      const relation=bidirectional?'BIDIR':(focusedIncoming?'IN':'OUT');
      return '<path class="edge '+esc(e.kind)+cls+'" d="'+d+'" marker-end="'+marker+'"/>'+
             '<path class="stream" d="'+d+'" style="animation-delay:-'+((i%19)*.07)+'s;display:'+(state.fx?'block':'none')+'"/>'+
             (state.focused?'<text class="directionLabel '+(focusedIncoming?'inLabel':'outLabel')+'" x="'+mid+'" y="'+((p.y+q.y)/2-6)+'">'+relation+'</text>':'');
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

    svg.innerHTML=defs+'<g class="layerGuides">'+guides+'</g><g class="actualEdges">'+real+'</g>'+ns;
    bindNodes();
  }

  function bindNodes(){
    document.querySelectorAll('#graphSvg .node').forEach(el=>{
      el.addEventListener('mouseenter',e=>showTip(e,el.dataset.id));
      el.addEventListener('mouseleave',hideTip);
      el.addEventListener('click',e=>{
        e.stopPropagation();
        hideTip();
        state.selected=el.dataset.id;
        state.focused=el.dataset.id;
        state.positions={};
        renderGraph();
      });
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

  function intelPanel(title, body){
    const el=$('graphIntel');if(!el)return;
    el.innerHTML='<header><b>'+esc(title)+'</b><button id="intelClose">×</button></header><div class="intelBody">'+body+'</div>';
    el.classList.add('open');
    $('intelClose')?.addEventListener('click',()=>el.classList.remove('open'));
  }
  function showImpact(){
    if(!state.focused){intelPanel('IMPACT ANALYSIS','<p>Select a node first.</p>');return;}
    const graph=state.data.graph||{}, edges=(graph.edges||[]).filter(e=>e.kind!=='contains');
    const nodes=graph.nodes||[], labels=Object.fromEntries(nodes.map(n=>[n.id,n.path||n.label||n.id]));
    const incoming=new Set(),outgoing=new Set();
    edges.forEach(e=>{
      if(e.target===state.focused)incoming.add(e.source);
      if(e.source===state.focused)outgoing.add(e.target);
    });
    const up=[...incoming].map(id=>labels[id]||id).sort();
    const down=[...outgoing].map(id=>labels[id]||id).sort();
    const blast=new Set([...incoming,...outgoing]).size;
    const li=a=>a.length?a.map(v=>'<li>'+esc(v)+'</li>').join(''):'<li>NONE</li>';
    intelPanel('IMPACT // '+esc(labels[state.focused]||state.focused),
      '<div class="intelMetric"><b>'+blast+'</b><span>DIRECT BLAST RADIUS</span></div>'+
      '<section><small>UPSTREAM / INBOUND</small><ul>'+li(up)+'</ul></section>'+
      '<section><small>DOWNSTREAM / OUTBOUND</small><ul>'+li(down)+'</ul></section>');
  }

  function showXray(){
    const x=state.data.intelligence?.xray||{};
    const roles=Object.entries(x.roles||{}).map(([k,v])=>'<span><b>'+esc(k)+'</b> '+esc(v)+'</span>').join('');
    const flows=(x.flows||[]).slice(0,8).map(p=>'<li>'+p.map(esc).join(' → ')+'</li>').join('')||'<li>NO ENTRY-TO-DATA FLOW</li>';
    intelPanel('PROJECT X-RAY','<div class="intelTags">'+roles+'</div><section><small>ENTRYPOINTS</small><ul>'+((x.entrypoints||[]).map(v=>'<li>'+esc(v)+'</li>').join('')||'<li>NONE</li>')+'</ul></section><section><small>FLOWS</small><ul>'+flows+'</ul></section>');
  }
  function showCycles(){
    const a=state.data.intelligence?.cycles||[];
    intelPanel('CIRCULAR DEPENDENCIES',a.length?'<div class="intelAlert">'+a.length+' CYCLE(S) DETECTED</div>'+a.map((p,i)=>'<section><small>CYCLE '+(i+1)+'</small><div>'+p.map(esc).join(' → ')+' → '+esc(p[0])+'</div></section>').join(''):'<div class="intelOk">✓ NO CIRCULAR DEPENDENCIES</div>');
  }
  function showDeadCode(){
    const a=state.data.intelligence?.dead_code||[];
    intelPanel('DEAD CODE RADAR',a.length?'<div class="intelAlert">'+a.length+' CANDIDATES</div><ul>'+a.map(x=>'<li><b>'+esc(x.symbol||x.path||'UNKNOWN')+'</b><br><small>'+esc(x.path||'')+(x.line?' : '+x.line:'')+'</small><br>'+esc(x.reason||'')+'</li>').join('')+'</ul>':'<div class="intelOk">✓ NO DEAD-CODE CANDIDATES</div>');
  }
  async function refresh(){
    try{
      const d=await api('/api/state'); state.data=d; clearError();
      text('project',d.project);text('watch',d.watching?'WATCHING':'STOPPED');text('scan','#'+String(d.scan||0).padStart(3,'0'));text('ms',(d.duration_ms||0)+' ms');
      const s=d.stats||{},sum=d.summary||{}; text('files',s.files||0);text('sfiles',s.files||0);text('lines',Number(s.lines||0).toLocaleString());text('functions',s.functions||0);text('classes',s.classes||0);text('imports',s.imports||0);text('total',sum.total||0);text('health',d.health??100);text('gapcount',String((d.shortages||[]).length).padStart(2,'0'));text('bugcount',String((d.bugs||[]).length).padStart(2,'0'));text('sev',(sum.critical||0)+' CRITICAL / '+(sum.high||0)+' HIGH');text('arch','ARCHITECTURE: '+(d.dna?.architecture||'—'));
      html('gaps',(d.shortages||[]).length?d.shortages.map(issueCard).join(''):'<div class="empty">✓ NO ROOT PROBLEMS DETECTED</div>');
      html('bugs',(d.bugs||[]).length?d.bugs.map(issueCard).join(''):'<div class="empty">✓ NO ANOMALIES DETECTED</div>');
      html('activity',(d.activity||[]).map(x=>'<div>› '+esc(x)+'</div>').join('')||'<div class="empty">Waiting for telemetry...</div>');
      renderDNA();renderFiles();renderSecurity();renderHistory();renderGraph();
      if(d.error)showError('Backend scan error',d.error);
    }catch(e){
      text('watch','OFFLINE');
      const message=e?.message==='Failed to fetch' ? 'Local Forge server is unreachable.' : e.message;
      showError('Cannot reach Forge server',message);
    }
  }

  function init(){
    document.querySelectorAll('.nav').forEach(b=>b.addEventListener('click',()=>switchTab(b.dataset.tab)));
    $('fileFilter')?.addEventListener('input',renderFiles);
    $('filesTree')?.addEventListener('click',e=>{const b=e.target.closest('[data-open-file]');if(b)openFile(decodeURIComponent(b.dataset.openFile));});
    $('searchBtn')?.addEventListener('click',doSearch);
    $('query')?.addEventListener('keydown',e=>{if(e.key==='Enter')doSearch();});
    document.addEventListener('click',e=>{
      const el=e.target.closest('.issue-locatable[data-location-file]');
      if(!el)return;
      e.preventDefault();
      openFile(
        decodeURIComponent(el.dataset.locationFile),
        Number(el.dataset.locationLine)||0,
        Number(el.dataset.locationColumn)||0
      );
    });
    document.addEventListener('keydown',e=>{
      const el=document.activeElement?.closest?.('.issue-locatable[data-location-file]');
      if(el && (e.key==='Enter'||e.key===' ')){
        e.preventDefault();
        openFile(decodeURIComponent(el.dataset.locationFile),Number(el.dataset.locationLine)||0,Number(el.dataset.locationColumn)||0);
      }
    });
        $('results')?.addEventListener('click',e=>{const el=e.target.closest('[data-search-file]');if(el)openFile(decodeURIComponent(el.dataset.searchFile));});
    document.querySelectorAll('.graph-controls [data-mode]').forEach(b=>b.addEventListener('click',()=>{state.mode=b.dataset.mode;document.querySelectorAll('.graph-controls [data-mode]').forEach(x=>x.classList.toggle('active',x===b));renderGraph();}));
    $('hotBtn')?.addEventListener('click',focusHot);
    $('impactBtn')?.addEventListener('click',showImpact);
    $('xrayBtn')?.addEventListener('click',showXray);
    $('cyclesBtn')?.addEventListener('click',showCycles);
    $('deadBtn')?.addEventListener('click',showDeadCode);
    $('centerBtn')?.addEventListener('click',centerGraph); $('fxBtn')?.addEventListener('click',toggleFX); $('miniBtn')?.addEventListener('click',toggleMinimap);
    $('graphSvg')?.addEventListener('mousemove',e=>{
      if(!state.drag)return;
      const r=$('graphbox').getBoundingClientRect();
      const dx=(e.clientX-state.drag.ox)/r.width*1200,dy=(e.clientY-state.drag.oy)/r.height*700;
      state.positions[state.drag.n.id]={x:Math.max(20,Math.min(1180,state.drag.sx+dx)),y:Math.max(20,Math.min(680,state.drag.sy+dy))};
      queueGraphRender();
    });
    window.addEventListener('mouseup',()=>state.drag=null);
    $('graphSvg')?.addEventListener('click',e=>{
      if(e.target.closest('.node'))return;
      state.selected=null;
      state.focused=null;
      state.positions={};
      renderGraph();
    });
    window.addEventListener('keydown',e=>{
      if(e.ctrlKey&&e.key.toLowerCase()==='k'){e.preventDefault();switchTab('search');$('query')?.focus();}
      if(e.key==='Escape'){
        state.selected=null;
        state.focused=null;
        state.positions={};
        renderGraph();
      }
    });
    window.addEventListener('error',e=>showError('JavaScript error',e.message||'Unknown error'));
    window.addEventListener('unhandledrejection',e=>showError('Promise error',e.reason?.message||String(e.reason||'Unknown rejection')));
    refresh();setInterval(refresh,1200);
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();