// Designsystem-Galerie (System → Über → Designsystem): Tokens, Raster und Bausteine live aus denselben Klassen.
// Ausgelagert aus app.js (0.33).

export function initDesignsystem({ $, el, css }) {
  let galleryDone = false;
  function renderGallery() {
    if (galleryDone) return;
    galleryDone = true;
    const root = $('ds-gallery');
    const sec = (title, text) => {
      const s = el('section', 'ds-section');
      const h = el('div', 'section-head');
      h.append(el('h3', null, title));
      if (text) h.append(el('p', null, text));
      s.append(h);
      root.append(s);
      return s;
    };
    const head = el('header', 'page-head');
    head.append(el('h2', null, 'Designsystem'), el('p', null,
      'IBM Carbon mit dem Theme Gray 90 als Grundlage: neutrale, sehr dunkle Graustufen in Ebenen und IBM Plex. ' +
      'Darüber die Knowlin-Ebene: alles flach mit feiner Kontur statt Schatten, das Schnabel-Orange als einziger Akzent, die weichsten Formen dort, wo die Ente selbst agiert.'));
    root.append(head);
    const swatch = (name, varName, note) => {
      const d = el('div', 'swatch');
      const i = el('i');
      i.style.background = `var(${varName})`;
      const t = el('div');
      t.append(el('b', null, name), el('span', null, `${varName}  ${css(varName)}`));
      if (note) t.append(el('span', null, note));
      d.append(i, t);
      return d;
    };
    const colors = sec('Farben', 'Carbon-Rollen statt Töne: jede Farbe hat eine Aufgabe. Orange nur für die Hauptaktion, Auswahl und das Sprechen der Ente; der Tastaturfokus ist weiß, der Feldfokus blau.');
    const g1 = el('div', 'swatches');
    [['Grund', '--surface-0', '$background'], ['Ebene 1', '--surface-1', '$layer-01'], ['Ebene 2', '--surface-2', '$layer-02'], ['Darüber', '--surface-hover', '$layer-hover-01'], ['Feld', '--field', '$field-01'],
      ['Linie', '--line'], ['Linie stark', '--line-strong'], ['Text', '--ink'], ['Text leise', '--ink-2'], ['Hilfetext', '--ink-3'], ['Link', '--link'], ['Fokus', '--focus'],
      ['Ente (Akzent)', '--accent', 'Hauptaktion, Auswahl'], ['Messwert', '--data-1', 'gemessen, angewendet'], ['Sollwert', '--data-2', 'verlangt'],
      ['gut', '--good'], ['Warnung', '--warning'], ['ernst', '--serious'], ['kritisch', '--critical', 'Sturz'], ['Gefahr', '--danger', 'Stopp']].forEach(([n, v, note]) => g1.append(swatch(n, v, note)));
    colors.append(g1);

    const type = sec('Schrift', 'IBM Plex Sans und Plex Mono für Messwerte. Carbon-Typografie: große Überschriften leicht (300), Text normal, Beschriftungen halbfett. Zahlen immer tabellarisch.');
    const ts = el('div', 'type-scale');
    [['heading-07 · 54', 't-display', 'steht'], ['heading-06 · 42', 't-display-m', 'läuft zum Ball'], ['heading-04 · 28', 't-h1', 'Was sich die Ente gemerkt hat'],
      ['heading-03 · 20', 't-h2', 'Pollens Emotionen'], ['heading-02 · 16', 't-h3', 'Persönlichkeit'], ['body-01 · 14', '', 'Sag der Ente, was sie tun soll. Sie versteht freie Sprache.'],
      ['label-01 · 12', 't-caption', 'Gespeichert im Datenordner'], ['Mono · 12', 't-caption t-mono', 'x 0,42 m  y −0,18 m  31°']]
      .forEach(([label, cls, text]) => {
        const r = el('div', 'type-row');
        r.append(el('span', null, label), el('p', cls, text));
        ts.append(r);
      });
    type.append(ts);

    const space = sec('Abstand, Radien, Ebenen', 'Carbon-Abstände spacing-01 bis -13, mit Carbons Namen und Werten. Radien nach Rang: Bedienelemente 6 px, Kacheln 8 px, schwebende Flächen 10 px; was zur Ente gehört – Gesten, Gesprächsblasen, Sprechtaste, Persönlichkeit – 14 px. Ebenen entstehen aus Grauwert und feiner Kontur, ohne Schatten.');
    const sp = el('div', 'spacing');
    for (let i = 1; i <= 13; i++) {
      const name = `--spacing-${String(i).padStart(2, '0')}`;
      const d = el('div');
      const bar = el('i');
      bar.style.height = `var(${name})`;
      d.append(bar, el('span', null, `${name.slice(2)} · ${css(name)}`));
      sp.append(d);
    }
    space.append(sp);
    const ev = el('div', 'elev');
    ev.style.marginTop = 'var(--spacing-06)';
    [['Kachel – feine Kontur', '--e-1'], ['HUD – Kontur über der 3D-Ansicht', '--e-2'], ['Popover – deutlichere Kontur', '--e-3']].forEach(([n, v]) => {
      const d = el('div', null, n);
      d.style.boxShadow = `var(${v})`;
      ev.append(d);
    });
    space.append(ev);

    // Raster: aus denselben Klassen gebaut wie die Seiten – zeigt live, wie viele Spalten gerade gelten
    const raster = sec('Raster', 'Carbons 2x Grid für alle Seiten: 16 Spalten ab 1056 px Fensterbreite (lg), 8 ab 672 px (md), darunter 4. ' +
      'Abstand 16 px, Rand 32 px (auf dem Handy 16 px). Es wächst fließend bis 1584 px und steht darüber mittig. ' +
      'Kacheln belegen ganze Spalten, darum sitzen ihre Kanten auf jeder Seite auf denselben Linien.');
    const cols = el('div', 'grid ds-cols');
    cols.setAttribute('aria-hidden', 'true');
    for (let i = 1; i <= 16; i++) cols.append(el('i', null, String(i)));
    raster.append(cols);
    const pattern = (label, cls, parts) => {
      const g = el('div', `grid ds-pattern ${cls}`);
      parts.forEach(([text, c]) => g.append(el('div', c || null, text)));
      const w = el('div', 'ds-pattern-row');
      w.append(el('span', 't-caption', label), g);
      raster.append(w);
    };
    pattern('Hälften – 8 / 4 / 4', 'grid--halves', [['Hälfte'], ['Hälfte']]);
    pattern('Kacheln – 4 / 4 / 4', 'grid--tiles', [['Kachel'], ['Kachel'], ['Kachel'], ['Kachel']]);
    pattern('Haupt + Seite – 10 + 6, darunter übereinander', '', [['Hauptfläche', 'g-main'], ['Seite', 'g-side']]);

    const comps = sec('Bausteine', 'Alle Zustände nebeneinander: normal, darüber, gedrückt, Fokus, aus.');
    const row = (label, items) => {
      const r = el('div', 'ds-row');
      r.append(el('span', null, label), ...items);
      comps.append(r);
    };
    const btn = (text, cls, state) => {
      const b = el('button', `btn ${cls}${state ? ' ' + state : ''}`, text);
      b.type = 'button';
      if (state === 'disabled') { b.disabled = true; b.classList.remove('disabled'); }
      return b;
    };
    for (const [label, cls] of [['Primär', 'btn--primary'], ['Sekundär', ''], ['Tertiär', 'btn--tertiary'], ['Leise', 'btn--ghost'], ['Gefahr', 'btn--danger']]) {
      row(label, [btn('Speichern', cls), btn('Darüber', cls, 'is-hover'), btn('Gedrückt', cls, 'is-active'), btn('Fokus', cls, 'is-focus'), btn('Aus', cls, 'disabled'), btn('Lädt', cls, 'is-busy')]);
    }
    row('Größen', [btn('Klein', 'btn--sm'), btn('Mittel', ''), btn('Groß', 'btn--lg btn--accent')]);
    const stopDemo = (live, label) => {
      const w = el('div', 'ds-stop');
      const b = $('stop').cloneNode(true);
      b.removeAttribute('id'); b.classList.toggle('live', live); b.tabIndex = -1;
      w.append(b, el('span', 't-caption', label));
      return w;
    };
    row('Not-Aus', [stopDemo(false, 'bereit'), stopDemo(true, 'Ente aktiv – Ring leuchtet')]);
    const chips = ['Simulator', 'offiziell', 'vorgemerkt', 'auf der Ente'].map((t, i) => el('span', ['chip', 'chip chip--accent', 'chip chip--data', 'chip chip--solid-accent'][i], t));
    const status = el('span', 'chip');
    status.append(el('i', 'dot dot--good'), el('span', null, 'verbunden'));
    const pressed = el('button', 'chip', 'gewählt');
    pressed.setAttribute('aria-pressed', 'true');
    row('Chips', [...chips, status, pressed]);
    // Klickbar – gewählt – scharf: die drei Zustände, die man nie verwechseln darf
    const zustand = (text, cls, attr) => { const b = btn(text, cls); if (attr) b.setAttribute('aria-pressed', 'true'); return b; };
    row('Zustände', [zustand('klickbar', ''), zustand('gewählt', '', true), zustand('scharf – klick auf den Boden', 'is-armed')]);
    const inp = (ph, state, val) => {
      const i = el('input', `input${state ? ' ' + state : ''}`);
      i.placeholder = ph; if (val) i.value = val; i.style.maxWidth = '200px';
      if (state === 'disabled') i.disabled = true;
      if (state === 'invalid') i.setAttribute('aria-invalid', 'true');
      return i;
    };
    row('Felder', [inp('Normal'), inp('Darüber', 'is-hover'), inp('Fokus', 'is-focus'), inp('Fehler', 'invalid', 'tcp:7900'), inp('Aus', 'disabled')]);
    const sw = (on, dis) => {
      const l = el('label', 'switch');
      const c = el('input');
      c.type = 'checkbox'; c.checked = on; c.disabled = !!dis;
      l.append(c, el('span', null, dis ? 'gesperrt' : on ? 'an' : 'aus'));
      return l;
    };
    const seg = el('div', 'seg');
    seg.style.minWidth = '260px';
    ['Online', 'Lokal', 'Aus'].forEach((t, i) => {
      const l = el('label');
      const r = el('input');
      r.type = 'radio'; r.name = 'ds-seg'; r.checked = i === 1;
      l.append(r, el('span', null, t));
      seg.append(l);
    });
    row('Auswahl', [sw(true), sw(false), sw(true, true), seg]);
    const range = el('input', 'range');
    range.type = 'range'; range.value = 60; range.setAttribute('aria-label', 'Beispielregler'); range.style.maxWidth = '240px'; range.style.setProperty('--_fill', '60%');
    range.addEventListener('input', () => range.style.setProperty('--_fill', `${range.value}%`));
    row('Regler', [range]);
    const t1 = el('span', 'toast toast--static', 'Gespeichert');
    const t2 = el('span', 'toast toast--bad toast--static', 'Nicht geladen');
    row('Meldungen', [t1, t2]);
    const cards = el('div', 'ds-grid2');
    const c1 = el('article', 'card');
    c1.append(el('h3', 't-h3', 'Karte'), el('p', 't-small t-muted', 'Carbon-Kachel auf Ebene 1, flach mit feiner Kontur. Für alles, was zusammengehört.'));
    const c2 = el('article', 'card card--accent');
    c2.append(el('h3', 't-h3', 'Karte mit Akzent'), el('p', 't-small t-muted', 'Nur für das eine, das jetzt wichtig ist – etwa die Einrichtung.'));
    const c3 = el('div', 'empty');
    c3.append(el('p', null, 'Leerer Zustand'), el('span', 't-caption', 'Sagt, was als Nächstes zu tun ist.'));
    cards.append(c1, c2, c3);
    comps.append(cards);
  }
  return { render: renderGallery };
}
