import { Scene3D } from './duck3d.js';
import { LineChart, MapView, TofTerrain, Joints, eventItem, SHOWN_EVENTS } from './dashboard.js';
import { Listener, playSound, speak, stopSpeaking, playPlan, germanVoices, setVoice, currentVoice, setKlang } from './voice.js';
import { initVoicePage } from './stimme.js';
import { initTraining, trainingsfeldLaden } from './training.js';
import { initLernen } from './lernen.js';
import { initParcours } from './parcours.js';
import { initAkrobatik } from './akrobatik.js';
import { initAlltag } from './alltag.js';
import { personaName } from './personality.js';
import { PointStore } from './pointcloud.js';
import { initSkills } from './skills.js';
import { initFern } from './fernbedienung.js';
import { initBeenden } from './beenden.js';
import { initErsteSchritte } from './erste.js';
import { initTanz } from './tanz.js';
import { initSprachwahl } from './sprachwahl.js';
import { initFehlerbericht } from './fehlerbericht.js';
import { initEnten } from './enten.js';
import { initAussehen } from './aussehen.js';
import { initRaum } from './raum.js';
import { initKnowlets } from './knowlets.js';
import { initSicherung } from './sicherung.js';
import { initKoerperwahl } from './koerperwahl.js';
import { setzeModul } from './modul.js';
import { initReachy } from './reachy_ui.js';
import { initReachyApps } from './reachy_apps.js';
import { initAuswahl } from './auswahl.js';
import { initAugen } from './augen.js';
import { initFollow, initLaser } from './laser.js';
import { initHandyLeiste } from './handy.js';
import { initKollision } from './kollision.js';
import { initController } from './controller.js';
import { ladeSprache, uebersetze, uebersetzeText } from './i18n.js';
import { $, el, css, toast, REDUCED } from './ui.js';                  // seit 0.38.17: app.js schlank, Teile als Module
import { initEreignisse } from './ereignisse.js';
import { initKachel } from './kachel.js';
import { initTouchFahren } from './touchfahren.js';
import { initGedaechtnis } from './gedaechtnis_ui.js';
import { initEinstellungen } from './einstellungen_ui.js';
import { initKopfleiste } from './kopfleiste.js';
import { initTricksSeite } from './tricks_seite.js';
import { initStossreihe } from './stossreihe.js';
import { initNfc } from './nfc.js';
import { initHirn } from './hirn.js';
import { initStart } from './start.js';
import { initKopf } from './kopf.js';
import { initCharakter } from './charakter.js';
import { initPflege } from './pflege.js';
import { initDesignsystem } from './designsystem.js';
import { initKameraSpiele } from './kamera_spiele.js';   // Kamera-Spiele mit Reachy (0.38.13)
import { initMentor } from './mentor_arm.js';             // Vormachen mit Ari (0.38.57)
import { initOffenlegung } from './offenlegung.js';

document.body.classList.add('booting');

const scene = new Scene3D($('view'));
const map = new MapView($('map'));
let raum = null;                       // Raum kennenlernen – liefert auch die Karte fürs Lagebild
const cloud = new PointStore();
const tof3d = new TofTerrain($('tof3d'), cloud);
scene.setCloud(cloud);
const joints = new Joints($('joints'), $('joints-summary'));
const ereignisse = initEreignisse({ getState: () => lastState, scene, map, addLine });
// Gelenk-Check: Soll, Nachlauf, Last – einmal je Sekunde, solange das Dashboard offen ist
setInterval(() => {
  if ($('view-dashboard').hidden || document.hidden) return;
  api('/api/gelenke').then((r) => { if (r && r.ok) joints.report(r); }).catch(() => {});
}, 1000);
const chartVx = new LineChart($('chart-vx'), {
  unit: 'm/s', digits: 2, min: -0.05, max: 0.1,
  series: [{ key: 'a', label: 'gefahren', color: css('--data-1') }, { key: 'b', label: 'verlangt', color: css('--data-2'), dash: [5, 4] }],
});
const chartMood = new LineChart($('chart-mood'), {
  unit: '', digits: 2, min: -1, max: 1, window: 120, fixed: true,
  ticks: { 1: 'freudig', 0: 'ausgeglichen', '-1': 'frustriert' },
  series: [{ key: 'a', label: 'Stimmung', color: css('--data-1') }],
});
const chartYaw = new LineChart($('chart-yaw'), {
  unit: '°/s', digits: 0, min: -20, max: 20,
  series: [{ key: 'a', label: 'gedreht', color: css('--data-1') }, { key: 'b', label: 'verlangt', color: css('--data-2'), dash: [5, 4] }],
});

let ws = null;
let config = {};
let lastState = null;
let lastEngine = null;
let laser = null;                 // laser.js – wird unten bei der 3D-Ansicht angelegt
let follow = null;                // laser.js, Art „mensch“ (Folg mir)
let kollision = null;             // kollision.js – schubsen, greifen, werfen (Simulator) und Stopp-Fenster
let ctl = null;                   // controller.js – Vollbild-Controller fürs Handy, Vibrieren
const activePointer = () => (laser?.on() ? laser : follow?.on() ? follow : null);
let thinkingEl = null;
let listener = null;
let ttsOn = true;
let view = 'cockpit';

const SKILL_DE = {
  sit_toggle: 'setzt sich / steht auf', ground_pick: 'hebt mit dem Schnabel auf', kick_left: 'schießt links',
  kick_right: 'schießt rechts', roulade: 'macht einen Purzelbaum', _init: 'fährt die Motoren hoch',
  _recover: 'rappelt sich auf', _rest: 'legt sich schlafen',
};

// ── Verbindung ─────────────────────────────────────────────────────────
const outbox = [];
const offeneChats = new Map();    // Nachrichten ohne Echo vom Server – nach einem Abbruch erneut senden (Fund 6.11.)
function connect() {
  ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  ws.onopen = () => {
    setLink(true);
    const raus = new Set(outbox);
    while (outbox.length) ws.send(outbox.shift());
    for (const t of offeneChats.values()) if (!raus.has(t)) ws.send(t);   // der Server kennt die cid und nimmt sie nur einmal
  };
  ws.onclose = () => {
    setLink(false);
    // Handy: abgemeldet oder Fernbedienung am PC aus? Dann zeigt der Server statt der App einen Hinweis.
    if (fern.remote) fetch('/api/ping').then((r) => { if (r.status === 401 || r.status === 403) location.reload(); }).catch(() => {});
    setTimeout(connect, 1500);
  };
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.type === 'chat' && m.cid) offeneChats.delete(m.cid);
    handle(m);
  };
}
function send(obj) {
  const text = JSON.stringify(obj);
  if (ws && ws.readyState === 1) ws.send(text);
  else if (obj.type !== 'drive' && obj.type !== 'listening' && outbox.length < 20) outbox.push(text);
}
async function api(path, method = 'GET', body) {
  const res = await fetch(path, {
    method, headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined,
  });
  return res.json();
}

let wsOpen = false;
let letzteWelt = '';      // Körper/Simulator/Physik zuletzt – „Weitere Enten“ neu laden, wenn sich das ändert
let bodyOnline = null;
function setLink(on) {
  wsOpen = on;
  renderLink();
}
function renderLink() {
  const b = $('badge-link');
  const ok = wsOpen && bodyOnline !== false;
  const text = !wsOpen ? 'Knowlin getrennt' : bodyOnline === false
    ? (config.backend === 'robotd' ? 'Roboter nicht erreichbar' : 'Körper nicht verbunden') : fern.remote ? 'verbunden · Handy' : 'verbunden';
  b.querySelector('span').textContent = text;
  b.title = text;                      // am Handy wird der Text gekürzt
  b.querySelector('.dot').className = `dot ${ok ? 'dot--good' : 'dot--critical'}`;
}

function handle(msg) {
  switch (msg.type) {
    case 'init': kollision?.refresh(); return onInit(msg);
    case 'state': return onState(msg);
    case 'event': laser?.onEvent(msg.event); follow?.onEvent(msg.event); kollision?.onEvent(msg.event); ctl?.onEvent(msg.event); return ereignisse.onEvent(msg.event);
    case 'kollision': return kollision?.onStatus(msg);
    case 'musik': return tanz?.spielen(msg.datei, msg.ab);
    case 'choreo': return tanz?.neu(msg.name);
    case 'kollision_objekte': return kollision?.onObjekte(msg);
    case 'chat': if (msg.an === 'kopf') return kopf.onChat(msg); parcours.onChat(msg); return onChat(msg);
    case 'action': if (msg.an === 'kopf') return; laser?.onAction(msg); follow?.onAction(msg); return onAction(msg);
    case 'thinking': return msg.an === 'kopf' ? kopf.denkt(msg.on) : setThinking(msg.on);
    case 'memory': return gedaechtnis.onMemory(msg);
    case 'stimme': return voicePage.update(msg);
    case 'training': return training.update(msg);
    case 'stossreihe': return stossreihe.update(msg);
    case 'lernen': return lernen && lernen.update(msg);
    case 'parcours': return parcours.update(msg);
    case 'alltag': augen.update(msg); return alltag.update(msg);
    case 'nfc': return nfc && nfc.update(msg);
    case 'erfahrung':
      if (msg.zahlen) $('netz-zahlen').textContent = `${msg.zahlen.knoten} Knoten, ${msg.zahlen.verbindungen} Verbindungen.`;
      return hirn && hirn.update(msg);
    case 'nfc_beruehrt': return nfc && nfc.touched(msg);
    case 'beenden': return beenden.update(msg);
    case 'augen_bitte': return augen.onRequest(msg);
    case 'personen': return augen.onPersons(msg);
    case 'verbindung': return onConnection(msg);
    case 'fernzugang': return fern.update(msg);
    case 'alltag_alarm': return alltag.onAlarm(msg);
    case 'aufgaben': return renderTasks(msg.liste);
    case 'physik': kollision?.refresh(); return view === 'settings' ? einst.renderPhysik(msg) : null;
    case 'modell': return einst.renderModell(msg);
    case 'reachy': case 'reachy_ton': return reachy.nachricht(msg);
    case 'reachy_app': return reachyApps.nachricht(msg);
    case 'spiel': return kameraSpiele.nachricht(msg);
    case 'mentor': return mentor.meldung(msg);
  }
}

// ── Start: Knowlins Bewusstsein lädt ─────────────────────────────────
// Seit 0.38.24 statt des Startbilds: Funken laufen ins Knowlin-Zeichen, bis die Ente verbunden ist – mindestens
// 1,6 s, höchstens 8 s. Dann leuchtet das Zeichen auf („Knowlin ist wach“) wie beim Einzug in einen Körper.
// Klick oder Taste überspringt. Neu laden in derselben Sitzung zeigt es nicht noch einmal.
const splash = (() => {
  const box = document.getElementById('splash');
  if (!box) return { ready() {}, text() {} };
  const t0 = performance.now();
  let done = false;
  let readyAt = null;
  const close = () => {
    if (done) return;
    done = true;
    box.classList.add('is-done');
    try { sessionStorage.setItem('duckpilot.splash', '1'); } catch { /* egal */ }
    setTimeout(() => box.remove(), 600);
    window.removeEventListener('keydown', close, true);
  };
  box.addEventListener('click', close);
  window.addEventListener('keydown', close, true);
  setTimeout(close, 8000);
  return {
    ready(msg) {
      if (readyAt !== null) return;
      readyAt = performance.now();
      const warten = Math.max(0, 1600 - (readyAt - t0));   // die Funken laufen mindestens einmal ganz ins Zeichen
      setTimeout(() => {
        if (done) return;                             // schon weggeklickt: nichts mehr
        box.classList.add('is-wach');
        if (msg) document.getElementById('splash-text').textContent = msg;
      }, warten);
      setTimeout(close, warten + 1100);
    },
    text(msg) { if (!done) document.getElementById('splash-text').textContent = msg; },
  };
})();

function onInit(msg) {
  const first = !config.duck_name;
  const vorher = config.modul && `${config.modul}|${config.backend}`;
  config = msg.config;
  // Der Verlauf geht über alle Körper weiter – sichtbar getrennt, wenn eine andere Verkörperung übernimmt (0.38.10)
  if (vorher && vorher !== `${config.modul}|${config.backend}` && $('log').querySelector('.msg')) {
    const art = { duckpilot: 'Microduck', reachy_mini: 'Reachy Mini', open_duck_mini: 'Open Duck Mini v2', so101: 'SO-101' }[config.modul] || '';
    const t = `Jetzt in ${config.duck_name} · ${art} · ${config.backend === 'sim' ? 'Simulator' : 'echter Roboter'}`;
    $('log').append(el('p', 'msg-trenner', uebersetzeText(t) || t));
  }
  setKlang(config.klang_hoehe, config.klang_farbe);   // Klangsignatur der Ente
  kopf.namen(config);                                 // „Hallo Mensch“ oder dein Name, Knowlins Name (0.38.9)
  charakter.zeigen(config);                           // Ausprägung und Eigenschaften der Gestalt (0.38.10)
  if (config.duck_name) $('memory-titel').textContent = uebersetzeText(`Was sich ${config.duck_name} gemerkt hat`) || `Was sich ${config.duck_name} gemerkt hat`;
  beenden.update(config.beenden);
  splash.ready(`Knowlin ist wach${config.version ? ` · ${config.version}` : ''}`);
  renderTasks(msg.aufgaben || []);
  einst.renderModell(config.modell);
  // Die App heißt wie die Ente: oben, im Fenstertitel, in der Taskleiste
  $('duck-name').textContent = config.duck_name;
  appName = config.duck_name || 'Knowlin';
  updateTitle();
  $('welcome-title').textContent = uebersetzeText('Willkommen bei Knowlin') || 'Willkommen bei Knowlin';
  const body = $('badge-body');
  body.textContent = config.backend === 'sim' ? (config.physik ? 'Simulator · Physik' : 'Simulator') : 'Echter Roboter';
  body.className = `chip${config.backend === 'sim' ? '' : ' chip--accent'}`;
  document.body.classList.toggle('robot', config.backend !== 'sim');
  koerperwahl.update(config);
  $('hub-body').textContent = body.textContent;
  $('hub-body').className = body.className;
  setzeModul(config, { $, hiddenTabs });                // Reachy Mini: ohne Beine (seit 0.38.1)
  { const [g, t] = groupOf(view, part); renderSubnav(g, t); }   // Reiter je Körper auch nach Neuladen (Fund 6.11.)
  kachel.setTile(kachel.modus);
  if (first && direkt) direktZurFigur();
  else if (first && !imKopf && !config.im_koerper) send({ type: 'koerper' });   // per Lesezeichen gleich im Körper
  if (config.modul === 'reachy_mini') reachy.laden();
  if (config.model_style) { scene.setModelStyle(config.model_style); $('opt-model').checked = config.model_style === 'original'; }
  if (config.farbe) scene.setFarbe(config.farbe);
  const brain = $('badge-brain');
  const lm = config.lokal_programm === 'lmstudio';   // LM Studio seit 0.38.41 unter „Lokales Modell“
  const local = config.gehirn === 'lokal' && (lm ? config.anbieter_bereit && config.lmstudio_modell : config.lokal_modell);
  const anderes = config.gehirn === 'anbieter' && config.anbieter_bereit;
  brain.textContent = local ? `Lokales Modell · ${lm ? config.lmstudio_modell : config.lokal_modell}` : anderes ? `Modell · ${config.anbieter_modell}`
    : config.online ? `Claude ${modelShort(config.model)}` : 'Einfache Befehle';
  brain.title = local ? 'Ein offenes Sprachmodell läuft auf diesem PC (Ollama oder LM Studio) – ohne Internet, mit demselben Gedächtnis'
    : anderes ? 'Ein anderes KI-Modell denkt mit – dieselben Werkzeuge und Sicherheitsregeln'
    : config.online ? 'Claude versteht freie Sprache und plant Bewegungen'
      : 'Kein API-Schlüssel – nur kurze Befehle wie „tanz“ oder „stopp“. Schlüssel unter Einstellungen.';
  // Punkt am System-Knopf nur, wenn gar kein KI-Modell denkt (seit 0.38.34; vorher auch mit lokalem/anderem Modell)
  $('settings-dot').hidden = Boolean(config.online || local || anderes);
  $('opt-chat').checked = !!config.plaudern;
  if (typeof updatePov === 'function') updatePov();
  if (typeof setStageMode === 'function') setStageMode(scene.mode);
  $('card-care').hidden = config.backend !== 'robotd';
  voicePage.config(config);
  // „Weitere Enten“ gibt es nur im einfachen Simulator – beim Umschalten (Physik, Roboter) sofort frei/gesperrt (0.38.34)
  const welt = `${config.backend}|${config.sim_physik}|${config.modul}`;
  if (welt !== letzteWelt) { letzteWelt = welt; enten?.laden(); setTimeout(() => enten?.laden(), 2500); }
  document.body.classList.toggle('goofy', !!config.goofy);
  $('persona-name').textContent = personaName(config.energie, config.humor);
  kopfleiste.padQuick.set(config.energie, config.humor);
  kopfleiste.padSettings.set(config.energie, config.humor);
  if (config.agent_error) addLine('err', config.agent_error);
  $('wake').textContent = config.wake_word;
  scene.setWorld(msg.world);
  scene.setItems(msg.items);
  map.setWorld(msg.world);
  tof3d.setWorld(msg.world);
  map.setItems(msg.items);
  $('map-note').textContent = msg.world ? '' : 'Ohne Zimmerplan: Spur und Orte aus der Odometrie, ab dem Start des Roboters.';
  const evList = $('events');
  evList.replaceChildren();
  for (const ev of (msg.events || []).filter((e) => SHOWN_EVENTS.has(e.type))) evList.prepend(eventItem(ev));
  setupVoice();
  if (first) {
    setTimeout(() => document.body.classList.remove('booting'), 60);
    ersteSchritte.auto(config);
  }
  if (view === 'settings' || view === 'persoenlichkeit') einst.laden();
  if (view === 'settings') fern.load();
  if (view === 'alltag') augen.loadPersons();
}

function modelShort(m) {
  return ({ 'claude-sonnet-5-5': 'Sonnet 5.5', 'claude-haiku-5-5': 'Haiku 5.5', 'claude-opus-5-5': 'Opus 5.5' })[m] || m;
}

// ── Bereiche ───────────────────────────────────────────────────────────
// Fünf Bereiche in der Leiste, nach dem, was man tut:
//   Steuern   – sie bewegen, mit ihr reden, Tricks abspielen
//   Alltag    – Uhr, Timer, Erinnerungen, Termine, To-dos (Erweiterung „Alltagsbuddy“)
//   Charakter – wer sie ist: Persönlichkeit, Stimme, Gespräch (womit sie denkt), Gedächtnis
//   Lernen    – Neues beibringen: Akrobatik, Parcours, Training
//   System    – Zustand und Pflege, Einstellungen, Erweiterungen
// Bereiche mit mehreren Seiten zeigen oben Reiter. Ein Reiter ist eine Seite (view) oder ein Teil
// einer Seite (part, über data-part).
const GROUPS = [
  { id: 'steuern', tabs: [{ view: 'cockpit', label: 'Cockpit' }, { view: 'tricks', part: 'tricks', label: 'Tricks' },
    { view: 'tricks', part: 'tanz', label: 'Tanzen' }, { view: 'tricks', part: 'team', label: 'Team' },
    { view: 'tricks', part: 'hub', label: 'Vom Hub' }, { view: 'tricks', part: 'spiele', label: 'Spiele' }] },
  { id: 'alltag', tabs: [{ view: 'alltag' }] },
  { id: 'umgebung', tabs: [{ view: 'umgebung' }] },                 // seit 0.38: eigener Bereich (Befund, Wahl)
  { id: 'charakter', tabs: [{ view: 'persoenlichkeit', label: 'Persönlichkeit' }, { view: 'stimme', part: 'stimme', label: 'Stimme' },
    { view: 'stimme', part: 'gespraech', label: 'Gespräch' }, { view: 'memory', label: 'Gedächtnis' },
    { view: 'knowlets', label: 'Knowlets' }] },
  { id: 'lernen', tabs: [{ view: 'akrobatik', label: 'Akrobatik' }, { view: 'parcours', label: 'Parcours' }, { view: 'training', label: 'Training' }] },
  { id: 'system', tabs: [{ view: 'dashboard', label: 'Körper' }, { view: 'settings', label: 'Einstellungen' },
    { view: 'tricks', part: 'pakete', label: 'Erweiterungen' }] },
  { id: 'design', tabs: [{ view: 'design' }] },
  { id: 'start', tabs: [{ view: 'start' }], kopf: true },           // Knowlin-Startseite (seit 0.38), ohne Leistenknopf
  // Kopf zuerst (seit 0.38.4): auf Knowlins Seiten die geteilten Bereiche, ohne die Körperbereiche
  { id: 'wissen', tabs: [{ view: 'memory', label: 'Gedächtnis' }, { view: 'knowlets', label: 'Knowlets' }], kopf: true },
  { id: 'einstellungen', tabs: [{ view: 'settings', label: 'Einstellungen' }, { view: 'stimme', part: 'stimme', label: 'Knowlins Stimme' }], kopf: true },
];
const KOERPER_GRUPPEN = new Set(['steuern', 'charakter', 'lernen', 'system']);
let imKopf = true;                     // auf Knowlins Seiten (Kopf) oder in einer Verkörperung (Körper)
const hiddenTabs = new Set();          // z. B. „memory“, wenn das Gedächtnis aus ist
const tabKey = (t) => t.part ? `${t.view}/${t.part}` : t.view;
const lastTab = {};
try { Object.assign(lastTab, JSON.parse(localStorage.getItem('duckpilot.tabs') || '{}')); } catch { /* egal */ }
let part = null;

function groupOf(name, p) {
  // im Kopf zuerst Knowlins Gruppen (Gedächtnis → Wissen), in der Verkörperung ihre eigenen (Gedächtnis → Charakter)
  const reihe = imKopf ? [...GROUPS.filter((g) => g.kopf), ...GROUPS.filter((g) => !g.kopf)] : GROUPS.filter((g) => !g.kopf || g.id === 'start');
  for (const g of reihe) {
    const t = g.tabs.find((x) => x.view === name && (!p || !x.part || x.part === p));
    if (t) return [g, t];
  }
  return [GROUPS[0], GROUPS[0].tabs[0]];
}

function renderSubnav(g, tab) {
  const nav = $('subnav');
  const tabs = g.tabs.filter((t) => !hiddenTabs.has(tabKey(t)) && !hiddenTabs.has(t.view));
  nav.hidden = tabs.length < 2;
  document.querySelector('.views').classList.toggle('has-subnav', !nav.hidden);
  if (nav.hidden) return;
  nav.replaceChildren(...tabs.map((t) => {
    const b = el('button', 'subnav-tab', t.label);
    b.type = 'button';
    if (tabKey(t) === tabKey(tab)) b.setAttribute('aria-current', 'page');
    b.addEventListener('click', () => showView(t.view, t.part));
    return b;
  }));
}

// Fenstertitel nennt die Seite (WCAG 2.4.2): „Tricks – Quacki“
let appName = 'Knowlin';
let pageTitle = '';
// Fenstertitel seit 0.38 mit der Suite: „Cockpit – Quacki · duckpilot – Knowlin“, auf der Startseite nur „Knowlin“
// Im Kopf (seit 0.38.7): „Umgebung – Knowlin“ – ohne Verkörperung, die gerade keinen Körper hat
function updateTitle() {
  const seite = pageTitle ? (uebersetzeText(pageTitle) || pageTitle) : '';
  if (view === 'start' || !seite) { document.title = imKopf ? 'Knowlin' : `${appName} – Knowlin`; return; }
  document.title = imKopf ? `${seite} – Knowlin` : `${seite} – ${appName} · Knowlin`;
}

function showView(name, p) {
  const wantedPart = p;
  let [g, tab] = groupOf(name, p);
  // Kopf oder Körper: Körperbereiche betreten die Verkörperung (sie wacht auf), Knowlins Seiten sind der Kopf
  if (KOERPER_GRUPPEN.has(g.id) && imKopf) {
    imKopf = false;
    document.body.classList.remove('im-kopf');
    if (!config.im_koerper) send({ type: 'koerper' });
  } else if (g.kopf && !imKopf) {
    imKopf = true;
    try { start.zurueck(); } catch { /* beim Laden noch nicht bereit */ }   // Body to Mind: kurz, aber sichtbar (0.38.10)
    document.body.classList.add('im-kopf');
    [g, tab] = groupOf(name, p);
  }
  p = tab.part || null;
  name = tab.view;
  const same = name === view && p === part && !$(`view-${name}`).hidden;
  view = name;
  part = p;
  lastTab[g.id] = tabKey(tab);
  try { localStorage.setItem('duckpilot.tabs', JSON.stringify(lastTab)); } catch { /* egal */ }
  renderSubnav(g, tab);
  pageTitle = tab.label || ($(`view-${name}`) && $(`view-${name}`).getAttribute('aria-label')) || '';
  updateTitle();
  for (const b of document.querySelectorAll('.rail-btn')) {
    if (b.dataset.group === g.id) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
  }
  const page = $(`view-${name}`);
  if (p) for (const sec of page.querySelectorAll('[data-part]')) sec.hidden = sec.dataset.part !== p;
  // Einstellungen sind eine Seite mit Abschnitten: #settings/koerper springt zum Abschnitt
  const anchor = name === 'settings' && wantedPart ? document.getElementById(`set-${wantedPart}`)
    : name === 'training' && wantedPart === 'stossreihe' ? $('stossreihe') : null;   // #training/stossreihe
  if (anchor) requestAnimationFrame(() => anchor.scrollIntoView({ block: 'start', behavior: REDUCED ? 'auto' : 'smooth' }));
  if (same) return;
  for (const v of document.querySelectorAll('.view')) {
    const on = v === page;
    v.hidden = !on;
    if (on && !REDUCED) { v.classList.remove('entering'); void v.offsetWidth; v.classList.add('entering'); }
  }
  // Tanzen und Team: dieselbe 3D-Ansicht als Vorschau daneben (die Leinwand zieht um, ein Renderer für alle)
  const vorschau = name !== 'tricks' ? null : p === 'tanz' ? $('tanz-vorschau') : p === 'team' ? $('team-vorschau')
    : !p || p === 'tricks' ? $('tricks-vorschau') : null;
  const heim = vorschau || stageEl;
  if (heim && scene.canvas.parentElement !== heim) { heim.prepend(scene.canvas); requestAnimationFrame(() => scene.resize()); }
  scene.paused = name !== 'cockpit' && !vorschau;
  if (['settings', 'persoenlichkeit', 'stimme', 'memory'].includes(name)) einst.laden();
  if (name === 'tricks') { tricksSeite.laden(p); if (document.body.classList.contains('koerper-reachy')) reachyApps.laden(); }
  // „KI-Modell“ steht seit 0.38.0 unter Einstellungen – dort laden (Anbieterliste, Ollama), nicht nur auf „Stimme“
  if (name === 'stimme' || name === 'settings') voicePage.load();
  if (name === 'training') { training.load(true); stossreihe.load(); feld.zeigen(); }
  if (name === 'alltag') augen.loadPersons();
  if (name === 'parcours') parcours.load(); else parcours.hide();
  if (name === 'akrobatik') akrobatik.load(); else akrobatik.hide();
  if (name === 'alltag') { alltag.render(); nfc.load(); }
  if (name === 'dashboard') { pflege.load(); raum?.laden(); }
  if (name === 'memory') { hirn.show(); gedaechtnis.welt.laden(true); }   // Innenleben (0.38), Themenkarten (0.38.27)
  if (name === 'start') start.laden();
  if (name === 'umgebung') raum?.laden();
  if (name === 'knowlets') knowlets.laden();
  if (name === 'settings') sicherung?.laden();
  if (name === 'design') designsystem.render();
  if (name === 'cockpit') requestAnimationFrame(() => scene.resize());
  try { history.replaceState(null, '', `#${p ? `${name}/${p}` : name}`); } catch { /* egal */ }
}
document.querySelectorAll('.rail-btn').forEach((b) => b.addEventListener('click', () => {
  const g = GROUPS.find((x) => x.id === b.dataset.group);
  const remembered = g.tabs.find((t) => tabKey(t) === lastTab[g.id] && !hiddenTabs.has(t.view));
  const t = remembered || g.tabs.find((x) => !hiddenTabs.has(x.view)) || g.tabs[0];
  showView(t.view, t.part);
}));

// ── Zustand ────────────────────────────────────────────────────────────
function posture(st) {
  if (!st.connected) return 'nicht verbunden';
  if (st.fallen) return 'umgefallen';
  if (!st.powered) return st.skill === '_init' ? 'wacht auf' : 'ruht';
  if (st.skill) return SKILL_DE[st.skill] || st.skill;
  const sp = st.werkbank?.spiel;                   // Tic-Tac-Toe (seit 0.38.54)
  if (sp) return sp.ergebnis || (sp.dran === 'du' ? 'du bist dran' : 'Ari setzt');
  const auf = st.werkbank?.auftrag;                // Arm bei der Arbeit (seit 0.38.54): „Aufräumen 2/6“
  if (auf) return `${auf.titel} ${auf.erledigt}/${auf.gesamt}`;
  if (st.koerper === 'so101') return st.sitting ? 'Ruhelage' : 'bereit';   // Arm (0.38.47): sitzt und steht nicht
  if (st.sitting) return 'sitzt';
  const v = Math.hypot(st.twist.vx, st.twist.vy);
  if (v > 0.02) return 'läuft';
  if (Math.abs(st.twist.vyaw) > 0.1) return 'dreht sich';
  return 'steht';
}
// Feste Breite (Ziffernplatz = U+2007), damit die Anzeige bei wechselnden Werten nicht springt
const FIG = '\u2007';
const fmtM = (v) => (v == null ? `frei${FIG.repeat(2)}` : `${String(Math.round(v * 100)).padStart(3, FIG)} cm`);
const fmtSigned = (v, d) => {
  const r = Number(v.toFixed(d));
  const body = Math.abs(r).toFixed(d).replace('.', ',');
  return `${r < 0 ? '\u2212' : FIG}${body}`;
};
const num = (v, d = 2) => v.toFixed(d).replace('.', ',');

function gauge(el, label, v, max, text) {
  const frac = Math.max(-1, Math.min(1, v / max)) * 50;
  el.style.left = `${frac < 0 ? 50 + frac : 50}%`;
  el.style.width = `${Math.abs(frac)}%`;
  label.textContent = text;
}

let lastPosture = '', lastEnde;           // lastEnde: Ende des letzten Auftrags (nicht beim Laden melden)
let t0 = performance.now();
function onState(msg) {
  const st = msg.state;
  lastState = st;
  if (!!st.kopf_stabil !== ($('stab-btn').getAttribute('aria-pressed') === 'true')) $('stab-btn').setAttribute('aria-pressed', String(!!st.kopf_stabil));
  if (bodyOnline !== st.connected) { bodyOnline = st.connected; renderLink(); }
  lastEngine = msg.engine || {};
  const trieb = msg.antrieb || '';     // Antrieb (0.38.44): nur ein feiner Hinweis, Wunsch „nahezu unsichtbar“
  if ($('d-mood').title !== trieb) { $('d-mood').title = trieb; $('mood').title = trieb; }
  scene.update(st, lastEngine);
  scene.setEnten(msg.enten);
  tanz?.pruefen(lastEngine);
  map.update(st, lastEngine);
  cloud.add(st);
  tof3d.setPose(st);
  if (msg.items) { scene.setItems(msg.items); map.setItems(msg.items); }
  laser?.onState(msg.laser);
  follow?.onState(msg.mensch);
  map.setLaser(msg.laser);

  document.body.classList.toggle('spielt-ttt', !!st.werkbank?.spiel);
  const ende = st.werkbank?.auftrag_ende;
  if (ende && lastEnde !== undefined && ende !== lastEnde) toast(ende, ende.includes('abgebrochen'));
  lastEnde = ende;
  const p = posture(st);
  if (p !== lastPosture) {
    $('posture').textContent = p;
    $('d-posture').textContent = p;
    if (!REDUCED && lastPosture) { const el = $('posture'); el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash'); }
    lastPosture = p;
  }
  const e = lastEngine;
  let doing = e.aktuell || '';
  if (st.holding) {                                   // an der Werkbank: „hält den roten Würfel“ (Akkusativ aus dem Zustand)
    const ding = st.werkbank?.dinge?.find((d) => d.name === st.holding);
    doing = `${doing ? doing + ', ' : ''}hält ${ding?.akk || st.holding}`;
  }
  doing = doing || (st.powered ? 'wartet auf dich' : '');
  $('doing').textContent = doing;
  $('d-doing').textContent = doing;
  const items = [e.aktuell, ...(e.warteschlange || [])].filter(Boolean);
  const moving = Math.hypot(st.twist.vx, st.twist.vy) > 0.02 || Math.abs(st.twist.vyaw) > 0.1;
  $('stop').classList.toggle('live', items.length > 0 || moving || !!(st.skill && st.skill !== '_init'));
  for (const q of [$('queue'), $('d-queue')]) {
    if (q.dataset.sig === items.join('|')) continue;
    q.dataset.sig = items.join('|');
    q.replaceChildren(...(items.length > 1 ? items.slice(0, 5) : []).map((t, i) => {
      const li = document.createElement('li');
      li.textContent = i ? `danach: ${t}` : `jetzt: ${t}`;
      return li;
    }));
  }
  renderMood(e.gefuehl);
  $('reflex').hidden = !e.reflex;
  $('reflex').textContent = e.reflex || '';

  gauge($('g-vx'), $('g-vx-v'), st.twist.vx, 0.25, `${fmtSigned(st.twist.vx, 2)} m/s`);
  const yawDeg = (st.twist.vyaw * 180) / Math.PI;
  gauge($('g-yaw'), $('g-yaw-v'), yawDeg, 57, `${fmtSigned(yawDeg, 0).padStart(4, FIG)} °/s`);
  const s = st.perception.sectors || {};
  $('s-l').textContent = $('d-s-l').textContent = fmtM(s.links);
  $('s-m').textContent = $('d-s-m').textContent = fmtM(s.mitte);
  $('s-r').textContent = $('d-s-r').textContent = fmtM(s.rechts);
  drawTof(st.perception.tof_mm);
  tof3d.set(st.perception.tof_mm);

  // Dashboard-Daten (immer sammeln, nur zeichnen wenn sichtbar)
  const t = (performance.now() - t0) / 1000;
  chartVx.push(t, { a: st.twist.vx, b: st.requested.vx });
  if (e.gefuehl) chartMood.push(t, { a: e.gefuehl.valenz });
  chartYaw.push(t, { a: yawDeg, b: (st.requested.vyaw * 180) / Math.PI });
  joints.update(st.joints && st.joints.length === 15 ? st.joints : st.display_joints);  // gemessen, sonst abgeleitet
  const ring = $('d-batt');
  if (st.battery != null) {
    ring.style.setProperty('--v', st.battery.toFixed(3));
    ring.classList.toggle('low', st.battery < 0.3);
    ring.classList.toggle('empty', st.battery < 0.15);
    $('d-batt-v').textContent = `${Math.round(st.battery * 100)} %`;
  }
  $('d-pos').textContent = `x ${num(st.x)} m, y ${num(st.y)} m`;
  $('d-yaw').textContent = `${Math.round((st.yaw * 180) / Math.PI)}°`;
  $('d-hold').textContent = st.holding || 'nichts';
  $('d-dist').textContent = `${num(map.distance(), 1)} m`;
  const memory = gedaechtnis.daten;
  const brainSig = `${config.online}|${config.model}|${memory ? JSON.stringify([Object.keys(memory.data.tricks).length, Object.keys(memory.data.orte).length]) : ''}`;
  const db = $('d-brain');
  if (db.dataset.sig !== brainSig) {
    db.dataset.sig = brainSig;
    db.replaceChildren();
    const rows = [['Gehirn', config.online ? `Claude ${modelShort(config.model)}` : 'einfache Befehle'],
      ['Tricks', memory ? String(Object.keys(memory.data.tricks).length) : '–'],
      ['Orte', memory ? String(Object.keys(memory.data.orte).length) : '–']];
    for (const [dt, dd] of rows) {
      const d = document.createElement('div');
      const a = document.createElement('dt'); a.textContent = dt;
      const b = document.createElement('dd'); b.textContent = dd;
      d.append(a, b);
      db.append(d);
    }
  }
}

const TONE = { begeistert: 'pos', 'fröhlich': 'pos', frustriert: 'neg', angestrengt: 'neg', erschrocken: 'neg', 'mitfühlend': 'care' };
let lastMood = '';
let moodNow = 'ausgeglichen';
function renderMood(g) {
  if (!g) return;
  moodNow = g.name;
  const sig = `${g.name}|${g.grund}`;
  if (sig === lastMood) return;
  const changed = lastMood && lastMood.split('|')[0] !== g.name;
  lastMood = sig;
  const el = $('mood');
  el.hidden = g.name === 'ausgeglichen';
  el.dataset.tone = TONE[g.name] || '';
  el.querySelector('span').textContent = g.grund ? `${g.name}, weil ${g.grund}` : g.name;
  if (changed && !REDUCED) { el.classList.remove('pulse'); void el.offsetWidth; el.classList.add('pulse'); }
  $('d-mood').textContent = g.name;
  $('d-mood-why').textContent = g.grund ? `weil ${g.grund}` : 'nichts Besonderes passiert';
}

function drawTof(tof) {
  const c = $('tof').getContext('2d');
  c.clearRect(0, 0, 64, 64);
  if (!tof || tof.length !== 64) return;
  // ein Farbton (blau), je näher desto heller – wie das 3D-Gelände im Dashboard
  for (let i = 0; i < 64; i++) {
    const near = 1 - Math.min(2000, tof[i]) / 2000;
    const l = 22 + near * 62;
    c.fillStyle = `hsl(213 70% ${l}%)`;
    c.fillRect((i % 8) * 8, Math.floor(i / 8) * 8, 8, 8);
  }
}

// Zeichnen im Takt des Bildschirms – nur was sichtbar ist
let lastFrame = performance.now();
let cloudCountAt = 0;
function frame() {
  const now = performance.now();
  const dt = Math.min(0.1, (now - lastFrame) / 1000);
  lastFrame = now;
  if (view === 'memory') chartMood.draw((now - t0) / 1000);
  if (view === 'dashboard') {
    const t = (now - t0) / 1000;
    map.draw(now);
    chartVx.draw(t);
    chartYaw.draw(t);
    tof3d.draw(dt);
    if (tof3d.mode === 'cloud' && now - cloudCountAt > 500) {
      cloudCountAt = now;
      const n = cloud.alive();
      $('cloud-count').textContent = `${n.toLocaleString('de-DE')} Punkte`;
    }
  }
  drawMicWave(now);
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

// ── Ereignisse ─────────────────────────────────────────────────────────
// ── Gespräch ───────────────────────────────────────────────────────────
function addLine(kind, text, meta, wer) {
  $('hello')?.remove();
  const log = $('log');
  const p = document.createElement('p');
  if (wer) p.append(el('span', 'msg-wer', wer));   // wer spricht (seit 0.38.10: der Verlauf geht über alle Körper)
  p.className = kind === 'user' ? 'msg msg-user' : kind === 'err' ? 'msg msg-err' : kind === 'event' ? 'msg msg-event' : 'msg msg-duck';
  if (kind === 'user' || kind === 'duck') p.translate = false;   // eigene Worte und ihre Antworten nie übersetzen
  if (kind === 'duck') {
    // Entenlaute (*quak*) als kleine Marke – nur Textknoten, nie HTML aus der Antwort
    String(text).split(/(\*[^*\n]{1,40}\*)/).forEach((part) => {
      if (/^\*[^*]+\*$/.test(part)) p.append(el('span', 'laut', part.slice(1, -1)));
      else if (part) p.append(document.createTextNode(part));
    });
  } else p.textContent = text;
  if (meta) {
    const m = document.createElement('span');
    m.className = 'msg-meta';
    m.textContent = meta;
    p.append(m);
  }
  log.append(p);
  log.scrollTop = log.scrollHeight;
  return p;
}

let actsEl = null;
function onAction(a) {
  const log = $('log');
  if (!actsEl) {
    actsEl = document.createElement('ul');
    actsEl.className = 'acts';
    log.append(actsEl);
  }
  const li = document.createElement('li');
  const r = a.result || {};
  const POWER = { stand_up: 'steht auf', sit_down: 'setzt sich', rest: 'legt sich schlafen' };
  const label = {
    sound: `Laut: ${a.input?.tag}`, get_status: 'schaut nach dem Zustand', stop: 'angehalten',
    power: POWER[a.input?.action], wait: 'wartet, bis die Bewegung fertig ist', recall: 'schaut ins Gedächtnis',
    szene: 'Szene zurückgesetzt',
  }[a.tool];
  li.textContent = r.gestartet || (r.gemerkt && `merkt sich ${r.gemerkt}`) || (r.vergessen && `vergisst ${r.vergessen}`) || label || r.info || a.tool;
  if (r.ok === false) { li.classList.add('bad'); li.textContent += ` – ${r.fehler || r.grund || 'abgelehnt'}`; }
  else if (r.hinweis) li.textContent += ` (${r.hinweis})`;
  else if (r.grund) li.textContent += ` (${r.grund})`;
  actsEl.append(li);
  log.scrollTop = log.scrollHeight;
}

function onChat(m) {
  actsEl = null;
  if (m.role === 'user') {
    addLine('user', m.text, m.via === 'stimme' || m.via === 'weckwort' ? 'gesprochen' : null);
    lastUserSpoke = m.via === 'stimme' || m.via === 'weckwort';
    return;
  }
  const meta = m.source === 'claude' ? `Claude, ${m.seconds} s` : m.source === 'lokal' ? `lokales Modell, ${m.seconds} s`
    : m.source === 'anbieter' ? `anderes Modell, ${m.seconds} s`
    : m.source === 'system' ? 'Knowlin'
    : m.source === 'reflex' ? 'sofort, ohne Sprachmodell' : m.source === 'alltag' ? 'Alltagsbuddy' : m.source === 'spiel' ? 'beim Spielen' : 'einfache Befehle';
  // Körper ohne eigene Stimme (der Arm): Knowlin spricht für ihn – so steht es auch dran (seit 0.38.55)
  const stumm = !imKopf && config.eigenschaften && !config.eigenschaften.some((e) => e === 'lautsprecher' || e === 'stimmbank');
  const metaText = (uebersetzeText(meta) || meta) + (stumm && ttsOn && m.source !== 'system' ? ` · ${uebersetzeText('Knowlin spricht') || 'Knowlin spricht'}` : '');
  addLine('duck', m.text, metaText, config.duck_name);
  if (m.error && m.source !== 'claude') addLine('err', m.error);
  if (!imKopf || m.source === 'alltag') vorlesen(m, stumm ? { kopf: true } : {});   // bei Knowlin keine Entenstimme
}
// Eine Antwort vorlesen (Verkörperung oder Kopf, seit 0.38.8 auch für den Kopf); `extra` meldet Anfang und Ende
function vorlesen(m, extra = {}) {
  if (ttsOn && m.text) {
    const hooks = {
      send: extra.kopf ? null : send, goofy: !extra.kopf && !!config.goofy, mood: m.gefuehl || moodNow, energie: config.energie,
      onStart: () => { listener?.pause(true); document.body.classList.add('duck-speaking'); extra.onStart?.(); },
      onEnd: () => {
        extra.onEnd?.();
        document.body.classList.remove('duck-speaking');
        listener?.pause(false);
        // Plaudern: gleich zuhören, ohne Weckwort und ohne Taste
        // nur wenn du gerade gesprochen hast – nach getippten Befehlen und Meldungen bleibt das Mikrofon aus
        if (config.plaudern && lastUserSpoke && ['claude', 'lokal', 'einfach'].includes(m.source)
            && listener?.openWindow(8)) $('partial').textContent = 'Du bist dran …';
      },
      onError: (why) => { if (!voiceWarned) { voiceWarned = true; toast(`Eigene Stimme hakt (${why}) – spreche mit der Browser-Stimme`); } },
    };
    if (m.sprache && m.sprache.teile) playPlan(m.sprache, hooks);
    else speak(m.text, { ...hooks, onEnd: hooks.onEnd });
  }
}
let voiceWarned = false;
let lastUserSpoke = false;   // Gesprächsfenster nur nach gesprochenen Sätzen

function setThinking(on) {
  if (on && !thinkingEl) {
    thinkingEl = document.createElement('p');
    thinkingEl.className = 'thinking';
    thinkingEl.innerHTML = '<i></i><i></i><i></i><span>überlegt</span>';
    $('log').append(thinkingEl);
    $('log').scrollTop = $('log').scrollHeight;
  } else if (!on && thinkingEl) {
    thinkingEl.remove();
    thinkingEl = null;
  }
}

function sendChat(text, via = 'text') {
  text = (text || '').trim();
  if (!text) return;
  stopSpeaking();
  const nachricht = { type: 'chat', text, via, cid: Math.random().toString(36).slice(2, 12),
    ...(imKopf ? { an: 'kopf' } : {}) };                        // auf Knowlins Seiten antwortet der Kopf
  if (offeneChats.size > 10) offeneChats.delete(offeneChats.keys().next().value);
  offeneChats.set(nachricht.cid, JSON.stringify(nachricht));
  send(nachricht);
}

$('say').addEventListener('submit', (e) => {
  e.preventDefault();
  sendChat($('say-text').value);
  $('say-text').value = '';
});
$('hello').addEventListener('click', (e) => { if (e.target.tagName === 'LI') sendChat(e.target.textContent); });

document.querySelectorAll('.quick button').forEach((b) => b.addEventListener('click', () => {
  if (b.dataset.chat) return sendChat(b.dataset.chat);
  send({ type: 'tool', name: b.dataset.tool, args: JSON.parse(b.dataset.args || '{}') });
}));

// Not-Aus: Pilz rastet kurz sichtbar ein – auch bei Esc und Gamepad
let stopLatch = null;
function showStopHit() {
  cancelStageInput();
  scene.setGaze(null);
  const b = $('stop');
  b.classList.add('hit');
  clearTimeout(stopLatch);
  stopLatch = setTimeout(() => b.classList.remove('hit'), 900);
}
$('stop').addEventListener('click', () => { showStopHit(); stopSpeaking(); mentor.aus(); send({ type: 'stop' }); });
$('opt-follow').addEventListener('change', (e) => { scene.follow = e.target.checked; });
$('opt-sensor').addEventListener('change', (e) => { scene.showSensor = e.target.checked; });
$('opt-trail').addEventListener('change', (e) => { scene.showTrail = e.target.checked; });
// Darstellungsqualität der 3D-Ansicht (nur in diesem Browser)
for (const r of document.querySelectorAll('input[name=quality3d]')) {
  r.checked = r.value === scene.quality;
  r.addEventListener('change', () => { scene.setQuality(r.value, true); toast(`3D-Darstellung: ${r.parentElement.textContent.trim()}`); });
}
scene.onQualityDrop = () => toast('3D-Ansicht ruckelte – Verdeckung aus (Einstellungen → Darstellung)');

// Punktwolke: Darstellung merken (nur in diesem Browser)
const remember = (k, v) => { try { localStorage.setItem(`duckpilot.${k}`, v); } catch { /* egal */ } };
const recall = (k) => { try { return localStorage.getItem(`duckpilot.${k}`); } catch { return null; } };
function setTofMode(mode) {
  tof3d.setMode(mode);
  const isCloud = tof3d.mode === 'cloud';
  $('card-tof').classList.toggle('is-cloud', isCloud);
  $('cloud-legend').hidden = !isCloud;
  $('tof-note').textContent = isCloud ? 'Messpunkte der letzten Minute · ziehen zum Drehen' : '8 × 8, Höhe = Nähe';
  $('tof3d').setAttribute('aria-label', isCloud ? 'Punktwolke des Tiefensensors' : 'Tiefenbild als 3D-Gelände');
  for (const r of document.querySelectorAll('input[name=tof-mode]')) r.checked = r.value === tof3d.mode;
  remember('tofMode', tof3d.mode);
}
for (const r of document.querySelectorAll('input[name=tof-mode]')) r.addEventListener('change', (e) => setTofMode(e.target.value));
setTofMode(recall('tofMode') || 'terrain');
$('cloud-clear').addEventListener('click', () => cloud.clear());
$('opt-cloud').addEventListener('change', (e) => { scene.showCloud = e.target.checked; remember('cloud3d', e.target.checked ? '1' : '0'); });
$('opt-cloud').checked = scene.showCloud = recall('cloud3d') === '1';
// Simulator aufräumen (seit 0.37.14): z. B. den Ball aus einer unerreichbaren Ecke holen
$('szene-reset').addEventListener('click', async () => {
  try {
    const r = await api('/api/szene', 'POST', { aktion: 'zuruecksetzen' });
    const tx = (s) => uebersetzeText(s) || s;
    if (r.ok) toast(r.hinweis ? `${tx(r.text)}. ${tx(r.hinweis)}` : tx(r.text)); else toast(tx(r.fehler || 'Geht gerade nicht'), true);
  } catch (e) { toast(e.message || String(e), true); }
});
scene.povFrame = $('pov');
// Kein kleines Entenblick-Bild mehr (seit 0.38.24): es lag hinter dem Gesprächsglas, und die Kachel unten links zeigt
// das Kamerabild schon (Hinweis 7.11.). Der Entenblick als ganze Bühne bleibt – am Roboter mit dem Kamerabild.
function updatePov() {
  const robot = config.backend === 'robotd';
  const main = scene.mode === 'entenblick';
  scene.showPov = false;
  $('pov').hidden = !(main && robot);
  $('pov').classList.toggle('pov--main', main && robot);
  $('pov-img').hidden = $('pov-boxes').hidden = !robot;
  const blick = config.modul === 'reachy_mini' ? 'Reachys Blick' : 'Entenblick';
  $('pov-label').textContent = robot ? `${blick} · Kopfkamera` : `${blick} · Kopfkamera (Simulator)`;
}
// Am echten Roboter: Bilder von mediad, ein paar pro Sekunde, nur wenn der Entenblick sichtbar ist
let povBusy = false;
let povUrl = null;
setInterval(async () => {
  if (povBusy || config.backend !== 'robotd' || $('pov').hidden || view !== 'cockpit' || document.hidden) return;
  povBusy = true;
  try {
    const r = await fetch('/api/kamera/bild', { cache: 'no-store' });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      $('pov-label').textContent = `Kamera: ${j.fehler || r.status}`;
    } else {
      const info = JSON.parse(r.headers.get('X-Info') || '{}');
      const url = URL.createObjectURL(await r.blob());
      const img = $('pov-img');
      img.onload = () => { if (povUrl) URL.revokeObjectURL(povUrl); povUrl = url; drawBoxes(info); };
      img.src = url;
      $('pov-label').textContent = info.enten ? `Entenblick · ${info.enten.length ? `${info.enten.length} Ente${info.enten.length > 1 ? 'n' : ''} erkannt` : 'keine Ente'}` : 'Entenblick · Kopfkamera';
    }
  } catch { /* nächster Versuch */ }
  povBusy = false;
}, 300);
function drawBoxes(info) {
  const c = $('pov-boxes');
  const img = $('pov-img');
  c.width = img.clientWidth; c.height = img.clientHeight;
  const g = c.getContext('2d');
  g.clearRect(0, 0, c.width, c.height);
  if (!info.enten || !info.breite) return;
  const kx = c.width / info.breite, ky = c.height / info.hoehe;
  g.strokeStyle = css('--accent'); g.lineWidth = 2; g.fillStyle = css('--accent'); g.font = '12px "IBM Plex Sans"';
  for (const e of info.enten) {
    const [x0, y0, x1, y1] = e.box;
    g.strokeRect(x0 * kx, y0 * ky, (x1 - x0) * kx, (y1 - y0) * ky);
    g.fillText(`Ente ${Math.round(e.wert * 100)} %`, x0 * kx + 3, Math.max(12, y0 * ky - 4));
  }
}
updatePov();

// ── Blick per Klick und Ziehen (wie Street View) ─────────────────────────
// Beobachten: Klick = hinschauen, Doppelklick = hinlaufen, Ziehen dreht die Kamera.
// Entenblick: Ziehen = umschauen (der Kopf folgt, am Anschlag dreht sich der Körper mit), Doppelklick = hinlaufen.
const HINTS = {
  beobachten: '<b>Klick</b> hinschauen · <b>Doppelklick</b> hinlaufen · <b>Ziehen</b> Kamera drehen · <kbd>W</kbd><kbd>A</kbd><kbd>S</kbd><kbd>D</kbd> fahren · <kbd>Esc</kbd> stoppt',
  entenblick: '<b>Ziehen</b> umschauen · <b>Klick</b> hinschauen · <b>Doppelklick</b> hinlaufen · <kbd>W</kbd><kbd>A</kbd><kbd>S</kbd><kbd>D</kbd> fahren · <kbd>Esc</kbd> stoppt',
};
// Reachy Mini (seit 0.38.3): steht fest – A/D drehen den Körper, Doppelklick dreht hin statt hinzulaufen
const HINTS_REACHY = {
  beobachten: '<b>Klick</b> hinschauen · <b>Doppelklick</b> hindrehen · <b>Ziehen</b> Kamera drehen · <kbd>A</kbd><kbd>D</kbd> drehen · <kbd>Esc</kbd> stoppt',
  entenblick: '<b>Ziehen</b> umschauen · <b>Klick</b> hinschauen · <kbd>A</kbd><kbd>D</kbd> drehen · <kbd>Esc</kbd> stoppt',
};
const HINTS_OHNE_KOPF = { beobachten: '<b>Ziehen</b> Kamera drehen · <kbd>Esc</kbd> stoppt', entenblick: '<kbd>Esc</kbd> stoppt' };
const YAW_MAX = 1.05, PITCH_MAX = 0.65;
function setStageMode(mode) {
  mode = mode === 'entenblick' ? 'entenblick' : 'beobachten';
  scene.setMode(mode);
  if (activePointer()) scene.controls.enabled = false;   // Laser oder Folg mir an: Ziehen bewegt den Zeiger
  for (const r of document.querySelectorAll('input[name="stage-mode"]')) r.checked = r.value === mode;
  const ohneKopf = config.eigenschaften && !config.eigenschaften.includes('kopf');      // Arm (0.38.47)
  $('stage-hint').innerHTML = (ohneKopf ? HINTS_OHNE_KOPF : config.modul === 'reachy_mini' ? HINTS_REACHY : HINTS)[mode];   // feste Texte
  updatePov();
  document.querySelector('.view-cockpit .stage').classList.toggle('is-pov', mode === 'entenblick');
  remember('stageMode', mode);
}
for (const r of document.querySelectorAll('input[name="stage-mode"]')) r.addEventListener('change', (e) => setStageMode(e.target.value));
setStageMode(recall('stageMode'));

$('stab-btn').addEventListener('click', async () => {
  const on = $('stab-btn').getAttribute('aria-pressed') !== 'true';
  $('stab-btn').setAttribute('aria-pressed', String(on));
  const r = await api('/api/settings', 'POST', { kopf_stabil: on }).catch(() => ({ ok: false }));
  if (!r.ok) { $('stab-btn').setAttribute('aria-pressed', String(!on)); toast(r.fehler || 'Nicht geändert', true); return; }
  toast(on ? 'Kopf bleibt ruhig – wie bei einem Huhn' : 'Kopf wieder locker');
});

const stageEl = document.querySelector('.view-cockpit .stage');
let drag = null, clickTimer = null, lastClick = null, lookSentAt = 0;
const DOUBLE_MS = 300, DOUBLE_MS_TOUCH = 450;
// Not-Aus: nichts, was noch in der Leitung hängt, darf danach losgehen
function cancelStageInput() {
  clearTimeout(clickTimer);
  clickTimer = null; drag = null; lastClick = null;
  laser?.off(true);
  follow?.off(true);
}

// ── Laserpointer (laser.js) ───────────────────────────────────────────
const pointerHelp = { $, scene, send, toast, stageEl, state: () => lastState, others: () => [laser, follow] };
laser = initLaser(pointerHelp);
follow = initFollow(pointerHelp);
kollision = initKollision({ ...pointerHelp, api, listener: () => listener, estop: () => $('stop').click() });
ctl = initController({ ...pointerHelp, headNow, listener: () => listener, stopSpeaking, estop: () => $('stop').click(),
  showView: (v) => showView(v), setStageMode, stageMode: () => scene.mode, getConfig: () => config });
function headNow() {
  // was der Kopf soll (ohne Stabilisator-Ausgleich), sonst die gemessene Stellung
  const soll = lastEngine && lastEngine.kopf_soll;
  if (soll) return { yaw: soll.yaw || 0, pitch: soll.pitch || 0 };
  const h = (lastState && lastState.head) || {};
  return { yaw: h.head_yaw || 0, pitch: h.head_pitch || 0 };
}
function lookAtScreen(x, y) {
  const p = scene.pick(x, y);
  auswahl.klick(p, x, y);                    // Ding, Möbel oder andere Ente anwählen (seit 0.37.3)
  if (!p.look) return;
  send({ type: 'blick', x: p.look.x, y: p.look.y, z: p.look.z || 0, sekunden: 8 });
  scene.setGaze(p.look, 8);
  scene.pulse('look', p.look.x, p.look.y);
}
function goToScreen(x, y) {
  const p = scene.pick(x, y);
  if (p.ding === 'moebel') { toast('Da steht ein Möbelstück – auf den freien Boden doppelklicken'); return; }
  const at = p.hit && p.ding ? p.hit : p.floor;      // Ball oder Socke: hin zum Ding
  if (!at) { toast('Dorthin kann sie nicht laufen – auf den Boden doppelklicken'); return; }
  send({ type: 'hingehen', x: at.x, y: at.y });
  scene.setGaze({ x: at.x, y: at.y, z: 0 }, 4);
  scene.pulse('go', at.x, at.y);
}
function onStageDown(e) {
  if (e.button !== 0 || e.target.closest('.view-tools, .talk, .hud-tele, .ticker, .drive-pad, .auswahl-pop')) return;
  if (activePointer()) {
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch { /* egal */ }
    activePointer().pointAt(e.clientX, e.clientY);
    return;
  }
  drag = { x: e.clientX, y: e.clientY, t: performance.now(), moved: false, start: headNow(), id: e.pointerId };
  if (scene.mode === 'entenblick') {
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch { /* egal */ }
  }
}
function onStageMove(e) {
  if (activePointer()) {
    if (!e.target.closest('.view-tools, .talk, .hud-tele, .ticker, .drive-pad, .auswahl-pop')) activePointer().pointAt(e.clientX, e.clientY);
    return;
  }
  if (!drag || e.pointerId !== drag.id) return;
  const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
  if (!drag.moved && Math.hypot(dx, dy) > 5) drag.moved = true;
  if (!drag.moved || scene.mode !== 'entenblick') return;
  // „Die Welt anfassen“: was unter dem Zeiger liegt, bleibt ungefähr unter dem Zeiger
  const rect = stageEl.getBoundingClientRect();
  const k = (70 * Math.PI / 180) / Math.max(200, rect.height);
  let yaw = drag.start.yaw + dx * k, pitch = drag.start.pitch - dy * k;
  pitch = Math.max(-PITCH_MAX, Math.min(PITCH_MAX, pitch));
  const now = performance.now();
  if (now - lookSentAt < 50) return;
  lookSentAt = now;
  if (Math.abs(yaw) > YAW_MAX) {
    // am Anschlag dreht sich der Körper mit – wie wenn man in Street View weiterzieht
    send({ type: 'drive', vx: 0, vy: 0, vyaw: Math.sign(yaw) * 0.8, head: { yaw: Math.sign(yaw) * YAW_MAX, pitch } });
    yaw = Math.sign(yaw) * YAW_MAX;
  }
  send({ type: 'blick', yaw, pitch, sekunden: 10 });
  scene.setGaze(null);
}
function onStageUp(e) {
  if (activePointer()) return;
  if (!drag || e.pointerId !== drag.id) return;
  const d = drag;
  drag = null;
  if (d.moved || performance.now() - d.t > 450) return;
  // Finger sind ungenauer und langsamer als die Maus: beim Doppeltippen mehr Spielraum
  const touch = e.pointerType === 'touch' || e.pointerType === 'pen';
  const win = touch ? DOUBLE_MS_TOUCH : DOUBLE_MS, slop = touch ? 40 : 14;
  const near = lastClick && performance.now() - lastClick.t < win && Math.hypot(e.clientX - lastClick.x, e.clientY - lastClick.y) < slop;
  if (near) {
    clearTimeout(clickTimer);
    lastClick = null;
    goToScreen(e.clientX, e.clientY);
    return;
  }
  lastClick = { x: e.clientX, y: e.clientY, t: performance.now() };
  const x = e.clientX, y = e.clientY;
  clickTimer = setTimeout(() => { clickTimer = null; lookAtScreen(x, y); }, win);
}
stageEl.addEventListener('pointerdown', onStageDown);
stageEl.addEventListener('pointermove', onStageMove);
stageEl.addEventListener('pointerup', onStageUp);
stageEl.addEventListener('pointercancel', () => { drag = null; });
stageEl.addEventListener('pointerleave', (e) => {
  if (e.pointerType === 'mouse') { laser?.leave(); follow?.leave(); }   // Maus raus: Zeiger „aus“, verlischt nach 3 s
});
$('opt-model').addEventListener('change', (e) => {
  const style = e.target.checked ? 'original' : 'einfach';
  scene.setModelStyle(style);
  api('/api/settings', 'POST', { model_style: style });
});
$('opt-tts').addEventListener('change', (e) => { ttsOn = e.target.checked; if (!ttsOn) stopSpeaking(); });
$('opt-chat').addEventListener('change', async (e) => {
  const on = e.target.checked;
  const r = await api('/api/settings', 'POST', { plaudern: on });
  if (!r.ok) { e.target.checked = !on; toast(r.fehler || 'Nicht gespeichert'); return; }
  if (on && config.stt !== 'browser') toast('Plaudern: Nach jeder Antwort bitte die Sprechtaste nutzen – automatisches Zuhören gibt es mit der Online-Erkennung.');
  else toast(on ? 'Plaudern an – nach jeder Antwort kurz zuhören' : 'Plaudern aus');
  if (!on) listener?.closeWindow();
});

// ── Sprache ────────────────────────────────────────────────────────────
let micState = 'idle';
const mic = $('mic');
function setupVoice() {
  const mode = config.stt === 'whisper' && config.whisper ? 'whisper' : config.stt === 'aus' ? 'aus' : 'browser';
  const sig = `${mode}|${config.wake_word}`;
  ttsOn = config.tts && !fern.remote;
  $('opt-tts').checked = ttsOn; $('opt-tts').dispatchEvent(new Event('input'));
  // Sprache aus: Sprechtaste, Weckwort und Plaudern ausblenden, nur „Antworten vorlesen“ bleibt
  document.querySelector('.voice').classList.toggle('voice--off', mode === 'aus');
  document.querySelector('.voice').classList.toggle('voice--insecure', !window.isSecureContext);
  if (listener && listener.sig === sig) return;
  if (listener) listener.dispose();
  $('opt-always').checked = false;
  mic.classList.remove('always');
  listener = new Listener({
    mode,
    wakeWord: config.wake_word,
    onPartial: (t) => { $('partial').textContent = t; kopf.partial(t); },
    onFinal: (t, via) => { $('partial').textContent = ''; kopf.partial(''); sendChat(t, via); },
    onState: (s) => {
      micState = s;
      mic.setAttribute('aria-pressed', s === 'listening' ? 'true' : 'false');
      $('mic-label').textContent = s === 'listening' ? 'Ich höre …' : s === 'working' ? 'Verstehe …' : s === 'window' ? 'Ich höre zu …' : 'Halten und sprechen';
      mic.classList.toggle('window', s === 'window');
      if (s !== 'window' && $('partial').textContent === 'Du bist dran …') $('partial').textContent = '';
      if (s === 'listening') send({ type: 'listening' });
      kopf.hoert(s === 'listening');
    },
    onError: (msg) => addLine('err', msg),
  });
  listener.sig = sig;
  $('wake').textContent = listener.wake;          // auf Englisch „duck“
  mic.disabled = !listener.supported;
  $('opt-always').disabled = !listener.supported || mode !== 'browser';
  $('opt-always').closest('label').title = mode === 'whisper'
    ? 'Das Weckwort braucht die Spracherkennung von Edge oder Chrome (Charakter → Gespräch) – lokal mit Whisper nur die Sprechtaste'
    : `Dauerhören: „${listener.wake}“ am Satzanfang, z. B. „${listener.wake}, tanz“ – oder erst „${listener.wake}“, dann den Befehl`;
  $('partial').textContent = '';
  if (!listener.supported) {
    $('mic-label').textContent = mode === 'aus' ? 'Sprache aus' : 'Sprache hier nicht verfügbar';
    if (mode !== 'aus' && !window.isSecureContext) $('partial').textContent = 'Sprechen am Handy: im Textfeld oben das Mikrofon der Handy-Tastatur antippen und diktieren.';
    else if (mode === 'browser') $('partial').textContent = 'Spracherkennung gibt es in Edge und Chrome – oder lokal (Einstellungen).';
  } else {
    $('mic-label').textContent = 'Halten und sprechen';
  }
}
mic.addEventListener('pointerdown', (e) => {
  if (!listener || !listener.supported) return;
  e.preventDefault(); stopSpeaking(); if (config.modul !== 'reachy_mini') playSound('peck'); listener.start();   // nur Enten picken
});
mic.addEventListener('pointerup', (e) => { e.preventDefault(); listener?.stop(); });
mic.addEventListener('pointerleave', () => listener?.stop());
$('opt-always').addEventListener('change', (e) => {
  const on = listener ? listener.setAlways(e.target.checked) : false;
  e.target.checked = on;
  mic.classList.toggle('always', on);
});

// Pegelbalken in der Sprechtaste (Leinwand 192 × 64 für scharfe Kanten, angezeigt 96 × 32)
function drawMicWave(now) {
  const c = $('mic-wave');
  const g = c.getContext('2d');
  g.clearRect(0, 0, c.width, c.height);
  const active = micState === 'listening' || micState === 'working' || micState === 'window' || (listener && listener.always);
  if (view !== 'cockpit' || !active) return;
  const strong = micState === 'listening';
  const t = now / 1000, n = 16, w = 6, gap = (c.width - n * w) / (n - 1), mid = c.height / 2;
  g.fillStyle = css('--accent');
  g.globalAlpha = strong ? 1 : 0.55;
  for (let i = 0; i < n; i++) {
    const env = Math.sin((i + 0.5) / n * Math.PI);
    const wave = REDUCED ? 0.3 : (strong ? 0.35 + 0.65 * Math.abs(Math.sin(t * 7 + i * 0.9) * Math.sin(t * 3.1 - i * 0.5))
      : 0.2 + 0.2 * Math.abs(Math.sin(t * 2 + i * 0.7)));
    const h = Math.max(6, env * wave * (c.height - 8));
    const x = i * (w + gap);
    g.beginPath();
    g.roundRect(x, mid - h / 2, w, h, 3);
    g.fill();
  }
  g.globalAlpha = 1;
}

// ── Tastatur & Gamepad ─────────────────────────────────────────────────
const keys = new Set();
const typing = () => {
  const el = document.activeElement;
  return el && (el.tagName === 'INPUT' || el.tagName === 'SELECT' || el.tagName === 'TEXTAREA') && el.type !== 'checkbox' && el.type !== 'radio';
};
window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { showStopHit(); mentor.aus(); send({ type: 'stop' }); stopSpeaking(); return; }
  if (typing() || view !== 'cockpit') return;
  if (e.code === 'Space') {
    if (!e.repeat && listener && listener.supported) { stopSpeaking(); listener.start(); }
    e.preventDefault();
    return;
  }
  keys.add(e.key.toLowerCase());
});
window.addEventListener('keyup', (e) => {
  if (e.code === 'Space' && listener) { listener.stop(); e.preventDefault(); return; }
  keys.delete(e.key.toLowerCase());
});
window.addEventListener('blur', () => keys.clear());

setInterval(() => {
  let vx = 0, vy = 0, vyaw = 0;
  if (keys.has('w') || keys.has('arrowup')) vx += 0.22;
  if (keys.has('s') || keys.has('arrowdown')) vx -= 0.12;
  if (keys.has('a') || keys.has('arrowleft')) vyaw += 0.9;
  if (keys.has('d') || keys.has('arrowright')) vyaw -= 0.9;
  if (keys.has('q')) vy += 0.1;
  if (keys.has('e')) vy -= 0.1;
  let head = null;
  const pads = navigator.getGamepads ? [...navigator.getGamepads()].filter(Boolean) : [];
  if (pads.length) {
    const g = pads[0];
    const dz = (v) => (Math.abs(v) < 0.15 ? 0 : v);
    const ly = dz(g.axes[1] || 0), lx = dz(g.axes[0] || 0), rx = dz(g.axes[2] || 0), ry = dz(g.axes[3] || 0);
    if (ly || lx) { vx = ly < 0 ? -ly * 0.25 : -ly * 0.15; vyaw = -lx * 1.0; }
    if (rx || ry) head = { yaw: -rx * 0.9, pitch: ry * 0.5 };
    if (g.buttons[1]?.pressed) { showStopHit(); send({ type: 'stop' }); }
  }
  if (touchDrive.id !== null) { vx = touchDrive.vx; vyaw = touchDrive.vyaw; }
  if (vx || vy || vyaw || head) send({ type: 'drive', vx, vy, vyaw, head });
}, 100);

// ── Kachel unten links: Tiefensensor oder Kamerabild ─────────────────
const kachel = initKachel({ getConfig: () => config, getView: () => view, scene, recall, remember });

// ── Fahren per Touch (Handy, Tablet): Steuerkreuz auf der Bühne ──────
const touchDrive = initTouchFahren({ send });

// ── Gedächtnis ─────────────────────────────────────────────────────────
const gedaechtnis = initGedaechtnis({ $, api, send, showView, toast, scene, map, addLine, num });

// ── Einstellungen (einstellungen_ui.js) ─────────────────────────────────
const einst = initEinstellungen({ $, api, toast, showView: (v, p) => showView(v, p), getConfig: () => config, scene });
const { save } = einst;

// ── Kopfleiste: Persönlichkeit, Ansicht-Menü, Hintergrund-Aufgaben (kopfleiste.js) ──
const kopfleiste = initKopfleiste({ $, api, toast, send, showView: (v, p) => showView(v, p), getConfig: () => config,
  getView: () => view, einst });
const { renderTasks } = kopfleiste;

// ── Tricks: Gefühle und Hub ───────────────────────────────────────────
const tricksSeite = initTricksSeite({ $, api, el, toast, send, showView: (v, p) => showView(v, p), getConfig: () => config,
  skillPacks: () => skillPacks, reachy: () => reachy });

const pflege = initPflege({ $, api, el, getConfig: () => config });
const designsystem = initDesignsystem({ $, el, css });
const skillPacks = initSkills({ $, api, el, toast, send, showView: (v) => showView(v) });
ladeSprache().then(() => uebersetze());   // eingestellte Sprache; Englisch übersetzt die Seite laufend (0.34)
let lernen = null;
const feld = trainingsfeldLaden($, () => ({ koerper: config.modul === 'open_duck_mini' ? 'open_duck_mini' : scene.koerper, original: scene.modelStyle === 'original', farbe: scene.farbe }));
const training = initTraining({ $, api, el, toast, onLaeufe: (r) => feld.laeufe(r), onLocal: (on) => lernen && lernen.show(on),
  onGoal: () => lernen && lernen.render() });
const parcours = initParcours({ $, api, el, toast, sendChat, showView });
lernen = initLernen({ $, api, el, toast, chart: training.chart, showView: (v) => showView(v),
  onGoal: (g) => training.setGoal(g),
  pickSource: (id) => parcours.pickSource(id) });
$('pc-learn').addEventListener('click', () => { training.setProvider('pc'); showView('training'); lernen.prepareLoop(); });
const akrobatik = initAkrobatik({ $, api, el, toast, showView: (v) => showView(v) });
const stossreihe = initStossreihe({ $, api, el, toast });
const alltag = initAlltag({ $, api, el, toast });
const nfc = initNfc({ $, api, el, toast });
const hirn = initHirn({ $, api, el, toast, getConfig: () => config });
const reachy = initReachy({ $, api, el, toast, showView: (v, p) => showView(v, p), scene, isRemote: () => fern.remote });
const reachyApps = initReachyApps({ $, api, el, toast, isRemote: () => fern.remote });
const start = initStart({ $, api, el, toast, showView: (v, p) => showView(v, p), save, isRemote: () => fern.remote,
  getConfig: () => config, personaName, vorschlaege: (f) => kopf.vorschlaege(f) });
const charakter = initCharakter({ $, el, save });
const kopf = initKopf({ $, el, toast, sendChat, vorlesen, figurWecken: (m) => start.figurWecken(m), isRemote: () => fern.remote,
  aufStartseite: () => view === 'start',
  mikro: (an) => { if (!listener || !listener.supported) { if (an) toast('Sprache hier nicht verfügbar', true); return; }
    if (an) { stopSpeaking(); listener.start(); } else listener.stop(); } });
$('rail-start').addEventListener('click', () => showView('start'));
$('geist-link').addEventListener('click', () => showView('start'));   // Kopfzeile „Knowlin › Quacki“: zu Knowlin
$('netz-show').addEventListener('click', () => $('card-brain').scrollIntoView({ behavior: 'smooth', block: 'start' }));
$('goto-ki').addEventListener('click', () => showView('settings', 'ki'));
{
  let armed = null;
  $('netz-reset').addEventListener('click', async () => {
    const b = $('netz-reset');
    if (!armed) {                       // zwei Klicks: Zurücksetzen lässt sich nicht rückgängig machen
      b.textContent = 'Wirklich alles vergessen?';
      armed = setTimeout(() => { armed = null; b.textContent = 'Netz zurücksetzen'; }, 4000);
      return;
    }
    clearTimeout(armed); armed = null; b.textContent = 'Netz zurücksetzen';
    const r = await api('/api/erfahrung/vergessen', 'POST', { alles: true }).catch(() => null);
    toast(r && r.ok ? 'Erfahrungsnetz zurückgesetzt' : 'Nicht zurückgesetzt', !(r && r.ok));
  });
}
const knowlets = initKnowlets({ $, api, el, toast, isRemote: () => fern.remote });
const sicherung = initSicherung({ $, api, el, toast, isRemote: () => fern.remote, showView: (v) => showView(v) });
const augen = initAugen({ $, api, el, toast, getScene: () => scene, getConfig: () => config, isRemote: () => fern.remote });
const kameraSpiele = initKameraSpiele({ $, api, toast, scene, isRemote: () => fern.remote });
const mentor = initMentor({ $, api, send, toast, isRemote: () => fern.remote });
const fern = initFern({ $, api, el, toast, isApp: () => !!config.app_mode, openQuit: () => beenden.open() });
initOffenlegung();
const beenden = initBeenden({ $, api, el, toast, isRemote: () => fern.remote });
const tanz = initTanz({ $, api, el, toast, send, gestenName: tricksSeite.gefuehlName });
initSprachwahl({ $ });
initFehlerbericht({ $, api });
const enten = initEnten({ $, api, el });
initAussehen({ $, scene });
raum = initRaum({ $, api, el, scene, toast, zumCockpit: () => showView('cockpit'), lagebild: (k) => map.setKarte(k) });
const auswahl = initAuswahl({ $, api, el, scene, send, toast, stageEl });
const koerperwahl = initKoerperwahl({ $, api, save, showView: (v, p) => showView(v, p), isRemote: () => fern.remote });
const ersteSchritte = initErsteSchritte({ $, api, toast, isRemote: () => fern.remote, showView: (v) => showView(v) });
let fernAnnounced = false;
function onConnection(msg) {
  fern.setRemote(msg.fern, msg.geraet);
  renderLink();
  if (msg.fern && !fernAnnounced) {
    fernAnnounced = true;
    // auf dem Handy nicht doppelt vorlesen – der PC spricht schon; einschalten unter „Antworten vorlesen“
    ttsOn = false;
    $('opt-tts').checked = false; $('opt-tts').dispatchEvent(new Event('input'));
    toast(`Verbunden als Fernbedienung (${msg.geraet || 'Handy'})`);
  }
}
const voicePage = initVoicePage({ $, api, el, toast, send, playPlan, speak, germanVoices, setVoice, currentVoice,
  getConfig: () => config, getMood: () => moodNow, imKopf: () => imKopf });
$('open-design').addEventListener('click', () => showView('design'));
$('modell-laden').addEventListener('click', async () => {
  const r = await api('/api/modell/laden', 'POST').catch(() => null);
  if (!r || !r.ok) toast((r && r.fehler) || 'Laden geht gerade nicht', true);
});

// Direktstart in eine Verkörperung (Verknüpfung): ist gerade eine andere im Körper, wechseln – mit Mind to Body
async function direktZurFigur() {
  const art = { duckpilot: 'Microduck', reachy_mini: 'Reachy Mini', open_duck_mini: 'Open Duck Mini v2', so101: 'SO-101' }[direktModul];
  const id = { duckpilot: 'duckpilot', reachy_mini: 'reachy-mini', open_duck_mini: 'open-duck-mini', so101: 'so101' }[direktModul];
  await new Promise((r) => setTimeout(r, 1800));          // erst der Knowlin-Splash
  const anders = config.modul !== direktModul;
  await start.mindToBody({ id, modell: art, figur: anders ? art : config.duck_name }, async () => {
    if (anders) {
      await save(direktModul === 'duckpilot' ? { modul: 'duckpilot' } : { modul: direktModul, backend: 'sim', sim_physik: false });
      for (let i = 0; i < 60 && config.modul !== direktModul; i++) await new Promise((r) => setTimeout(r, 100));
    }
    send({ type: 'koerper' });                            // Mind to Body: jetzt wacht sie auf
  });
}

// ── Start ──────────────────────────────────────────────────────────────
connect();
const [startView, startPart] = (location.hash || '').slice(1).split('/');
// Auch beim Start im Cockpit die Unternavigation (Cockpit, Tricks, …) zeigen – sie erschien bis 0.36.3 erst nach dem
// ersten Klick auf einen Bereich (Hinweis aus dem Test 1.11.)
// Seit 0.38 öffnet Knowlin mit der Startseite; die Verknüpfung „duckpilot“ (?modul=duckpilot) und Lesezeichen auf eine
// Seite (#tricks …) gehen direkt dorthin
// Seit 0.38.3 auch „?modul=reachy_mini“ (Verknüpfung „Reachy“): nach dem Splash Mind to Body in diese Verkörperung
const direktModul = new URLSearchParams(location.search).get('modul');
const direkt = ['duckpilot', 'reachy_mini', 'open_duck_mini'].includes(direktModul);
if (startView && startView !== 'cockpit' && document.getElementById(`view-${startView}`)) showView(startView, startPart);
else if (direkt || startView === 'cockpit') {
  imKopf = false;                                         // gleich in der Verkörperung – sie wacht nach der Startnachricht auf
  document.body.classList.remove('im-kopf');
  const [g0, t0] = groupOf('cockpit'); renderSubnav(g0, t0); pageTitle = t0.label || ''; updateTitle();
}
else showView('start');
initHandyLeiste();
window.duckpilot = { scene, map, send, showView, renderTasks, akrobatik, alltag, kollision, ctl, get state() { return lastState; } };
