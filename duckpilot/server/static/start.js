// Knowlin-Startseite (seit 0.38; seit 0.38.3 nach dem Bild „Menschen sind verschieden in Sprache, Aussehen,
// Verhalten, können aber gleiches Wissen und Umgebung haben“): Oben, was alle Verkörperungen teilen (Wissen über die Umwelt,
// Umgebung, Alltag, Erlebnisse), darunter die Verkörperungen – jede mit eigenem Körper, Namen, Stimme und Charakter. Zu einer
// Verkörperung wechseln ist ein eigener Moment (Mind to Body: Knowlin weckt sie in ihrem Körper). Geplante Körper stehen
// ehrlich als „geplant“ da – nichts Anklickbares, das nicht geht.
import { uebersetzeText } from './i18n.js';
import { initHandyStart } from './handy_start.js';

const tr = (text) => (text ? uebersetzeText(text) || text : '');
const REDUCED = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const warte = (ms) => new Promise((r) => setTimeout(r, ms));

// Umrisse der Körper (Strich, currentColor) – kein Markenzeichen, nur die Gestalt
const UMRISS = {
  duckpilot: '<svg viewBox="0 0 48 48" aria-hidden="true"><circle cx="27" cy="12" r="6"/><path d="M33 12h7l-7 3"/><path d="M23 17c-6 1-11 6-11 13 0 6 5 9 12 9s13-3 13-10c0-4-2-7-6-9"/><path d="M20 39l-2 6M28 39l2 6M15 45h6M27 45h6"/></svg>',
  'reachy-mini': '<svg viewBox="0 0 48 48" aria-hidden="true"><path d="M17 4l3 9M31 4l-3 9"/><rect x="11" y="13" width="26" height="14" rx="7"/><circle cx="19" cy="20" r="2.5"/><circle cx="29" cy="20" r="2.5"/><path d="M19 27l-2 5M29 27l2 5M24 27v5"/><path d="M13 44c0-8 4-12 11-12s11 4 11 12z"/></svg>',
  'open-duck-mini': '<svg viewBox="0 0 48 48" aria-hidden="true"><path d="M19 3l2 6M29 3l-2 6"/><path d="M15 15a9 6.5 0 0 1 18 0v2H15z"/><path d="M33 15.5h6"/><path d="M24 17v5"/><rect x="15" y="22" width="18" height="11" rx="5.5"/><path d="M19 33l-3 6 3 6M29 33l3 6-3 6"/></svg>',
  'ohne-koerper': '<svg viewBox="0 0 48 48" aria-hidden="true"><rect x="6" y="8" width="28" height="20" rx="2"/><path d="M14 34h12M20 28v6"/><rect x="34" y="18" width="10" height="20" rx="2"/></svg>',
  lab: '<svg viewBox="0 0 48 48" aria-hidden="true"><path d="M18 6h12M20 6v12L9 40h30L28 18V6"/><path d="M14 30h20"/></svg>',
  // Knowlets: ein Paket mit Knoten darin (seit 0.38.5)
  knowlets: '<svg viewBox="0 0 48 48" aria-hidden="true"><path d="M24 6 40 15v18L24 42 8 33V15z"/><path d="M8 15l16 9 16-9M24 24v18"/></svg>',
  'eigenes-modul': '<svg viewBox="0 0 48 48" aria-hidden="true"><path d="M8 18h10v-6a4 4 0 0 1 8 0v6h10v10h-6a4 4 0 0 0 0 8h6v8H8z"/></svg>',
};

// Porträt je Körper (seit 0.38.4): aus dem 3D-Modell gerendert, für alle gleich im Kreis – fehlt eines (öffentliche
// Fassung ohne Pollens Modelle), steht der Umriss da
const BILD = { duckpilot: '/static/figuren/microduck.png', 'reachy-mini': '/static/figuren/reachy-mini.png',
  'open-duck-mini': '/static/figuren/open-duck-mini.png' };

const ohneBild = new Set();             // Körper ohne Porträt (aus /api/module) – gar nicht erst anfragen
function portraet(id, klasse) {
  const box = document.createElement('span');
  box.className = klasse;
  const umriss = () => { box.innerHTML = UMRISS[id] || UMRISS['eigenes-modul']; };
  if (!BILD[id] || ohneBild.has(id)) { umriss(); return box; }
  const img = document.createElement('img');
  img.src = BILD[id];
  img.alt = '';
  img.addEventListener('error', umriss, { once: true });
  box.append(img);
  return box;
}

// Mind to Body: Knowlin (oben) → Strahl → Verkörperung in ihrem Körper (unten). `modell` ist der Roboter (Microduck …),
// `figur` der Name des Charakters (Quacki …). Endet, wenn der Übergang vorbei ist; `warten` läuft dazwischen.
export async function mindToBody($, { id, modell, figur }, warten = null) {
  const ov = $('einzug');
  if (!ov) { if (warten) await warten(); return; }
  $('einzug-koerper').replaceChildren(portraet(id, 'einzug-bild'));
  $('einzug-name').textContent = modell;
  $('einzug-text').textContent = tr(`Knowlin weckt ${figur} …`);
  ov.hidden = false;
  ov.classList.remove('is-fertig', 'is-an');
  void ov.offsetWidth;
  ov.classList.add('is-an');
  const t0 = performance.now();
  if (warten) await warten();
  await warte(Math.max(0, (REDUCED ? 300 : 1500) - (performance.now() - t0)));
  ov.classList.add('is-fertig');
  $('einzug-text').textContent = tr(`${figur} ist wach`);
  await warte(REDUCED ? 250 : 800);
  ov.classList.remove('is-an');
  await warte(REDUCED ? 0 : 240);
  ov.hidden = true;
}

// Body to Mind (seit 0.38.10, Wunsch des Maintainers „kurz, aber sichtbar“): die Verkörperung tritt zurück, der Strahl läuft
// nach oben, Knowlin leuchtet auf – etwa eine Sekunde. Die Verkörperung bleibt in ihrem Körper wach.
export async function bodyToMind($, { id, modell, figur }) {
  const ov = $('einzug');
  if (!ov || !ov.hidden) return;
  $('einzug-koerper').replaceChildren(portraet(id, 'einzug-bild'));
  $('einzug-name').textContent = 'Knowlin';
  $('einzug-text').textContent = tr(`Zurück aus ${figur}`);
  ov.hidden = false;
  ov.classList.remove('is-an', 'is-oben');
  ov.classList.add('is-zurueck', 'is-fertig');
  void ov.offsetWidth;
  ov.classList.add('is-an');
  await warte(REDUCED ? 150 : 420);
  ov.classList.remove('is-fertig');
  ov.classList.add('is-oben');
  await warte(REDUCED ? 200 : 460);
  ov.classList.remove('is-an');
  await warte(REDUCED ? 0 : 240);
  ov.hidden = true;
  ov.classList.remove('is-zurueck', 'is-oben');
  void modell;
}

export function initStart({ $, api, el, toast, showView, save, isRemote, getConfig, personaName, vorschlaege }) {
  const box = $('start-module');
  if (!box) return { laden() {}, zurueck: async () => {}, mindToBody: async () => {}, figurWecken: async () => false };
  let geladen = false;
  let module = [];                     // zuletzt geladene Kacheln – der Kopf weckt Verkörperungen darüber (seit 0.38.8)
  const handy = initHandyStart({ $, api, toast, showView, isRemote });   // „Auf Handy oder Tablet“ (T2, 0.38.28)

  // Zu einer anderen Verkörperung wechseln: Übergang zeigen, Körper wechseln, warten, bis er antwortet
  async function wechseln(m) {
    if (isRemote && isRemote()) { toast(tr('Die Verkörperung wechseln geht nur am PC'), true); return; }
    const f = m.figur || {};
    await mindToBody($, { id: m.id, modell: tr(m.koerper_name), figur: f.name || tr(m.koerper_name) }, async () => {
      await save(m.modul === 'duckpilot' ? { modul: 'duckpilot' } : { modul: m.modul, backend: 'sim', sim_physik: false });
      for (let i = 0; i < 60 && getConfig().modul !== m.modul; i++) await warte(100);   // neue Startnachricht abwarten
    });
    geladen = false;
    showView('cockpit');
  }

  // Die Verkörperung, die zuletzt einen Körper hatte: nur wecken, nichts tauschen – mit demselben Übergang
  async function wecken(m) {
    const f = m.figur || {};
    await mindToBody($, { id: m.id, modell: tr(m.koerper_name), figur: f.name || tr(m.koerper_name) }, async () => {});
    showView('cockpit');
  }

  // Eine Kachel, für jeden Körper gleich gebaut: Porträt, Modell, Stand oben rechts; Verkörperung und Charakter; ein Satz;
  // Knöpfe unten. Geplante Körper sind dieselbe Kachel, nur ruhig gestellt.
  function kachel(m) {
    const fertig = m.stand === 'fertig';
    const f = m.figur;
    const hier = Boolean(f && f.aktiv);
    const card = el('article', `modul-kachel${fertig ? ' is-on' : ' is-planned'}${hier ? ' modul-kachel--hier' : ''}`);
    const marke = hier ? tr('zuletzt wach') : fertig ? tr(m.art !== 'koerper' ? 'neu' : m.id === 'duckpilot' ? 'bereit' : 'Simulator')
      : m.stand === 'anleitung' ? `${tr('Anleitung')} ${tr(m.version)}` : `${tr('geplant')} ${tr(m.version)}`;
    const kopf = el('div', 'kachel-kopf');
    const titel = el('div', 'kachel-titel');
    titel.append(el('h3', 'kachel-name', m.art === 'koerper' ? tr(m.koerper_name) : tr(m.name)),
      el('p', 'kachel-art', tr(m.koerper)));
    kopf.append(portraet(m.id, 'kachel-bild'), titel, el('span', `chip kachel-chip${hier ? ' chip--accent' : ''}`, marke));
    card.append(kopf);
    if (f) {
      const persona = personaName ? personaName(f.energie, f.humor) : '';
      const stimmung = hier && f.stimmung && f.stimmung.toLowerCase() !== persona.toLowerCase() ? f.stimmung : '';
      const zuege = [tr(persona), stimmung ? tr(`gerade ${stimmung}`) : '',
        hier ? tr(`${f.tricks || 0} ${f.tricks === 1 ? 'eigener Trick' : 'eigene Tricks'}`) : ''].filter(Boolean);
      const figur = el('p', 'kachel-figur');
      // je Zug ein eigener Textknoten: kommt die englische Übersetzung erst nach dem Zeichnen, übersetzt die Seite
      // jeden Zug für sich (vorher blieb „Ausgeglichen · 0 eigene Tricks“ als ein Stück deutsch, Fund 7.11.)
      figur.append(el('b', null, f.name));
      for (const zug of zuege) figur.append(document.createTextNode(' · '), el('span', null, zug));
      card.append(figur);
    }
    card.append(el('p', 'kachel-kurz', tr(m.kurz)));
    const zeile = el('div', 'kachel-aktionen');
    if (fertig) {
      const name = f ? f.name : tr(m.name);
      // Gleiche Beschriftung auf jeder Kachel: am Anfang ist Knowlin nur im Kopf – jede Verkörperung wird erst geweckt
      const auf = el('button', 'btn btn--primary btn--sm', m.modul ? tr(`${name} wecken`) : tr(`${name} öffnen`));
      auf.type = 'button';
      auf.addEventListener('click', () => (!m.modul ? showView(m.ansicht || 'cockpit') : hier ? wecken(m) : wechseln(m)));
      zeile.append(auf);
      if (m.art === 'koerper') {
        const lnk = el('button', 'btn btn--ghost btn--sm pc-only', tr('Verknüpfung'));
        lnk.type = 'button';
        lnk.title = tr('Verknüpfung auf dem Desktop und im Startmenü – startet direkt bei dieser Verkörperung');
        lnk.addEventListener('click', async () => {
          const r = await api('/api/verknuepfung', 'POST', { modul: m.id }).catch(() => null);
          if (r && r.ok) toast(tr('Verknüpfung angelegt – ans Taskleiste-Anheften geht per Rechtsklick'));
          else toast((r && r.fehler) || tr('Verknüpfung ließ sich nicht anlegen'), true);
        });
        zeile.append(lnk);
      }
    }
    card.append(zeile);
    return card;
  }

  // Was alle teilen: je Bereich eine Kachel mit Zahl
  function gemeinsam(kern, g) {
    const zahl = {
      memory: g.gedaechtnis ? tr(`${g.wissen} Einträge · ${g.personen} angelernte Personen · ${g.erlebnisse} Erlebnisse`) : tr('Gedächtnis aus'),
      umgebung: tr(`${g.orte} gemerkte Orte · erkundeter Bereich`),
      alltag: tr('Termine, Timer, Erinnerungen, To-dos'),
      settings: tr('KI-Modell, Sprache, Datenschutz'),
    };
    return kern.map((k) => {
      const b = el('button', 'gemeinsam-teil');
      b.type = 'button';
      b.append(el('b', null, tr(k.name)), el('span', null, zahl[k.ansicht] || ''));
      b.addEventListener('click', () => showView(k.ansicht, k.teil || undefined));
      return b;
    });
  }

  async function laden() {
    handy.laden();
    const r = await api('/api/module').catch(() => null);
    if (!r || !r.ok) return;
    $('start-kern').replaceChildren(...gemeinsam(r.kern, r.gemeinsam || {}));
    for (const m of r.module) if (m.bild === false) ohneBild.add(m.id);
    box.replaceChildren(...r.module.filter((m) => m.art === 'koerper').map(kachel));
    $('start-werkzeuge').replaceChildren(...r.module.filter((m) => m.art !== 'koerper').map(kachel));
    module = r.module;
    if (vorschlaege) vorschlaege(r.module.filter((m) => m.figur && m.stand === 'fertig').map((m) => m.figur));
    geladen = true;
  }

  // Der Kopf weckt eine Verkörperung (Gespräch auf der Startseite): derselbe Weg wie der Knopf auf ihrer Kachel
  async function figurWecken(modul) {
    if (!module.length) await laden();
    const m = module.find((x) => x.modul === modul && x.stand === 'fertig');
    if (!m) { toast(tr('Diese Verkörperung gibt es hier nicht'), true); return false; }
    await (m.figur && m.figur.aktiv ? wecken(m) : wechseln(m));
    return true;
  }

  // Zurück zu Knowlin: Porträt und Name der Verkörperung, die gerade einen Körper hat
  function zurueck() {
    const c = getConfig() || {};
    const id = { reachy_mini: 'reachy-mini', open_duck_mini: 'open-duck-mini' }[c.modul] || 'duckpilot';
    return bodyToMind($, { id, modell: '', figur: c.duck_name || 'Quacki' });
  }

  return { laden, figurWecken, zurueck, get geladen() { return geladen; }, mindToBody: (fig, warten) => mindToBody($, fig, warten) };
}
