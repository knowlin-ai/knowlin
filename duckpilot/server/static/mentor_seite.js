// Mentor als eigenes Modul (seit 0.48): Lernziele, Marionette, Übungen. Server: /api/mentor, /api/marionette.
// Marionette: Am Handy führt die Lage des Geräts den Kopf (DeviceOrientation, relativ zur Lage beim Start), am PC das
// Feld mit der Maus oder den Pfeiltasten. An Knowlin gehen nur drei Zahlen (rad): gieren (+ links), nicken (+ hoch),
// neigen (+ rechts) – höchstens ≈ 15 je Sekunde. Not-Aus (Knopf, Esc) beendet das Führen hier wie überall.
import { uebersetzeText } from './i18n.js';

const tr = (t) => uebersetzeText(t) || t;
const TAKT_MS = 66;
const GRAD = Math.PI / 180;
const FELD_RAD = 1.0;                   // Rand des Feldes = so weit dreht/nickt der Kopf (vor den Grenzen des Körpers)

const winkel = (d) => ((d + 540) % 360) - 180;

export function initMentorSeite({ $, api, el, toast, send, showView }) {
  const seite = $('view-mentor');
  if (!seite) return { laden() {} };
  let stand = null, mar = null, zuletzt = 0, handyAn = false, null0 = null, nimmtAuf = false;

  const senden = (g, n, r, quelle) => {
    const t = performance.now();
    if (t - zuletzt < TAKT_MS) return;
    zuletzt = t;
    send({ type: 'marionette', gieren: +g.toFixed(3), nicken: +n.toFixed(3), neigen: +r.toFixed(3), quelle });
  };
  const ende = () => send({ type: 'marionette_ende' });

  // ── Lernziele ──────────────────────────────────────────────────────────
  function zeigeZiele(d) {
    const name = Object.fromEntries((d.koerper_liste || []).map((k) => [k.id, k.name]));
    const sel = $('mt-neu-koerper');
    if (sel.options.length <= 1) {
      for (const k of d.koerper_liste || []) sel.append(new Option(k.name, k.id));
    }
    const z = d.zahlen || {};
    $('mt-zahlen').replaceChildren(...[['Lernziele', z.ziele], ['offen', z.offen], ['gelernt', z.gelernt],
      ['Bewegungen', z.bewegungen]].flatMap(([k, v]) => [el('dt', null, tr(k)), el('dd', null, String(v ?? 0))]));
    $('mt-ziele').replaceChildren(...(d.ziele || []).map((zi) => {
      const li = el('li', `mt-ziel${zi.erledigt ? ' is-done' : ''}`);
      const kopf = el('div', 'mt-ziel-kopf');
      if (zi.eigen) {
        const cb = el('input');
        cb.type = 'checkbox';
        cb.checked = !!zi.erledigt;
        cb.setAttribute('aria-label', `${tr('erledigt')}: ${zi.titel}`);
        cb.addEventListener('change', () => aendern({ id: zi.id, erledigt: cb.checked }));
        kopf.append(cb);
      }
      kopf.append(el('b', null, zi.titel), el('span', 'chip', tr(name[zi.koerper] || (zi.koerper ? zi.koerper : 'alle'))));
      if (zi.eigen) {
        const weg = el('button', 'btn btn--ghost btn--sm', '×');
        weg.type = 'button';
        weg.setAttribute('aria-label', `${tr('Löschen')}: ${zi.titel}`);
        weg.addEventListener('click', () => loeschen(zi.id));
        kopf.append(weg);
      }
      li.append(kopf);
      const unten = el('div', 'mt-ziel-stand');
      if (zi.fortschritt != null) {
        const bar = el('div', 'bar');
        bar.setAttribute('role', 'progressbar');
        bar.setAttribute('aria-valuemin', '0');
        bar.setAttribute('aria-valuemax', '100');
        bar.setAttribute('aria-valuenow', String(Math.round(zi.fortschritt * 100)));
        bar.setAttribute('aria-label', zi.titel);
        const i = el('i');
        i.style.width = `${Math.round(zi.fortschritt * 100)}%`;
        bar.append(i);
        unten.append(bar);
      }
      unten.append(el('span', null, tr(zi.stand)));
      li.append(unten);
      return li;
    }));
    if (!(d.ziele || []).length) $('mt-ziele').append(el('li', 'field-help', tr('Noch keine Lernziele.')));
    $('mt-uebungen').replaceChildren(...(d.uebungen || []).map((u) => {
      const li = el('li', `mt-uebung${u.geht ? '' : ' is-off'}`);
      li.append(el('b', null, tr(u.titel)), el('p', 'field-help', tr(u.text)));
      const b = el('button', 'btn btn--sm', tr(u.geht ? 'Los' : 'braucht anderen Körper'));
      b.type = 'button';
      b.disabled = !u.geht;
      b.addEventListener('click', () => {
        if (u.id === 'marionette_handy') { $('mt-feld').focus(); return; }
        if (u.id === 'marionette_vr') toast(tr('Im Cockpit „In VR ansehen“ (Quest-Browser, sichere Adresse), dann „Kopf vormachen“.'));
        showView(u.ansicht, u.teil || undefined);
      });
      li.append(b);
      return li;
    }));
  }
  const fehler = (r) => toast(tr((r && r.fehler) || 'Das ging nicht'), true);
  async function aendern(body) {
    const r = await api('/api/mentor/ziel', 'POST', body).catch((e) => ({ fehler: e.message }));
    if (!r || r.ok === false) fehler(r); else { stand = r; zeigeZiele(r); }
  }
  async function loeschen(id) {
    const r = await fetch(`/api/mentor/ziel/${encodeURIComponent(id)}`, { method: 'DELETE' }).then((x) => x.json()).catch(() => null);
    if (!r || r.ok === false) fehler(r); else { stand = r; zeigeZiele(r); }
  }
  $('mt-neu').addEventListener('submit', (ev) => {
    ev.preventDefault();
    const text = $('mt-neu-text').value.trim();
    if (!text) return;
    aendern({ text, koerper: $('mt-neu-koerper').value }).then(() => { $('mt-neu-text').value = ''; });
  });

  // ── Marionette ─────────────────────────────────────────────────────────
  function zeigeMar(m) {
    mar = m;
    $('mt-grund').hidden = !m.grund;
    $('mt-grund').textContent = m.grund ? tr(m.grund) : '';
    for (const id of ['mt-feld', 'mt-aufnahme', 'mt-handy']) $(id).classList.toggle('is-off', !!m.grund);
    $('mt-aufnahme').disabled = !!m.grund;
    $('mt-bewegungen').replaceChildren(...(m.bewegungen || []).map((b) => {
      const li = el('li', 'mt-bewegung');
      li.append(el('b', null, b.name), el('span', null, `${b.dauer.toFixed(1).replace('.', ',')} s`));
      const ab = el('button', 'btn btn--sm', tr('Nachmachen'));
      ab.type = 'button';
      ab.addEventListener('click', async () => {
        const r = await api('/api/marionette/abspielen', 'POST', { name: b.name }).catch((e) => ({ fehler: e.message }));
        if (!r || r.ok === false) fehler(r); else toast(tr(r.text));
      });
      const weg = el('button', 'btn btn--ghost btn--sm', '×');
      weg.type = 'button';
      weg.setAttribute('aria-label', `${tr('Löschen')}: ${b.name}`);
      weg.addEventListener('click', async () => {
        const r = await fetch(`/api/marionette/${encodeURIComponent(b.name)}`, { method: 'DELETE' }).then((x) => x.json()).catch(() => null);
        if (r && r.bewegungen) zeigeMar({ ...mar, bewegungen: r.bewegungen });
      });
      li.append(ab, weg);
      return li;
    }));
    if (!(m.bewegungen || []).length) $('mt-bewegungen').append(el('li', 'field-help', tr('Noch keine.')));
  }
  function aufnahmeZeigen(an) {
    nimmtAuf = an;
    $('mt-aufnahme').textContent = tr(an ? 'Stopp' : 'Aufnehmen');
    $('mt-aufnahme').classList.toggle('btn--primary', an);
  }
  $('mt-aufnahme').addEventListener('click', async () => {
    if (!nimmtAuf) {
      const r = await api('/api/marionette/aufnahme', 'POST', { aktion: 'start' }).catch((e) => ({ fehler: e.message }));
      if (!r || r.ok === false) { fehler(r); return; }
      aufnahmeZeigen(true);
      $('mt-mar-text').textContent = tr(r.text);
      return;
    }
    aufnahmeZeigen(false);
    for (const id of ['mt-name-feld', 'mt-merken', 'mt-verwerfen']) $(id).hidden = false;
    $('mt-aufnahme').hidden = true;
    $('mt-name').focus();
  });
  const nachAufnahme = async (name) => {
    const r = await api('/api/marionette/aufnahme', 'POST', { aktion: 'stopp', name }).catch((e) => ({ fehler: e.message }));
    for (const id of ['mt-name-feld', 'mt-merken', 'mt-verwerfen']) $(id).hidden = true;
    $('mt-aufnahme').hidden = false;
    $('mt-name').value = '';
    if (!r || r.ok === false) fehler(r);
    $('mt-mar-text').textContent = tr((r && (r.text || r.fehler)) || '');
    if (r && r.bewegungen) zeigeMar({ ...mar, bewegungen: r.bewegungen });
    laden();
  };
  $('mt-merken').addEventListener('click', () => nachAufnahme($('mt-name').value.trim()));
  $('mt-verwerfen').addEventListener('click', () => nachAufnahme(''));

  // Feld: Maus/Finger ziehen oder Pfeiltasten → gieren/nicken
  const feld = $('mt-feld'), punkt = $('mt-punkt');
  let fx = 0, fy = 0, zieht = false;
  const feldSetzen = (x, y) => {
    fx = Math.max(-1, Math.min(1, x));
    fy = Math.max(-1, Math.min(1, y));
    punkt.style.left = `${50 + fx * 50}%`;
    punkt.style.top = `${50 - fy * 50}%`;
    feld.setAttribute('aria-valuetext', `${tr('drehen')} ${Math.round(-fx * 100)} %, ${tr('nicken')} ${Math.round(fy * 100)} %`);
    if (!mar || !mar.grund) senden(-fx * FELD_RAD, fy * FELD_RAD * 0.7, 0, 'feld');
  };
  const ausZeiger = (ev) => {
    const r = feld.getBoundingClientRect();
    feldSetzen(((ev.clientX - r.left) / r.width) * 2 - 1, 1 - ((ev.clientY - r.top) / r.height) * 2);
  };
  feld.addEventListener('pointerdown', (ev) => { zieht = true; feld.setPointerCapture(ev.pointerId); ausZeiger(ev); });
  feld.addEventListener('pointermove', (ev) => { if (zieht) ausZeiger(ev); });
  const loslassen = () => { if (!zieht) return; zieht = false; feldSetzen(0, 0); ende(); };
  feld.addEventListener('pointerup', loslassen);
  feld.addEventListener('pointercancel', loslassen);
  feld.addEventListener('keydown', (ev) => {
    const s = 0.1;
    const d = { ArrowLeft: [-s, 0], ArrowRight: [s, 0], ArrowUp: [0, s], ArrowDown: [0, -s] }[ev.key];
    if (d) { ev.preventDefault(); zuletzt = 0; feldSetzen(fx + d[0], fy + d[1]); }
    if (ev.key === 'Home') { feldSetzen(0, 0); ende(); }
  });

  // Handy: Lage des Geräts relativ zur Lage beim Start
  const istHandy = matchMedia('(pointer: coarse)').matches && 'DeviceOrientationEvent' in window;
  $('mt-handy').hidden = !istHandy;
  function lage(ev) {
    if (ev.alpha == null) return;
    if (!null0) { null0 = { a: ev.alpha, b: ev.beta, g: ev.gamma }; return; }
    const g = winkel(ev.alpha - null0.a) * GRAD;
    const n = -winkel(ev.beta - null0.b) * GRAD;
    const r = winkel(ev.gamma - null0.g) * GRAD;
    if (!mar || !mar.grund) senden(g, n, r, 'handy');
  }
  // Am Handy führt man mit Blick auf die 3D-Ansicht: kleine Leiste über dem Cockpit
  const leiste = el('div', 'mt-leiste');
  leiste.hidden = true;
  leiste.setAttribute('role', 'toolbar');
  leiste.setAttribute('aria-label', tr('Marionette'));
  const lAuf = el('button', 'btn btn--sm', tr('Aufnehmen'));
  const lEnde = el('button', 'btn btn--primary btn--sm', tr('Führen beenden'));
  lAuf.type = lEnde.type = 'button';
  leiste.append(el('span', 'mt-leiste-text', tr('Marionette')), lAuf, lEnde);
  document.body.append(leiste);
  lAuf.addEventListener('click', async () => {
    if (!nimmtAuf) {
      const r = await api('/api/marionette/aufnahme', 'POST', { aktion: 'start' }).catch((e) => ({ fehler: e.message }));
      if (!r || r.ok === false) { fehler(r); return; }
      aufnahmeZeigen(true);
    } else {
      aufnahmeZeigen(false);
      const name = `${tr('Bewegung')} ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
      const r = await api('/api/marionette/aufnahme', 'POST', { aktion: 'stopp', name }).catch((e) => ({ fehler: e.message }));
      if (!r || r.ok === false) fehler(r); else toast(tr(r.text));
    }
    lAuf.textContent = tr(nimmtAuf ? 'Stopp' : 'Aufnehmen');
  });
  lEnde.addEventListener('click', () => { handy(false); showView('mentor'); });

  async function handy(an) {
    if (an && typeof DeviceOrientationEvent.requestPermission === 'function') {
      const ok = await DeviceOrientationEvent.requestPermission().catch(() => 'denied');
      if (ok !== 'granted') { toast(tr('Ohne Bewegungssensoren geht es nicht – im Browser erlauben.'), true); return; }
    }
    handyAn = an;
    null0 = null;
    if (an) window.addEventListener('deviceorientation', lage); else { window.removeEventListener('deviceorientation', lage); ende(); }
    leiste.hidden = !an;
    lAuf.textContent = tr('Aufnehmen');
    if (an) {
      showView('cockpit');
      toast(tr('Halte das Handy wie ihren Kopf – drehen, nicken, neigen. Die Lage beim Start ist die Mitte.'));
    }
  }
  $('mt-handy').addEventListener('click', () => handy(!handyAn));

  // Not-Aus (Knopf, Esc): Führen endet hier sofort (der Server lässt den Kopf ohnehin los)
  const notaus = () => { if (handyAn) handy(false); if (zieht) { zieht = false; feldSetzen(0, 0); } aufnahmeZeigen(false); };
  $('stop')?.addEventListener('click', notaus);
  window.addEventListener('keydown', (ev) => { if (ev.key === 'Escape') notaus(); });

  async function laden() {
    const [d, m] = await Promise.all([api('/api/mentor').catch(() => null), api('/api/marionette').catch(() => null)]);
    if (d && d.ok !== false) { stand = d; zeigeZiele(d); }
    if (m) { zeigeMar(m); aufnahmeZeigen(!!m.nimmt_auf); }
  }
  // Seite sichtbar → neu laden (ohne Zeile in app.js: die Seite beobachtet ihr eigenes hidden)
  new MutationObserver(() => { if (!seite.hidden) laden(); })
    .observe(seite, { attributes: true, attributeFilter: ['hidden'] });
  return { laden };
}
