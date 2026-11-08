// Erste Schritte (seit 0.36): Sprache → Körper → Gehirn → Bereit. Beim allerersten Start von selbst, sonst unter
// Einstellungen → Über. Nur am PC. Jeder Schritt speichert sofort über dieselben Wege wie die Einstellungen; nach dem
// Sprachwechsel lädt die Seite neu und der Assistent macht beim nächsten Schritt weiter (sessionStorage).

import { verbindePruefknopf } from './verbindungstest.js';

export function initErsteSchritte({ $, api, toast, isRemote, showView }) {
  // Verbindungstest (seit 0.38.16): im Assistenten und in den Einstellungen – nur lesend, bewegt nichts
  verbindePruefknopf({ knopf: $('wizard-robot-test'), feld: $('wizard-robot-addr'), liste: $('wizard-robot-befund'), koerper: 'microduck', api, toast });
  verbindePruefknopf({ knopf: $('set-robot-test'), feld: $('set-robot-addr'), liste: $('set-robot-befund'), koerper: 'microduck', api, toast });
  verbindePruefknopf({ knopf: $('set-reachy-test'), feld: $('set-reachy-addr'), liste: $('set-reachy-befund'), koerper: 'reachy_mini', api, toast });
  const dlg = $('wizard');
  if (!dlg) return { start() {}, auto() {} };
  const MERK = 'duckpilot.erste-schritte';
  let schritt = 1;

  const merk = (v) => { try { v ? sessionStorage.setItem(MERK, String(v)) : sessionStorage.removeItem(MERK); } catch { /* egal */ } };
  const gemerkt = () => { try { return Number(sessionStorage.getItem(MERK)) || 0; } catch { return 0; } };

  function zeige(n) {
    schritt = Math.max(1, Math.min(4, n));
    for (const s of dlg.querySelectorAll('[data-wiz]')) s.hidden = Number(s.dataset.wiz) !== schritt;
    $('wizard-step').textContent = `Schritt ${schritt} von 4`;
    $('wizard-back').hidden = schritt === 1;
    $('wizard-next').textContent = schritt === 4 ? 'Los geht\'s' : 'Weiter';
    merk(schritt);
  }

  async function speichern(patch) {
    const r = await api('/api/settings', 'POST', patch).catch(() => ({ ok: false }));
    if (!r.ok) toast(r.fehler || 'Nicht gespeichert', true);
    return r.ok;
  }

  function waehle(gruppe, wert) {
    for (const b of dlg.querySelectorAll(`[data-wiz-${gruppe}]`)) b.setAttribute('aria-pressed', String(b.dataset[`wiz${gruppe[0].toUpperCase()}${gruppe.slice(1)}`] === wert));
  }

  function start(n = 1) {
    if (isRemote()) return;
    waehle('lang', document.documentElement.lang || 'de');   // die eingestellte Sprache ist sichtbar gewählt
    zeige(n);
    if (!dlg.open) dlg.showModal();
  }

  function fertig() {
    merk(0);
    dlg.close();
    showView('start');                                     // danach auf Knowlins Startseite: eine Verkörperung wecken
  }

  // Schritt 1: Sprache – Wechsel lädt die Seite neu, danach geht es mit Schritt 2 weiter
  for (const b of dlg.querySelectorAll('[data-wiz-lang]')) {
    b.addEventListener('click', async () => {
      waehle('lang', b.dataset.wizLang);
      const jetzt = document.documentElement.lang || 'de';
      if (b.dataset.wizLang === jetzt) { zeige(2); return; }
      merk(2);
      if (await speichern({ sprache: b.dataset.wizLang })) location.reload();
    });
  }
  // Schritt 2: Körper
  for (const b of dlg.querySelectorAll('[data-wiz-body]')) {
    b.addEventListener('click', async () => {
      const art = b.dataset.wizBody;
      waehle('body', art);
      $('wizard-robot').hidden = art !== 'robot';
      if (art === 'sim' && await speichern({ backend: 'sim', sim_physik: false })) zeige(3);
      if (art === 'physik' && await speichern({ backend: 'sim', sim_physik: true })) {
        toast('Echte Physik: Knowlin lädt die Pakete einmalig – das dauert ein paar Minuten.');
        zeige(3);
      }
    });
  }
  $('wizard-robot-go').addEventListener('click', async () => {
    const robot = $('wizard-robot-addr').value.trim();
    if (await speichern({ backend: 'robotd', robot })) { toast('Verbinde mit dem Roboter …'); zeige(3); }
  });
  // Schritt 3: Gehirn
  for (const b of dlg.querySelectorAll('[data-wiz-brain]')) {
    b.addEventListener('click', async () => {
      const art = b.dataset.wizBrain;
      waehle('brain', art);
      $('wizard-key-form').hidden = art !== 'claude';
      $('wizard-key-help').hidden = art !== 'claude';
      if (art === 'claude') { $('wizard-key').focus(); return; }
      if (art === 'ohne') { await speichern({ gehirn: 'claude' }); zeige(4); return; }
      await speichern({ gehirn: art });
      toast(art === 'lokal' ? 'Unter Einstellungen → KI-Modell das lokale Modell wählen.' : 'Unter Einstellungen → KI-Modell Anbieter, Schlüssel und Modell wählen.');
      zeige(4);
    });
  }
  $('wizard-key-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const key = $('wizard-key').value.trim();
    if (!key) return;
    const r = await api('/api/key', 'POST', { key }).catch(() => ({ ok: false }));
    $('wizard-key').value = '';
    if (!r.ok) { toast(r.fehler || 'Nicht gespeichert', true); return; }
    await speichern({ gehirn: 'claude' });
    toast('Gespeichert');
    zeige(4);
  });

  $('wizard-next').addEventListener('click', () => (schritt === 4 ? fertig() : zeige(schritt + 1)));
  $('wizard-back').addEventListener('click', () => zeige(schritt - 1));
  $('wizard-skip').addEventListener('click', fertig);
  dlg.addEventListener('cancel', () => merk(0));                 // Esc schließt – der Not-Aus-Knopf bleibt Esc außerhalb
  $('wizard-open')?.addEventListener('click', () => start(1));

  return {
    start,
    // Beim ersten Start (noch keine Einstellungen, kein Schlüssel) oder nach dem Sprachwechsel mittendrin
    auto(config) {
      const weiter = gemerkt();
      if (weiter) start(weiter);
      else if (config && config.needs_setup) start(1);
    },
  };
}
