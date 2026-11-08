// Dashboard: Live-Diagramme, Lagebild von oben, Tiefensensor als 3D-Gelände oder Punktwolke,
// Gelenke, Ereignisse.
import * as THREE from './vendor/three.module.min.js';
import { OrbitControls } from './vendor/OrbitControls.js';
import { CloudLayer } from './pointcloud.js';

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const REDUCED = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const fmt = (v, d = 2) => (v == null || Number.isNaN(v) ? '–' : v.toFixed(d).replace('.', ','));

function fitCanvas(canvas) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  const g = canvas.getContext('2d');
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { g, w, h };
}

// ── Liniendiagramm mit zwei Reihen, Fadenkreuz und Tooltip ────────────────
export class LineChart {
  constructor(canvas, { series, unit, digits = 2, window = 30, min = -0.1, max = 0.1, fixed = false, ticks = null }) {
    this.canvas = canvas;
    this.series = series;              // [{key, label, color}]
    this.unit = unit;
    this.digits = digits;
    this.window = window;
    this.minSpan = [min, max];
    this.fixed = fixed;          // feste Skala statt mitwachsen
    this.tickLabels = ticks;     // z. B. {1: 'freudig', 0: 'ausgeglichen', -1: 'frustriert'}
    this.data = [];                    // [{t, a, b}]
    this.hover = null;
    canvas.addEventListener('pointermove', (e) => {
      const r = canvas.getBoundingClientRect();
      this.hover = e.clientX - r.left;
    });
    canvas.addEventListener('pointerleave', () => { this.hover = null; });
  }

  push(t, values) {
    this.data.push({ t, ...values });
    while (this.data.length && this.data[0].t < t - this.window - 1) this.data.shift();
  }

  draw(now) {
    const { g, w, h } = fitCanvas(this.canvas);
    if (!w || !h) return;
    const pad = { l: this.tickLabels ? 84 : 44, r: 12, t: this.series.length > 1 ? 26 : 10, b: 22 };
    const pw = w - pad.l - pad.r, ph = h - pad.t - pad.b;
    g.clearRect(0, 0, w, h);
    let lo = this.minSpan[0], hi = this.minSpan[1];
    if (!this.fixed) {
      for (const d of this.data) for (const s of this.series) { lo = Math.min(lo, d[s.key]); hi = Math.max(hi, d[s.key]); }
    }
    const span = hi - lo || 1;
    lo -= span * 0.08; hi += span * 0.08;
    const X = (t) => pad.l + pw * (1 - (now - t) / this.window);
    const Y = (v) => pad.t + ph * (1 - (v - lo) / (hi - lo));

    // Raster (zurückhaltend) und Nulllinie
    g.font = '11px "IBM Plex Sans", system-ui, sans-serif';
    g.fillStyle = css('--ink-3');
    g.textAlign = 'right';
    g.textBaseline = 'middle';
    const ticks = this.tickLabels ? Object.keys(this.tickLabels).map(Number) : niceTicks(lo, hi, 4);
    for (const v of ticks) {
      g.strokeStyle = Math.abs(v) < 1e-9 ? css('--ink-3') : css('--line');
      g.globalAlpha = Math.abs(v) < 1e-9 ? 0.8 : 0.5;
      g.beginPath(); g.moveTo(pad.l, Y(v)); g.lineTo(w - pad.r, Y(v)); g.stroke();
      g.globalAlpha = 1;
      g.fillText(this.tickLabels ? this.tickLabels[v] : fmt(v, this.digits === 0 ? 0 : 2), pad.l - 6, Y(v));
    }
    g.textAlign = 'center';
    g.textBaseline = 'top';
    const marks = this.window > 60 ? [120, 90, 60, 30, 0] : [30, 20, 10, 0];
    for (const s of marks) {
      if (s > this.window) continue;
      g.fillText(s ? `−${s} s` : 'jetzt', X(now - s), h - pad.b + 6);
    }

    // Reihen: 2px-Linien
    g.save();
    g.beginPath(); g.rect(pad.l, pad.t - 2, pw, ph + 4); g.clip();
    for (const s of this.series) {
      g.strokeStyle = s.color;
      g.lineWidth = 2;
      g.lineJoin = 'round';
      g.setLineDash(s.dash || []);
      g.beginPath();
      this.data.forEach((d, i) => (i ? g.lineTo(X(d.t), Y(d[s.key])) : g.moveTo(X(d.t), Y(d[s.key]))));
      g.stroke();
    }
    g.restore();
    g.setLineDash([]);

    // Legende oben links (Text in Textfarbe, Kennzeichen in Reihenfarbe) – eine Reihe braucht keine
    let lx = pad.l;
    if (this.series.length > 1) {
    g.textAlign = 'left';
    g.textBaseline = 'middle';
    g.font = '12px "IBM Plex Sans", system-ui, sans-serif';
    for (const s of this.series) {
      g.strokeStyle = s.color; g.lineWidth = 2; g.setLineDash(s.dash || []);
      g.beginPath(); g.moveTo(lx, 9); g.lineTo(lx + 16, 9); g.stroke(); g.setLineDash([]);
      g.fillStyle = css('--ink-2');
      g.fillText(s.label, lx + 22, 9);
      lx += 30 + g.measureText(s.label).width + 16;
    }
    }

    // Fadenkreuz + Tooltip
    if (this.hover != null && this.data.length) {
      const tAt = now - (1 - (this.hover - pad.l) / pw) * this.window;
      let best = this.data[0];
      for (const d of this.data) if (Math.abs(d.t - tAt) < Math.abs(best.t - tAt)) best = d;
      const x = X(best.t);
      if (x >= pad.l && x <= w - pad.r) {
        g.strokeStyle = css('--ink-3'); g.lineWidth = 1;
        g.beginPath(); g.moveTo(x, pad.t); g.lineTo(x, pad.t + ph); g.stroke();
        const lines = this.series.map((s) => `${s.label}: ${fmt(best[s.key], this.digits)}${this.unit ? ' ' + this.unit : ''}`);
        lines.unshift(`vor ${fmt(now - best.t, 1)} s`);
        g.font = '12px "IBM Plex Sans", system-ui, sans-serif';
        const bw = Math.max(...lines.map((l) => g.measureText(l).width)) + 20, bh = lines.length * 17 + 10;
        const bx = Math.min(w - bw - 4, x + 10), by = pad.t + 4;
        g.fillStyle = css('--surface-sunken'); g.strokeStyle = css('--line');
        roundRect(g, bx, by, bw, bh, 8); g.fill(); g.stroke();
        lines.forEach((l, i) => {
          if (i > 0) {
            g.fillStyle = this.series[i - 1].color;
            g.beginPath(); g.arc(x, Y(best[this.series[i - 1].key]), 4, 0, Math.PI * 2); g.fill();
            g.strokeStyle = css('--surface-1'); g.lineWidth = 2; g.stroke();
          }
          g.fillStyle = i ? css('--ink') : css('--ink-3');
          g.fillText(l, bx + 10, by + 14 + i * 17);
        });
      }
    }
  }
}

function niceTicks(lo, hi, n) {
  const step0 = (hi - lo) / n;
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) || step0;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(Math.abs(v) < 1e-9 ? 0 : v);
  return out;
}

function roundRect(g, x, y, w, h, r) {
  g.beginPath();
  g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath();
}

// ── Lagebild: Draufsicht ──────────────────────────────────────────────────
export class MapView {
  constructor(canvas) {
    this.canvas = canvas;
    this.world = null;
    this.items = [];
    this.places = [];
    this.trail = [];
    this.state = null;
    this.target = null;
    this.pings = [];
  }

  setWorld(world) { this.world = world; }
  setItems(items) { if (items) this.items = items; }
  setLaser(p) { this.laser = p || null; }
  setPlaces(places) { this.places = places; }
  // gelernte Rasterkarte aus dem Kartieren (seit 0.37.12): am echten Roboter das eigentliche Lagebild
  setKarte(k) { this.karte = k && k.messungen ? k : null; }

  update(st, engine) {
    this.state = st;
    this.target = engine && engine.ziel;
    if (!st.connected) return;
    const last = this.trail[this.trail.length - 1];
    if (!last || Math.hypot(last[0] - st.x, last[1] - st.y) > 0.015) {
      if (last && Math.hypot(last[0] - st.x, last[1] - st.y) > 0.6) this.trail = [];
      this.trail.push([st.x, st.y]);
      if (this.trail.length > 1500) this.trail.shift();
    }
  }

  ping(x, y, color) { if (!REDUCED) this.pings.push({ x, y, color, t: performance.now() }); }

  distance() {
    let d = 0;
    for (let i = 1; i < this.trail.length; i++) d += Math.hypot(this.trail[i][0] - this.trail[i - 1][0], this.trail[i][1] - this.trail[i - 1][1]);
    return d;
  }

  draw(now) {
    const { g, w, h } = fitCanvas(this.canvas);
    if (!w || !h) return;
    g.fillStyle = css('--surface-sunken');
    g.fillRect(0, 0, w, h);
    // Ausschnitt: Zimmer oder (Roboter) Spur ± 1 m
    let x0, x1, y0, y1;
    if (this.world) {
      x0 = -this.world.width / 2; x1 = this.world.width / 2; y0 = -this.world.depth / 2; y1 = this.world.depth / 2;
    } else {
      const zk = this.karte ? this.karte.zelle_m : 0;
      const zellen = this.karte ? [...this.karte.frei, ...this.karte.belegt] : [];
      const xs = this.trail.map((p) => p[0]).concat(this.places.map((p) => p.x), [0], zellen.map(([i]) => (i + 0.5) * zk));
      const ys = this.trail.map((p) => p[1]).concat(this.places.map((p) => p.y), [0], zellen.map(([, j]) => (j + 0.5) * zk));
      x0 = Math.min(...xs) - 1; x1 = Math.max(...xs) + 1; y0 = Math.min(...ys) - 1; y1 = Math.max(...ys) + 1;
    }
    const m = 18;
    const s = Math.min((w - 2 * m) / (x1 - x0), (h - 2 * m) / (y1 - y0));
    const ox = (w - s * (x1 - x0)) / 2, oy = (h - s * (y1 - y0)) / 2;
    // x nach rechts, y nach oben (links der Ente = oben im Bild, Blick nach rechts zu Beginn)
    const P = (x, y) => [ox + (x - x0) * s, h - oy - (y - y0) * s];

    // 10-cm-Raster
    g.strokeStyle = css('--surface-2'); g.lineWidth = 1;
    for (let gx = Math.ceil(x0 * 2) / 2; gx <= x1; gx += 0.5) { const [a] = P(gx, 0); g.beginPath(); g.moveTo(a, P(0, y0)[1]); g.lineTo(a, P(0, y1)[1]); g.stroke(); }
    for (let gy = Math.ceil(y0 * 2) / 2; gy <= y1; gy += 0.5) { const [, b] = P(0, gy); g.beginPath(); g.moveTo(P(x0, 0)[0], b); g.lineTo(P(x1, 0)[0], b); g.stroke(); }

    if (this.karte) {                        // was sie selbst erkundet hat: frei hell, Hindernis dunkel
      const z = this.karte.zelle_m, zp = Math.max(1, z * s) + 0.5;
      g.globalAlpha = this.world ? 0.55 : 0.9;
      g.fillStyle = css('--raum-frei');
      for (const [i, j] of this.karte.frei) { const [a, b] = P(i * z, (j + 1) * z); g.fillRect(a, b, zp, zp); }
      g.fillStyle = css('--raum-belegt');
      for (const [i, j] of this.karte.belegt) { const [a, b] = P(i * z, (j + 1) * z); g.fillRect(a, b, zp, zp); }
      g.globalAlpha = 1;
    }
    if (this.world) {
      const [ax, ay] = P(x0, y1);
      g.strokeStyle = css('--ink-3'); g.lineWidth = 2;
      g.strokeRect(ax, ay, (x1 - x0) * s, (y1 - y0) * s);
      g.font = '11px "IBM Plex Sans", system-ui, sans-serif';
      g.textAlign = 'center'; g.textBaseline = 'middle';
      for (const b of this.world.boxes) {
        const [bx, by] = P(b.x - b.sx / 2, b.y + b.sy / 2);
        g.fillStyle = css('--surface-2'); g.strokeStyle = css('--line');
        g.fillRect(bx, by, b.sx * s, b.sy * s); g.strokeRect(bx, by, b.sx * s, b.sy * s);
        g.fillStyle = css('--ink-3'); g.fillText(b.name, bx + b.sx * s / 2, by + b.sy * s / 2);
      }
      for (const c of this.world.cylinders) {
        const [cx, cy] = P(c.x, c.y);
        g.fillStyle = css('--surface-2'); g.strokeStyle = css('--line');
        g.beginPath(); g.arc(cx, cy, c.r * s, 0, Math.PI * 2); g.fill(); g.stroke();
      }
    }
    for (const it of this.items) {
      if (it.held) continue;
      const [ix, iy] = P(it.x, it.y);
      g.fillStyle = it.color;
      g.beginPath(); g.arc(ix, iy, Math.max(4, it.r * s), 0, Math.PI * 2); g.fill();
    }
    if (this.laser) {                                   // Laserpunkt: roter Kern mit Schein
      const [lx, ly] = P(this.laser.x, this.laser.y);
      g.fillStyle = 'rgba(255, 36, 20, 0.35)';
      g.beginPath(); g.arc(lx, ly, 7, 0, Math.PI * 2); g.fill();
      g.fillStyle = '#ff2414';
      g.beginPath(); g.arc(lx, ly, 3, 0, Math.PI * 2); g.fill();
    }

    // Spur, ausblendend
    const n = this.trail.length;
    g.lineWidth = 2; g.lineCap = 'round';
    for (let i = 1; i < n; i++) {
      const [a, b] = P(...this.trail[i - 1]), [c, d] = P(...this.trail[i]);
      g.strokeStyle = css('--data-1');
      g.globalAlpha = 0.12 + 0.88 * Math.pow(i / n, 1.5);
      g.beginPath(); g.moveTo(a, b); g.lineTo(c, d); g.stroke();
    }
    g.globalAlpha = 1;

    // Orte
    g.font = '600 12px "IBM Plex Sans", system-ui, sans-serif';
    g.textAlign = 'left'; g.textBaseline = 'middle';
    for (const p of this.places) {
      const [px, py] = P(p.x, p.y);
      g.fillStyle = css('--data-1');
      g.beginPath(); g.arc(px, py, 5, 0, Math.PI * 2); g.fill();
      g.strokeStyle = css('--surface-sunken'); g.lineWidth = 2; g.stroke();
      g.fillStyle = css('--ink'); g.fillText(p.name, px + 9, py);
    }

    // Ziel
    if (this.target) {
      const [tx, ty] = P(this.target[0], this.target[1]);
      const k = (now / 900) % 1;
      g.strokeStyle = css('--accent'); g.lineWidth = 2;
      g.beginPath(); g.arc(tx, ty, 7, 0, Math.PI * 2); g.stroke();
      g.globalAlpha = 1 - k;
      g.beginPath(); g.arc(tx, ty, 7 + k * 14, 0, Math.PI * 2); g.stroke();
      g.globalAlpha = 1;
      if (this.state) {
        const [dx, dy] = P(this.state.x, this.state.y);
        g.setLineDash([4, 5]); g.globalAlpha = 0.6;
        g.beginPath(); g.moveTo(dx, dy); g.lineTo(tx, ty); g.stroke();
        g.setLineDash([]); g.globalAlpha = 1;
      }
    }

    // Ente: Sichtfächer des Tiefensensors + Pfeil
    const st = this.state;
    if (st && st.connected) {
      const [dx, dy] = P(st.x, st.y);
      const gaze = st.yaw + (st.head ? st.head.head_yaw : 0);
      const reach = (st.perception.sectors && Math.min(...Object.values(st.perception.sectors).filter((v) => v != null))) || 1.2;
      const r = Math.min(isFinite(reach) ? reach : 1.2, 2) * s;
      const grad = g.createRadialGradient(dx, dy, 0, dx, dy, r);
      grad.addColorStop(0, 'rgba(57,135,229,0.35)'); grad.addColorStop(1, 'rgba(57,135,229,0)');
      g.fillStyle = grad;
      g.beginPath(); g.moveTo(dx, dy); g.arc(dx, dy, r, -gaze - Math.PI / 8, -gaze + Math.PI / 8); g.closePath(); g.fill();
      g.save();
      g.translate(dx, dy); g.rotate(-st.yaw);
      g.fillStyle = st.fallen ? css('--critical') : css('--accent');
      g.strokeStyle = css('--surface-sunken'); g.lineWidth = 2;
      g.beginPath(); g.moveTo(12, 0); g.lineTo(-8, 8); g.lineTo(-4, 0); g.lineTo(-8, -8); g.closePath(); g.fill(); g.stroke();
      g.restore();
    }

    // Ereignis-Pings
    this.pings = this.pings.filter((p) => {
      const k = (now - p.t) / 1200;
      if (k >= 1) return false;
      const [px, py] = P(p.x, p.y);
      g.strokeStyle = p.color; g.globalAlpha = 1 - k; g.lineWidth = 2;
      g.beginPath(); g.arc(px, py, 6 + k * 34, 0, Math.PI * 2); g.stroke();
      g.globalAlpha = 1;
      return true;
    });
  }
}

// ── Tiefensensor als 3D-Gelände ───────────────────────────────────────────
// Sequenziell, ein Farbton: je näher, desto höher und heller (auf dunklem Grund).
// Carbon Blau 80 → 10
const RAMP = ['#002d9c', '#0043ce', '#0f62fe', '#4589ff', '#78a9ff', '#a6c8ff', '#d0e2ff', '#edf5ff'];

export class TofTerrain {
  constructor(canvas, store) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(css('--surface-sunken') || '#262626');
    this.camera = new THREE.PerspectiveCamera(36, 1, 0.1, 50);
    this.scene.add(new THREE.HemisphereLight(0xe0e0e0, 0x262626, 1.6));
    const key = new THREE.DirectionalLight(0xffffff, 1.6);
    key.position.set(3, 6, 4);
    this.scene.add(key);
    this.colors = RAMP.map((c) => new THREE.Color(c));
    this.mesh = new THREE.InstancedMesh(new THREE.BoxGeometry(0.9, 1, 0.9), new THREE.MeshStandardMaterial({ roughness: 0.55 }), 64);
    this.scene.add(this.mesh);
    const base = new THREE.Mesh(new THREE.PlaneGeometry(9, 9), new THREE.MeshStandardMaterial({ color: 0x303030 }));
    base.rotation.x = -Math.PI / 2;
    base.position.y = -0.01;
    this.scene.add(base);
    this.heights = new Float32Array(64).fill(0.05);
    this.target = new Float32Array(64).fill(0.05);
    this.angle = 0.6;
    this.visible = true;
    this._m = new THREE.Matrix4();
    this._set(0);
    this.mode = 'terrain';
    if (store) this._buildCloud(store);
  }

  // ── Punktwolke: gesammelte Messpunkte im Raum, mit der Maus drehbar ──
  _buildCloud(store) {
    const bg = css('--surface-sunken') || '#262626';
    const s = this.cloudScene = new THREE.Scene();
    s.background = new THREE.Color(bg);
    this.cloudCam = new THREE.PerspectiveCamera(45, 1, 0.02, 60);
    this.cloudCam.position.set(-1.2, 1.4, 1.4);
    this.controls = new OrbitControls(this.cloudCam, this.canvas);
    this.controls.enabled = false;
    this.controls.enableDamping = true;
    this.controls.minDistance = 0.4;
    this.controls.maxDistance = 8;
    this.controls.maxPolarAngle = Math.PI * 0.49;
    this.controls.target.set(0, 0.1, 0);
    const grid = new THREE.GridHelper(10, 20, 0x4a4a4a, 0x333333);
    s.add(grid);
    this.room = new THREE.Group();
    s.add(this.room);
    this.layer = new CloudLayer(store, { size: 0.028, background: bg });
    s.add(this.layer.points);
    // Die Ente: Schnabel-Orange, mit dem Sichtkegel des Sensors (45°, 2 m)
    const duck = this.duckMark = new THREE.Group();
    const body = new THREE.Mesh(new THREE.ConeGeometry(0.06, 0.16, 20), new THREE.MeshBasicMaterial({ color: 0xf0962c }));
    body.rotation.z = -Math.PI / 2;
    body.position.y = 0.06;
    duck.add(body);
    const half = Math.PI / 8, r = 2;
    const pts = [new THREE.Vector3(0, 0.21, 0)];
    for (let i = 0; i <= 16; i++) {
      const a = -half + (i / 16) * 2 * half;
      pts.push(new THREE.Vector3(Math.cos(a) * r, 0.21, -Math.sin(a) * r));
    }
    pts.push(new THREE.Vector3(0, 0.21, 0));
    this.fan = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
      new THREE.LineBasicMaterial({ color: 0xf0962c, transparent: true, opacity: 0.45 }));
    duck.add(this.fan);
    s.add(duck);
    this._lastDuck = new THREE.Vector3();
  }

  setWorld(world) {
    if (!this.room) return;
    this.room.clear();
    if (!world) return;
    const mat = new THREE.LineBasicMaterial({ color: 0x6f6f6f, transparent: true, opacity: 0.6 });
    const edges = (geo, x, y, z) => {
      const l = new THREE.LineSegments(new THREE.EdgesGeometry(geo), mat);
      l.position.set(x, y, z);
      this.room.add(l);
    };
    edges(new THREE.BoxGeometry(world.width, 0.18, world.depth), 0, 0.09, 0);
    for (const b of world.boxes) edges(new THREE.BoxGeometry(b.sx, b.h, b.sy), b.x, b.h / 2, -b.y);
    for (const c of world.cylinders) edges(new THREE.CylinderGeometry(c.r, c.r, c.h, 16, 1), c.x, c.h / 2, -c.y);
  }

  setMode(mode) {
    this.mode = mode === 'cloud' && this.layer ? 'cloud' : 'terrain';
    if (this.controls) this.controls.enabled = this.mode === 'cloud';
    this.canvas.style.cursor = this.mode === 'cloud' ? 'grab' : '';
  }

  setPose(st) {
    if (!this.duckMark || !st) return;
    this.duckMark.position.set(st.x, 0, -st.y);
    this.duckMark.rotation.y = st.yaw;
    this.fan.rotation.y = st.head ? st.head.head_yaw : 0;
    this.duckMark.visible = !!st.connected;
  }

  _drawCloud(dt) {
    // Kamera folgt der Ente; Drehen und Zoomen mit der Maus bleiben erhalten.
    const p = this.duckMark.position;
    const delta = p.clone().sub(this._lastDuck);
    if (delta.length() < 1) {
      this.cloudCam.position.add(delta);
      this.controls.target.add(delta);
    } else {
      this.controls.target.set(p.x, 0.1, p.z);
      this.cloudCam.position.set(p.x - 1.2, 1.4, p.z + 1.4);
    }
    this._lastDuck.copy(p);
    this.controls.update();
    this.layer.update();
    this.renderer.render(this.cloudScene, this.cloudCam);
  }

  set(tof) {
    if (!tof || tof.length !== 64) return;
    for (let i = 0; i < 64; i++) {
      const near = 1 - Math.min(2000, Math.max(0, tof[i])) / 2000;
      this.target[i] = 0.05 + near * 2.4;
    }
  }

  _set(dt) {
    for (let i = 0; i < 64; i++) {
      this.heights[i] += (this.target[i] - this.heights[i]) * Math.min(1, dt * 10);
      const row = Math.floor(i / 8), col = i % 8;
      const hgt = this.heights[i];
      // Spalte 0 = links aus Sicht der Ente → im Bild links; Zeile 0 = oben → hinten
      this._m.makeScale(1, hgt, 1).setPosition(col - 3.5, hgt / 2, row - 3.5);
      this.mesh.setMatrixAt(i, this._m);
      const k = Math.min(RAMP.length - 1, Math.round(((hgt - 0.05) / 2.4) * (RAMP.length - 1)));
      this.mesh.setColorAt(i, this.colors[Math.max(0, k)]);
    }
    this.mesh.instanceMatrix.needsUpdate = true;
    if (this.mesh.instanceColor) this.mesh.instanceColor.needsUpdate = true;
  }

  draw(dt) {
    const c = this.canvas;
    const w = c.clientWidth, h = c.clientHeight;
    if (!w || !h) return;
    if (c.width !== Math.round(w * this.renderer.getPixelRatio()) || c.height !== Math.round(h * this.renderer.getPixelRatio())) {
      this.renderer.setSize(w, h, false);
      for (const cam of [this.camera, this.cloudCam]) {
        if (!cam) continue;
        cam.aspect = w / h;
        cam.updateProjectionMatrix();
      }
    }
    if (this.mode === 'cloud') { this._drawCloud(dt); return; }
    if (!REDUCED) this.angle += dt * 0.12;
    const a = 0.35 * Math.sin(this.angle);
    this.camera.position.set(Math.sin(a) * 13, 10, Math.cos(a) * 13);
    this.camera.lookAt(0, 0.3, 0);
    this._set(dt);
    this.renderer.render(this.scene, this.camera);
  }
}

// ── Gelenke ───────────────────────────────────────────────────────────────
const GROUPS = [
  ['Linkes Bein', [[0, 'Hüfte drehen'], [1, 'Hüfte seitlich'], [2, 'Hüfte vor/zurück'], [3, 'Knie'], [4, 'Knöchel']]],
  ['Rechtes Bein', [[10, 'Hüfte drehen'], [11, 'Hüfte seitlich'], [12, 'Hüfte vor/zurück'], [13, 'Knie'], [14, 'Knöchel']]],
  ['Kopf', [[5, 'Nacken'], [6, 'Nicken'], [7, 'Drehen'], [8, 'Neigen'], [9, 'Schnabel']]],
];

const AMPEL = { gut: ['good', 'gut'], auffaellig: ['warning', 'auffällig'], pruefen: ['critical', 'prüfen'] };
const DEG = 180 / Math.PI;
const barFrac = (rad) => Math.max(-1, Math.min(1, (rad * DEG) / 120)) * 50;

export class Joints {
  constructor(root, summary = null) {
    this.cells = [];
    this.summary = summary;
    for (const [title, joints] of GROUPS) {
      const grp = document.createElement('div');
      grp.className = 'joint-group';
      const h = document.createElement('h3');
      h.textContent = title;
      grp.append(h);
      for (const [idx, name] of joints) {
        const row = document.createElement('div');
        row.className = 'joint';
        row.title = name;
        row.innerHTML = `<span class="joint-name"></span><span class="joint-bar"><b></b><i hidden></i></span><span class="joint-val"></span><span class="joint-state" aria-hidden="true"></span>`;
        row.querySelector('.joint-name').textContent = name;
        row.querySelector('.joint-name').title = name;   // ganzer Name, falls er abgeschnitten ist
        grp.append(row);
        this.cells.push({ idx, name, row, bar: row.querySelector('b'), soll: row.querySelector('i'),
          val: row.querySelector('.joint-val'), state: row.querySelector('.joint-state'), mouth: idx === 9 });
      }
      root.append(grp);
    }
  }

  update(joints) {
    if (!joints || joints.length !== 15) return;
    for (const c of this.cells) {
      const v = joints[c.idx];
      if (c.mouth) {
        const p = Math.max(0, Math.min(1, v));
        c.bar.style.left = '50%';
        c.bar.style.width = `${p * 50}%`;
        c.val.textContent = `${Math.round(p * 100)} %`;
        continue;
      }
      const frac = barFrac(v);
      c.bar.style.left = `${frac < 0 ? 50 + frac : 50}%`;
      c.bar.style.width = `${Math.abs(frac)}%`;
      c.val.textContent = `${Math.round(v * DEG)}°`;
    }
  }

  // Gelenk-Check vom Server: Sollwert als Strich, Ampel je Gelenk (Symbol + Wort im Tooltip, nie nur Farbe)
  report(rep) {
    if (!rep || !Array.isArray(rep.gelenke)) return;
    const rows = rep.gelenke;
    for (const c of this.cells) {
      const r = rows[c.idx];
      if (!r) continue;
      if (r.soll != null && !c.mouth) {
        c.soll.hidden = false;
        c.soll.style.left = `${50 + barFrac(r.soll)}%`;
      } else c.soll.hidden = true;
      const [lvl, word] = AMPEL[r.ampel] || AMPEL.gut;
      c.row.dataset.ampel = r.ampel;
      const showIcon = r.ampel !== 'gut';
      c.state.innerHTML = showIcon ? ICON[lvl] : '';
      const bits = [c.name];
      if (r.soll != null && r.fehler != null) bits.push(`Soll ${Math.round(r.soll * DEG)}°, Nachlauf ${(r.fehler * DEG).toFixed(1)}°`);
      if (r.last != null) bits.push(`Last ${Math.round(r.last * 100)} %${r.strom_ma != null ? ` (${Math.round(r.strom_ma)} mA)` : ''}`);
      bits.push(`Zustand: ${word}`);
      c.row.title = bits.join(' · ');
      c.row.setAttribute('aria-label', c.row.title);
    }
    if (this.summary) {
      const s = rep.summe || {};
      const parts = [];
      if (s.nachlauf_mittel != null) parts.push(`Nachlauf Ø ${(s.nachlauf_mittel * DEG).toFixed(1)}°, max ${(s.nachlauf_max * DEG).toFixed(1)}°`);
      if (s.last_max != null) parts.push(`Last bis ${Math.round(s.last_max * 100)} %`);
      if (!rep.aktiv) parts.push('Motoren ohne Strom – keine Bewertung');
      else if (s.auffaellig && s.auffaellig.length) parts.push(`ansehen: ${s.auffaellig.slice(0, 3).join(', ')}`);
      else if (parts.length) parts.push('alle Gelenke gut');
      if (rep.hinweis) parts.push(rep.hinweis);
      this.summary.textContent = parts.join(' · ');
    }
  }
}

// ── Ereignisse mit Status-Symbol + Wort (nie nur Farbe) ───────────────────
const LEVELS = {
  fall: ['critical', 'Sturz'],
  bump: ['warning', 'Angestoßen'],
  reflex: ['serious', 'Reflex'],
  kick_miss: ['warning', 'Daneben'],
  pick_miss: ['warning', 'Daneben'],
  recover: ['good', 'Wieder auf'],
  pick: ['good', 'Aufgehoben'],
  drop: ['info', 'Abgelegt'],
  schwarm: ['info', 'Enten'],                 // weitere Enten begegnen sich (0.36.3)
  kick: ['good', 'Geschossen'],
  memory: ['info', 'Gedächtnis'],
  connected: ['info', 'Verbindung'],
  disconnected: ['critical', 'Verbindung'],
  curious: ['info', 'Neugier'],
  goofy: ['good', 'Goofy'],
  charakter: ['info', 'Charakter'],
  gefuehl: ['info', 'Gefühl'],
  trick: ['good', 'Trick'],
  mcp: ['info', 'Von außen'],
};
const ICON = {
  critical: '<svg viewBox="0 0 16 16"><path d="M8 1.5 15 14H1z" fill="var(--critical)"/><path d="M8 6v3.5M8 11.5v.5" stroke="#fff" stroke-width="1.6" stroke-linecap="round"/></svg>',
  warning: '<svg viewBox="0 0 16 16"><path d="M8 1.5 15 14H1z" fill="var(--warning)"/><path d="M8 6v3.5M8 11.5v.5" stroke="#161616" stroke-width="1.6" stroke-linecap="round"/></svg>',
  serious: '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.5" fill="var(--serious)"/><path d="M8 4.5v4M8 11v.5" stroke="#161616" stroke-width="1.6" stroke-linecap="round"/></svg>',
  good: '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.5" fill="var(--good)"/><path d="m5 8.2 2 2 4-4.2" stroke="#fff" stroke-width="1.6" fill="none" stroke-linecap="round"/></svg>',
  info: '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.5" fill="var(--data-1)"/><path d="M8 7.5V11M8 5v.5" stroke="#fff" stroke-width="1.6" stroke-linecap="round"/></svg>',
};

export function eventLevel(ev) {
  return (LEVELS[ev.type] || ['info', 'Info'])[0];
}

export function eventItem(ev) {
  const [lvl, word] = LEVELS[ev.type] || ['info', 'Info'];
  const li = document.createElement('li');
  const time = new Date((ev.t || Date.now() / 1000) * 1000);
  li.innerHTML = `${ICON[lvl]}<span><span class="lvl"></span><span class="txt"></span></span><time></time>`;
  li.querySelector('.lvl').textContent = word;
  li.querySelector('.txt').textContent = ev.message || ev.result || ev.type;
  li.querySelector('time').textContent = time.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  return li;
}

export const SHOWN_EVENTS = new Set(Object.keys(LEVELS));
