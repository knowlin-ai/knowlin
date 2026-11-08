// Aussehen mit Vorschaubildern (seit 0.38.26, Hinweis „bei Aussehen ist eine riesen freie Kachel – dann mach doch
// da bei der Farbauswahl Vorschaubilder rein“): Jede Farbe zeigt die eigene Figur in dieser Farbe, im eigenen Zimmer.
// Die Bilder entstehen hier im Browser aus dem Modell, das gerade auf der Bühne steht – Pollens Modell wird nie als Bild
// mitgeliefert. Gezeichnet wird, sobald die Kachel sichtbar wird, und neu, wenn eine andere Figur geladen ist.
import * as THREE from './vendor/three.module.min.js';

const GROSS = 480;           // gerendert doppelt so groß, dann weich verkleinert (Kanten ohne Treppen)

export function initAussehen({ $, scene }) {
  const karte = $('aussehen');
  const bilder = karte ? [...karte.querySelectorAll('canvas.farbbild')] : [];
  if (!bilder.length || !scene || !scene.renderer) return;
  const cam = new THREE.PerspectiveCamera(28, 1, 0.01, 20);
  const zwischen = document.createElement('canvas');
  zwischen.width = zwischen.height = GROSS;
  let gezeichnetFuer = null;

  function zeichnen() {
    const fig = scene.duck;
    if (!fig || !fig.root) return;
    const r = scene.renderer, p = fig.root.position;
    const h = scene._figurHoehe ? scene._figurHoehe() : 0.26;
    const yaw = ((scene.state && scene.state.yaw) || 0) - 0.65;             // leicht von vorn-seitlich
    cam.position.set(p.x + Math.cos(yaw) * h * 3.3, p.y + h * 0.78, p.z - Math.sin(yaw) * h * 3.3);
    cam.lookAt(p.x, p.y + h * 0.5, p.z);
    const rt = new THREE.WebGLRenderTarget(GROSS, GROSS);
    rt.texture.colorSpace = THREE.SRGBColorSpace;
    const puffer = new Uint8Array(GROSS * GROSS * 4);
    // Nur die Figur auf ihrem Boden: Möbel und Wände blendet das Bild aus – sonst stand sie je nach Platz hinter dem
    // Blumentopf (gemeldet nach 0.38.32: „wieso steht sie hier verdeckt?“)
    // Alles andere aus: Möbel, Wände, Dinge, weitere Enten, Strahlen, Karte – nur Licht, Himmel und Boden bleiben
    const licht = (o) => { let ja = false; o.traverse((k) => { if (k.isLight) ja = true; }); return ja; };
    const welt = scene.worldGroup ? scene.worldGroup.children.filter((o) => o !== scene.bodenGruppe) : [];
    // auch die Himmelskuppel: hinter dem Bodenende schien ihre dunkle, kantige Unterseite durch – dafür einfarbig
    const weg = [...scene.scene.children.filter((o) => o !== fig.root && o !== scene.worldGroup && !licht(o)), ...welt];
    const vorherKlar = r.getClearColor(new THREE.Color()), vorherAlpha = r.getClearAlpha();
    const flaeche = getComputedStyle(document.documentElement).getPropertyValue('--surface-2').trim() || '#2a2c31';
    const sichtbar = weg.map((o) => o.visible);
    weg.forEach((o) => { o.visible = false; });
    const merkFarbe = scene.farbe || 'cream', vorher = r.getRenderTarget();
    const zctx = zwischen.getContext('2d'), bild = zctx.createImageData(GROSS, GROSS);
    try {
      r.setClearColor(new THREE.Color(flaeche).convertSRGBToLinear(), 1);
      for (const c of bilder) {
        scene.setFarbe(c.dataset.farbe);
        r.setRenderTarget(rt);
        r.render(scene.scene, cam);
        r.readRenderTargetPixels(rt, 0, 0, GROSS, GROSS, puffer);
        for (let y = 0; y < GROSS; y++) {                                    // WebGL liest von unten nach oben
          bild.data.set(puffer.subarray((GROSS - 1 - y) * GROSS * 4, (GROSS - y) * GROSS * 4), y * GROSS * 4);
        }
        zctx.putImageData(bild, 0, 0);
        const ctx = c.getContext('2d');
        ctx.imageSmoothingQuality = 'high';
        ctx.drawImage(zwischen, 0, 0, c.width, c.height);
      }
      gezeichnetFuer = fig;
    } finally {
      r.setRenderTarget(vorher);
      r.setClearColor(vorherKlar, vorherAlpha);
      scene.setFarbe(merkFarbe);
      weg.forEach((o, i) => { o.visible = sichtbar[i]; });
      rt.dispose();
    }
  }

  const beobachter = new IntersectionObserver((eintraege) => {
    if (eintraege.some((e) => e.isIntersecting) && gezeichnetFuer !== scene.duck) requestAnimationFrame(zeichnen);
  });
  beobachter.observe(karte);
}
