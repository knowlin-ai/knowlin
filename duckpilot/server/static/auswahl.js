// Anwählen und Handeln (seit 0.37.3, Wunsch des Maintainers): Ein Klick auf ein Ding, ein Möbelstück oder eine andere Ente
// wählt es an – Ring am Boden, daneben ein kleines Menü mit dem, was die Ente damit tun kann (aufheben, schießen,
// begrüßen, ärgern …). Solange etwas angewählt ist, meint „das“ im Chat genau dieses Ding („heb das auf“).

import { uebersetzeText } from './i18n.js';

const tr = (text) => uebersetzeText(text) || text;

export function initAuswahl({ $, api, el, scene, send, toast, stageEl }) {
  const pop = $('auswahl-pop');
  const chip = $('auswahl-chip');
  if (!pop || !chip) return { klick() {}, leeren() {} };
  let sel = null;
  let zielenFuer = null;   // „Schießen auf …“ (seit 0.37.9): der nächste Klick ist das Ziel

  function zu() { pop.hidden = true; }

  async function leeren(melden = true) {
    zu();
    if (!sel) return;
    sel = null;
    scene.setAuswahl(null);
    chip.hidden = true;
    if (melden) api('/api/handeln', 'POST', { auswahl: null }).catch(() => {});
  }

  async function handeln(aktion, d) {
    zu();
    if (aktion === 'zielen') {
      zielenFuer = d;
      toast(tr('Worauf soll sie schießen? Klick auf ein Möbel, eine Ente oder ein Ding (Esc bricht ab).'));
      return;
    }
    if (aktion === 'anschauen') {               // wie ein Klick: nur der Kopf
      send({ type: 'blick', x: d.x, y: d.y, z: 0.03, sekunden: 6 });
      return;
    }
    const r = await api('/api/handeln', 'POST', { ding: d.name, aktion }).catch((e) => ({ ok: false, fehler: e.message }));
    if (r && r.ok === false) toast(r.fehler || tr('Geht gerade nicht'), true);
    else if (r && r.text) toast(tr(r.text));                // z. B. „Ball liegt wieder an seinem Platz“ (seit 0.37.14)
  }

  function menu(d, aktionen, x, y, tipp = 'Oder im Chat: „heb das auf“, „schieß den“ …') {
    const rect = stageEl.getBoundingClientRect();
    pop.replaceChildren();
    const kopf = el('div', 'auswahl-kopf');
    kopf.append(el('strong', '', tr(d.name)));
    const schliessen = el('button', 'auswahl-zu', '×');
    schliessen.type = 'button';
    schliessen.setAttribute('aria-label', tr('Auswahl aufheben'));
    schliessen.addEventListener('click', () => leeren());
    kopf.append(schliessen);
    const liste = el('div', 'auswahl-aktionen');
    liste.setAttribute('role', 'group');
    liste.setAttribute('aria-label', tr(`Was soll sie mit ${d.name} tun?`));
    for (const a of aktionen) {
      const b = el('button', 'btn btn--ghost btn--sm', tr(a.label));
      b.type = 'button';
      b.addEventListener('click', () => handeln(a.id, d));
      liste.append(b);
    }
    pop.append(kopf, liste, el('p', 'auswahl-tipp', tr(tipp)));
    pop.hidden = false;
    // neben den Klick, aber innerhalb der Bühne
    const w = pop.offsetWidth || 220, h = pop.offsetHeight || 160;
    pop.style.left = `${Math.max(8, Math.min(rect.width - w - 8, x - rect.left + 14))}px`;
    pop.style.top = `${Math.max(8, Math.min(rect.height - h - 8, y - rect.top + 14))}px`;
  }

  async function waehle(p, x, y) {
    // mit dem Treffpunkt: ein Klick auf Aris Werkbank heißt „hier ablegen“ (seit 0.38.55)
    const wo = p.hit ? `&x=${p.hit.x.toFixed(3)}&y=${p.hit.y.toFixed(3)}` : '';
    const r = await api(`/api/handeln?ding=${encodeURIComponent(p.name)}${wo}`).catch(() => null);
    if (r && r.hinweis) toast(tr(r.hinweis));             // Werkbank: warum dort nichts hinkommt (seit 0.38.55)
    if (!r || !r.ok || !r.aktionen.length) { leeren(); return; }
    sel = { name: r.ding.name, art: p.art === 'ente' ? 'ente' : r.ding.art === 'möbel' ? 'moebel' : r.ding.art };
    scene.setAuswahl(sel);
    chip.hidden = false;
    $('auswahl-name').textContent = tr(r.ding.name);
    api('/api/handeln', 'POST', { auswahl: r.ding.name }).catch(() => {});
    menu(r.ding, r.aktionen, x, y, r.tipp);
  }

  $('auswahl-weg').addEventListener('click', () => leeren());
  document.addEventListener('pointerdown', (e) => {
    if (!pop.hidden && !e.target.closest('#auswahl-pop') && !e.target.closest('.stage')) zu();
  });
  window.addEventListener('keydown', (e) => { if (e.key === 'Escape') { zielenFuer = null; leeren(); } });

  return {
    // ein einfacher Klick in der 3D-Ansicht: Ding/Ente/Möbel anwählen, freier Boden hebt die Auswahl auf
    klick(p, x, y) {
      if (zielenFuer) {
        const ball = zielenFuer;
        zielenFuer = null;
        if (!p || !p.name || p.name === ball.name) { toast(tr('Kein Ziel gewählt – Schießen abgebrochen')); return; }
        api('/api/handeln', 'POST', { ding: ball.name, aktion: 'zielen', ziel: p.name })
          .then((r) => { if (r && r.ok === false) toast(r.fehler || tr('Geht gerade nicht'), true); })
          .catch((e) => toast(e.message, true));
        return;
      }
      if (p && p.art === 'feld') {               // Tic-Tac-Toe (seit 0.38.54): Klick aufs Feld = dein Zug
        zu();
        api('/api/handeln', 'POST', { ding: p.name, aktion: 'setzen' })
          .then((r) => { if (r && r.ok === false) toast(r.fehler || tr('Geht gerade nicht'), true); })
          .catch((e) => toast(e.message, true));
        return;
      }
      if (p && p.name) waehle(p, x, y);
      else leeren();
    },
    leeren,
  };
}
