// Wo du sitzt (seit 0.50, „Aufmerksamkeit suchen“): Die Kamera der 3D-Ansicht steht für dich vor dem Bildschirm. Alle
// 5 s, solange das Fenster sichtbar ist und die Kamera beobachtet (nicht durch ihre Augen schaut), geht ihr Punkt auf
// dem Boden an Knowlin – zwei Zahlen, kein Bild. Ohne offenes Fenster sucht sie keine Aufmerksamkeit.
export function initBetrachter(scene, send) {
  if (!scene || !scene.camera) return;
  setInterval(() => {
    if (document.visibilityState !== 'visible' || scene.mode !== 'beobachten') return;
    const p = scene.camera.position;
    if (!Number.isFinite(p.x) || !Number.isFinite(p.z)) return;
    send({ type: 'betrachter', x: Math.round(p.x * 100) / 100, y: Math.round(-p.z * 100) / 100 });
  }, 5000);
}
