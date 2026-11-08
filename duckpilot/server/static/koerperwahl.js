// Körper direkt oben umschalten (seit 0.37.1, Wunsch des Maintainers „mach, dass man oben auch den Simulator direkt
// umschalten kann“): Der Körper-Chip neben dem Namen öffnet ein Menü – einfacher Simulator, echte Physik, echter
// Roboter. Dieselben Einstellungen wie unter Einstellungen → Körper (backend, sim_physik); am Handy nur Anzeige,
// denn wohin duckpilot sich verbindet, ändert nur der PC (remote.PC_ONLY_SETTINGS).

import { uebersetzeText } from './i18n.js';

const tr = (text) => uebersetzeText(text) || text;

export function initKoerperwahl({ $, api, save, showView, isRemote }) {
  const btn = $('koerper-btn');
  const pop = $('koerper-pop');
  if (!btn || !pop) return { update() {} };
  let aktuell = 'sim';
  let modul = 'duckpilot';               // Körper bleibt beim Umschalten derselbe (0.38.14: Open Duck blieb nicht Open Duck)
  let physikBereit = null;              // null = noch nicht gefragt

  const setOpen = (open) => {
    pop.hidden = !open;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) pruefen();
  };
  btn.addEventListener('click', (e) => { e.stopPropagation(); if (!btn.disabled) setOpen(pop.hidden); });
  document.addEventListener('pointerdown', (e) => { if (!pop.hidden && !e.target.closest('.koerperwahl')) setOpen(false); });
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !pop.hidden) { setOpen(false); btn.focus(); }
  });

  function optionen() {
    for (const b of pop.querySelectorAll('[data-koerper]')) {
      const k = b.dataset.koerper;
      b.setAttribute('aria-pressed', String(k === aktuell));
      b.disabled = k === 'physik' && physikBereit === false && aktuell !== 'physik';
    }
    const info = $('koerper-physik-info');
    if (physikBereit === false) info.textContent = tr('Erst einrichten: Einstellungen → Körper (MuJoCo und Pollens Policies)');
    else info.textContent = tr('Pollens MuJoCo-Modell und Policies – auch Hub-Tricks');
  }

  // Ist die echte Physik startklar? (MuJoCo installiert, Pollens Policies geladen)
  async function pruefen() {
    const m = await api('/api/physik').catch(() => null);
    if (m && m.installiert && m.policies) physikBereit = Boolean(m.installiert.physik && m.policies.bereit);
    optionen();
  }

  for (const b of pop.querySelectorAll('[data-koerper]')) {
    b.addEventListener('click', async () => {
      const k = b.dataset.koerper;
      setOpen(false);
      // auch bei „schon gewählt“ schicken: Steht sim_physik an, die Physik startet aber nicht, ist die Anzeige „einfach“
      // Reachy Mini (seit 0.38.1) ist ein anderer Körper: „Echter Roboter“ bleibt beim gewählten Körper
      const patch = k === 'robotd' ? { backend: 'robotd' }
        : k === 'reachy_sim' ? { modul: 'reachy_mini', backend: 'sim', sim_physik: false }
          : { modul: modul === 'open_duck_mini' ? modul : 'duckpilot', backend: 'sim', sim_physik: k === 'physik' };
      await save(patch);
    });
  }
  $('koerper-mehr').addEventListener('click', () => { setOpen(false); showView('settings', 'koerper'); });

  return {
    // config aus der Startnachricht: backend, physik (läuft gerade)
    update(config) {
      const reachy = config.modul === 'reachy_mini';
      modul = config.modul || 'duckpilot';
      aktuell = config.backend !== 'sim' ? 'robotd' : reachy ? 'reachy_sim' : config.physik ? 'physik' : 'sim';
      $('koerper-robot-info').textContent = reachy ? tr('Reachy Mini über Pollens Daemon – Adresse unter Einstellungen → Körper')
        : tr('Verbindet sich mit robotd');
      const fern = isRemote();
      btn.disabled = fern;
      btn.title = fern ? tr('Was gesteuert wird – umschalten nur am PC') : tr('Was gesteuert wird – umschalten');
      optionen();
    },
  };
}
