(() => {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const $ = id => document.getElementById(id);
  function render(report) {
    if (!report) return;
    let panel = $('exceptionSafetyPanel');
    if (!panel) {
      panel = document.createElement('article');
      panel.id = 'exceptionSafetyPanel';
      panel.className = 'panel exceptionSafetyPanel';
      const overview = $('overview');
      if (overview) overview.appendChild(panel);
    }
    const m = report.metrics || {};
    const r = report.recovery || {};
    const findings = report.findings || [];
    const score = Number(report.score ?? 100);
    panel.innerHTML = `<header><div><small>RESILIENCE ENGINE</small><h3>EXCEPTION SAFETY</h3></div><b>${score}/100</b></header>
      <div class="exceptionSafetyGrid">
        <div><small>HANDLERS</small><strong>${Number(report.handlers||0)}</strong></div>
        <div><small>RISK SIGNALS</small><strong>${Number(report.risky_findings||0)}</strong></div>
        <div><small>LOGGED</small><strong>${Number(r.logged||0)}</strong></div>
        <div><small>RE-RAISED</small><strong>${Number(r.reraised||0)}</strong></div>
        <div><small>SWALLOWED</small><strong>${Number(r.swallowed||0)}</strong></div>
      </div>
      <div class="exceptionMeter"><i style="width:${Math.max(0,Math.min(100,score))}%"></i></div>
      <div class="exceptionFindings">${findings.length ? findings.slice(0,12).map(x => `<div class="exceptionFinding"><b>${esc(x.title||x.type)}</b><span>${esc(x.file)}:${esc(x.line)}</span><em>${esc(x.severity)}</em><p>${esc(x.message)}</p></div>`).join('') : '<div class="empty">✓ NO EXCEPTION HANDLING RISKS DETECTED</div>'}</div>
      ${Number(m.analysis_errors||0) ? `<small class="exceptionWarning">${Number(m.analysis_errors)} file analysis error(s) were isolated and did not stop the scan.</small>` : ''}`;
  }
  async function poll(){
    try {
      const response = await fetch('/api/state?_='+Date.now(), {cache:'no-store'});
      if (response.ok) render((await response.json()).exception_safety);
    } catch (_) {}
  }
  setInterval(poll, 1200);
  poll();
})();
