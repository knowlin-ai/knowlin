// Persönlichkeit als Punkt auf einer Fläche: X ruhig ↔ lebhaft, Y ernst ↔ albern (ab der Mitte: Goofy).

const NAMES = [
  // Zeilen von ernst (unten) nach albern (oben), Spalten ruhig → lebhaft
  ['Gelassen', 'Sachlich', 'Eifrig'],
  ['Gemütlich', 'Ausgeglichen', 'Munter'],
  ['Verträumt', 'Verschmitzt', 'Quirlig'],
  ['Tollpatschig', 'Goofy', 'Chaos-Ente'],
];
const DESCRIBE = {
  Gelassen: 'Ruhig und ernst. Kleine Gesten, keine Albernheiten.',
  Sachlich: 'Erledigt Aufgaben ordentlich, ohne viel Tamtam.',
  Eifrig: 'Voller Tatendrang, aber bei der Sache.',
  Gemütlich: 'Lässt es ruhig angehen, mit einem Augenzwinkern.',
  Ausgeglichen: 'Freundlich, aufmerksam, zeigt Gefühle in Maßen.',
  Munter: 'Lebhaft und zugewandt, große Gesten.',
  Verträumt: 'Goofy, aber gemächlich: staunt viel, stolpert manchmal.',
  Verschmitzt: 'Goofy light: ab und zu ein kurzes „Nö!“ und ein Stolperer.',
  Quirlig: 'Goofy und flink: bockt öfter, kann kaum stillhalten.',
  Tollpatschig: 'Sehr goofy, aber langsam: stolpert, schüttelt sich, gackert.',
  Goofy: 'Witzig, naiv, oft tollpatschig und kurz trotzig – immer liebevoll.',
  'Chaos-Ente': 'Maximal albern und wild. Für gute Laune, nicht für Präzisionsarbeit.',
};

// Knowlin selbst (seit 0.38.10, Wunsch des Maintainers): dasselbe Feld, aber seriös ↔ verspielt und ohne Goofy-Bereich
export const KNOWLIN_NAMEN = [
  ['Besonnen', 'Sachlich', 'Zielstrebig'],
  ['Gelassen', 'Ausgeglichen', 'Engagiert'],
  ['Nachdenklich-heiter', 'Heiter', 'Schwungvoll'],
  ['Verschmitzt', 'Verspielt', 'Übermütig'],
];
export const KNOWLIN_TEXTE = {
  Besonnen: 'Ruhig, genau, wägt ab. Keine Witze.',
  Sachlich: 'Klar und seriös – so beginnt Knowlin.',
  Zielstrebig: 'Seriös und mit Tempo bei der Sache.',
  Gelassen: 'Ruhig, freundlich, mit leisem Humor.',
  Ausgeglichen: 'Seriös im Kern, mit einem Lächeln.',
  Engagiert: 'Zugewandt und lebhaft, ohne albern zu werden.',
  'Nachdenklich-heiter': 'Gemächlich, mit hintergründigem Humor.',
  Heiter: 'Locker und freundlich, scherzt gern.',
  Schwungvoll: 'Lebhaft und zum Scherzen aufgelegt.',
  Verschmitzt: 'Ruhig, aber voller kleiner Späße.',
  Verspielt: 'Spielt mit Worten, nimmt wenig ernst.',
  'Übermütig': 'Maximal lebhaft und verspielt.',
};

function nameIn(namen, x, y) {
  const row = y < 0.25 ? 0 : y < 0.5 ? 1 : y < 0.75 ? 2 : 3;
  const col = x < 0.34 ? 0 : x < 0.67 ? 1 : 2;
  return namen[row][col];
}

export function personaName(x, y) {
  return nameIn(NAMES, x, y);
}
export const personaText = (name) => DESCRIBE[name] || '';

// Was der Charakter im Leerlauf tut – kommt vom Server (/api/emotions), bis dahin leer
const idleByPersona = new Map();
const pads = new Set();
export function setIdleRepertoire(catalog) {
  idleByPersona.clear();
  for (const e of catalog) {
    if (e.art !== 'charakter' && !(e.bei || []).length) continue;
    for (const p of e.bei || []) {
      if (!idleByPersona.has(p)) idleByPersona.set(p, []);
      if (e.text) idleByPersona.get(p).push(e.text);
    }
  }
  for (const pad of pads) pad.render();
}
export function idleText(name) {
  // Entengesten nur bei Enten (Befund der Abnahme 12.11.: Reachy „putzt sich das Gefieder“)
  const cl = document.body.classList;
  if (cl.contains('koerper-reachy')) return 'Im Leerlauf: kleine Regungen mit Kopf und Antennen.';
  if (cl.contains('keine-ente')) return '';
  if (name === 'Ausgeglichen') return 'Im Leerlauf: schaut sich ruhig um.';
  const list = idleByPersona.get(name);
  return list && list.length ? `Im Leerlauf: ${list.slice(0, 4).join(', ')}${list.length > 4 ? ' …' : '.'}` : '';
}

export class PersonalityPad {
  constructor(root, { onCommit, compact = false, namen = NAMES, texte = DESCRIBE, achsen = null, goofy = true,
    titel = 'Persönlichkeit', leerlauf = true, schluessel = ['energie', 'humor'], onMarke = null }) {
    this.onCommit = onCommit;
    this.onMarke = onMarke;      // (id, x, y) – Punkte der Verkörperungen ziehen (Knowlins Feld, Wunsch des Maintainers 5.11.)
    this.namen = namen;
    this.texte = texte;
    this.goofy = goofy;
    this.leerlauf = leerlauf;
    this.schluessel = schluessel;
    const a = { oben: 'albern', unten: 'ernst', links: 'ruhig', rechts: 'lebhaft', ...(achsen || {}) };
    this.achsen = a;
    this.x = 0.55;
    this.y = 0.25;
    this.dragging = false;
    root.classList.add('pad-wrap');
    if (compact) root.classList.add('pad-compact');
    root.innerHTML = `
      <div class="pad-axis pad-top">${a.oben}</div>
      <div class="pad-row">
        <div class="pad-axis pad-left">${a.links}</div>
        <div class="pad" role="group" aria-label="${titel}">
          ${goofy ? '<div class="pad-goofy"><span>Goofy-Bereich</span></div>' : ''}
          <div class="pad-grid"></div>
          <div class="pad-marks"></div>
          <button class="pad-puck" type="button" aria-label=""></button>
        </div>
        <div class="pad-axis pad-right">${a.rechts}</div>
      </div>
      <div class="pad-axis pad-bottom">${a.unten}</div>
      <p class="pad-name"></p>
      <p class="pad-desc"></p>
      <p class="pad-idle"></p>`;
    this.pad = root.querySelector('.pad');
    this.puck = root.querySelector('.pad-puck');
    this.marksEl = root.querySelector('.pad-marks');
    this.nameEl = root.querySelector('.pad-name');
    this.descEl = root.querySelector('.pad-desc');
    this.idleEl = root.querySelector('.pad-idle');
    pads.add(this);
    const at = (e) => {
      const r = this.pad.getBoundingClientRect();
      return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, 1 - (e.clientY - r.top) / r.height))];
    };
    this.at = at;
    this.pad.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      this.dragging = true;
      this.pad.setPointerCapture(e.pointerId);
      this.pad.classList.add('grabbing');
      this.set(...at(e), true);
    });
    this.pad.addEventListener('pointermove', (e) => { if (this.dragging) this.set(...at(e), true); });
    const end = () => {
      if (!this.dragging) return;
      this.dragging = false;
      this.pad.classList.remove('grabbing');
      this.commit();
    };
    this.pad.addEventListener('pointerup', end);
    this.pad.addEventListener('pointercancel', end);
    this.puck.addEventListener('keydown', (e) => {
      const step = e.shiftKey ? 0.15 : 0.05;
      const d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] }[e.key];
      if (!d) return;
      e.preventDefault();
      this.set(this.x + d[0], this.y + d[1], true);
      clearTimeout(this._kbd);
      this._kbd = setTimeout(() => this.commit(), 450);
    });
    this.render();
  }

  set(x, y, local = false) {
    if (this.dragging && !local) return;   // während des Ziehens keine Fremd-Updates
    this.x = Math.min(1, Math.max(0, x));
    this.y = Math.min(1, Math.max(0, y));
    this.render();
  }

  commit() {
    const [ke, kh] = this.schluessel;
    this.onCommit && this.onCommit({ [ke]: Math.round(this.x * 100) / 100, [kh]: Math.round(this.y * 100) / 100 });
  }

  // Weitere Punkte im Feld (bei Knowlin: die Verkörperungen) – mit `onMarke` und `id` zum Ziehen und per Pfeiltasten
  marken(liste) {
    if (this.markeZieht) return;           // während des Ziehens keine Fremd-Updates
    const fokus = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.marke : null;
    this.marksEl.replaceChildren(...(liste || []).map((m) => {
      const ziehbar = !!(this.onMarke && m.id);
      const d = document.createElement(ziehbar ? 'button' : 'span');
      d.className = `pad-mark${m.aktiv ? ' is-aktiv' : ''}`;
      d.textContent = m.name;
      this.markeSetzen(d, m.name, m.x, m.y);
      if (ziehbar) this.markeZiehbar(d, m);
      return d;
    }));
    if (fokus) { const d = this.marksEl.querySelector(`[data-marke="${CSS.escape(fokus)}"]`); if (d) d.focus(); }
  }

  markeSetzen(d, name, x, y) {
    d.style.left = `${Math.min(1, Math.max(0, x)) * 100}%`;
    d.style.top = `${(1 - Math.min(1, Math.max(0, y))) * 100}%`;
    if (d.tagName === 'BUTTON') {
      d.setAttribute('aria-label', `${name}: ${nameIn(NAMES, x, y)}, ${Math.round(x * 100)} Prozent ${this.achsen.rechts}, `
        + `${Math.round(y * 100)} Prozent ${this.achsen.oben}. Ziehen oder mit den Pfeiltasten verschieben.`);
    }
  }

  markeZiehbar(d, m) {
    let pos = [Math.min(1, Math.max(0, m.x)), Math.min(1, Math.max(0, m.y))];
    let zieht = false;
    d.type = 'button';
    d.dataset.marke = m.id;
    const melde = () => this.onMarke(m.id, Math.round(pos[0] * 100) / 100, Math.round(pos[1] * 100) / 100);
    d.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      e.stopPropagation();                  // nicht den Punkt von Knowlin mitziehen
      zieht = true;
      this.markeZieht = true;
      d.setPointerCapture(e.pointerId);
      d.classList.add('is-ziehen');
    });
    d.addEventListener('pointermove', (e) => {
      if (!zieht) return;
      e.stopPropagation();
      pos = this.at(e);
      this.markeSetzen(d, m.name, ...pos);
    });
    const ende = (e) => {
      if (!zieht) return;
      e.stopPropagation();
      zieht = false;
      this.markeZieht = false;
      d.classList.remove('is-ziehen');
      melde();
    };
    d.addEventListener('pointerup', ende);
    d.addEventListener('pointercancel', ende);
    d.addEventListener('keydown', (e) => {
      const step = e.shiftKey ? 0.15 : 0.05;
      const r = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] }[e.key];
      if (!r) return;
      e.preventDefault();
      pos = [Math.min(1, Math.max(0, pos[0] + r[0])), Math.min(1, Math.max(0, pos[1] + r[1]))];
      this.markeSetzen(d, m.name, ...pos);
      clearTimeout(d._kbd);
      d._kbd = setTimeout(melde, 450);
    });
  }

  render() {
    this.puck.style.left = `${this.x * 100}%`;
    this.puck.style.top = `${(1 - this.y) * 100}%`;
    const name = nameIn(this.namen, this.x, this.y);
    this.nameEl.textContent = name;
    this.descEl.textContent = this.texte[name] || '';
    this.idleEl.textContent = this.leerlauf ? idleText(name) : '';
    this.idleEl.hidden = !this.leerlauf;
    this.puck.classList.toggle('goofy', this.goofy && this.y >= 0.5);
    this.puck.setAttribute('aria-label', `${name}: ${Math.round(this.x * 100)} Prozent ${this.achsen.rechts}, `
      + `${Math.round(this.y * 100)} Prozent ${this.achsen.oben}. Mit den Pfeiltasten verschieben.`);
  }
}
