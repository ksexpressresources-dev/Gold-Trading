/* Minimal stand-in for the claude.ai dashboard runtime, so dashboard.html runs as a public website.
   It implements the few calls the page uses: dash.loader, dash.data, dash.draw, dash.calc,
   dash.onData and dash.setLink. Data comes from data/bundle.json (rebuilt every 15 minutes
   by GitHub Actions) and data/research.json. */
(() => {
  const st = { loaders: {}, data: {}, status: {}, draws: [], mounted: new Map(), onData: [] };
  const BASE = window.GR_DATA || 'data/';
  const FILES = { research: BASE + 'research.json' };

  window.dash = {
    colors: ['#2962ff', '#26a69a', '#ef5350', '#f7a600'],
    loader(id, def) { st.loaders[id] = def.fn; },
    calc() {},
    onData(fn) { st.onData.push(fn); },
    setLink(name) { try { history.replaceState(null, '', name ? '#' + name : location.pathname); } catch (e) { /* ignore */ } },
    data(id) {
      const s = st.status[id] || 'loading';
      return { status: s, data: st.data[id] ?? [], columns: [], refreshing: false, truncated: false, meta: null };
    },
    draw(name, def) { st.draws.push([name, def]); if (st.ready) run(); },
  };

  function run() {
    for (const [name, def] of st.draws) {
      document.querySelectorAll(`[data-draw="${name}"]`).forEach((el) => {
        if (el.closest('[hidden]')) return;
        try {
          if (typeof def === 'function') { def(el); return; }
          if (!st.mounted.has(el)) { el.replaceChildren(); st.mounted.set(el, (def.mount && def.mount(el)) || {}); }
          if (def.update) def.update(el, st.mounted.get(el));
        } catch (e) { console.error('draw', name, e); }
      });
    }
    st.onData.forEach((fn) => { try { fn(); } catch (e) { console.error(e); } });
  }

  async function load() {
    const bust = '?t=' + Date.now();
    try {
      const bundle = await fetch(BASE + 'bundle.json' + bust).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); });
      for (const [id, fn] of Object.entries(st.loaders)) {
        try { st.data[id] = fn({ answer: bundle }); st.status[id] = 'ok'; } catch (e) { st.status[id] = 'error'; console.error(id, e); }
      }
    } catch (e) {
      Object.keys(st.loaders).forEach((id) => { st.status[id] = 'error'; });
      console.error('bundle', e);
    }
    for (const [id, path] of Object.entries(FILES)) {
      try { st.data[id] = await fetch(path + bust).then((r) => r.json()); st.status[id] = 'ok'; } catch (e) { st.status[id] = 'error'; }
    }
    run();
  }

  let t = 0;
  const later = () => { cancelAnimationFrame(t); t = requestAnimationFrame(run); };
  document.addEventListener('DOMContentLoaded', () => {
    st.ready = true;
    run();
    load();
    // a tab shown later gets drawn when its hidden attribute goes away
    new MutationObserver(later).observe(document.body, { attributes: true, subtree: true, attributeFilter: ['hidden'] });
    let rz = 0;
    window.addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(run, 150); });
    setInterval(load, 5 * 60 * 1000);
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') load(); });
  });
})();
