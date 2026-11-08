// „Auf Handy oder Tablet“ auf der Startseite (T2, seit 0.38.28; Wunsch: „viele werden das Ganze evtl. lieber auf
// Tablet oder Smartphone nutzen“). Ein Klick schaltet die Handy-Fernbedienung ein und zeigt den QR-Code plus einen kurzen
// Code zum Eintippen – vorher lag das tief unter System → Einstellungen. Nur am PC (Koppeln verwaltet der PC).
import { qrSvg } from './fernbedienung.js';

export function initHandyStart({ $, api, toast, showView, isRemote }) {
  const karte = $('start-handy');
  if (!karte) return { laden() {} };
  let tick = null;

  const kurzLesbar = (k) => (k ? `${k.slice(0, 3)}-${k.slice(3)}` : '');

  function zustand(r) {
    const n = (r.geraete || []).length;
    $('handy-satz').textContent = !r.an ? 'Knowlin im selben WLAN auf Handy oder Tablet bedienen – im Browser, ohne App.'
      : n ? `An – ${n === 1 ? 'ein Gerät' : `${n} Geräte`} gekoppelt. Für ein weiteres Gerät einen Code anzeigen.`
        : 'An – noch kein Gerät gekoppelt.';
    $('handy-los').textContent = r.an ? 'Code anzeigen' : 'Einschalten und Code anzeigen';
    if (r.fehler) $('handy-hinweis').textContent = r.fehler;
  }

  function zeigen(r) {
    zustand(r);
    clearInterval(tick); tick = null;
    const c = r.code;
    const da = !!(c && c.qr);
    $('handy-qr').hidden = !da;
    $('handy-code').hidden = !da;
    if (!da) { $('handy-hinweis').textContent = r.fehler || ''; return; }
    $('handy-los').textContent = 'Neuen Code anzeigen';
    $('handy-qr').replaceChildren(qrSvg(c.qr));
    const adresse = (r.name || (r.adressen || [])[0] || '').replace(/^https?:\/\//, '');
    $('handy-code').replaceChildren();
    $('handy-code').append(document.createTextNode('Code: '), Object.assign(document.createElement('b'), { textContent: kurzLesbar(c.kurz) }));
    const ip = (r.adressen || [])[0] ? (r.adressen[0]).replace(/^https?:\/\//, '') : '';
    const restText = () => {
      const s = Math.round(c.gueltig_bis - Date.now() / 1000);
      if (s <= 0) { zeigen({ ...r, code: null }); $('handy-hinweis').textContent = 'Abgelaufen – bei Bedarf einen neuen Code anzeigen.'; return; }
      $('handy-hinweis').textContent = `Mit der Kamera den QR-Code scannen. Ohne Kamera: ${adresse} im Browser öffnen und den Code eintippen`
        + `${r.name && ip ? ` (klappt das auf einem Android-Gerät nicht, nimm ${ip})` : ''}. Gilt noch ${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')} min, für ein Gerät.`;
    };
    restText();
    tick = setInterval(restText, 1000);
  }

  async function laden() {
    if (isRemote && isRemote()) { karte.hidden = true; return; }
    const r = await api('/api/fernzugang').catch(() => null);
    if (r && !r.error) zustand(r);
  }

  $('handy-los').addEventListener('click', async (ev) => {
    const knopf = ev.currentTarget;
    knopf.disabled = true;
    try {
      let r = await api('/api/fernzugang').catch(() => null);
      if (r && !r.an) {
        r = await api('/api/fernzugang', 'POST', { an: true }).catch(() => null);
        if (!r || !r.ok) { toast((r && r.fehler) || 'Ließ sich nicht einschalten', true); if (r) zustand(r); return; }
      }
      r = await api('/api/fernzugang/code', 'POST').catch(() => null);
      if (!r) { toast('Keine Antwort vom PC', true); return; }
      if (!r.ok) toast(r.fehler || 'Ging nicht', true);
      zeigen(r);
    } finally { knopf.disabled = false; }
  });
  $('handy-verwalten').addEventListener('click', () => {
    showView('settings');
    setTimeout(() => $('set-fern')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 300);
  });

  return { laden };
}
