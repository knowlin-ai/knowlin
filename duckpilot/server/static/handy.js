// Handyleiste (seit 0.38.41, Alex: „alles viel zu eng – da bitte schauen, wie andere Apps das lösen“): Unten stehen am
// Handy höchstens vier Bereiche mit vollem Namen und „Mehr“; der Rest (Charakter, System, Knowlin) öffnet sich darüber
// als kleines Menü – wie bei den üblichen Apps. Der Not-Aus bleibt groß und rot rechts daneben.
// Welche Bereiche vorn stehen, folgt einer festen Rangfolge; was der Körper nicht hat (z. B. Umgebung ohne Tiefensensor),
// ist ohnehin ausgeblendet und rückt nach.

const SCHMAL = matchMedia('(max-width: 671.98px)');
const RANG = ['steuern', 'alltag', 'umgebung', 'lernen', 'wissen', 'charakter', 'einstellungen', 'system'];
const VORN = 4;
const PUNKTE = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="1.6" class="fill"/>'
  + '<circle cx="12" cy="12" r="1.6" class="fill"/><circle cx="19" cy="12" r="1.6" class="fill"/></svg>';

export function initHandyLeiste() {
  const rail = document.querySelector('.rail');
  const stopp = rail && rail.querySelector('.rail-stopzone');
  const logo = document.getElementById('rail-start');
  if (!rail || !stopp) return;

  const mehr = document.createElement('button');
  mehr.type = 'button';
  mehr.className = 'rail-btn rail-mehr';
  mehr.id = 'rail-mehr';
  mehr.hidden = true;
  mehr.setAttribute('aria-haspopup', 'menu');
  mehr.setAttribute('aria-expanded', 'false');
  mehr.setAttribute('aria-controls', 'mehr-pop');
  mehr.innerHTML = `${PUNKTE}<span>Mehr</span><b class="rail-dot" hidden></b>`;
  rail.insertBefore(mehr, stopp);

  const pop = document.createElement('div');
  pop.className = 'mehr-pop';
  pop.id = 'mehr-pop';
  pop.setAttribute('role', 'menu');
  pop.setAttribute('aria-label', 'Weitere Bereiche');
  pop.hidden = true;
  document.body.append(pop);

  let hinten = [];
  const sichtbar = (b) => !b.hidden && getComputedStyle(b).display !== 'none';

  function zu(fokus = false) {
    if (pop.hidden) return;
    pop.hidden = true;
    mehr.setAttribute('aria-expanded', 'false');
    if (fokus) mehr.focus();
  }

  function ordnen() {
    for (const b of rail.querySelectorAll('.in-mehr')) b.classList.remove('in-mehr');
    hinten = [];
    if (!SCHMAL.matches) { mehr.hidden = true; zu(); return; }
    const gruppen = [...rail.querySelectorAll('.rail-btn[data-group]')].filter(sichtbar)
      .sort((a, b) => RANG.indexOf(a.dataset.group) - RANG.indexOf(b.dataset.group));
    const mitLogo = logo && sichtbar(logo);
    if (gruppen.length + (mitLogo ? 1 : 0) <= VORN + 1) { mehr.hidden = true; zu(); return; }
    hinten = gruppen.slice(VORN);
    if (mitLogo) hinten.push(logo);
    for (const b of hinten) b.classList.add('in-mehr');
    mehr.hidden = false;
    const aktiv = hinten.some((b) => b.getAttribute('aria-current') === 'page');
    mehr.classList.toggle('ist-aktiv', aktiv);
    mehr.querySelector('.rail-dot').hidden = !hinten.some((b) => [...b.querySelectorAll('.rail-dot, .rail-count')]
      .some((d) => !d.hidden));
  }

  function auf() {
    pop.replaceChildren(...hinten.map((b) => {
      const e = document.createElement('button');
      e.type = 'button';
      e.className = 'mehr-eintrag';
      e.setAttribute('role', 'menuitem');
      const svg = b.querySelector('svg, img');
      const name = (b.querySelector('span') || b).textContent.trim();
      if (svg) e.append(svg.cloneNode(true));
      e.append(Object.assign(document.createElement('span'), { textContent: name }));
      if (b.getAttribute('aria-current') === 'page') e.setAttribute('aria-current', 'page');
      e.addEventListener('click', () => { zu(); b.click(); });
      return e;
    }));
    pop.hidden = false;
    mehr.setAttribute('aria-expanded', 'true');
    const erster = pop.querySelector('[aria-current]') || pop.firstElementChild;
    if (erster) erster.focus();
  }

  mehr.addEventListener('click', () => (pop.hidden ? auf() : zu(true)));
  pop.addEventListener('keydown', (ev) => {
    const eintraege = [...pop.children];
    const i = eintraege.indexOf(document.activeElement);
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      ev.preventDefault();
      const n = eintraege.length;
      eintraege[(i + (ev.key === 'ArrowDown' ? 1 : n - 1)) % n].focus();
    } else if (ev.key === 'Tab') {
      zu();
    }
  });
  // Esc schließt das Menü – der Not-Aus auf Esc bleibt davon unberührt (er hört auf dem Dokument)
  document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape') zu(true); });
  document.addEventListener('pointerdown', (ev) => {
    if (!pop.hidden && !pop.contains(ev.target) && !mehr.contains(ev.target)) zu();
  });

  const beobachter = new MutationObserver((liste) => {
    if (liste.some((m) => !mehr.contains(m.target))) ordnen();
  });
  beobachter.observe(rail, { subtree: true, attributes: true, attributeFilter: ['hidden', 'aria-current'] });
  beobachter.observe(document.body, { attributes: true, attributeFilter: ['class'] });
  SCHMAL.addEventListener('change', ordnen);
  ordnen();
  vorleseKnopf();
}

// „Antworten vorlesen“ als Knopf neben der Eingabe (am Handy); er schaltet dasselbe Häkchen wie am PC
function vorleseKnopf() {
  const knopf = document.getElementById('say-laut');
  const haken = document.getElementById('opt-tts');
  if (!knopf || !haken) return;
  const zeigen = () => knopf.setAttribute('aria-pressed', String(haken.checked));
  knopf.addEventListener('click', () => {
    haken.checked = !haken.checked;
    haken.dispatchEvent(new Event('change', { bubbles: true }));
    zeigen();
  });
  haken.addEventListener('change', zeigen);
  haken.addEventListener('input', zeigen);      // app.js setzt das Häkchen auch ohne Klick
  zeigen();
  // Ohne sichere Verbindung (Handy übers WLAN) gibt es keine Sprechtaste: diktiert wird über die Handy-Tastatur
  const feld = document.getElementById('say-text');
  if (feld && !window.isSecureContext) feld.placeholder = 'Schreiben oder diktieren …';
}
