// Conic fretboard G-code generator. Strict-typed TypeScript port of
// conic_fretboard_cam.py. Compiles to a plain browser script that
// `fretboard_cam.html` loads with <script src="fretboard_cam.js">.
//
// No imports, no modules, no DOM frameworks — runs from file://.

interface Fretboard {
  length: number;
  nut_width: number;
  heel_width: number;
  radius_nut: number;
  radius_heel: number;
  z_crown: number;
}

type ToolKind = "ball" | "flat";

interface Tool {
  diameter: number;
  kind: ToolKind;
}

interface CamParams {
  stepover: number;
  sample_step: number;
  safe_z: number;
  feed_xy: number;
  feed_z: number;
  spindle_rpm: number;
  margin_xy: number;
  rainbow_pad: number;
  rainbow_transitions: boolean;
}

type CutPoint = readonly [number, number, number]; // x, y, tip_z

interface Arc {
  x1: number; y1: number;
  x2: number; y2: number;
  cx: number; cy: number;
  r: number;
  signY: 1 | -1;
}

interface GcodeResult {
  text: string;
  rows: ReadonlyArray<ReadonlyArray<CutPoint>>;
  arcs: ReadonlyArray<Arc>;
}

// ---------- Geometry ----------

function clamp01(t: number): number {
  return t < 0 ? 0 : (t > 1 ? 1 : t);
}

function fbRadiusAt(fb: Fretboard, x: number): number {
  const t = clamp01(x / fb.length);
  return fb.radius_nut + (fb.radius_heel - fb.radius_nut) * t;
}

function fbHalfWidthAt(fb: Fretboard, x: number): number {
  const t = clamp01(x / fb.length);
  return (fb.nut_width / 2) + ((fb.heel_width - fb.nut_width) / 2) * t;
}

function fbSurfaceZ(fb: Fretboard, x: number, y: number): number {
  if (x < 0 || x > fb.length) return -Infinity;
  if (Math.abs(y) > fbHalfWidthAt(fb, x)) return -Infinity;
  const r = fbRadiusAt(fb, x);
  const under = r * r - y * y;
  if (under <= 0) return -Infinity;
  return fb.z_crown - r + Math.sqrt(under);
}

// ---------- Top-down clearance sampler ----------

function safeTipZ(
  fb: Fretboard,
  tool: Tool,
  xc: number,
  yc: number,
  sampleStep: number,
): number {
  const R = tool.diameter / 2;
  const R2 = R * R;
  let best = -Infinity;
  const n = Math.max(1, Math.ceil(R / sampleStep));
  for (let i = -n; i <= n; i++) {
    const dx = i * sampleStep;
    for (let j = -n; j <= n; j++) {
      const dy = j * sampleStep;
      const dd = dx * dx + dy * dy;
      if (dd > R2) continue;
      const sz = fbSurfaceZ(fb, xc + dx, yc + dy);
      if (sz === -Infinity) continue;
      const tipReq = tool.kind === "flat"
        ? sz
        : sz - (R - Math.sqrt(R2 - dd));
      if (tipReq > best) best = tipReq;
    }
  }
  return best;
}

// ---------- Raster generator ----------

interface RasterPt { x: number; y: number; newRow: boolean; }

function* rasterPositions(
  fb: Fretboard,
  tool: Tool,
  params: CamParams,
): Generator<RasterPt> {
  const R = tool.diameter / 2;
  const pad = R + params.margin_xy;
  let x = -params.margin_xy;
  const endX = fb.length + params.margin_xy;
  let direction = 1;
  while (x <= endX + 1e-9) {
    const xClamp = Math.max(0, Math.min(fb.length, x));
    const hw = fbHalfWidthAt(fb, xClamp);
    let y0 = -hw - pad;
    let y1 = hw + pad;
    if (direction < 0) { const t = y0; y0 = y1; y1 = t; }
    const n = Math.max(1, Math.ceil(Math.abs(y1 - y0) / params.stepover));
    let first = true;
    for (let i = 0; i <= n; i++) {
      const t = i / n;
      yield { x, y: y0 + (y1 - y0) * t, newRow: first };
      first = false;
    }
    x += params.stepover;
    direction = -direction;
  }
}

function collectRows(
  fb: Fretboard,
  tool: Tool,
  params: CamParams,
): CutPoint[][] {
  const rows: CutPoint[][] = [];
  let current: CutPoint[] = [];
  for (const p of rasterPositions(fb, tool, params)) {
    if (p.newRow && current.length) { rows.push(current); current = []; }
    const z = safeTipZ(fb, tool, p.x, p.y, params.sample_step);
    if (z === -Infinity) continue;
    current.push([p.x, p.y, z] as const);
  }
  if (current.length) rows.push(current);
  return rows;
}

// ---------- Rainbow arc + boundary check ----------

function arcClearsPart(
  fb: Fretboard,
  tool: Tool,
  cx: number,
  cy: number,
  radius: number,
  pad: number,
  samples = 32,
): boolean {
  const signY: 1 | -1 = cy >= 0 ? 1 : -1;
  const R = tool.diameter / 2;
  for (let i = 0; i <= samples; i++) {
    const theta = Math.PI * i / samples;
    const x = cx - radius * Math.cos(theta);
    const y = cy + signY * radius * Math.sin(theta);
    if (x < 0 || x > fb.length) continue;
    const hw = fbHalfWidthAt(fb, x);
    if (Math.abs(y) < hw + R + pad) return false;
  }
  return true;
}

// ---------- G-code emitter ----------

function fmt(n: number): string { return n.toFixed(3); }

interface RapidArgs { x?: number; y?: number; z?: number; }
interface FeedArgs extends RapidArgs { f?: number; }

function makeGcode(
  fb: Fretboard,
  tool: Tool,
  params: CamParams,
): GcodeResult {
  const lines: string[] = [];
  const arcs: Arc[] = [];
  let lastFeed: number | null = null;

  function rapid(p: RapidArgs): void {
    const parts: string[] = ["G0"];
    if (p.x !== undefined) parts.push("X" + fmt(p.x));
    if (p.y !== undefined) parts.push("Y" + fmt(p.y));
    if (p.z !== undefined) parts.push("Z" + fmt(p.z));
    lines.push(parts.join(" "));
  }

  function feed(p: FeedArgs): void {
    const parts: string[] = ["G1"];
    if (p.x !== undefined) parts.push("X" + fmt(p.x));
    if (p.y !== undefined) parts.push("Y" + fmt(p.y));
    if (p.z !== undefined) parts.push("Z" + fmt(p.z));
    if (p.f !== undefined && p.f !== lastFeed) {
      parts.push("F" + p.f.toFixed(0));
      lastFeed = p.f;
    }
    lines.push(parts.join(" "));
  }

  lines.push("(Conic fretboard surfacing — rainbow transitions)");
  lines.push("G90 G94 G17");
  lines.push("G21");
  lines.push("G53 G0 Z" + fmt(params.safe_z + 20));
  lines.push("M3 S" + Math.round(params.spindle_rpm));
  rapid({ z: params.safe_z });

  const rows = collectRows(fb, tool, params);
  const R = tool.diameter / 2;
  if (rows.length === 0) {
    lines.push("M5"); lines.push("M30");
    return { text: lines.join("\n") + "\n", rows, arcs };
  }

  for (let i = 0; i < rows.length; i++) {
    const row = rows[i]!;
    const first = row[0]!;
    if (i === 0) {
      rapid({ x: first[0], y: first[1] });
      feed({ z: first[2], f: params.feed_z });
    }
    for (let k = 1; k < row.length; k++) {
      const pt = row[k]!;
      feed({ x: pt[0], y: pt[1], z: pt[2], f: params.feed_xy });
    }
    if (i + 1 >= rows.length) break;
    const next = rows[i + 1]!;
    const end = row[row.length - 1]!;
    const start = next[0]!;
    const sameSide = (end[1] >= 0) === (start[1] >= 0);
    if (params.rainbow_transitions && sameSide) {
      const signY: 1 | -1 = (end[1] + start[1]) >= 0 ? 1 : -1;
      const hwMax = Math.max(fbHalfWidthAt(fb, end[0]),
                             fbHalfWidthAt(fb, start[0]));
      const minClear = hwMax + R + params.margin_xy + params.rainbow_pad;
      const yT = signY * Math.max(
        Math.abs(end[1]), Math.abs(start[1]), minClear,
      );
      const cx = (end[0] + start[0]) / 2;
      const cy = yT;
      const r = Math.abs(start[0] - end[0]) / 2;
      if (r > 0 && !arcClearsPart(fb, tool, cx, cy, r, params.rainbow_pad)) {
        throw new Error(
          `Rainbow arc would intersect part at center=(` +
          `${cx.toFixed(2)}, ${cy.toFixed(2)}) r=${r.toFixed(2)}. ` +
          `Increase margin or rainbow pad.`,
        );
      }
      const transitZ = Math.max(end[2], start[2]);
      if (transitZ > end[2] + 1e-9) feed({ z: transitZ, f: params.feed_z });
      if (Math.abs(end[1] - yT) > 1e-6) {
        feed({ x: end[0], y: yT, f: params.feed_xy });
      }
      if (r > 0) {
        const cmd = signY > 0 ? "G3" : "G2";
        const iOff = cx - end[0];
        lines.push(
          `${cmd} X${fmt(start[0])} Y${fmt(yT)} ` +
          `I${fmt(iOff)} J0.000 F${params.feed_xy.toFixed(0)}`,
        );
        lastFeed = params.feed_xy;
        arcs.push({
          x1: end[0], y1: yT, x2: start[0], y2: yT,
          cx, cy, r, signY,
        });
      }
      if (Math.abs(start[1] - yT) > 1e-6) {
        feed({ x: start[0], y: start[1], f: params.feed_xy });
      }
      if (transitZ > start[2] + 1e-9) {
        feed({ z: start[2], f: params.feed_z });
      }
    } else {
      rapid({ z: params.safe_z });
      rapid({ x: start[0], y: start[1] });
      feed({ z: start[2], f: params.feed_z });
    }
  }
  rapid({ z: params.safe_z });
  lines.push("M5");
  lines.push("M30");
  return { text: lines.join("\n") + "\n", rows, arcs };
}

// ---------- Preview ----------

function drawPreview(
  canvas: HTMLCanvasElement,
  fb: Fretboard,
  tool: Tool,
  result: GcodeResult,
): void {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const W = canvas.width;
  const H = canvas.height;
  ctx.clearRect(0, 0, W, H);
  const pad = tool.diameter / 2 + 4;
  const yMax = Math.max(fb.heel_width / 2, fb.nut_width / 2) + pad + 8;
  const xMin = -8;
  const xMax = fb.length + 8;
  const yMin = -yMax;
  const yMaxV = yMax;
  const sx = (W - 20) / (xMax - xMin);
  const sy = (H - 20) / (yMaxV - yMin);
  const s = Math.min(sx, sy);
  const ox = 10 - xMin * s;
  const oy = H - 10 + yMin * s;
  const T = (x: number, y: number): [number, number] =>
    [ox + x * s, oy - y * s];

  ctx.save();
  ctx.strokeStyle = "#aaa";
  ctx.setLineDash([4, 3]);
  ctx.lineWidth = 1;
  ctx.beginPath();
  let p: [number, number] = T(0, fb.nut_width / 2);
  ctx.moveTo(p[0], p[1]);
  p = T(fb.length, fb.heel_width / 2);   ctx.lineTo(p[0], p[1]);
  p = T(fb.length, -fb.heel_width / 2);  ctx.lineTo(p[0], p[1]);
  p = T(0, -fb.nut_width / 2);           ctx.lineTo(p[0], p[1]);
  ctx.closePath();
  ctx.stroke();
  ctx.restore();

  ctx.strokeStyle = "#1f77b4";
  ctx.lineWidth = 0.5;
  ctx.beginPath();
  for (const row of result.rows) {
    if (row.length < 2) continue;
    const first = row[0]!;
    let q = T(first[0], first[1]);
    ctx.moveTo(q[0], q[1]);
    for (let k = 1; k < row.length; k++) {
      const pt = row[k]!;
      q = T(pt[0], pt[1]);
      ctx.lineTo(q[0], q[1]);
    }
  }
  ctx.stroke();

  ctx.strokeStyle = "#d62728";
  ctx.lineWidth = 1.0;
  for (const a of result.arcs) {
    const [cx, cy] = T(a.cx, a.cy);
    const r = a.r * s;
    ctx.beginPath();
    if (a.signY > 0) ctx.arc(cx, cy, r, Math.PI, 0, true);
    else             ctx.arc(cx, cy, r, Math.PI, 0, false);
    ctx.stroke();
  }

  ctx.fillStyle = "#888";
  ctx.font = "11px ui-monospace, monospace";
  const bar = 50;
  const bx = W - bar * s - 14;
  const by = H - 14;
  ctx.fillRect(bx, by, bar * s, 2);
  ctx.fillText(bar + " mm", bx, by - 4);
}

// ---------- UI wiring ----------

interface FormCfg {
  fb: Fretboard;
  tool: Tool;
  params: CamParams;
}

function readForm(): FormCfg {
  const f = document.getElementById("controls") as HTMLFormElement | null;
  if (!f) throw new Error("controls form missing");
  const num = (k: string): number => {
    const el = f.elements.namedItem(k) as HTMLInputElement | null;
    if (!el) throw new Error(`field ${k} missing`);
    return parseFloat(el.value);
  };
  const kindEl = f.elements.namedItem("kind") as HTMLSelectElement;
  const rainbowEl =
    f.elements.namedItem("rainbow_transitions") as HTMLInputElement;
  return {
    fb: {
      length: num("length"),
      nut_width: num("nut_width"),
      heel_width: num("heel_width"),
      radius_nut: num("radius_nut"),
      radius_heel: num("radius_heel"),
      z_crown: num("z_crown"),
    },
    tool: {
      diameter: num("diameter"),
      kind: kindEl.value as ToolKind,
    },
    params: {
      stepover: num("stepover"),
      sample_step: num("sample_step"),
      safe_z: num("safe_z"),
      feed_xy: num("feed_xy"),
      feed_z: num("feed_z"),
      spindle_rpm: num("spindle_rpm"),
      margin_xy: num("margin_xy"),
      rainbow_pad: num("rainbow_pad"),
      rainbow_transitions: rainbowEl.checked,
    },
  };
}

let lastResult: GcodeResult | null = null;

function run(): void {
  const stats = document.getElementById("stats");
  const err = document.getElementById("error");
  const pre = document.getElementById("gcode");
  const dl = document.getElementById("download") as HTMLButtonElement | null;
  if (!stats || !err || !pre || !dl) return;
  err.innerHTML = "";
  err.className = "row";
  stats.textContent = "Computing…";
  const t0 = performance.now();
  let cfg: FormCfg;
  let result: GcodeResult;
  try {
    cfg = readForm();
    result = makeGcode(cfg.fb, cfg.tool, cfg.params);
  } catch (e) {
    err.className = "row err";
    err.textContent = (e as Error).message;
    stats.textContent = "";
    pre.textContent = "—";
    dl.disabled = true;
    return;
  }
  const ms = (performance.now() - t0).toFixed(0);
  lastResult = result;
  const nLines = result.text.split("\n").length;
  const nArcs = result.arcs.length;
  const nCutPts = result.rows.reduce((a, r) => a + r.length, 0);
  stats.textContent =
    `${nLines} lines · ${result.rows.length} rows · ${nCutPts} cut pts ` +
    `· ${nArcs} rainbow arcs · ${ms} ms`;
  pre.textContent = result.text.split("\n").slice(0, 200).join("\n");
  dl.disabled = false;
  const canvas =
    document.getElementById("preview") as HTMLCanvasElement | null;
  if (canvas) drawPreview(canvas, cfg.fb, cfg.tool, result);
}

function download(): void {
  if (!lastResult) return;
  const blob = new Blob([lastResult.text], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "fretboard.nc";
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 0);
}

document.getElementById("run")?.addEventListener("click", run);
document.getElementById("download")?.addEventListener("click", download);
window.addEventListener("DOMContentLoaded", run);
