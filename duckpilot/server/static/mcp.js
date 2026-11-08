// MCP-Zugang in den Einstellungen: Zustand, neuer Schlüssel, Befehle zum Kopieren. Texte nur über textContent.

export function initMcp(h) {
  const { $, api, toast } = h;
  const box = $('mcp-box');

  function render(info, fresh) {
    box.hidden = !info.an;
    if (!info.an) return;
    $('mcp-state').textContent = `Adresse ${info.adresse} · Schlüssel ${info.schluessel || 'noch keiner'} · `
      + `${info.werkzeuge.length} Werkzeuge · ${info.aufrufe} Aufrufe seit dem Start`;
    $('mcp-code').textContent = info.claude_code;
    $('mcp-desktop').textContent = info.claude_desktop;
    $('mcp-key-note').hidden = !fresh;
  }

  async function load() {
    const info = await api('/api/mcp').catch(() => null);
    if (info) render(info, false);
  }

  $('mcp-key').addEventListener('click', async () => {
    const r = await api('/api/mcp/schluessel', 'POST').catch(() => null);
    if (!r || !r.ok) { toast(r ? r.fehler : 'Keine Antwort', true); return; }
    render(r, true);
    toast('Neuer Schlüssel – der alte gilt nicht mehr');
  });
  for (const b of box.querySelectorAll('[data-copy]')) {
    b.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText($(b.dataset.copy).textContent); toast('Kopiert'); }
      catch { toast('Kopieren ging nicht – bitte markieren und Strg+C', true); }
    });
  }
  return { load };
}
