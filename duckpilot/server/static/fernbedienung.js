// Handy-Fernbedienung: am PC einschalten, Handy per QR-Code koppeln, Geräte abmelden, mit Windows starten.
// Auf dem Handy selbst blendet die Oberfläche aus, was nur am PC geht (Schlüssel, Installationen, …).
// Gerätenamen kommen vom Handy – sie landen nur über textContent im Dokument.
import { offenlegen } from './offenlegung.js';

const SVG = 'http://www.w3.org/2000/svg';

export function qrSvg(rows) {
  const n = rows.length, q = 4;           // 4 Module Ruhezone – sonst erkennen manche Kameras den Code nicht
  const svg = document.createElementNS(SVG, 'svg');
  svg.setAttribute('viewBox', `0 0 ${n + 2 * q} ${n + 2 * q}`);
  svg.setAttribute('shape-rendering', 'crispEdges');
  const bg = document.createElementNS(SVG, 'rect');
  bg.setAttribute('width', n + 2 * q); bg.setAttribute('height', n + 2 * q); bg.setAttribute('fill', '#fff');
  let d = '';
  rows.forEach((row, y) => {
    for (let x = 0; x < row.length; x++) if (row[x] === '1') d += `M${x + q} ${y + q}h1v1h-1z`;
  });
  const path = document.createElementNS(SVG, 'path');
  path.setAttribute('d', d); path.setAttribute('fill', '#000');
  svg.append(bg, path);
  return svg;
}

function ago(ts) {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 90) return 'gerade eben';
  if (s < 3600) return `vor ${Math.round(s / 60)} min`;
  if (s < 86400 * 2) return `vor ${Math.round(s / 3600)} h`;
  return `vor ${Math.round(s / 86400)} Tagen`;
}

export function initFern(h) {
  const { $, api, el, toast } = h;
  let data = null;
  let remote = false;
  let tick = null;
  let busy = false;

  async function load() {
    if (remote) return;
    const r = await api('/api/fernzugang').catch(() => null);
    if (r && !r.error) render(r);
  }

  async function post(body) {
    if (busy) return;
    busy = true;
    try {
      const r = await api('/api/fernzugang', 'POST', body).catch(() => null);
      if (!r) toast('Keine Antwort vom PC', true);
      else { if (!r.ok) toast(r.fehler || 'Ging nicht', true); render(r); }
    } finally { busy = false; }
  }

  function render(r) {
    data = r;
    $('fern-an').checked = !!r.an;
    offenlegen();                                  // Details erst, wenn die Fernbedienung an ist (0.38.14)
    $('fern-port').value = r.port;
    const state = $('fern-state');
    if (!r.an) state.textContent = 'Aus. Nur dieser PC kann Knowlin bedienen.';
    else if (r.fehler) state.textContent = r.fehler;
    else if (!r.lauscht) state.textContent = 'Startet …';
    else if (!r.adressen.length) state.textContent = 'An, aber kein Heimnetz gefunden. Ist der PC im WLAN oder per Kabel verbunden?';
    else state.textContent = `An. Erreichbar im Heimnetz unter ${r.adressen[0]}`;
    state.classList.toggle('is-bad', !!(r.an && r.fehler));
    $('fern-code').disabled = !r.an || !r.lauscht || !r.adressen.length;
    $('fern-code').hidden = !!(r.code && r.code.qr);
    renderPair(r.code);
    renderDevices(r.geraete || []);
    $('fern-auto-row').hidden = !r.autostart_moeglich;
    $('fern-autostart').checked = !!r.autostart;
    $('fern-quit').hidden = !(r.an && h.isApp());
    renderTs(r.tailscale || {});
  }

  function renderTs(t) {
    const st = t.status || {};
    $('fern-ts-an').checked = !!t.an;
    $('fern-ts-an').disabled = !data || !data.an;
    let msg;
    if (t.an && t.adresse) msg = `An: ${t.adresse} – auch unterwegs, mit https.`;
    else if (data && !data.an) msg = 'Erst „Vom Handy aus bedienen“ einschalten.';
    else if (st.installiert === false) msg = 'Tailscale ist auf diesem PC nicht installiert.';
    else if (st.fehler) msg = st.fehler;
    else if (st.name) msg = `Bereit: dieser PC heißt im Tailnet ${st.name}.`;
    else msg = 'Aus.';
    $('fern-ts-state').textContent = msg;
    // Tailscale ist ein eigenes Programm mit Netzwerktreiber – Knowlin kann es nicht wie Python-Pakete nachinstallieren.
    // Deshalb der Weg dorthin (seit 0.38.34, „Tailscale kann man doch verlinken?“)
    if (st.installiert === false && !(data && !data.an)) {
      const a = el('a', 'link', 'Tailscale für Windows laden');
      a.href = 'https://tailscale.com/download/windows'; a.target = '_blank'; a.rel = 'noopener';
      $('fern-ts-state').append(' ', a, document.createTextNode(' – installieren, anmelden, dann den Schalter einschalten.'));
    }
  }
  function showTsLink(link) {
    const ok = typeof link === 'string' && link.startsWith('https://login.tailscale.com/');
    $('fern-ts-link-row').hidden = !ok;
    if (ok) $('fern-ts-link').href = link;
  }

  function renderPair(code) {
    const box = $('fern-pair');
    clearInterval(tick); tick = null;
    if (!code || !code.qr) { box.hidden = true; return; }
    box.hidden = false;
    $('fern-qr').replaceChildren(qrSvg(code.qr));
    $('fern-link').textContent = code.link;
    const name = (data && data.name ? data.name : '').replace(/^https?:\/\//, '');
    $('fern-kurz').textContent = code.kurz ? `Oder${name ? ` ${name}` : ' die Adresse ohne „/koppeln?c=…“'} öffnen und den Code `
      + `${code.kurz.slice(0, 3)}-${code.kurz.slice(3)} eintippen.` : '';
    const left = () => Math.round(code.gueltig_bis - Date.now() / 1000);
    const upd = () => {
      const s = left();
      if (s <= 0) { $('fern-left').textContent = 'Abgelaufen – neuen Code anzeigen.'; box.hidden = true; $('fern-code').hidden = false; clearInterval(tick); return; }
      $('fern-left').textContent = `Gilt noch ${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')} min und nur für ein Gerät.`;
    };
    upd();
    tick = setInterval(upd, 1000);
  }

  function renderDevices(list) {
    const ul = $('fern-devices');
    $('fern-all').hidden = list.length < 2;
    if (!list.length) { ul.replaceChildren(el('li', 'fern-empty', 'Noch kein Gerät gekoppelt.')); return; }
    ul.replaceChildren(...list.map((d) => {
      const li = el('li', 'fern-dev');
      const txt = el('div', 'fern-dev-text');
      txt.append(el('b', '', d.name), el('small', '', `gekoppelt ${new Date(d.seit * 1000).toLocaleDateString('de-DE')} · zuletzt ${ago(d.zuletzt)}`));
      const btn = el('button', 'btn btn--ghost btn--sm', 'Abmelden');
      btn.type = 'button';
      btn.addEventListener('click', async () => {
        const r = await api(`/api/fernzugang/geraet/${encodeURIComponent(d.id)}`, 'DELETE').catch(() => null);
        if (r && r.ok) { toast(`${d.name} abgemeldet`); render({ ...data, ...r, code: data.code }); }
        else toast((r && r.fehler) || 'Ging nicht', true);
      });
      li.append(txt, btn);
      return li;
    }));
  }

  // ── Bedienelemente am PC ──────────────────────────────────────────────
  $('fern-an').addEventListener('change', (e) => post({ an: e.target.checked }));
  $('fern-port').addEventListener('change', (e) => {
    const p = parseInt(e.target.value, 10);
    if (Number.isFinite(p)) post({ port: p }); else e.target.value = data ? data.port : 8766;
  });
  $('fern-autostart').addEventListener('change', (e) => post({ autostart: e.target.checked }));
  $('fern-ts-an').addEventListener('change', async (e) => {
    $('fern-ts-state').textContent = e.target.checked ? 'Richte Tailscale ein …' : 'Schalte ab …';
    const r = await api('/api/fernzugang', 'POST', { tailscale: e.target.checked }).catch(() => null);
    if (!r) { toast('Keine Antwort vom PC', true); return; }
    showTsLink(r.link);
    if (!r.ok) toast(r.fehler || 'Ging nicht', true);
    load();
  });
  $('fern-code').addEventListener('click', async () => {
    const r = await api('/api/fernzugang/code', 'POST').catch(() => null);
    if (!r || !r.ok) toast((r && r.fehler) || 'Kein Code', true);
    if (r) render(r);
  });
  $('fern-cancel').addEventListener('click', async () => {
    const r = await api('/api/fernzugang/code', 'DELETE').catch(() => null);
    if (r) render(r);
  });
  $('fern-all').addEventListener('click', async () => {
    const r = await api('/api/fernzugang/geraete', 'DELETE').catch(() => null);
    if (r && r.ok) { toast('Alle Geräte abgemeldet'); render(r); }
  });
  $('fern-quit').addEventListener('click', () => h.openQuit());   // derselbe Dialog wie oben rechts „Beenden“

  return {
    load,
    // Nachricht nach dem Koppeln (an alle Fenster): Liste auffrischen, QR-Code schließen
    update(msg) {
      if (remote) return;
      const before = data ? (data.geraete || []).length : 0;
      const now = (msg.geraete || []).length;
      if (now > before) toast(`${msg.geraete[now - 1].name} ist gekoppelt`);
      load();
    },
    // Diese Oberfläche läuft selbst auf einem Handy
    setRemote(on, name) {
      remote = !!on;
      document.body.classList.toggle('is-fern', remote);
      if (remote) $('fern-remote-name').textContent = name || 'dieses Gerät';
    },
    get remote() { return remote; },
  };
}
