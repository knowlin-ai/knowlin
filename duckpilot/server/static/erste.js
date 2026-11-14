// Erste Schritte (seit 0.36): Sprache → Körper → Kopf → Bereit. Beim allerersten Start von selbst, sonst unter
// Einstellungen → Über. Nur am PC. Jeder Schritt speichert über dieselben Wege wie die Einstellungen; nach dem
// Sprachwechsel lädt die Seite neu und der Assistent macht beim nächsten Schritt weiter (sessionStorage).
// Seit 0.38.60 (Maintainer: „Weiter“ auf den Vorschlag, den ersten Start zu überarbeiten): alle fertigen Körper zur
// Wahl statt nur der Microduck, „Erst mal ohne“ zuerst und alle Cloud-Modelle gleichrangig, und am Ende wacht der
// gewählte Körper gleich im Cockpit auf – dort stehen seine Beispielsätze zum Anklicken.

import { verbindePruefknopf } from './verbindungstest.js';

export function initErsteSchritte({ $, api, toast, isRemote, showView, wecken }) {
  // Verbindungstest (seit 0.38.16): im Assistenten und in den Einstellungen – nur lesend, bewegt nichts
  verbindePruefknopf({ knopf: $('wizard-robot-test'), feld: $('wizard-robot-addr'), liste: $('wizard-robot-befund'), koerper: 'microduck', api, toast });
  verbindePruefknopf({ knopf: $('set-robot-test'), feld: $('set-robot-addr'), liste: $('set-robot-befund'), koerper: 'microduck', api, toast });
  verbindePruefknopf({ knopf: $('set-reachy-test'), feld: $('set-reachy-addr'), liste: $('set-reachy-befund'), koerper: 'reachy_mini', api, toast });
  const dlg = $('wizard');
  if (!dlg) return { start() {}, auto() {} };
  const MERK = 'duckpilot.erste-schritte';
  const MERK_KOERPER = 'duckpilot.erste-schritte.koerper';
  let schritt = 1;
  let wahl = null;                       // { modul, name } – wer am Ende aufwacht
  let echt = false;                      // echte Microduck verbunden: dann nichts im Simulator wecken

  const merk = (k, v) => { try { v ? sessionStorage.setItem(k, String(v)) : sessionStorage.removeItem(k); } catch { /* egal */ } };
  const gemerkt = (k) => { try { return sessionStorage.getItem(k) || ''; } catch { return ''; } };

  function zeige(n) {
    schritt = Math.max(1, Math.min(4, n));
    for (const s of dlg.querySelectorAll('[data-wiz]')) s.hidden = Number(s.dataset.wiz) !== schritt;
    $('wizard-step').textContent = `Schritt ${schritt} von 4`;
    $('wizard-back').hidden = schritt === 1;
    $('wizard-next').textContent = schritt < 4 ? 'Weiter' : wahl && !echt ? `${wahl.name} wecken` : 'Los geht\'s';
    merk(MERK, schritt);
  }

  async function speichern(patch) {
    const r = await api('/api/settings', 'POST', patch).catch(() => ({ ok: false }));
    if (!r.ok) toast(r.fehler || 'Nicht gespeichert', true);
    return r.ok;
  }

  function waehle(gruppe, wert) {
    for (const b of dlg.querySelectorAll(`[data-wiz-${gruppe}]`)) b.setAttribute('aria-pressed', String(b.dataset[`wiz${gruppe[0].toUpperCase()}${gruppe.slice(1)}`] === wert));
  }

  // Schritt 2: je fertigem Körper eine Wahl mit Verkörperung, Modell und Charakter (aus /api/module)
  async function koerperLaden() {
    const box = $('wizard-koerper');
    const r = await api('/api/module').catch(() => null);
    if (!box || !r || !r.ok) return;
    const fertige = r.module.filter((m) => m.art === 'koerper' && m.stand === 'fertig' && m.modul && m.figur);
    box.replaceChildren(...fertige.map((m) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'quit-choice';
      b.dataset.wizKoerper = m.modul;
      const name = document.createElement('b');
      name.textContent = m.figur.name;
      name.translate = false;
      const was = document.createElement('small');
      was.textContent = m.koerper_name;
      b.append(name, was);
      b.addEventListener('click', () => {
        wahl = { modul: m.modul, name: m.figur.name };
        echt = false;
        merk(MERK_KOERPER, JSON.stringify(wahl));
        waehle('koerper', m.modul);
        waehle('body', '');
        $('wizard-robot').hidden = true;
        zeige(3);
      });
      return b;
    }));
    if (wahl) waehle('koerper', wahl.modul);
  }

  function start(n = 1) {
    if (isRemote()) return;
    waehle('lang', document.documentElement.lang || 'de');   // die eingestellte Sprache ist sichtbar gewählt
    try { wahl = JSON.parse(gemerkt(MERK_KOERPER) || 'null'); } catch { wahl = null; }
    koerperLaden();
    zeige(n);
    if (!dlg.open) dlg.showModal();
  }

  async function fertig() {
    const wer = schritt === 4 && !echt ? wahl : null;          // „Überspringen“ weckt niemanden
    merk(MERK, 0); merk(MERK_KOERPER, 0);
    dlg.close();
    if (wer && wecken && await wecken(wer.modul)) {
      toast(`${wer.name} ist wach – rechts im Gespräch stehen Sätze zum Anklicken.`);
      return;
    }
    showView(echt ? 'cockpit' : 'start');                      // sonst auf der Startseite eine Verkörperung wecken
  }

  // Schritt 1: Sprache – Wechsel lädt die Seite neu, danach geht es mit Schritt 2 weiter
  for (const b of dlg.querySelectorAll('[data-wiz-lang]')) {
    b.addEventListener('click', async () => {
      waehle('lang', b.dataset.wizLang);
      const jetzt = document.documentElement.lang || 'de';
      if (b.dataset.wizLang === jetzt) { zeige(2); return; }
      merk(MERK, 2);
      if (await speichern({ sprache: b.dataset.wizLang })) location.reload();
    });
  }
  // Schritt 2: echte Microduck – Checkliste und Verbindungstest wie bisher
  for (const b of dlg.querySelectorAll('[data-wiz-body]')) {
    b.addEventListener('click', () => {
      const offen = $('wizard-robot').hidden;
      $('wizard-robot').hidden = !offen;
      b.setAttribute('aria-expanded', String(offen));
    });
  }
  $('wizard-robot-go').addEventListener('click', async () => {
    const robot = $('wizard-robot-addr').value.trim();
    if (await speichern({ modul: 'duckpilot', backend: 'robotd', robot })) {
      echt = true; wahl = null; merk(MERK_KOERPER, 0);
      waehle('koerper', '');
      toast('Verbinde mit dem Roboter …');
      zeige(3);
    }
  });
  // Schritt 3: Kopf – ohne Modell, lokal oder ein Cloud-Modell mit eigenem Schlüssel (alle gleichrangig)
  for (const b of dlg.querySelectorAll('[data-wiz-brain]')) {
    b.addEventListener('click', async () => {
      const art = b.dataset.wizBrain;
      waehle('brain', art);
      $('wizard-key-form').hidden = art !== 'cloud';
      $('wizard-modell-feld').hidden = true;
      if (art === 'cloud') { $('wizard-anbieter').focus(); return; }
      if (art === 'ohne') { await speichern({ gehirn: 'claude' }); zeige(4); return; }   // ohne Schlüssel: einfache Sätze
      await speichern({ gehirn: 'lokal' });
      toast('Unter Einstellungen → KI-Modell das lokale Modell wählen.');
      zeige(4);
    });
  }
  $('wizard-key-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const key = $('wizard-key').value.trim();
    const anbieter = $('wizard-anbieter').value;
    if (!key) { $('wizard-key').focus(); return; }
    const r = anbieter === 'claude'
      ? await api('/api/key', 'POST', { key }).catch(() => ({ ok: false }))
      : await api('/api/anbieter/schluessel', 'POST', { anbieter, schluessel: key }).catch(() => ({ ok: false }));
    $('wizard-key').value = '';
    if (!r.ok) { toast(r.fehler || 'Nicht gespeichert', true); return; }
    toast('Gespeichert');
    if (anbieter === 'claude') { await speichern({ gehirn: 'claude' }); zeige(4); return; }
    // andere Anbieter: Modell gleich hier wählen (die Liste ist alphabetisch, Modelle für Roboter oben)
    await speichern({ gehirn: 'anbieter', anbieter, anbieter_modell: '' });
    const m = await api('/api/anbieter/modelle', 'POST', { anbieter }).catch(() => null);
    const liste = m && m.ok && Array.isArray(m.modelle) ? m.modelle : [];
    if (!liste.length) { toast((m && m.fehler) || 'Modell später unter Einstellungen → KI-Modell wählen.', !m || !m.ok); zeige(4); return; }
    const pick = $('wizard-modell');
    const leer = document.createElement('option');
    leer.value = ''; leer.textContent = '– wählen –';
    pick.replaceChildren(leer, ...liste.map((x) => { const o = document.createElement('option'); o.value = x; o.textContent = x; return o; }));
    $('wizard-modell-feld').hidden = false;
    pick.focus();
  });
  $('wizard-modell').addEventListener('change', async (e) => {
    if (e.target.value && await speichern({ anbieter_modell: e.target.value })) zeige(4);
  });

  $('wizard-next').addEventListener('click', () => (schritt === 4 ? fertig() : zeige(schritt + 1)));
  $('wizard-back').addEventListener('click', () => zeige(schritt - 1));
  $('wizard-skip').addEventListener('click', () => { schritt = 0; fertig(); });
  dlg.addEventListener('cancel', () => { merk(MERK, 0); merk(MERK_KOERPER, 0); });   // Esc schließt – der Not-Aus bleibt Esc außerhalb
  $('wizard-open')?.addEventListener('click', () => start(1));

  return {
    start,
    // Beim ersten Start (noch keine Einstellungen, kein Schlüssel) oder nach dem Sprachwechsel mittendrin
    auto(config) {
      const weiter = Number(gemerkt(MERK)) || 0;
      if (weiter) start(weiter);
      else if (config && config.needs_setup) start(1);
    },
  };
}
