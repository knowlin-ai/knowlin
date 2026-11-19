// Avatare für Stack-chans Bildschirm (seit 0.39, „wie ab Werk“): neben dem Standardgesicht drei eigene Gesichter –
// Kulleraugen, Pixel und Katze. Alle zeigen dieselben Ausdrücke (froh, traurig, überrascht, wütend, müde, neugierig,
// verlegen, schwindelig), sprechen mit dem Mund und blinzeln. Eigene Entwürfe von Knowlin, je Verkörperung gewählt
// (Einstellung `avatar`, kommt als `st.gesicht.avatar`). Gezeichnet auf schwarzem Grund wie das Standardgesicht.

export const AVATARE = ['standard', 'kulleraugen', 'pixel', 'katze'];

const WEISS = '#fff';
const SCHWARZ = '#000';
const WANGE = '#e8707a';

function grund(ctx, w, h) {
  ctx.fillStyle = SCHWARZ;
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = ctx.strokeStyle = WEISS;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
}

// Mund für alle: offen beim Sprechen/Staunen, Bogen bei froh/traurig, Welle bei schwindelig, sonst Strich
function mund(ctx, { a, m }, mx, my, breit, dicke = 4) {
  const offen = Math.max(0, Math.min(1, m));
  ctx.lineWidth = dicke;
  ctx.beginPath();
  if (offen > 0.08 || a === 'ueberrascht') {
    const hh = Math.max(offen, a === 'ueberrascht' ? 0.5 : 0) * 14 + 3;
    ctx.ellipse(mx, my, breit * 0.45, hh, 0, 0, Math.PI * 2);
    ctx.fill();
  } else if (a === 'froh') {
    ctx.arc(mx, my - 8, breit * 0.55, Math.PI * 0.2, Math.PI * 0.8);
    ctx.stroke();
  } else if (a === 'traurig') {
    ctx.arc(mx, my + 10, breit * 0.5, Math.PI * 1.25, Math.PI * 1.75);
    ctx.stroke();
  } else if (a === 'schwindelig') {
    for (let i = 0; i <= 20; i++) {
      const px = mx - breit / 2 + i * breit / 20, py = my + 3 * Math.sin(i / 20 * Math.PI * 4);
      if (i) ctx.lineTo(px, py); else ctx.moveTo(px, py);
    }
    ctx.stroke();
  } else {
    ctx.moveTo(mx - breit / 2, my); ctx.lineTo(mx + breit / 2, my);
    ctx.stroke();
  }
}

function wangen(ctx, w, y, abstand) {
  ctx.fillStyle = WANGE;
  for (const s of [-1, 1]) { ctx.beginPath(); ctx.ellipse(w / 2 + s * abstand, y, 9, 4.5, 0, 0, Math.PI * 2); ctx.fill(); }
  ctx.fillStyle = WEISS;
}

// Kulleraugen: große runde Augen mit Pupille und Glanzpunkt, die Pupillen folgen dem Blick
function kulleraugen(ctx, f, w, h) {
  grund(ctx, w, h);
  const { a, auf, bx, by } = f;
  const y = h * 0.42, r = a === 'ueberrascht' ? 22 : 19;
  for (const s of [-1, 1]) {
    const x = w / 2 + s * w * 0.23;
    ctx.beginPath();
    if (a === 'froh' && auf > 0.2) {
      ctx.lineWidth = 6; ctx.arc(x, y + 6, r * 0.8, Math.PI * 1.15, Math.PI * 1.85); ctx.stroke();
      continue;
    }
    if (auf < 0.25 || a === 'muede') {
      ctx.lineWidth = 5; ctx.arc(x, y - 4, r * 0.8, Math.PI * 0.15, Math.PI * 0.85); ctx.stroke();
      continue;
    }
    ctx.ellipse(x, y, r, r * auf, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = SCHWARZ;
    const pr = a === 'schwindelig' ? r * 0.35 : r * 0.55;
    const px = x + bx * r * 0.35 + (a === 'schwindelig' ? s * 4 : 0), py = y + by * r * 0.35 * auf;
    ctx.beginPath(); ctx.ellipse(px, py, pr, pr * auf, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = WEISS;
    ctx.beginPath(); ctx.arc(px - pr * 0.35, py - pr * 0.4 * auf, pr * 0.28, 0, Math.PI * 2); ctx.fill();
    if (a === 'wuetend' || a === 'traurig') {              // Braue
      const innen = a === 'wuetend' ? 1 : -1;
      ctx.lineWidth = 5; ctx.beginPath();
      ctx.moveTo(x - s * r, y - r - 6 - innen * 4); ctx.lineTo(x + s * r * 0.2, y - r - 6 + innen * 4); ctx.stroke();
    }
  }
  if (a === 'verlegen') wangen(ctx, w, y + 26, w * 0.3);
  mund(ctx, f, w / 2, h * 0.8, 22);
}

// Pixel: grobe Blöcke wie ein kleiner Bildschirm auf 16 × 12 Feldern
function pixel(ctx, f, w, h) {
  grund(ctx, w, h);
  const z = w / 16;
  const block = (cx, cy, bw = 1, bh = 1) => ctx.fillRect(Math.round(cx * z), Math.round(cy * z), Math.ceil(bw * z) - 1, Math.ceil(bh * z) - 1);
  const { a, auf, bx } = f;
  const dx = Math.round(bx);
  for (const x0 of [3, 11]) {
    const x = x0 + dx;
    if (a === 'froh' && auf > 0.2) { block(x - 1, 5); block(x, 4); block(x + 1, 5); }
    else if (auf < 0.25 || a === 'muede') { block(x - 1, 5, 3, 1); }
    else if (a === 'schwindelig') { block(x - 1, 3); block(x + 1, 3); block(x, 4); block(x - 1, 5); block(x + 1, 5); }
    else if (a === 'ueberrascht') { block(x - 1, 3, 3, 3); }
    else {
      block(x - 1, 3 + (a === 'wuetend' || a === 'traurig' ? 1 : 0), 2, a === 'wuetend' || a === 'traurig' ? 2 : 3);
      if (a === 'neugierig' && x0 === 11) block(x + 1, 3, 1, 3);
    }
  }
  if (a === 'verlegen') { ctx.fillStyle = WANGE; block(2, 7, 2, 1); block(12, 7, 2, 1); ctx.fillStyle = WEISS; }
  const offen = Math.max(0, Math.min(1, f.m));
  if (offen > 0.08 || a === 'ueberrascht') block(7, 8, 2, 1 + Math.round(Math.max(offen, 0.5) * 2));
  else if (a === 'froh') { block(6, 8); block(7, 9, 2, 1); block(9, 8); }
  else if (a === 'traurig') { block(6, 9); block(7, 8, 2, 1); block(9, 9); }
  else block(6, 9, 4, 1);
}

// Katze: Mandelaugen, ω-Mund, Schnurrhaare und zwei Ohrenspitzen oben
function katze(ctx, f, w, h) {
  grund(ctx, w, h);
  const { a, auf, bx } = f;
  ctx.beginPath();                                          // Ohren
  for (const s of [-1, 1]) {
    const x = w / 2 + s * w * 0.3;
    ctx.moveTo(x - 12, 14); ctx.lineTo(x + s * 4, 2); ctx.lineTo(x + 12, 14);
  }
  ctx.lineWidth = 3; ctx.stroke();
  const y = h * 0.42;
  for (const s of [-1, 1]) {
    const x = w / 2 + s * w * 0.22 + bx * 6;
    ctx.beginPath();
    if (a === 'froh' && auf > 0.2) { ctx.lineWidth = 5; ctx.arc(x, y + 5, 12, Math.PI * 1.15, Math.PI * 1.85); ctx.stroke(); continue; }
    if (auf < 0.25 || a === 'muede') { ctx.lineWidth = 4; ctx.moveTo(x - 12, y + 2); ctx.lineTo(x + 12, y + 2); ctx.stroke(); continue; }
    const hoch = (a === 'ueberrascht' ? 13 : 9) * auf;
    ctx.ellipse(x, y, 14, hoch, s * (a === 'wuetend' ? 0.25 : a === 'traurig' ? -0.25 : 0), 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = SCHWARZ;                                 // Schlitzpupille
    ctx.beginPath(); ctx.ellipse(x + bx * 3, y, a === 'ueberrascht' ? 5 : 2.2, hoch * 0.9, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = WEISS;
  }
  ctx.lineWidth = 2;                                         // Schnurrhaare
  ctx.beginPath();
  for (const s of [-1, 1]) for (const d of [-5, 3]) { ctx.moveTo(w / 2 + s * 24, h * 0.68 + d / 2); ctx.lineTo(w / 2 + s * 52, h * 0.66 + d); }
  ctx.stroke();
  if (a === 'verlegen') wangen(ctx, w, y + 22, w * 0.28);
  const offen = Math.max(0, Math.min(1, f.m));
  if (offen > 0.08 || a === 'ueberrascht' || a === 'traurig' || a === 'schwindelig') { mund(ctx, f, w / 2, h * 0.74, 18, 3); return; }
  ctx.lineWidth = 3; ctx.beginPath();                        // ω
  ctx.arc(w / 2 - 6, h * 0.7, 6, 0, Math.PI);
  ctx.moveTo(w / 2 + 12, h * 0.7); ctx.arc(w / 2 + 6, h * 0.7, 6, 0, Math.PI);
  ctx.stroke();
}

export const ZEICHNER = { kulleraugen, pixel, katze };
