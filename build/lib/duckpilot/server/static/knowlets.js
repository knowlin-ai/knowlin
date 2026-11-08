// Knowlets (seit 0.38.5): Verkörperung, Tricks und Tänze als Paket packen, laden, prüfen, übernehmen und teilen.
// Ablauf beim Laden: Datei, Hub-Repo oder Sicherung → Server prüft streng → Vorschau mit Auswahl → Übernehmen.
// Teilen auf Hugging Face nur mit zweitem Klick („Jetzt hochladen“), privat, solange nicht „Öffentlich“ gewählt ist.
import { uebersetzeText } from './i18n.js';

const tr = (text) => uebersetzeText(text) || text;

export function initKnowlets({ $, api, el, toast, isRemote }) {
  if (!$('view-knowlets')) return { laden() {} };
  let daten = null;            // Übersicht vom Server
  let offen = null;            // geprüftes Paket (Vorschau)

  async function post(pfad, body, roh) {
    const res = await fetch(pfad, roh ? { method: 'POST', body } : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}),
    });
    return res;
  }

  function haken(name, wert, an = true, zusatz = '') {
    const l = el('label', 'knowlet-wahl');
    const i = el('input');
    i.type = 'checkbox'; i.name = name; i.value = wert; i.checked = an;
    l.append(i, document.createTextNode(` ${wert}${zusatz}`));
    return l;
  }

  function figurWahl() {
    const sel = $('kn-figur');
    const modul = sel.value;
    const f = daten.figuren.find((x) => x.modul === modul) || daten.figuren[0];
    const box = $('kn-tricks');
    box.replaceChildren(...(f.tricks.length ? f.tricks.map((t) => haken('kn-trick', t)) : [el('span', 'field-help', tr('Noch keine eigenen Tricks.'))]));
    if (!$('kn-titel').value || $('kn-titel').dataset.auto === '1') { $('kn-titel').value = f.name; $('kn-titel').dataset.auto = '1'; }
  }

  async function laden() {
    if (isRemote && isRemote()) return;
    daten = await api('/api/knowlets').catch(() => null);
    if (!daten) return;
    const sel = $('kn-figur');
    const vorher = sel.value;
    sel.replaceChildren(...daten.figuren.map((f) => {
      const o = el('option', null, `${f.name} · ${tr(f.koerper)}`);
      o.value = f.modul;
      return o;
    }));
    sel.value = vorher || (daten.figuren.find((f) => f.aktiv) || daten.figuren[0]).modul;
    figurWahl();
    $('kn-taenze').replaceChildren(...(daten.taenze.length ? daten.taenze.map((t) => haken('kn-tanz', t, false)) : [el('span', 'field-help', tr('Noch keine Tänze.'))]));
    const liz = $('kn-lizenz');
    if (!liz.options.length) liz.replaceChildren(...daten.lizenzen.map((l) => { const o = el('option', null, l); o.value = l; return o; }));
    const sich = $('kn-sicherungen');
    sich.replaceChildren(...(daten.gesichert.length ? daten.gesichert.map((d) => {
      const li = el('li');
      const b = el('button', 'btn btn--ghost btn--sm', tr('Ansehen'));
      b.type = 'button';
      b.addEventListener('click', () => pruefen(post(`/api/knowlets/gesichert/${encodeURIComponent(d)}`)));
      const m = d.match(/^sicherung-(.+)-(\d{4})(\d\d)(\d\d)-(\d\d)(\d\d)\d\d\.knowlet$/);
      const zeit = m ? new Date(+m[2], +m[3] - 1, +m[4], +m[5], +m[6]) : null;
      const wann = zeit ? zeit.toLocaleString(document.documentElement.lang || 'de', { dateStyle: 'medium', timeStyle: 'short' }) : '';
      li.append(el('span', null, m ? `${m[1].replace(/_/g, ' ')} · ${wann}` : d.replace(/\.knowlet$/, '')), b);
      return li;
    }) : [el('li', 'field-help', tr('Noch keine.'))]));
    $('kn-teilen-hinweis').textContent = daten.hub.schluessel
      ? tr('Lädt das Knowlet in ein Dataset-Repo unter deinem Hugging-Face-Konto.')
      : tr('Dafür braucht Knowlin deinen Hugging-Face-Schlüssel – hinterlegen unter Lernen → Training.');
    $('kn-hochladen').disabled = !daten.hub.schluessel;
  }

  function auswahl() {
    return {
      modul: $('kn-figur').value, figur: $('kn-mit-figur').checked,
      tricks: [...document.querySelectorAll('input[name="kn-trick"]:checked')].map((i) => i.value),
      taenze: [...document.querySelectorAll('input[name="kn-tanz"]:checked')].map((i) => i.value),
      titel: $('kn-titel').value.trim(), beschreibung: $('kn-beschreibung').value.trim(),
      urheber: $('kn-urheber').value.trim(), lizenz: $('kn-lizenz').value,
    };
  }

  // ── Laden und Vorschau ─────────────────────────────────────────────
  async function pruefen(anfrage) {
    const box = $('kn-vorschau');
    let r;
    try { r = await (await anfrage).json(); } catch { r = { ok: false, fehler: tr('Keine Antwort') }; }
    if (!r.ok) { toast(r.fehler || tr('Das Knowlet ließ sich nicht öffnen'), true); return; }
    offen = r;
    const s = r.steckbrief;
    const kopf = el('div');
    kopf.append(el('h4', null, s.name), el('p', 'field-help', [tr(`für ${s.koerper}`), s.urheber && tr(`von ${s.urheber}`), s.lizenz].filter(Boolean).join(' · ')));
    const teile = [kopf];
    if (s.beschreibung) teile.push(el('p', null, s.beschreibung));
    if (r.figur) {
      const f = r.figur;
      teile.push(haken('kn-ueb-figur', tr(`Charakter „${f.name}“`), false,
        ` – ${tr(`ersetzt den von ${r.ziel.figur}`)} (${tr('vorher gesichert')})`));
    }
    if (r.tricks.length) {
      const g = el('fieldset', 'knowlet-gruppe');
      g.append(el('legend', 'field-label', tr('Tricks')));
      const d = el('div');
      for (const t of r.tricks) d.append(haken('kn-ueb-trick', t.name, true, t.gibt_es ? ` (${tr('gibt es schon – kommt als Kopie')})` : ''));
      g.append(d);
      teile.push(g, el('p', 'field-help', tr('Tricks aus Knowlets laufen am echten Roboter erst, nachdem sie einmal im Simulator liefen.')));
    }
    if (r.taenze.length) {
      const g = el('fieldset', 'knowlet-gruppe');
      g.append(el('legend', 'field-label', tr('Tänze')));
      const d = el('div');
      for (const t of r.taenze) d.append(haken('kn-ueb-tanz', t.name, true, t.gibt_es ? ` (${tr('gibt es schon – kommt als Kopie')})` : ''));
      g.append(d);
      teile.push(g);
    }
    const z = el('div', 'knowlet-zeile');
    const ok = el('button', 'btn btn--primary', tr(`Zu ${r.ziel.figur} übernehmen`));
    ok.type = 'button';
    ok.addEventListener('click', uebernehmen);
    const ab = el('button', 'btn btn--ghost', tr('Verwerfen'));
    ab.type = 'button';
    ab.addEventListener('click', () => { offen = null; box.hidden = true; });
    z.append(ok, ab);
    teile.push(z);
    box.replaceChildren(...teile);
    box.hidden = false;
    box.scrollIntoView({ block: 'nearest' });
  }

  async function uebernehmen() {
    if (!offen) return;
    const body = {
      id: offen.id, figur: Boolean(document.querySelector('input[name="kn-ueb-figur"]:checked')),
      tricks: [...document.querySelectorAll('input[name="kn-ueb-trick"]:checked')].map((i) => i.value),
      taenze: [...document.querySelectorAll('input[name="kn-ueb-tanz"]:checked')].map((i) => i.value),
    };
    const r = await (await post('/api/knowlets/uebernehmen', body)).json().catch(() => ({ ok: false }));
    if (!r.ok) { toast(r.fehler || tr('Übernehmen ging nicht'), true); return; }
    toast(tr(`Übernommen: ${r.uebernommen.join(', ')}`));
    offen = null;
    $('kn-vorschau').hidden = true;
    laden();
  }

  $('kn-oeffnen').addEventListener('click', () => $('kn-datei').click());
  $('kn-datei').addEventListener('change', (ev) => {
    const d = ev.target.files?.[0];
    if (d) pruefen(d.arrayBuffer().then((b) => post('/api/knowlets/pruefen', b, true)));
    ev.target.value = '';
  });
  $('kn-repo-laden').addEventListener('click', () => {
    const repo = $('kn-repo').value.trim();
    if (repo) pruefen(post('/api/knowlets/hub/laden', { repo }));
  });
  async function suchen() {
    const liste = $('kn-treffer');
    liste.replaceChildren(el('li', 'field-help', tr('Suche auf Hugging Face …')));
    const r = await api(`/api/knowlets/hub/suche?q=${encodeURIComponent($('kn-suche').value.trim())}`).catch(() => ({ ok: false }));
    if (!r.ok) { liste.replaceChildren(el('li', 'field-help', r.fehler || tr('Hugging Face nicht erreichbar'))); return; }
    if (!r.treffer.length) { liste.replaceChildren(el('li', 'field-help', tr('Nichts gefunden.'))); return; }
    liste.replaceChildren(...r.treffer.map((t) => {
      const li = el('li');
      const info = el('span');
      info.append(el('b', null, t.repo), el('small', null, ` ${[t.koerper.map(tr).join(', '), tr(`${t.downloads} geladen`)].filter(Boolean).join(' · ')}`));
      const b = el('button', 'btn btn--ghost btn--sm', tr('Ansehen'));
      b.type = 'button';
      b.addEventListener('click', () => pruefen(post('/api/knowlets/hub/laden', { repo: t.repo })));
      li.append(info, b);
      return li;
    }));
  }
  $('kn-suchen').addEventListener('click', suchen);
  $('kn-suche').addEventListener('keydown', (ev) => { if (ev.key === 'Enter') suchen(); });

  // ── Packen und Teilen ──────────────────────────────────────────────
  $('kn-figur').addEventListener('change', figurWahl);
  $('kn-titel').addEventListener('input', () => { $('kn-titel').dataset.auto = '0'; });
  $('kn-speichern').addEventListener('click', async () => {
    const res = await post('/api/knowlets/packen', auswahl());
    if (!res.ok) { const r = await res.json().catch(() => ({})); toast(r.fehler || tr('Packen ging nicht'), true); return; }
    const blob = await res.blob();
    const name = (res.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/)?.[1] || 'figur.knowlet';
    const a = el('a');
    a.href = URL.createObjectURL(blob); a.download = name;
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 10000);
    toast(tr(`${name} gespeichert`));
  });
  $('kn-teilen').addEventListener('click', () => { $('kn-teilen-box').hidden = false; $('kn-hochladen').focus(); });
  $('kn-teilen-ab').addEventListener('click', () => { $('kn-teilen-box').hidden = true; });
  $('kn-hochladen').addEventListener('click', async () => {
    const b = $('kn-hochladen');
    b.disabled = true;
    const a = auswahl();
    const r = await (await post('/api/knowlets/hub/teilen', { ...a, slug: a.titel, oeffentlich: $('kn-oeffentlich').checked, bestaetigt: true }))
      .json().catch(() => ({ ok: false }));
    b.disabled = false;
    if (!r.ok) { toast(r.fehler || tr('Hochladen ging nicht'), true); return; }
    $('kn-teilen-box').hidden = true;
    toast(r.oeffentlich ? tr(`Geteilt: ${r.repo} (öffentlich)`) : tr(`Hochgeladen: ${r.repo} (privat)`));
  });

  return { laden };
}
