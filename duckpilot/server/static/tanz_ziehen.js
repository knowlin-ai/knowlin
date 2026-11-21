// Choreografie zum Ziehen (seit 0.51): Tänze direkt in der Zeitleiste bauen.
// - Bewegungen, Gefühle und Posen aus der Palette in die Zeitleiste ziehen (oder antippen: kommt an die Startmarke)
// - Blöcke in der Zeitleiste verschieben (rasten auf Takte ein; die anderen rücken nach)
// - am rechten Rand ziehen: länger oder kürzer (1–64 Takte)
// - Block anklicken und Entf: löschen; „Ab Marke proben“ spielt ab der Stelle (anhören)
// Die Schritte bleiben lückenlos hintereinander wie bisher (tanz.js `neuTakten`), der Server prüft wie immer (choreo.py).

export const RAND_PX = 7;          // so nah am rechten Rand eines Blocks zieht man die Länge

/** Index, an dem ein Block landet, der zur Zeit t abgelegt wird: vor dem ersten Schritt, dessen Mitte danach liegt. */
export function zielIndex(schritte, t, taktS) {
  for (let i = 0; i < schritte.length; i++) {
    const s = schritte[i];
    if (t < s.t + (s.takte * taktS) / 2) return i;
  }
  return schritte.length;
}

export function verschieben(schritte, von, nach) {
  const liste = [...schritte];
  const [s] = liste.splice(von, 1);
  liste.splice(nach > von ? nach - 1 : nach, 0, s);
  return liste;
}

export function einfuegen(schritte, schritt, an) {
  const liste = [...schritte];
  liste.splice(Math.max(0, Math.min(an, liste.length)), 0, schritt);
  return liste;
}

/** Welcher Block liegt unter dem Zeiger? Gleiche Spuren wie die Zeichnung in tanz.js (Bewegung oben, Pose/Gefühl unten). */
export function treffer(schritte, px, py, x, taktS) {
  for (let i = 0; i < schritte.length; i++) {
    const s = schritte[i];
    const unten = s.art === 'pose' || s.art === 'gefuehl';
    const y = unten ? 112 : 78;
    const a = x(s.t), b = x(s.t + s.takte * taktS);
    if (py >= y && py <= y + 28 && px >= a && px <= b) return { i, rand: b - px <= RAND_PX };
  }
  return null;
}

/**
 * Verdrahtet die Zeitleiste. `z` liefert den Zustand und schreibt zurück:
 * { choreo(), laenge(), taktS(), schritte(neu), neuTakten(), zeichnen(vorschau), markeSetzen(t), standard(art) }.
 */
export function initZiehen(leinwand, palette, z) {
  if (!leinwand) return { palette() {} };
  let zug = null;                  // {i, rand, x0, takte0}
  let gewaehlt = -1;
  let gezogen = false;
  const zeit = (clientX) => {
    const r = leinwand.getBoundingClientRect();
    return Math.max(0, ((clientX - r.left) / r.width) * z.laenge());
  };
  const xVon = () => { const w = leinwand.clientWidth; const L = z.laenge(); return (t) => (t / L) * w; };

  leinwand.tabIndex = 0;
  leinwand.addEventListener('pointerdown', (ev) => {
    const c = z.choreo();
    if (!c) return;
    const r = leinwand.getBoundingClientRect();
    const hit = treffer(c.schritte, ev.clientX - r.left, ev.clientY - r.top, xVon(), z.taktS());
    gezogen = false;
    if (!hit) { gewaehlt = -1; return; }
    gewaehlt = hit.i;
    zug = { i: hit.i, rand: hit.rand, x0: ev.clientX, takte0: c.schritte[hit.i].takte };
    leinwand.setPointerCapture(ev.pointerId);
    z.zeichnen({ gewaehlt });
  });
  leinwand.addEventListener('pointermove', (ev) => {
    const c = z.choreo();
    if (!c) return;
    if (!zug) {
      const r = leinwand.getBoundingClientRect();
      const hit = treffer(c.schritte, ev.clientX - r.left, ev.clientY - r.top, xVon(), z.taktS());
      leinwand.style.cursor = hit ? (hit.rand ? 'ew-resize' : 'grab') : '';
      return;
    }
    if (Math.abs(ev.clientX - zug.x0) > 4) gezogen = true;
    if (!gezogen) return;
    if (zug.rand) {
      const takte = Math.max(1, Math.min(64, zug.takte0 + Math.round((zeit(ev.clientX) - zeit(zug.x0)) / z.taktS())));
      if (takte !== c.schritte[zug.i].takte) { c.schritte[zug.i].takte = takte; z.neuTakten(); }
    } else {
      z.zeichnen({ gewaehlt, geist: { i: zug.i, t: zeit(ev.clientX) } });
    }
  });
  const loslassen = (ev) => {
    const c = z.choreo();
    if (!zug || !c) { zug = null; return; }
    if (gezogen && !zug.rand) {
      const nach = zielIndex(c.schritte, zeit(ev.clientX), z.taktS());
      if (nach !== zug.i && nach !== zug.i + 1) {
        z.schritte(verschieben(c.schritte, zug.i, nach));
        gewaehlt = nach > zug.i ? nach - 1 : nach;
      }
      z.neuTakten();
    }
    zug = null;
    z.zeichnen({ gewaehlt });
  };
  leinwand.addEventListener('pointerup', loslassen);
  leinwand.addEventListener('pointercancel', () => { zug = null; z.zeichnen({ gewaehlt }); });
  // Ein Klick ohne Ziehen setzt weiter die Startmarke (tanz.js); nach dem Ziehen nicht
  leinwand.addEventListener('click', (ev) => { if (gezogen) { ev.stopImmediatePropagation(); gezogen = false; } }, true);
  leinwand.addEventListener('keydown', (ev) => {
    const c = z.choreo();
    if (!c || gewaehlt < 0 || gewaehlt >= c.schritte.length) return;
    if (ev.key === 'Delete' || ev.key === 'Backspace') {
      ev.preventDefault();
      z.schritte(c.schritte.filter((_, k) => k !== gewaehlt));
      gewaehlt = -1;
      z.neuTakten();
    } else if (ev.key === 'ArrowLeft' || ev.key === 'ArrowRight') {
      ev.preventDefault();
      const nach = ev.key === 'ArrowLeft' ? gewaehlt - 1 : gewaehlt + 2;
      if (nach < 0 || nach > c.schritte.length) return;
      z.schritte(verschieben(c.schritte, gewaehlt, nach));
      gewaehlt = ev.key === 'ArrowLeft' ? gewaehlt - 1 : gewaehlt + 1;
      z.neuTakten();
      z.zeichnen({ gewaehlt });
    }
  });

  // Palette: ziehen (HTML-Drag) oder antippen
  leinwand.addEventListener('dragover', (ev) => ev.preventDefault());
  leinwand.addEventListener('drop', (ev) => {
    ev.preventDefault();
    const c = z.choreo();
    const art = ev.dataTransfer.getData('text/plain');
    if (!c || !art) return;
    const an = zielIndex(c.schritte, zeit(ev.clientX), z.taktS());
    z.schritte(einfuegen(c.schritte, z.standard(art), an));
    gewaehlt = an;
    z.neuTakten();
  });
  function paletteZeigen(arten, text) {
    if (!palette) return;
    palette.replaceChildren(...arten.map((art) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = `tanz-chip tanz-chip--${art}`;
      b.textContent = text(art);
      b.draggable = true;
      b.addEventListener('dragstart', (ev) => ev.dataTransfer.setData('text/plain', art));
      b.addEventListener('click', () => {              // antippen: an die Startmarke
        const c = z.choreo();
        if (!c) return;
        const an = zielIndex(c.schritte, z.marke(), z.taktS());
        z.schritte(einfuegen(c.schritte, z.standard(art), an));
        gewaehlt = an;
        z.neuTakten();
      });
      return b;
    }));
  }
  return { palette: paletteZeigen, gewaehlt: () => gewaehlt };
}
