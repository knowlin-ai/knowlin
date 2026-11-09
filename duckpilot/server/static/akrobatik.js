// Seite „Akrobatik“ (Lernen → Akrobatik): die Ente als Gliederpuppe. Gelenkpunkt antippen, dann an den Drehringen
// ziehen (wie im CAD: ein Ring je Motorachse – Hüfte und Kopf drei, Knie, Knöchel und Hals eine) oder die Regler
// nehmen. Die Ampel zeigt sofort, ob sie so stehen kann (Schwerpunkt über der Stützfläche). „Probe“ lässt MuJoCo zwei
// Sekunden rechnen, „Üben“ verbessert eine Übung und zeigt die Fähigkeit. Alles nur Simulation – am echten
// Roboter nimmt robotd für die Beine nur Policies an; der Kopf ginge direkt.
import * as THREE from './vendor/three.module.min.js';
import { Scene3D } from './duck3d.js';
import { skillMeter } from './training.js';

const ACT = ['left_hip_yaw', 'left_hip_roll', 'left_hip_pitch', 'left_knee', 'left_ankle',
  'neck_pitch', 'head_pitch', 'head_yaw', 'head_roll',
  'right_hip_yaw', 'right_hip_roll', 'right_hip_pitch', 'right_knee', 'right_ankle'];
const GROUPS = [
  ['Linkes Bein', ACT.slice(0, 5), 'sim'],
  ['Rechtes Bein', ACT.slice(9), 'sim'],
  ['Kopf und Hals', ACT.slice(5, 9), 'real'],
];
const SHORT = {
  left_hip_yaw: 'Hüfte drehen', left_hip_roll: 'Hüfte seitlich', left_hip_pitch: 'Hüfte vor/zurück', left_knee: 'Knie', left_ankle: 'Knöchel',
  right_hip_yaw: 'Hüfte drehen', right_hip_roll: 'Hüfte seitlich', right_hip_pitch: 'Hüfte vor/zurück', right_knee: 'Knie', right_ankle: 'Knöchel',
  neck_pitch: 'Hals', head_pitch: 'Nicken', head_yaw: 'Drehen', head_roll: 'Neigen',
};
const LONG = {
  left_hip_yaw: 'Linke Hüfte drehen', left_hip_roll: 'Linke Hüfte seitlich', left_hip_pitch: 'Linke Hüfte vor/zurück', left_knee: 'Linkes Knie', left_ankle: 'Linker Knöchel',
  right_hip_yaw: 'Rechte Hüfte drehen', right_hip_roll: 'Rechte Hüfte seitlich', right_hip_pitch: 'Rechte Hüfte vor/zurück', right_knee: 'Rechtes Knie', right_ankle: 'Rechter Knöchel',
  neck_pitch: 'Hals', head_pitch: 'Kopf nicken', head_yaw: 'Kopf drehen', head_roll: 'Kopf neigen',
};
// Gelenkpunkte zum Antippen: Hüfte und Kopf haben je drei Motoren an (fast) derselben Stelle
const POINTS = [
  { id: 'huefte_l', name: 'Linke Hüfte', joints: ['left_hip_yaw', 'left_hip_roll', 'left_hip_pitch'], r: 0.045 },
  { id: 'knie_l', name: 'Linkes Knie', joints: ['left_knee'], r: 0.032 },
  { id: 'knoechel_l', name: 'Linker Knöchel', joints: ['left_ankle'], r: 0.03 },
  { id: 'huefte_r', name: 'Rechte Hüfte', joints: ['right_hip_yaw', 'right_hip_roll', 'right_hip_pitch'], r: 0.045 },
  { id: 'knie_r', name: 'Rechtes Knie', joints: ['right_knee'], r: 0.032 },
  { id: 'knoechel_r', name: 'Rechter Knöchel', joints: ['right_ankle'], r: 0.03 },
  { id: 'hals', name: 'Hals', joints: ['neck_pitch'], r: 0.036, real: true },
  { id: 'kopf', name: 'Kopf', joints: ['head_pitch', 'head_yaw', 'head_roll'], r: 0.05, real: true },
];
const KIND = (n) => (n.includes('yaw') ? 'yaw' : n.includes('roll') ? 'roll' : 'pitch');
// CAD-Gewohnheit: Farben je Drehart (dazu immer der Name – nie nur Farbe)
const AXIS_COLOR = { yaw: 0x4589ff, roll: 0xfa4d56, pitch: 0x42be65 };
const AXIS_WORD = { yaw: 'drehen', roll: 'seitlich kippen', pitch: 'vor/zurück' };
const pointOf = (joint) => POINTS.find((p) => p.joints.includes(joint));

const AMPEL = {
  gruen: ['good', 'Steht sicher'],
  gelb: ['warning', 'Wackelig'],
  rot: ['critical', 'Kippt'],
};
const DEG = 180 / Math.PI;
const num = (v, d = 1) => Number(v).toFixed(d).replace('.', ',');

export function initAkrobatik(h) {
  const { $, el, api, toast } = h;
  let data = null;
  let scene = null;
  let pose = null;              // Name → Winkel (rad), MJCF wie der Roboter
  let check = null;             // letzte Antwort von /pruefen
  let sliders = {};
  let checking = false;
  let again = false;
  let checkTimer = null;
  let replay = null;            // { bilder, t, done }
  let lastT = 0;
  let drag = null;
  let jobTimer = null;
  let beforePractice = null;
  let overlay = null;
  let colors = null;
  let tint = null;
  let gizmo = null;             // Gelenkpunkte und Drehringe
  let selected = null;          // gewählter Gelenkpunkt (POINTS-Eintrag)
  let hoverRing = null;
  const axisSliders = {};
  const visible = () => !$('view-akrobatik').hidden;

  // ── Laden ─────────────────────────────────────────────────────────────
  async function load() {
    data = await api('/api/akrobatik').catch(() => null);
    if (!data) return;
    const off = $('ak-off');
    off.hidden = !!data.verfuegbar;
    off.textContent = data.verfuegbar ? '' : data.grund;
    $('ak-layout').hidden = !data.verfuegbar;
    if (!data.verfuegbar) return;
    if (!pose) pose = { ...data.grundstellung };
    buildSliders();
    renderExercises();
    renderPoses();
    ensureScene();
    scene.paused = false;
    requestCheck(0);
    if (data.job && data.job.laeuft) watchJob();
  }
  function hide() { if (scene) scene.paused = true; }

  // ── Bühne ─────────────────────────────────────────────────────────────
  function ensureScene() {
    if (scene) return;
    scene = new Scene3D($('ak-canvas'));
    Object.assign(scene, { showSensor: false, showTrail: false, follow: false, intro: null });
    scene.camera.position.set(0.42, 0.26, 0.5);
    scene.controls.target.set(0, 0.09, 0);
    scene.controls.minDistance = 0.18;
    scene.controls.maxDistance = 2.2;
    const css = getComputedStyle(document.documentElement);
    colors = Object.fromEntries(['good', 'warning', 'critical'].map((k) => [k, new THREE.Color(css.getPropertyValue(`--${k}`).trim() || '#888')]));
    overlay = new THREE.Group();
    scene.scene.add(overlay);
    gizmo = new THREE.Group();
    gizmo.renderOrder = 20;
    scene.scene.add(gizmo);
    const canvas = $('ak-canvas');
    canvas.addEventListener('pointerdown', onDown);
    canvas.addEventListener('pointermove', onMove);
    canvas.addEventListener('pointerup', onUp);
    canvas.addEventListener('pointercancel', onUp);
    canvas.addEventListener('pointerleave', () => { if (!drag) canvas.style.cursor = ''; });
    requestAnimationFrame(tick);
  }

  function joints15(p) {
    const j = ACT.map((n) => p[n] ?? 0);
    j.splice(9, 0, 0);          // Schnabel zu
    return j;
  }

  function showPose() {
    if (!scene || replay) return;
    const c = check || { z: 0.117, rollen: 0, kippen: 0 };
    scene.update({ x: 0, y: 0, yaw: 0, body: [c.z, c.rollen || 0, c.kippen || 0], display_joints: joints15(pose), connected: false }, null);
  }

  function tick(now) {
    const dt = lastT ? Math.min(0.1, (now - lastT) / 1000) : 0;
    lastT = now;
    if (replay && visible()) {
      replay.t += dt;
      const fr = replay.bilder;
      const i = Math.min(fr.length - 1, Math.floor(replay.t * 20));
      const f = fr[i];
      scene.update({ x: f.x, y: f.y, yaw: f.yaw, body: f.body, display_joints: joints15(Object.fromEntries(ACT.map((n, k) => [n, f.joints[k]]))), connected: false }, null);
      if (replay.t > fr.length / 20 + 1.2) { replay = null; showPose(); drawOverlay(); }
    }
    if (scene && scene.realDuck && tint !== (check && check.ampel)) applyTint();
    if (scene && scene.realDuck && visible()) updateGizmo();
    requestAnimationFrame(tick);
  }

  // Ampel: die ganze Ente leicht einfärben (dazu Wort und Symbol in der Statuszeile – nie nur Farbe)
  function applyTint() {
    tint = check && check.ampel;
    const col = tint ? colors[AMPEL[tint][0]] : null;
    const seen = new Set();
    scene.realDuck.root.traverse((o) => {
      if (!o.isMesh || seen.has(o.material)) return;
      seen.add(o.material);
      o.material.emissive = col ? col.clone() : new THREE.Color(0);
      o.material.emissiveIntensity = col ? 0.28 : 0;
    });
  }

  // Stützfläche (Boden) und Schwerpunkt (Kugel mit Lot)
  function drawOverlay() {
    if (!overlay) return;
    for (const o of [...overlay.children]) { overlay.remove(o); o.geometry.dispose(); o.material.dispose(); }
    if (!check || replay) return;
    const col = colors[AMPEL[check.ampel][0]];
    const hull = check.stuetzflaeche || [];
    if (hull.length >= 3) {
      const shape = new THREE.Shape(hull.map(([x, y]) => new THREE.Vector2(x, y)));
      const fill = new THREE.Mesh(new THREE.ShapeGeometry(shape), new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.28, depthWrite: false }));
      fill.rotation.x = -Math.PI / 2;
      fill.position.y = 0.0015;
      const pts = hull.map(([x, y]) => new THREE.Vector3(x, 0.002, -y));
      const line = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: col }));
      overlay.add(fill, line);
    }
    const [cx, cy] = check.schwerpunkt;
    const cz = check.schwerpunkt_hoehe || 0.08;
    const ball = new THREE.Mesh(new THREE.SphereGeometry(0.0065, 20, 14), new THREE.MeshBasicMaterial({ color: col, depthTest: false, transparent: true }));
    ball.position.set(cx, cz, -cy);
    ball.renderOrder = 10;
    const plumb = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(cx, cz, -cy), new THREE.Vector3(cx, 0.002, -cy)]),
      new THREE.LineDashedMaterial({ color: col, dashSize: 0.006, gapSize: 0.004, depthTest: false, transparent: true }));
    plumb.computeLineDistances();
    plumb.renderOrder = 10;
    const dot = new THREE.Mesh(new THREE.RingGeometry(0.004, 0.0075, 24), new THREE.MeshBasicMaterial({ color: col, side: THREE.DoubleSide }));
    dot.rotation.x = -Math.PI / 2;
    dot.position.set(cx, 0.0025, -cy);
    overlay.add(ball, plumb, dot);
  }

  // ── Prüfen (höchstens eine Anfrage unterwegs, die letzte gewinnt) ────
  function requestCheck(delay = 60) {
    clearTimeout(checkTimer);
    checkTimer = setTimeout(runCheck, delay);
  }
  async function runCheck() {
    if (checking) { again = true; return; }
    checking = true;
    const res = await api('/api/akrobatik/pruefen', 'POST', { pose }).catch(() => null);
    checking = false;
    if (res && res.ok) {
      check = res;
      showPose();
      drawOverlay();
      renderStatus();
    }
    if (again) { again = false; runCheck(); }
  }

  function renderStatus(extra = null) {
    const box = $('ak-status');
    box.replaceChildren();
    if (!check) return;
    const [lvl, word] = AMPEL[check.ampel];
    box.dataset.level = lvl;
    const icon = el('span', 'ak-status-icon');
    icon.textContent = { good: '✓', warning: '!', critical: '✕' }[lvl];
    icon.setAttribute('aria-hidden', 'true');
    const mm = check.reserve_mm;
    const detail = mm >= 0 ? `Schwerpunkt ${num(mm)} mm innerhalb der Stützfläche` : `Schwerpunkt ${num(-mm)} mm außerhalb – sie fällt`;
    const feet = check.fuesse_mm || {};
    const stance = feet.left > 5 && feet.right <= 1 ? 'steht auf dem rechten Fuß' : feet.right > 5 && feet.left <= 1 ? 'steht auf dem linken Fuß' : null;
    box.append(icon, el('b', null, word), el('span', null, [detail, stance, check.nicht_nur_fuesse ? 'liegt nicht nur auf den Füßen auf' : null].filter(Boolean).join(' · ')));
    if (extra) box.append(el('span', 'ak-status-extra', extra));
    if (drag) box.append(el('span', 'ak-status-extra', `${LONG[drag.joint]}: ${Math.round(pose[drag.joint] * DEG)}°`));
  }

  // ── Gelenkpunkte und Drehringe (wie im CAD) ──────────────────────────
  const ray = new THREE.Raycaster();
  const tmpV = new THREE.Vector3(), tmpQ = new THREE.Quaternion(), Z = new THREE.Vector3(0, 0, 1);
  function ndc(e) {
    const r = $('ak-canvas').getBoundingClientRect();
    return new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  }
  function overMat(color, opacity = 1) {
    return new THREE.MeshBasicMaterial({ color, transparent: true, opacity, depthTest: false, depthWrite: false });
  }
  function buildGizmo() {
    const duck = scene.realDuck;
    for (const o of [...gizmo.children]) { gizmo.remove(o); o.traverse((m) => { m.geometry?.dispose(); m.material?.dispose(); }); }
    for (const p of POINTS) {
      if (!p.joints.every((n) => duck.joints[n])) continue;
      const g = new THREE.Group();
      g.userData = { point: p };
      const dot = new THREE.Mesh(new THREE.SphereGeometry(0.0055, 16, 12), overMat(0xffffff, 0.9));
      dot.renderOrder = 22;
      const halo = new THREE.Mesh(new THREE.SphereGeometry(0.013, 12, 8), overMat(0xffffff, 0));   // größere Trefferfläche
      halo.userData = { pick: 'point', point: p };
      dot.userData = { pick: 'point', point: p };
      g.add(dot, halo);
      g.userData.dot = dot;
      g.userData.rings = p.joints.map((n, i) => {
        const kind = KIND(n);
        const rad = p.r * (1 - i * 0.14);
        const ring = new THREE.Mesh(new THREE.TorusGeometry(rad, 0.0018, 8, 96), overMat(AXIS_COLOR[kind], 0.95));
        const pick = new THREE.Mesh(new THREE.TorusGeometry(rad, 0.008, 6, 48), overMat(AXIS_COLOR[kind], 0));
        ring.renderOrder = 21;
        pick.userData = { pick: 'ring', joint: n, ring };
        const holder = new THREE.Group();
        holder.add(ring, pick);
        holder.userData = { joint: n };
        holder.visible = false;
        g.add(holder);
        return holder;
      });
      gizmo.add(g);
    }
    gizmo.userData.built = true;
  }
  function jointFrame(n) {
    const duck = scene.realDuck;
    const grp = duck.joints[n];
    const center = grp.getWorldPosition(new THREE.Vector3());
    const axis = duck.axes[n].clone().applyQuaternion(grp.parent.getWorldQuaternion(tmpQ)).normalize();
    return { center, axis };
  }
  function updateGizmo() {
    if (!gizmo.userData.built) buildGizmo();
    scene.realDuck.root.updateMatrixWorld(true);
    for (const g of gizmo.children) {
      const p = g.userData.point;
      const { center } = jointFrame(p.joints[0]);
      const sel = selected === p;
      g.userData.dot.position.copy(center);
      g.userData.dot.material.color.set(sel ? 0xf1913c : 0xffffff);
      g.children[1].position.copy(center);
      g.visible = !replay;
      for (const h of g.userData.rings) {
        h.visible = sel && !replay;
        if (!h.visible) continue;
        const f = jointFrame(h.userData.joint);
        h.position.copy(f.center);
        h.quaternion.setFromUnitVectors(Z, f.axis);
        const ring = h.children[0];
        const hot = (drag && drag.joint === h.userData.joint) || hoverRing === h.userData.joint;
        ring.material.opacity = hot ? 1 : 0.8;
        ring.scale.setScalar(hot ? 1.06 : 1);
      }
    }
  }
  function pickAt(e) {
    if (!scene || !scene.realDuck) return null;
    ray.setFromCamera(ndc(e), scene.camera);
    const targets = [];
    gizmo.traverse((o) => { if (o.userData && o.userData.pick && o.parent && o.parent.visible && (o.parent.parent ? o.parent.parent.visible !== false : true)) targets.push(o); });
    const hits = ray.intersectObjects(targets, false);
    const ring = hits.find((h) => h.object.userData.pick === 'ring');
    if (ring) return { kind: 'ring', joint: ring.object.userData.joint };
    const pt = hits.find((h) => h.object.userData.pick === 'point');
    if (pt) return { kind: 'point', point: pt.object.userData.point };
    // Körperteil getroffen: den nächsten Gelenkpunkt dazu wählen
    const hit = ray.intersectObject(scene.realDuck.root, true)[0];
    if (!hit) return null;
    const byGroup = new Map(Object.entries(scene.realDuck.joints).map(([n, g]) => [g, n]));
    for (let o = hit.object; o; o = o.parent) {
      const n = byGroup.get(o);
      if (n && ACT.includes(n)) return { kind: 'point', point: pointOf(n) };
    }
    return null;
  }
  function select(p) {
    selected = p;
    renderJointCard();
    $('ak-hint').hidden = !!p;
    if (p) focusSlider(p.joints[0]);
  }
  function planeHit(e, center, axis) {
    ray.setFromCamera(ndc(e), scene.camera);
    const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(axis, center);
    // Blickt man fast genau seitlich auf den Ring, ist die Ebene schlecht zu treffen – dann auf die Ansicht projizieren
    if (Math.abs(ray.ray.direction.dot(axis)) < 0.12) {
      const view = scene.camera.getWorldDirection(new THREE.Vector3());
      plane.setFromNormalAndCoplanarPoint(view.negate(), center);
    }
    return ray.ray.intersectPlane(plane, new THREE.Vector3());
  }
  function onDown(e) {
    if (replay || e.button !== 0) return;
    const hit = pickAt(e);
    if (!hit) return;
    e.preventDefault();
    if (hit.kind === 'point') { select(hit.point); return; }
    const { center, axis } = jointFrame(hit.joint);
    const at = planeHit(e, center, axis);
    if (!at) return;
    scene.controls.enabled = false;
    $('ak-canvas').setPointerCapture(e.pointerId);
    drag = { joint: hit.joint, center, axis, start: at.sub(center).normalize(), value: pose[hit.joint], id: e.pointerId };
    $('ak-canvas').style.cursor = 'grabbing';
    focusSlider(hit.joint);
    renderStatus();
  }
  function onMove(e) {
    if (!drag) {
      if (scene && !replay) {
        const h = pickAt(e);
        hoverRing = h && h.kind === 'ring' ? h.joint : null;
        $('ak-canvas').style.cursor = h ? (h.kind === 'ring' ? 'grab' : 'pointer') : '';
      }
      return;
    }
    const at = planeHit(e, drag.center, drag.axis);
    if (!at) return;
    const v = at.sub(drag.center).normalize();
    // Winkel zwischen Start und jetzt, gemessen um die Gelenkachse
    const ang = Math.atan2(drag.axis.dot(tmpV.copy(drag.start).cross(v)), drag.start.dot(v));
    const [lo, hi] = limits(drag.joint);
    pose[drag.joint] = Math.max(lo, Math.min(hi, drag.value + ang));
    syncSlider(drag.joint);
    showPose();
    renderStatus();
    requestCheck(40);
  }
  function onUp() {
    if (!drag) return;
    drag = null;
    scene.controls.enabled = true;
    $('ak-canvas').style.cursor = '';
    requestCheck(0);
  }

  // Karte „Gelenk“: die Achsen des gewählten Punkts als Regler
  function renderJointCard() {
    const box = $('ak-joint-axes');
    box.replaceChildren();
    for (const k of Object.keys(axisSliders)) delete axisSliders[k];
    if (!selected) {
      $('ak-joint-title').textContent = 'Gelenk wählen';
      $('ak-joint-help').hidden = false;
      return;
    }
    $('ak-joint-title').textContent = selected.name;
    $('ak-joint-help').hidden = true;
    const tag = el('p', `ak-tag ak-tag--${selected.real ? 'real' : 'sim'}`, selected.real ? 'auch am Roboter direkt' : 'nur Simulation – am Roboter per Training');
    box.append(tag);
    for (const n of selected.joints) {
      const kind = KIND(n);
      const [lo, hi] = limits(n);
      const row = el('label', 'ak-slider ak-axis-row');
      row.title = `${LONG[n]} – ${AXIS_WORD[kind]}`;
      const name = el('span', 'ak-slider-name');
      name.append(el('i', `ak-axis-dot ak-axis--${kind}`), el('span', null, SHORT[n]));
      const input = el('input');
      Object.assign(input, { type: 'range', min: lo, max: hi, step: 0.005, value: pose[n] });
      input.className = 'range';
      input.setAttribute('aria-label', LONG[n]);
      const val = el('output', 'ak-val');
      input.addEventListener('input', () => { pose[n] = Number(input.value); syncSlider(n); showPose(); requestCheck(30); });
      row.append(name, input, val);
      axisSliders[n] = { input, val, row };
      box.append(row);
      syncSlider(n);
    }
  }

  function limits(n) {
    const g = (data.gelenke || []).find((x) => x.name === n);
    return g ? [g.min, g.max] : [-Math.PI, Math.PI];
  }

  // ── Regler ───────────────────────────────────────────────────────────
  function buildSliders() {
    const root = $('ak-sliders');
    if (root.childElementCount) { for (const n of ACT) syncSlider(n); return; }
    for (const [title, names, kind] of GROUPS) {
      const fs = el('fieldset', 'ak-group');
      const lg = el('legend');
      lg.append(el('span', null, title), el('span', `ak-tag ak-tag--${kind}`, kind === 'real' ? 'auch am Roboter' : 'nur Simulation'));
      fs.append(lg);
      for (const n of names) {
        const [lo, hi] = limits(n);
        const row = el('label', 'ak-slider');
        const input = el('input');
        Object.assign(input, { type: 'range', min: lo, max: hi, step: 0.005, value: pose[n] });
        input.className = 'range';
        input.setAttribute('aria-label', LONG[n]);
        const val = el('output', 'ak-val');
        input.addEventListener('input', () => { pose[n] = Number(input.value); syncSlider(n); showPose(); requestCheck(30); });
        row.append(el('span', 'ak-slider-name', SHORT[n]), input, val);
        sliders[n] = { input, val, row };
        fs.append(row);
        syncSlider(n);
      }
      root.append(fs);
    }
  }
  function syncSlider(n) {
    for (const s of [sliders[n], axisSliders[n]]) {
      if (!s) continue;
      s.input.value = pose[n];
      fill(s.input);
      s.val.textContent = `${Math.round(pose[n] * DEG)}°`;
    }
  }
  function fill(input) {
    const f = (Number(input.value) - Number(input.min)) / Math.max(1e-6, Number(input.max) - Number(input.min));
    input.style.setProperty('--_fill', `${Math.round(f * 100)}%`);
  }
  function focusSlider(n) {
    for (const [k, s] of Object.entries(sliders)) s.row.classList.toggle('is-active', k === n);
  }
  function setPose(p) {
    pose = { ...data.grundstellung, ...p };
    for (const n of ACT) syncSlider(n);
    replay = null;
    requestCheck(0);
  }

  // ── Probe: zwei Sekunden Physik ──────────────────────────────────────
  async function probe() {
    const b = $('ak-probe');
    b.disabled = true;
    const res = await api('/api/akrobatik/probe', 'POST', { pose }).catch(() => null);
    b.disabled = false;
    if (!res || !res.ok) { toast(res ? res.fehler : 'Keine Antwort', true); return; }
    play(res);
  }
  function play(res) {
    replay = { bilder: res.bilder, t: 0 };
    drawOverlay();
    const msg = res.steht ? `Probe: steht nach 2 s noch (kippt höchstens ${num(res.kippen_max_grad, 0)}°)` : `Probe: fällt nach ${num(res.faellt_nach_s)} s um`;
    renderStatus(msg);
    $('ak-probe-result').textContent = msg;
  }

  // ── Üben ─────────────────────────────────────────────────────────────
  function renderExercises() {
    const list = $('ak-exercises');
    list.replaceChildren();
    const job = data.job || {};
    for (const u of data.uebungen || []) {
      const li = el('li', 'ak-ex');
      const head = el('div', 'ak-ex-head');
      const text = el('div');
      text.append(el('b', null, u.name), el('span', null, u.beschreibung));
      head.append(text);
      const running = job.laeuft && job.uebung === u.id;
      const btn = el('button', `btn btn--sm ${running ? 'btn--ghost' : ''}`, running ? 'Abbrechen' : 'Üben');
      btn.type = 'button';
      btn.disabled = !!job.laeuft && !running;
      btn.addEventListener('click', () => (running ? cancel() : practice(u.id)));
      head.append(btn);
      li.append(head);
      const hist = u.verlauf || [];
      if (running) {
        li.append(skillMeter(el, (job.faehigkeit ?? 0) / 100, job.verlauf && job.verlauf.length ? job.verlauf[0] / 100 : null,
          job.von ? `übt … Runde ${job.generation} von ${job.von}` : 'übt …'));   // „von ?“ war nicht übersetzbar (0.38.39)
      } else if (u.beste != null) {
        li.append(skillMeter(el, u.beste / 100, u.start != null ? u.start / 100 : null,
          `beste von ${hist.length} Übungsrunde${hist.length === 1 ? '' : 'n'}`));
        if (u.pose) {
          const use = el('button', 'link-btn', 'Beste Haltung zeigen');
          use.type = 'button';
          use.addEventListener('click', () => setPose(u.pose));
          li.append(use);
        }
      } else li.append(el('p', 'field-help', 'Noch nicht geübt.'));
      list.append(li);
    }
    const res = job.ergebnis;
    $('ak-practice-msg').textContent = job.fehler ? `Üben fehlgeschlagen: ${job.fehler}`
      : res && !job.laeuft ? `${(data.uebungen.find((u) => u.id === res.uebung) || {}).name || res.uebung}: Fähigkeit ${num(res.faehigkeit, 0)} % nach ${num(res.sekunden, 0)} s${job.abgebrochen ? ' (abgebrochen)' : ''}` : '';
  }
  async function practice(id) {
    beforePractice = { ...pose };
    const res = await api('/api/akrobatik/ueben', 'POST', { pose, uebung: id }).catch(() => null);
    if (!res || !res.ok) { toast(res ? res.fehler : 'Keine Antwort', true); return; }
    data.job = res.job;
    renderExercises();
    watchJob();
  }
  async function cancel() { await api('/api/akrobatik/abbrechen', 'POST').catch(() => {}); }
  function watchJob() {
    clearInterval(jobTimer);
    jobTimer = setInterval(async () => {
      const r = await api('/api/akrobatik/job').catch(() => null);
      if (!r) return;
      data.job = r.job;
      if (r.job.pose && visible() && !replay) {                 // die beste Haltung bisher live zeigen
        pose = { ...pose, ...r.job.pose };
        for (const n of ACT) syncSlider(n);
        requestCheck(0);
      }
      if (!r.job.laeuft) {
        clearInterval(jobTimer);
        const fresh = await api('/api/akrobatik').catch(() => null);
        if (fresh) data = fresh;
        if (r.job.ergebnis) {
          setPose(r.job.ergebnis.pose);
          play(r.job.ergebnis.probe);
          $('ak-undo').hidden = !beforePractice;
        }
      }
      if (visible()) renderExercises();
    }, 400);
  }

  // ── Haltungen ────────────────────────────────────────────────────────
  function renderPoses() {
    const list = $('ak-poses');
    list.replaceChildren();
    const names = Object.keys(data.posen || {});
    $('ak-poses-empty').hidden = names.length > 0;
    for (const name of names) {
      const li = el('li', 'ak-pose');
      const b = el('button', 'chip chip--btn', name);
      b.type = 'button';
      b.addEventListener('click', () => setPose(data.posen[name]));
      const x = el('button', 'icon-btn', '×');
      x.type = 'button';
      x.setAttribute('aria-label', `Haltung „${name}“ löschen`);
      x.addEventListener('click', async () => {
        await api(`/api/akrobatik/haltung/${encodeURIComponent(name)}`, 'DELETE');
        delete data.posen[name];
        renderPoses();
      });
      li.append(b, x);
      list.append(li);
    }
  }

  $('ak-goto-training').addEventListener('click', () => h.showView && h.showView('training'));
  $('ak-reset').addEventListener('click', () => { setPose(data.grundstellung); $('ak-probe-result').textContent = ''; });
  $('ak-probe').addEventListener('click', probe);
  $('ak-undo').addEventListener('click', () => { if (beforePractice) setPose(beforePractice); $('ak-undo').hidden = true; });
  $('ak-save').addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = $('ak-save-name').value.trim();
    const res = await api('/api/akrobatik/haltung', 'POST', { name, pose }).catch(() => null);
    if (!res || !res.ok) { toast(res ? res.fehler : 'Keine Antwort', true); return; }
    data.posen[res.name] = { ...pose };
    $('ak-save-name').value = '';
    renderPoses();
    toast(`Haltung „${res.name}“ gespeichert`);
  });

  return { load, hide, get scene() { return scene; }, get check() { return check; } };
}
