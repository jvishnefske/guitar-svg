"""Generate G-code for a compound-radius (conic) fretboard.

The fretboard surface is a section of a cone: the cross-sectional
radius varies linearly from R_nut at X=0 to R_heel at X=fb_length.
The crown (Y=0) stays at a constant Z; edges drop further at the
nut (tight radius) than at the heel (flat radius).

Toolpaths are computed by top-down projection sampling: at each
(Xc, Yc) tool position, we sample the surface under the tool's
footprint and lift the tool tip to whichever Z keeps the entire
tool body above the surface. This works for both ball-nose and
flat endmills without needing a full 3D collision check.

Stand-alone module — no FreeCAD dependency. Run with:
    python3 conic_fretboard_cam.py
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterator, Literal


@dataclass(frozen=True)
class ConicFretboard:
    """Compound-radius fretboard surface in mm.

    The neck runs along +X: nut at X=0, heel at X=length.
    Y is across the width (centered at Y=0).
    Z is vertical; the crown at Y=0 sits at z_crown for all X.
    """
    length: float            # nut-to-heel distance (mm)
    nut_width: float         # full width at nut (mm)
    heel_width: float        # full width at heel (mm)
    radius_nut: float        # cross-section radius at nut (mm)
    radius_heel: float       # cross-section radius at heel (mm)
    z_crown: float = 0.0     # Z of the crown line (Y=0) along the neck

    def radius_at(self, x: float) -> float:
        t = max(0.0, min(1.0, x / self.length))
        return self.radius_nut + (self.radius_heel - self.radius_nut) * t

    def half_width_at(self, x: float) -> float:
        t = max(0.0, min(1.0, x / self.length))
        nut_h = self.nut_width / 2.0
        heel_h = self.heel_width / 2.0
        return nut_h + (heel_h - nut_h) * t

    def surface_z(self, x: float, y: float) -> float:
        """Z of the fretboard surface at (x, y).

        Returns -inf outside the fretboard plan-view outline so the
        clearance sampler treats off-board points as not constraining.
        """
        if x < 0.0 or x > self.length:
            return float("-inf")
        if abs(y) > self.half_width_at(x):
            return float("-inf")
        r = self.radius_at(x)
        # Convex fretboard: arc center sits at z = z_crown - r (below the
        # surface). The upper branch of the circle gives the crown at Y=0
        # and drops off toward the edges.
        under = r * r - y * y
        if under <= 0.0:
            return float("-inf")
        return self.z_crown - r + math.sqrt(under)

    def z_at_edges(self, x: float) -> float:
        """Z of the surface at the fretboard edge (Y = +/- half_width)."""
        return self.surface_z(x, self.half_width_at(x))


@dataclass(frozen=True)
class Tool:
    """End mill geometry.

    kind="flat": flat-bottom endmill, tip is at tool_tip_z over the
        full footprint of radius `radius`.
    kind="ball": ball-nose, ball center is at tool_tip_z + radius;
        the ball surface bulges down to tool_tip_z at the axis.
    """
    diameter: float
    kind: Literal["flat", "ball"] = "ball"

    @property
    def radius(self) -> float:
        return self.diameter / 2.0


@dataclass(frozen=True)
class CamParams:
    """CAM parameters in mm and mm/min."""
    stepover: float = 1.0            # raster row spacing (X)
    sample_step: float = 0.5         # in-footprint sample spacing
    safe_z: float = 10.0             # rapid-travel Z above stock
    feed_xy: float = 1500.0          # mm/min
    feed_z: float = 500.0            # mm/min
    spindle_rpm: float = 18000.0
    margin_xy: float = 0.0           # extend toolpath this far past edges
    edge_clip: bool = True           # clip Y travel to fretboard outline
    rainbow_transitions: bool = True # use half-circle arcs between rows
    rainbow_pad: float = 1.0         # extra clearance past part boundary (mm)


def safe_tip_z(
    fb: ConicFretboard,
    tool: Tool,
    xc: float,
    yc: float,
    sample_step: float,
) -> float:
    """Lowest tip Z that keeps the tool above the surface at (xc, yc).

    Samples a square grid inside the tool's circular footprint and,
    for each sample, computes the tip Z required so the tool body
    sits exactly tangent to the surface at that sample. The max over
    samples is the safe tip Z.
    """
    R = tool.radius
    best = float("-inf")
    # +/- R grid, inclusive endpoints.
    n = max(1, int(math.ceil(R / sample_step)))
    samples = [i * sample_step for i in range(-n, n + 1)]
    R2 = R * R
    for dx in samples:
        for dy in samples:
            dd = dx * dx + dy * dy
            if dd > R2:
                continue
            sz = fb.surface_z(xc + dx, yc + dy)
            if sz == float("-inf"):
                continue
            if tool.kind == "flat":
                # Flat bottom: tip = surface height directly.
                tip_required = sz
            else:
                # Ball: tip = sz - (R - sqrt(R^2 - dd))
                # because the ball surface at offset (dx,dy) is at
                # z = tip + R - sqrt(R^2 - dd).
                tip_required = sz - (R - math.sqrt(R2 - dd))
            if tip_required > best:
                best = tip_required
    return best


@dataclass
class GCodeWriter:
    """Minimal absolute-mode metric G-code writer."""
    lines: list[str] = field(default_factory=list)
    _last_feed: float | None = None

    def header(self, params: CamParams) -> None:
        self.lines += [
            "(Conic fretboard surfacing)",
            "G90 G94 G17",   # absolute, units/min feed, XY plane
            "G21",           # metric
            "G53 G0 Z" + f"{params.safe_z + 20.0:.3f}",  # machine-coord rapid up
            f"M3 S{int(params.spindle_rpm)}",
        ]

    def footer(self, params: CamParams) -> None:
        self.lines += [
            f"G0 Z{params.safe_z:.3f}",
            "M5",
            "M30",
        ]

    def rapid(self, *, x: float | None = None, y: float | None = None,
              z: float | None = None) -> None:
        parts = ["G0"]
        if x is not None: parts.append(f"X{x:.3f}")
        if y is not None: parts.append(f"Y{y:.3f}")
        if z is not None: parts.append(f"Z{z:.3f}")
        self.lines.append(" ".join(parts))

    def feed(self, *, x: float | None = None, y: float | None = None,
             z: float | None = None, f: float | None = None) -> None:
        parts = ["G1"]
        if x is not None: parts.append(f"X{x:.3f}")
        if y is not None: parts.append(f"Y{y:.3f}")
        if z is not None: parts.append(f"Z{z:.3f}")
        if f is not None and f != self._last_feed:
            parts.append(f"F{f:.0f}")
            self._last_feed = f
        self.lines.append(" ".join(parts))

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def _y_extent(fb: ConicFretboard, x: float, tool: Tool,
              params: CamParams) -> tuple[float, float]:
    """Y range to sweep at column x. Adds tool radius + margin."""
    hw = fb.half_width_at(x)
    pad = tool.radius + params.margin_xy
    if not params.edge_clip:
        # Use the widest cross-section so the sweep covers the whole board.
        hw = max(fb.nut_width, fb.heel_width) / 2.0
    return (-hw - pad, hw + pad)


def raster_positions(
    fb: ConicFretboard,
    tool: Tool,
    params: CamParams,
) -> Iterator[tuple[float, float, bool]]:
    """Yield (x, y, new_row) for a zigzag raster.

    Rows step in X by params.stepover. Within a row, Y sweeps between
    the column extents in alternating directions.
    """
    x = -params.margin_xy
    end_x = fb.length + params.margin_xy
    direction = 1
    while x <= end_x + 1e-9:
        y0, y1 = _y_extent(fb, max(0.0, min(fb.length, x)), tool, params)
        if direction < 0:
            y0, y1 = y1, y0
        n = max(1, int(math.ceil(abs(y1 - y0) / params.stepover)))
        first = True
        for i in range(n + 1):
            t = i / n
            y = y0 + (y1 - y0) * t
            yield x, y, first
            first = False
        x += params.stepover
        direction = -direction


def _arc_clears_part(
    fb: ConicFretboard,
    tool: Tool,
    cx: float,
    cy: float,
    radius: float,
    pad: float,
    samples: int = 24,
) -> bool:
    """Check the half-circle of the given center/radius clears the part.

    Samples the arc in XY and verifies each point sits outside the
    fretboard outline by at least `tool.radius + pad` in Y at its X.
    """
    sign_y = 1.0 if cy > 0 else -1.0
    for i in range(samples + 1):
        t = i / samples
        # Half-circle parametrization. The arc apex is at the side away
        # from the centerline; endpoints are on the diameter through cx.
        theta = math.pi * t
        x = cx - radius * math.cos(theta)
        y = cy + sign_y * radius * math.sin(theta)
        if x < 0.0 or x > fb.length:
            continue  # past nut/heel, no part to clip
        hw = fb.half_width_at(x)
        if abs(y) < hw + tool.radius + pad:
            return False
    return True


def collect_rows(
    fb: ConicFretboard,
    tool: Tool,
    params: CamParams,
) -> list[list[tuple[float, float, float]]]:
    """Run the raster and return [(x, y, tip_z), ...] grouped by row.

    Off-board samples (tip_z == -inf) are dropped; rows with no cutting
    points are dropped entirely.
    """
    rows: list[list[tuple[float, float, float]]] = []
    current: list[tuple[float, float, float]] = []
    for x, y, new_row in raster_positions(fb, tool, params):
        if new_row and current:
            rows.append(current)
            current = []
        z = safe_tip_z(fb, tool, x, y, params.sample_step)
        if z == float("-inf"):
            continue
        current.append((x, y, z))
    if current:
        rows.append(current)
    return rows


def _emit_rainbow(
    gc: "GCodeWriter",
    fb: ConicFretboard,
    tool: Tool,
    params: CamParams,
    end_pt: tuple[float, float, float],
    start_pt: tuple[float, float, float],
) -> None:
    """Emit a half-circle XY arc transitioning between two cutting rows.

    Both end_pt and start_pt must sit at the fretboard edge on the same
    side of the centerline (zigzag invariant). The arc swings outward
    so it stays in air past the part boundary.
    """
    x1, y1, z1 = end_pt
    x2, y2, z2 = start_pt
    if (y1 >= 0) != (y2 >= 0):
        raise ValueError("rainbow arc requires same-side endpoints")
    sign_y = 1.0 if (y1 + y2) >= 0 else -1.0
    # Transit Y must lie outside the part at every X along the arc.
    hw_max = max(fb.half_width_at(x1), fb.half_width_at(x2))
    min_clear = hw_max + tool.radius + params.margin_xy + params.rainbow_pad
    y_transit = sign_y * max(abs(y1), abs(y2), min_clear)
    # Arc is a half-circle whose diameter is the chord (x1,y_t)→(x2,y_t).
    cx = (x1 + x2) / 2.0
    cy = y_transit
    radius = abs(x2 - x1) / 2.0
    if radius <= 0.0:
        # Degenerate (rows at same X) — just feed across in Y.
        gc.feed(x=x2, y=y2, z=z2, f=params.feed_xy)
        return
    if not _arc_clears_part(fb, tool, cx, cy, radius, params.rainbow_pad):
        raise RuntimeError(
            f"rainbow arc would intersect part boundary at "
            f"center=({cx:.3f},{cy:.3f}) r={radius:.3f}"
        )
    # Constant transit Z = higher of the two endpoints, so we never push
    # into material during the transition.
    transit_z = max(z1, z2)
    if transit_z > z1:
        gc.feed(z=transit_z, f=params.feed_z)
    # Lead-out: move Y from y1 to y_transit at the row's X.
    if abs(y1 - y_transit) > 1e-6:
        gc.feed(x=x1, y=y_transit, f=params.feed_xy)
    # Arc itself: CCW (G3) above centerline, CW (G2) below.
    cmd = "G3" if sign_y > 0 else "G2"
    i_off = cx - x1
    j_off = 0.0
    gc.lines.append(
        f"{cmd} X{x2:.3f} Y{y_transit:.3f} "
        f"I{i_off:.3f} J{j_off:.3f} F{params.feed_xy:.0f}"
    )
    gc._last_feed = params.feed_xy
    # Lead-in: move Y from y_transit to y2 at the next row's X.
    if abs(y2 - y_transit) > 1e-6:
        gc.feed(x=x2, y=y2, f=params.feed_xy)
    if transit_z > z2:
        gc.feed(z=z2, f=params.feed_z)


def generate_gcode(
    fb: ConicFretboard,
    tool: Tool,
    params: CamParams,
) -> str:
    """Build the G-code program for a conic fretboard surfacing pass.

    If `params.rainbow_transitions` is set, row-to-row moves are
    replaced with half-circle XY arcs that swing past the part edge.
    Otherwise the tool lifts to safe_z and rapid-travels between rows.
    """
    gc = GCodeWriter()
    gc.header(params)
    gc.rapid(z=params.safe_z)
    rows = collect_rows(fb, tool, params)
    if not rows:
        gc.footer(params)
        return gc.text()
    for i, row in enumerate(rows):
        first_x, first_y, first_z = row[0]
        if i == 0:
            gc.rapid(x=first_x, y=first_y)
            gc.feed(z=first_z, f=params.feed_z)
        for x, y, z in row[1:]:
            gc.feed(x=x, y=y, z=z, f=params.feed_xy)
        if i + 1 < len(rows):
            next_row = rows[i + 1]
            end_pt = row[-1]
            start_pt = next_row[0]
            same_side = (end_pt[1] >= 0) == (start_pt[1] >= 0)
            if params.rainbow_transitions and same_side:
                _emit_rainbow(gc, fb, tool, params, end_pt, start_pt)
            else:
                # Fall back to safe-Z rapid (e.g., first/last row asymmetry).
                gc.rapid(z=params.safe_z)
                gc.rapid(x=start_pt[0], y=start_pt[1])
                gc.feed(z=start_pt[2], f=params.feed_z)
    gc.rapid(z=params.safe_z)
    gc.footer(params)
    return gc.text()


# 1962 Strat-style default geometry. Numbers chosen to match
# create_neck.py where applicable; radii follow common compound spec.
DEFAULT_FRETBOARD = ConicFretboard(
    length=432.0,        # nut-to-end-of-fretboard (mm)
    nut_width=43.0,      # 1962 Strat nut width
    heel_width=57.15,    # 2.25" at fretboard end
    radius_nut=241.3,    # 9.5"
    radius_heel=406.4,   # 16"
    z_crown=27.0,        # matches BLANK_HEIGHT in create_neck.py
)

DEFAULT_TOOL = Tool(diameter=6.35, kind="ball")   # 1/4" ball-nose

DEFAULT_PARAMS = CamParams(
    stepover=1.0,
    sample_step=0.5,
    safe_z=40.0,
    feed_xy=1500.0,
    feed_z=500.0,
    spindle_rpm=18000.0,
    margin_xy=2.0,
    edge_clip=True,
)


def main() -> None:
    import os
    out_path = os.path.join(os.path.dirname(__file__), "fretboard.nc")
    text = generate_gcode(DEFAULT_FRETBOARD, DEFAULT_TOOL, DEFAULT_PARAMS)
    with open(out_path, "w") as f:
        f.write(text)
    n_lines = text.count("\n")
    print(f"Wrote {out_path}  ({n_lines} lines)")
    print(f"  fretboard: nut R{DEFAULT_FRETBOARD.radius_nut}mm → "
          f"heel R{DEFAULT_FRETBOARD.radius_heel}mm, "
          f"length {DEFAULT_FRETBOARD.length}mm")
    print(f"  tool: {DEFAULT_TOOL.kind} d{DEFAULT_TOOL.diameter}mm")
    print(f"  stepover {DEFAULT_PARAMS.stepover}mm, "
          f"sample {DEFAULT_PARAMS.sample_step}mm")


if __name__ == "__main__":
    main()
