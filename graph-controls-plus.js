(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const graph = () => $('graphbox');
  const svg = () => $('graphSvg');
  let zoom = 1, panX = 0, panY = 0, panning = false, startX = 0, startY = 0, moved = false;

  function applyView(){
    const s = svg(); if(!s) return;
    s.style.transformOrigin = '50% 50%';
    s.style.transform = `translate(${panX}px,${panY}px) scale(${zoom})`;
  }
  function resetView(){ zoom=1; panX=0; panY=0; applyView(); }
  function setFullscreen(on){
    document.body.classList.toggle('neuralFullscreen', on);
    const b=$('graphExit'), f=$('graphExitFloat');
    if(b) b.textContent = on ? '⟲ EXIT GRAPH' : '⛶ FULLSCREEN';
    if(f) f.hidden = !on;
    if(on) resetView();
    requestAnimationFrame(applyView);
  }
  function exitGraph(){
    setFullscreen(false);
    const overview=document.getElementById('overview');
    document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('activeTab',x===overview));
    document.querySelectorAll('.nav').forEach(x=>x.classList.toggle('active',x.dataset.tab==='overview'));
    window.scrollTo({top:0,behavior:'smooth'});
  }

  document.addEventListener('DOMContentLoaded', () => {
    const box=graph(), s=svg(); if(!box||!s) return;
    const controls=document.querySelector('.graph-controls');
    if(controls){
      const zoomIn=document.createElement('button'); zoomIn.id='zoomIn'; zoomIn.textContent='＋ ZOOM';
      const zoomOut=document.createElement('button'); zoomOut.id='zoomOut'; zoomOut.textContent='− ZOOM';
      const reset=document.createElement('button'); reset.id='zoomReset'; reset.textContent='◎ RESET VIEW';
      controls.insertBefore(zoomIn, controls.querySelector('#graphExit') || null);
      controls.insertBefore(zoomOut, controls.querySelector('#graphExit') || null);
      controls.insertBefore(reset, controls.querySelector('#graphExit') || null);
      zoomIn.onclick=()=>{zoom=Math.min(3,zoom*1.18);applyView()};
      zoomOut.onclick=()=>{zoom=Math.max(.45,zoom/1.18);applyView()};
      reset.onclick=resetView;
    }
    $('graphExit')?.addEventListener('click', e => { e.stopPropagation(); if(document.body.classList.contains('neuralFullscreen')) exitGraph(); else setFullscreen(true); });
    $('graphExitFloat')?.addEventListener('click', exitGraph);
    s.addEventListener('wheel', e => { e.preventDefault(); zoom=Math.max(.45,Math.min(3,zoom*(e.deltaY<0?1.1:.9))); applyView(); }, {passive:false});
    box.addEventListener('mousedown', e => {
      if(e.target.closest('.node') || e.target.closest('button')) return;
      panning=true; moved=false; startX=e.clientX-panX; startY=e.clientY-panY;
      box.classList.add('isPanning');
    });
    window.addEventListener('mousemove', e => {
      if(!panning) return;
      panX=e.clientX-startX; panY=e.clientY-startY; moved=true; applyView();
    });
    window.addEventListener('mouseup', () => { panning=false; box.classList.remove('isPanning'); });
    s.addEventListener('dblclick', e => { if(e.target.closest('.node')) return; resetView(); });
    window.addEventListener('keydown', e => {
      if(e.key==='Escape' && document.body.classList.contains('neuralFullscreen')) exitGraph();
      if((e.key==='f'||e.key==='F') && document.getElementById('graph')?.classList.contains('activeTab')) setFullscreen(!document.body.classList.contains('neuralFullscreen'));
      if(e.key==='0' && document.getElementById('graph')?.classList.contains('activeTab')) resetView();
    });
    const obs=new MutationObserver(()=>{ if(s.style.transform.includes('scale') && !document.body.classList.contains('neuralFullscreen')) applyView(); });
    obs.observe(s,{attributes:true,attributeFilter:['style']});
  });
})();
