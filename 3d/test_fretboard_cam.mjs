// Smoke-test the compiled TypeScript output for the conic fretboard
// CAM module. Loads ./fretboard_cam.js into a vm context (no DOM
// required: the source guards UI wiring behind `typeof document`).
//
// Run with: node test_fretboard_cam.mjs
//
// Mirrors the assertions in test_conic_fretboard_cam.py so the JS
// behavior stays in lock-step with the Python reference.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const js = readFileSync(resolve(here, "fretboard_cam.js"), "utf8");

const ctx = {
  Math, Date, JSON, console, performance: { now: () => Date.now() },
};
vm.createContext(ctx);
vm.runInContext(js, ctx);

const {
  makeGcode, arcClearsPart, fbSurfaceZ, fbHalfWidthAt,
  fbRadiusAt, safeTipZ, collectRows,
} = ctx;

function approx(a, b, eps = 1e-6) {
  if (Math.abs(a - b) > eps) throw new Error(`${a} not ≈ ${b}`);
}
function assert(cond, msg) { if (!cond) throw new Error(msg); }

const fb = {
  length: 400, nut_width: 43, heel_width: 57,
  radius_nut: 240, radius_heel: 400, z_crown: 27,
};
const tool = { diameter: 6, kind: "ball" };
const params = {
  stepover: 20, sample_step: 1.0, safe_z: 10,
  feed_xy: 1500, feed_z: 500, spindle_rpm: 18000,
  margin_xy: 2.0, rainbow_pad: 1.0, rainbow_transitions: true,
};

// Surface math.
approx(fbRadiusAt(fb, 0), 240);
approx(fbRadiusAt(fb, 400), 400);
approx(fbRadiusAt(fb, 200), 320);
approx(fbSurfaceZ(fb, 200, 0), 27);
assert(fbSurfaceZ(fb, 200, 0) > fbSurfaceZ(fb, 200, 10),
       "surface should be convex (drop off in Y)");
assert(fbSurfaceZ(fb, -1, 0) === -Infinity, "off-board returns -Infinity");

// Tighter nut radius => deeper drop at same Y than at the heel.
const dropNut = 27 - fbSurfaceZ(fb, 0, 15);
const dropHeel = 27 - fbSurfaceZ(fb, 400, 15);
assert(dropNut > dropHeel && dropHeel > 0,
       `nut drop ${dropNut} should exceed heel drop ${dropHeel}`);

// Ball-end tangent at crown.
approx(safeTipZ(fb, tool, 200, 0, 0.25), 27, 0.01);

// Exhaustive ball-vs-surface check at one position.
{
  const xc = 200, yc = 5;
  const tip = safeTipZ(fb, tool, xc, yc, 0.25);
  const R = tool.diameter / 2;
  const R2 = R * R;
  const step = 0.2;
  const n = Math.floor(R / step);
  for (let i = -n; i <= n; i++) {
    for (let j = -n; j <= n; j++) {
      const dx = i * step, dy = j * step;
      const dd = dx * dx + dy * dy;
      if (dd > R2) continue;
      const sz = fbSurfaceZ(fb, xc + dx, yc + dy);
      if (sz === -Infinity) continue;
      const ballZ = tip + R - Math.sqrt(R2 - dd);
      assert(ballZ >= sz - 1e-3,
             `ball intersects surface at dx=${dx} dy=${dy}: ` +
             `ball=${ballZ.toFixed(4)} surface=${sz.toFixed(4)}`);
    }
  }
}

// Arc boundary check positive + negative cases.
assert(arcClearsPart(fb, tool, 200, 35, 5, 1.0),
       "arc safely outside the part must pass");
const hwMid = fbHalfWidthAt(fb, 200);
assert(!arcClearsPart(fb, tool, 200, hwMid + 1, 5, 0.5),
       "arc that dips into the part must fail");

// collectRows zigzag invariant: consecutive row endpoints share a side.
const rows = collectRows(fb, tool, params);
assert(rows.length >= 4, "expected multiple cutting rows");
for (let i = 0; i < rows.length - 1; i++) {
  const endY = rows[i][rows[i].length - 1][1];
  const startY = rows[i + 1][0][1];
  assert((endY > 0) === (startY > 0),
         `row ${i}→${i + 1} endpoints on opposite sides: ` +
         `${endY.toFixed(2)} vs ${startY.toFixed(2)}`);
}

// Full G-code program: arcs emitted, both rotations, every arc clears.
const res = makeGcode(fb, tool, params);
const lines = res.text.split("\n");
const g2 = lines.filter(l => l.startsWith("G2 ")).length;
const g3 = lines.filter(l => l.startsWith("G3 ")).length;
assert(g2 > 0 && g3 > 0, `expected G2 and G3 arcs, got G2=${g2} G3=${g3}`);
assert(res.arcs.length === res.rows.length - 1,
       `expected ${res.rows.length - 1} arcs, got ${res.arcs.length}`);

// Re-parse every emitted arc and re-verify against the boundary.
let prevX = 0, prevY = 0;
for (const ln of lines) {
  if (!/^[GM]/.test(ln)) continue;
  const toks = {};
  for (const t of ln.split(" ").slice(1)) {
    if (t && /[A-Z]/.test(t[0])) toks[t[0]] = parseFloat(t.slice(1));
  }
  if (ln.startsWith("G2 ") || ln.startsWith("G3 ")) {
    const i = toks.I ?? 0, j = toks.J ?? 0;
    const cx = prevX + i, cy = prevY + j;
    const r = Math.hypot(i, j);
    assert(arcClearsPart(fb, tool, cx, cy, r, 0.0),
           `arc violates boundary: ${ln}`);
  }
  if (toks.X !== undefined) prevX = toks.X;
  if (toks.Y !== undefined) prevY = toks.Y;
}

// Rainbow disabled => no G2/G3 lines, several safe-Z rapids.
const noArc = makeGcode(fb, tool,
  { ...params, rainbow_transitions: false });
assert(noArc.arcs.length === 0, "rainbow disabled should emit no arcs");
const arcLines = noArc.text.split("\n")
  .filter(l => l.startsWith("G2 ") || l.startsWith("G3 "));
assert(arcLines.length === 0, "rainbow disabled should produce no G2/G3");

console.log(
  `PASS  rows=${res.rows.length} arcs=${res.arcs.length} ` +
  `lines=${lines.length}`,
);
