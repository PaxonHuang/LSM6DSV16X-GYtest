/**
 * Live panel for LSM6DSV16X units.
 *
 * Data arrives as SSE frames from tools/web_panel.py:
 *   { units: [{ i, a:[x,y,z], g:[x,y,z], q:[x,y,z,w], aq, va, vg, t }], ... }
 *
 * Attitude comes from the sensor's own SFLP fusion (q). When a unit reports
 * aq:0 the cube falls back to integrating the gyro, so the view still moves
 * before the fusion engine has settled.
 */

import * as THREE from "./vendor/three.module.js";

/* ------------------------------------------------------------- constants -- */

const SERIES = [
  { key: "x", color: "var(--series-1)", hex: () => cssVar("--series-1") },
  { key: "y", color: "var(--series-2)", hex: () => cssVar("--series-2") },
  { key: "z", color: "var(--series-3)", hex: () => cssVar("--series-3") },
];

const HISTORY = 240;          // samples kept per series (~4.8 s at 50 Hz)
const AXIS_LEN = 1.15;

const state = {
  units: new Map(),           // index -> { latest, acc:[[],[],[]], gyro:[[],[],[]] }
  selected: 0,
  connected: false,
  ageMs: null,
  rate: 0,
  frameTimes: [],
};

/* --------------------------------------------------------------- helpers -- */

const $ = (id) => document.getElementById(id);

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function fmt(v, digits = 2) {
  return Number.isFinite(v) ? v.toFixed(digits) : "–";
}

function clamp(v, lo, hi) {
  return Math.min(hi, Math.max(lo, v));
}

/* Euler angles (degrees) from a unit quaternion, ZYX order. */
function quatToEuler(q) {
  const [x, y, z, w] = q;
  const sinr = 2 * (w * x + y * z);
  const cosr = 1 - 2 * (x * x + y * y);
  const roll = Math.atan2(sinr, cosr);

  const sinp = clamp(2 * (w * y - z * x), -1, 1);
  const pitch = Math.asin(sinp);

  const siny = 2 * (w * z + x * y);
  const cosy = 1 - 2 * (y * y + z * z);
  const yaw = Math.atan2(siny, cosy);

  const deg = 180 / Math.PI;
  return { roll: roll * deg, pitch: pitch * deg, yaw: yaw * deg };
}

/* ------------------------------------------------------------ three scene -- */

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
const canvas = $("scene");
const renderer = new THREE.WebGLRenderer({
  canvas,
  antialias: true,
  alpha: true,
  // Keeps the buffer readable after compositing, so screenshots capture the
  // scene instead of a blank canvas.
  preserveDrawingBuffer: true,
});

/* Camera orbit, kept minimal on purpose: a handful of lines instead of
 * pulling in an extra module for a debug panel. */
const orbit = {
  yaw: 0.62,
  pitch: 0.42,
  dist: 7.4,
  minDist: 3.4,
  dragging: false,
  px: 0,
  py: 0,
};

function applyCamera() {
  const { yaw, pitch, dist } = orbit;
  camera.position.set(
    Math.sin(yaw) * Math.cos(pitch) * dist,
    Math.sin(pitch) * dist,
    Math.cos(yaw) * Math.cos(pitch) * dist,
  );
  camera.lookAt(0, 0.35, 0);
}

canvas.parentElement.addEventListener("pointerdown", (e) => {
  orbit.dragging = true;
  orbit.px = e.clientX;
  orbit.py = e.clientY;
  canvas.setPointerCapture(e.pointerId);
});

canvas.parentElement.addEventListener("pointermove", (e) => {
  if (!orbit.dragging) return;
  orbit.yaw -= (e.clientX - orbit.px) * 0.008;
  orbit.pitch = clamp(orbit.pitch + (e.clientY - orbit.py) * 0.008, -1.35, 1.35);
  orbit.px = e.clientX;
  orbit.py = e.clientY;
  applyCamera();
});

canvas.parentElement.addEventListener("pointerup", (e) => {
  orbit.dragging = false;
  canvas.releasePointerCapture(e.pointerId);
});

canvas.parentElement.addEventListener(
  "wheel",
  (e) => {
    e.preventDefault();
    const lo = orbit.minDist || 3.4;
    orbit.dist = clamp(orbit.dist + e.deltaY * 0.004, lo, lo * 3);
    applyCamera();
  },
  { passive: false },
);

const light = new THREE.HemisphereLight(0xffffff, 0x444455, 2.1);
scene.add(light);
const key = new THREE.DirectionalLight(0xffffff, 1.5);
key.position.set(4, 7, 5);
scene.add(key);

const grid = new THREE.GridHelper(12, 12, 0x8890a0, 0x8890a0);
grid.material.opacity = 0.28;
grid.material.transparent = true;
grid.position.y = -1.1;
scene.add(grid);

/* Per-unit rig: a box plus three coloured axis arrows. */
const rigs = new Map();

function makeLabel(text) {
  const size = 128;
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d");
  g.fillStyle = "rgba(0,0,0,0)";
  g.fillRect(0, 0, size, size);
  g.font = "600 74px system-ui, sans-serif";
  g.fillStyle = "#ffffff";
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.fillText(text, size / 2, size / 2);

  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const mat = new THREE.SpriteMaterial({ map: tex, depthWrite: false });
  const sprite = new THREE.Sprite(mat);
  sprite.scale.set(0.55, 0.55, 0.55);
  return sprite;
}

function ensureRig(index) {
  if (rigs.has(index)) return rigs.get(index);

  const root = new THREE.Group();
  const geo = new THREE.BoxGeometry(1.5, 0.32, 1.05);
  const body = new THREE.Mesh(
    geo,
    new THREE.MeshStandardMaterial({
      color: 0x2a78d6,
      metalness: 0.15,
      roughness: 0.55,
      transparent: true,
      opacity: 0.9,
    }),
  );
  root.add(body);
  root.add(
    new THREE.LineSegments(
      new THREE.EdgesGeometry(geo),
      new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.35 }),
    ),
  );

  const axes = [
    new THREE.Vector3(1, 0, 0),
    new THREE.Vector3(0, 1, 0),
    new THREE.Vector3(0, 0, 1),
  ];
  axes.forEach((dir, i) => {
    const arrow = new THREE.ArrowHelper(
      dir,
      new THREE.Vector3(0, 0, 0),
      AXIS_LEN,
      new THREE.Color(cssVar(`--series-${i + 1}`)),
      0.22,
      0.12,
    );
    root.add(arrow);
  });

  const label = makeLabel(String(index));
  label.position.set(0, 0.72, 0);
  root.add(label);

  root.userData.body = body;
  scene.add(root);
  rigs.set(index, root);
  return root;
}

/* Lay units out in a grid centred on the origin. One row stops reading once
 * there are more than about six cubes, so larger sets wrap. */
const LAYOUT = { cols: 1, rows: 1, spanX: 0, spanZ: 0 };

function layoutRigs() {
  const indices = Array.from(rigs.keys()).sort((a, b) => a - b);
  const n = indices.length;
  const stepX = 2.6;
  const stepZ = 2.4;

  const cols = Math.min(n, 6);
  const rows = Math.ceil(n / cols) || 1;

  indices.forEach((idx, i) => {
    const r = Math.floor(i / cols);
    const c = i % cols;
    /* Centre short last rows rather than left-aligning them. */
    const inRow = r === rows - 1 ? n - r * cols : cols;
    const x = (c - (inRow - 1) / 2) * stepX;
    const z = (r - (rows - 1) / 2) * stepZ;
    rigs.get(idx).position.set(x, 0.35, z);
  });

  LAYOUT.cols = cols;
  LAYOUT.rows = rows;
  LAYOUT.spanX = (Math.min(cols, n) - 1) * stepX + 2;
  LAYOUT.spanZ = (rows - 1) * stepZ + 2;

  /* GridHelper is built at a fixed 12 units, so scale it to the arrangement. */
  const gridSize = Math.max(LAYOUT.spanX, LAYOUT.spanZ) + 2;
  grid.scale.setScalar(gridSize / 12);
  grid.position.y = -1.1;

  fitCamera();
}

/* Pull the camera back until the whole grid is inside the frustum. Without
 * this an 11-unit row runs off both sides of the viewport. */
function fitCamera() {
  const vFov = (camera.fov * Math.PI) / 180;
  const aspect = camera.aspect || 1;
  const hFov = 2 * Math.atan(Math.tan(vFov / 2) * aspect);

  const needX = LAYOUT.spanX / 2 / Math.tan(hFov / 2);
  const needZ = LAYOUT.spanZ / 2 / Math.tan(vFov / 2);
  orbit.minDist = Math.max(3.4, Math.max(needX, needZ) * 1.15);
  orbit.dist = Math.max(orbit.dist, orbit.minDist);
  orbit.dist = clamp(orbit.dist, orbit.minDist, orbit.minDist * 3);
  applyCamera();
}

function resizeRenderer() {
  const wrap = canvas.parentElement;
  const w = wrap.clientWidth;
  const h = wrap.clientHeight;
  if (!w || !h) return;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  fitCamera();
}

new ResizeObserver(resizeRenderer).observe($("canvas-wrap"));

/* ------------------------------------------------------------- charts ----- */

function makeChart(svg, legendEl, title) {
  const pad = { top: 12, right: 34, bottom: 20, left: 40 };
  const plot = { series: [], hover: null };

  function render() {
    const w = svg.clientWidth || 640;
    const h = svg.clientHeight || 190;
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    svg.setAttribute("width", w);
    svg.setAttribute("height", h);

    const iw = Math.max(10, w - pad.left - pad.right);
    const ih = Math.max(10, h - pad.top - pad.bottom);

    const all = plot.series.flatMap((s) => s.values);
    if (!all.length) {
      svg.innerHTML = `<text x="${w / 2}" y="${h / 2}" text-anchor="middle"
        fill="${cssVar("--text-muted")}" font-size="12">等待数据…</text>`;
      return;
    }

    const t0 = all[0].t;
    const t1 = all[all.length - 1].t;
    const span = Math.max(1, t1 - t0);

    let lo = Infinity;
    let hi = -Infinity;
    for (const p of all) {
      lo = Math.min(lo, p.v);
      hi = Math.max(hi, p.v);
    }
    if (!Number.isFinite(lo)) {
      lo = -1;
      hi = 1;
    }
    const minSpan = 0.5;
    if (hi - lo < minSpan) {
      const mid = (hi + lo) / 2;
      lo = mid - minSpan / 2;
      hi = mid + minSpan / 2;
    }
    const padY = (hi - lo) * 0.12;
    lo -= padY;
    hi += padY;

    const X = (t) => pad.left + ((t - t0) / span) * iw;
    const Y = (v) => pad.top + (1 - (v - lo) / (hi - lo)) * ih;

    const muted = cssVar("--text-muted");
    const gridC = cssVar("--grid");
    const axisC = cssVar("--axis");

    const parts = [];

    /* Recessive grid: four horizontal rules with tick labels. */
    for (let i = 0; i <= 3; i++) {
      const v = lo + ((hi - lo) * i) / 3;
      const y = Y(v);
      parts.push(
        `<line x1="${pad.left}" y1="${y}" x2="${pad.left + iw}" y2="${y}"
           stroke="${i === 0 ? axisC : gridC}" stroke-width="1"/>`,
      );
      parts.push(
        `<text x="${pad.left - 7}" y="${y + 3.5}" text-anchor="end"
           fill="${muted}" font-size="10"
           style="font-variant-numeric:tabular-nums">${v.toFixed(2)}</text>`,
      );
    }

    parts.push(
      `<text x="${pad.left - 7}" y="${pad.top - 3}" text-anchor="end"
         fill="${muted}" font-size="10">${title}</text>`,
    );
    parts.push(
      `<text x="${pad.left + iw}" y="${h - 5}" text-anchor="end"
         fill="${muted}" font-size="10" style="font-variant-numeric:tabular-nums">${(span / 1000).toFixed(1)} s</text>`,
    );

    /* Series: 2px lines, plus a direct label at the line end so identity is
     * never carried by hue alone. */
    for (const s of plot.series) {
      if (!s.values.length) continue;
      const d = s.values
        .map((p, i) => `${i === 0 ? "M" : "L"}${X(p.t).toFixed(1)} ${Y(p.v).toFixed(1)}`)
        .join(" ");
      parts.push(
        `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="2"
           stroke-linejoin="round" stroke-linecap="round"/>`,
      );
      const last = s.values[s.values.length - 1];
      parts.push(
        `<text x="${pad.left + iw + 5}" y="${Y(last.v) + 3.5}"
           fill="${s.color}" font-size="10" font-weight="600">${s.label}</text>`,
      );
    }

    /* Crosshair, drawn on top of the data. */
    if (plot.hover !== null) {
      const x = X(plot.hover);
      parts.push(
        `<line x1="${x}" y1="${pad.top}" x2="${x}" y2="${pad.top + ih}"
           stroke="${axisC}" stroke-width="1" stroke-dasharray="3 3"/>`,
      );
      for (const s of plot.series) {
        const p = nearest(s.values, plot.hover);
        if (!p) continue;
        parts.push(
          `<circle cx="${X(p.t)}" cy="${Y(p.v)}" r="3.5" fill="${s.color}"
             stroke="${cssVar("--surface-1")}" stroke-width="2"/>`,
        );
      }
    }

    svg.innerHTML = parts.join("");
  }

  function nearest(values, t) {
    if (!values.length) return null;
    let best = values[0];
    let bestD = Math.abs(values[0].t - t);
    for (const p of values) {
      const d = Math.abs(p.t - t);
      if (d < bestD) {
        best = p;
        bestD = d;
      }
    }
    return best;
  }

  const tip = $("tooltip");

  svg.addEventListener("pointermove", (e) => {
    const all = plot.series.flatMap((s) => s.values);
    if (!all.length) return;
    const rect = svg.getBoundingClientRect();
    const w = rect.width;
    const iw = Math.max(10, w - pad.left - pad.right);
    const frac = clamp((e.clientX - rect.left - pad.left) / iw, 0, 1);

    const t0 = all[0].t;
    const t1 = all[all.length - 1].t;
    plot.hover = t0 + frac * Math.max(1, t1 - t0);
    render();

    const rows = plot.series
      .map((s) => {
        const p = nearest(s.values, plot.hover);
        return p
          ? `<div class="tip-row"><span class="tip-key">${s.label}</span><span>${p.v.toFixed(3)}</span></div>`
          : "";
      })
      .join("");
    tip.innerHTML =
      `<div class="tip-row"><span class="tip-key">${((plot.hover - t0) / 1000).toFixed(2)} s</span></div>` +
      rows;
    tip.hidden = false;
    tip.style.left = `${e.clientX}px`;
    tip.style.top = `${e.clientY - 10}px`;
  });

  svg.addEventListener("pointerleave", () => {
    plot.hover = null;
    tip.hidden = true;
    render();
  });

  return { plot, render };
}

const accChart = makeChart($("chart-acc"), $("legend-acc"), "g");
const gyroChart = makeChart($("chart-gyro"), $("legend-gyro"), "dps");

function buildLegend(el, letters) {
  el.innerHTML = SERIES.map(
    (s, i) =>
      `<span class="legend-item"><span class="swatch" style="background:${s.color}"></span>${letters[i]}</span>`,
  ).join("");
}

buildLegend($("legend-acc"), ["X", "Y", "Z"]);
buildLegend($("legend-gyro"), ["X", "Y", "Z"]);

/* --------------------------------------------------------------- ingest --- */

function unitState(index) {
  if (!state.units.has(index)) {
    state.units.set(index, {
      latest: null,
      accHist: SERIES.map(() => []),
      gyroHist: SERIES.map(() => []),
      fallbackQ: new THREE.Quaternion(),
    });
  }
  return state.units.get(index);
}

function onFrame(snapshot) {
  const now = performance.now();
  state.frameTimes.push(now);
  state.frameTimes = state.frameTimes.filter((t) => now - t < 1000);
  state.rate = state.frameTimes.length;

  state.connected = snapshot.connected;
  state.ageMs = snapshot.age_ms;

  for (const u of snapshot.units) {
    const st = unitState(u.i);
    const online = u.on !== 0;
    const prev = st.latest;
    st.online = online;

    /* An absent source is reported every frame with on:0. Keep it visible in
     * the chip list and table, but never integrate its stale/zero payload or
     * feed it to the charts. */
    if (!online) {
      st.latest = u;
      continue;
    }

    /* Gyro integration fallback, used until SFLP reports a quaternion. */
    if (!u.aq && prev) {
      const dt = Math.max(0, (u.t - prev.t) / 1000);
      if (dt > 0 && dt < 0.5) {
        const w = new THREE.Vector3(u.g[0], u.g[1], u.g[2])
          .multiplyScalar(Math.PI / 180);
        const angle = w.length() * dt;
        if (angle > 1e-6) {
          w.normalize();
          const dq = new THREE.Quaternion().setFromAxisAngle(w, angle);
          st.fallbackQ.multiply(dq).normalize();
        }
      }
    }
    st.latest = u;

    if (u.va !== 0) {
      SERIES.forEach((_, i) => {
        const arr = st.accHist[i];
        arr.push({ t: u.t, v: u.a[i] });
        if (arr.length > HISTORY) arr.shift();
      });
    }
    if (u.vg !== 0) {
      SERIES.forEach((_, i) => {
        const arr = st.gyroHist[i];
        arr.push({ t: u.t, v: u.g[i] });
        if (arr.length > HISTORY) arr.shift();
      });
    }
  }

  state.events = snapshot.events || [];
  state.present = snapshot.units.filter((u) => u.on).length;
  state.total = snapshot.units.length;

  syncUnitChips(snapshot.units.map((u) => ({ i: u.i, on: u.on !== 0 })));
  updateCharts();
  updateTiles();
  updatePose();
  updateTable();
  updateEventsLine();
}

function updateCharts() {
  const st = state.units.get(state.selected);
  if (!st) return;
  accChart.plot.series = SERIES.map((s, i) => ({
    label: ["X", "Y", "Z"][i],
    color: cssVar(`--series-${i + 1}`),
    values: st.accHist[i],
  }));
  gyroChart.plot.series = SERIES.map((s, i) => ({
    label: ["X", "Y", "Z"][i],
    color: cssVar(`--series-${i + 1}`),
    values: st.gyroHist[i],
  }));
  accChart.render();
  gyroChart.render();
}

function updateTiles() {
  const st = state.units.get(state.selected);
  const u = st?.latest;
  if (!u) return;

  if (u.on === 0) {
    for (const id of ["t-accmag", "t-gyromag", "t-roll", "t-pitch", "t-yaw"]) {
      $(id).textContent = "离线";
    }
    $("t-rate").textContent = "–";
    return;
  }

  const mag = (v) => Math.hypot(v[0], v[1], v[2]);

  $("t-accmag").textContent = fmt(mag(u.a), 3);
  $("t-gyromag").textContent = fmt(mag(u.g), 2);

  const q = u.aq ? u.q : st.fallbackQ.toArray();
  const { roll, pitch, yaw } = quatToEuler(q);
  $("t-roll").textContent = fmt(roll, 1);
  $("t-pitch").textContent = fmt(pitch, 1);
  $("t-yaw").textContent = fmt(yaw, 1);
  $("t-rate").textContent = String(Math.round(u.rate_a ?? state.rate));
}

function updatePose() {
  const st = state.units.get(state.selected);
  const u = st?.latest;
  if (!u) return;

  for (const [idx, rig] of rigs) {
    const s = state.units.get(idx);
    if (!s?.latest) continue;
    const q = s.latest.aq
      ? new THREE.Quaternion(...s.latest.q)
      : s.fallbackQ.clone();
    rig.quaternion.copy(q);
    rig.userData.body.material.opacity =
      s.latest.on === 0 ? 0.08 : idx === state.selected ? 0.95 : 0.45;
  }

  if (u.on === 0) {
    $("pose-source").textContent = `模块 ${u.i} · 离线（CS 无设备应答）`;
    return;
  }

  const src = u.aq ? "SFLP 硬件融合（四元数）" : "陀螺积分（回退）";
  $("pose-source").textContent =
    `模块 ${u.i} · 姿态来源：${src} · 四元数 ` +
    `(${u.q.map((v) => v.toFixed(3)).join(", ")})`;
}

/* ------------------------------------------------------------ unit chips -- */

let chipSignature = "";

function syncUnitChips(units) {
  const sig = units.map((u) => `${u.i}:${u.on ? 1 : 0}`).join(",");
  if (sig === chipSignature) return;
  chipSignature = sig;

  const box = $("unit-chips");
  box.innerHTML = "";

  if (units.length > 1) {
    for (const u of units) {
      const b = document.createElement("button");
      b.className = "chip" + (u.on ? "" : " chip-offline");
      b.textContent = `#${u.i}${u.on ? "" : " 离线"}`;
      b.dataset.live = String(u.on);
      b.title = u.on ? `模块 ${u.i} 在线` : `模块 ${u.i} 未应答（CS 无设备）`;
      b.setAttribute("role", "tab");
      b.setAttribute("aria-selected", String(u.i === state.selected));
      b.addEventListener("click", () => {
        state.selected = u.i;
        chipSignature = "";
        syncUnitChips(units);
        updateCharts();
        updateTiles();
        updatePose();
      });
      box.appendChild(b);
    }
  }

  for (const u of units) ensureRig(u.i);
  layoutRigs();
}

function updateEventsLine() {
  const el = $("events-line");
  if (!el) return;
  const present = state.present ?? 0;
  const total = state.total ?? 0;
  const ev = (state.events || []).slice(-2).map((e) => e.text).join(" · ");
  el.textContent = `在线 ${present}/${total}` + (ev ? ` · ${ev}` : "");
}

/* ---------------------------------------------------------------- table --- */

function updateTable() {
  const panel = $("table-panel");
  if (panel.hidden) return;
  const tbody = panel.querySelector("tbody");
  const rows = [];
  for (const idx of [...state.units.keys()].sort((a, b) => a - b)) {
    const u = state.units.get(idx).latest;
    if (!u) continue;
    const on = u.on !== 0;
    const stateCell = on ? "在线" : "离线";
    const idCell = on ? `0x${(u.id ?? 0).toString(16).padStart(2, "0").toUpperCase()}` : "—";
    if (!on) {
      rows.push(
        `<tr><td>${idx}</td><td>${stateCell}</td><td>${idCell}</td>` +
          `<td colspan="7" style="color:var(--text-muted)">未应答</td>` +
          `<td>${u.e ?? 0}</td></tr>`,
      );
      continue;
    }
    const q = u.aq ? u.q : state.units.get(idx).fallbackQ.toArray();
    rows.push(
      `<tr><td>${idx}</td><td>${stateCell}</td><td>${idCell}</td>` +
        u.a.map((v) => `<td>${v.toFixed(3)}</td>`).join("") +
        u.g.map((v) => `<td>${v.toFixed(2)}</td>`).join("") +
        `<td>${q.map((v) => v.toFixed(3)).join(", ")}</td>` +
        `<td>${u.e ?? 0}</td></tr>`,
    );
  }
  tbody.innerHTML = rows.join("") ||
    `<tr><td colspan="11" style="color:var(--text-muted)">暂无数据</td></tr>`;
}

/* ------------------------------------------------------------------- ui --- */

$("table-toggle").addEventListener("click", (e) => {
  const panel = $("table-panel");
  panel.hidden = !panel.hidden;
  e.currentTarget.setAttribute("aria-pressed", String(!panel.hidden));
  updateTable();
});

$("theme-toggle").addEventListener("click", () => {
  const root = document.documentElement;
  const next = root.dataset.theme === "dark" ? "light" : "dark";
  root.dataset.theme = next;
  try {
    localStorage.setItem("panel-theme", next);
  } catch {
    /* private mode: the theme just does not persist */
  }
  refreshColors();
});

try {
  const saved = localStorage.getItem("panel-theme");
  if (saved) document.documentElement.dataset.theme = saved;
} catch {
  /* ignore */
}
document.documentElement.dataset.theme ||= "dark";

/* Axis arrow colours are baked into geometry when a rig is created, so a
 * theme switch has to rebuild them. */
function refreshColors() {
  for (const [idx] of rigs) {
    const rig = rigs.get(idx);
    for (const child of [...rig.children]) {
      if (child.isArrowHelper) rig.remove(child);
    }
    const dirs = [
      new THREE.Vector3(1, 0, 0),
      new THREE.Vector3(0, 1, 0),
      new THREE.Vector3(0, 0, 1),
    ];
    dirs.forEach((dir, i) => {
      rig.add(
        new THREE.ArrowHelper(
          dir,
          new THREE.Vector3(0, 0, 0),
          AXIS_LEN,
          new THREE.Color(cssVar(`--series-${i + 1}`)),
          0.22,
          0.12,
        ),
      );
    });
  }
  updateCharts();
}

/* --------------------------------------------------------------- link ui -- */

const linkState = $("link-state");
const linkText = $("link-text");

function setLink(kind, text) {
  linkState.dataset.state = kind;
  linkText.textContent = text;
}

/* ----------------------------------------------------------------- loop --- */

function animate() {
  requestAnimationFrame(animate);
  renderer.render(scene, camera);
}

applyCamera();
resizeRenderer();
animate();

/* ------------------------------------------------------------------ sse --- */

function connect() {
  const es = new EventSource("/stream");

  es.onmessage = (ev) => {
    try {
      onFrame(JSON.parse(ev.data));
    } catch (err) {
      console.error("bad frame", err);
    }
  };

  es.onopen = () => setLink("live", "已连接");

  es.onerror = () => {
    setLink("down", "连接中断，重试中…");
    es.close();
    setTimeout(connect, 1500);
  };
}

/* Staleness is judged from the data age, not the socket: a socket can look
 * open while the board is silent. */
setInterval(() => {
  if (state.ageMs === null) return;
  if (state.ageMs < 400) setLink("live", `已连接 · ${state.rate} Hz`);
  else if (state.ageMs < 3000) setLink("stale", `数据滞后 ${state.ageMs} ms`);
  else setLink("down", "无数据");
}, 250);

connect();

/* Debug handle: lets the console (or an automated check) inspect the scene
 * without adding a UI surface for it. */
window.__panel = { scene, camera, renderer, rigs, orbit, state, LAYOUT };

window.addEventListener("resize", () => {
  resizeRenderer();
  accChart.render();
  gyroChart.render();
});