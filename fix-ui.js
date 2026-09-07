(() => {
  const esc = (s='') => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let selected = new Set();
  let latest = [];

  function ensurePanel() {
    const overview = document.getElementById('overview');
    if (!overview || document.getElementById('autoFixPanel')) return;
    const panel = document.createElement('article');
    panel.className = 'panel autoFixPanel';
    panel.id = 'autoFixPanel';
    panel.innerHTML = `<header><div><small>LOCAL REPAIR ENGINE / NO AI API</small><h3>AUTO CODE FIXER</h3></div><div><b id="fixCount">00</b> <button id="fixApply" disabled>APPLY SELECTED</button></div></header><div id="fixList" class="list"></div>`;
    const feed = overview.querySelector('.feed');
    overview.insertBefore(panel, feed || null);
    document.getElementById('fixApply').addEventListener('click', applySelected);
  }

  function render(data) {
    ensurePanel();
    const list = document.getElementById('fixList');
    const count = document.getElementById('fixCount');
    const btn = document.getElementById('fixApply');
    if (!list || !count) return;
    latest = data.fixes?.proposals || [];
    count.textContent = String(latest.length).padStart(2,'0');
    if (!latest.length) {
      list.innerHTML = `<div class="empty">✓ No supported safe fixes detected.</div>`;
      btn.disabled = true; return;
    }
    selected = new Set([...selected].filter(id => latest.some(x => x.id === id)));
    list.innerHTML = latest.map(f => `<div class="fixRow"><label><input type="checkbox" data-fix="${esc(f.id)}" ${selected.has(f.id)?'checked':''}><span><b>${esc(f.title)}</b><small>${esc(f.file)}:${esc(f.line)} • ${esc(f.confidence)} confidence</small><em>${esc(f.message)}</em><code>→ ${esc(f.replacement)}</code></span></label></div>`).join('');
    list.querySelectorAll('input[data-fix]').forEach(input => input.addEventListener('change', e => {
      const id=e.target.dataset.fix; e.target.checked ? selected.add(id) : selected.delete(id); btn.disabled=selected.size===0;
    }));
    btn.disabled = selected.size===0;
  }

  async function applySelected() {
    const fixes = latest.filter(x => selected.has(x.id));
    if (!fixes.length) return;
    if (!confirm(`Apply ${fixes.length} local fix${fixes.length===1?'':'es'}? Forge will rescan the project afterwards.`)) return;
    const btn=document.getElementById('fixApply'); btn.disabled=true; btn.textContent='APPLYING...';
    try {
      const res=await fetch('/api/fix/apply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fixes})});
      const data=await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || 'Fix failed');
      selected.clear();
      alert(`Forge applied ${data.count} fix${data.count===1?'':'es'} across ${data.changed_files.length} file${data.changed_files.length===1?'':'s'}.`);
    } catch (err) { alert(`Auto fixer error: ${err.message}`); }
    finally { btn.textContent='APPLY SELECTED'; btn.disabled=selected.size===0; }
  }

  async function poll() {
    try { const res=await fetch('/api/state?fixes=1',{cache:'no-store'}); if(res.ok) render(await res.json()); }
    catch (_) {}
  }
  setTimeout(() => { ensurePanel(); poll(); setInterval(poll, 1400); }, 350);
})();
