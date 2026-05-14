"""Tests for conic_fretboard_cam."""

from __future__ import annotations

import math

import pytest

from conic_fretboard_cam import (
    CamParams,
    ConicFretboard,
    Tool,
    _arc_clears_part,
    collect_rows,
    generate_gcode,
    raster_positions,
    safe_tip_z,
)


FB = ConicFretboard(
    length=400.0,
    nut_width=43.0,
    heel_width=57.0,
    radius_nut=240.0,
    radius_heel=400.0,
    z_crown=27.0,
)


def test_radius_interpolates_linearly():
    assert FB.radius_at(0.0) == pytest.approx(240.0)
    assert FB.radius_at(FB.length) == pytest.approx(400.0)
    assert FB.radius_at(FB.length / 2) == pytest.approx(320.0)


def test_crown_height_is_constant():
    for x in (0.0, 50.0, 200.0, FB.length):
        assert FB.surface_z(x, 0.0) == pytest.approx(FB.z_crown, abs=1e-9)


def test_edges_drop_more_at_nut_than_heel_for_same_y():
    # Tighter radius at the nut produces a deeper drop at the same Y
    # offset. (Edge-to-edge comparison is confounded by the width taper
    # since the heel is wider.)
    y = 15.0
    drop_nut = FB.z_crown - FB.surface_z(0.0, y)
    drop_heel = FB.z_crown - FB.surface_z(FB.length, y)
    assert drop_nut > drop_heel > 0


def test_surface_is_upper_branch_of_circle():
    x = 100.0
    y = 10.0
    r = FB.radius_at(x)
    expected = FB.z_crown - r + math.sqrt(r * r - y * y)
    assert FB.surface_z(x, y) == pytest.approx(expected)


def test_surface_is_convex_y_drops_off():
    x = 200.0
    z_center = FB.surface_z(x, 0.0)
    z_off = FB.surface_z(x, 10.0)
    assert z_center > z_off


def test_offboard_returns_neg_inf():
    assert FB.surface_z(-1.0, 0.0) == float("-inf")
    assert FB.surface_z(FB.length + 1.0, 0.0) == float("-inf")
    assert FB.surface_z(10.0, 1000.0) == float("-inf")


def test_flat_tool_clearance_at_crown_matches_surface():
    tool = Tool(diameter=6.0, kind="flat")
    z = safe_tip_z(FB, tool, xc=200.0, yc=0.0, sample_step=0.25)
    # Flat tool tip = max surface Z under footprint. At the crown the
    # surface is highest near Y=0 (lower branch peaks toward y=0).
    assert z == pytest.approx(FB.surface_z(200.0, 0.0), abs=0.01)


def test_ball_tool_clears_surface_everywhere():
    """For every sample under the tool footprint, the ball must sit
    on or above the surface when the tip is set by safe_tip_z."""
    tool = Tool(diameter=6.0, kind="ball")
    xc, yc = 200.0, 5.0
    tip = safe_tip_z(FB, tool, xc, yc, sample_step=0.25)
    R = tool.radius
    R2 = R * R
    step = 0.2
    n = int(R / step)
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            dx, dy = i * step, j * step
            dd = dx * dx + dy * dy
            if dd > R2:
                continue
            sz = FB.surface_z(xc + dx, yc + dy)
            if sz == float("-inf"):
                continue
            ball_z = tip + R - math.sqrt(R2 - dd)
            # Allow a small tolerance for the coarser inner grid.
            assert ball_z >= sz - 1e-3, (
                f"tool intersects at dx={dx}, dy={dy}: "
                f"ball={ball_z:.4f} surface={sz:.4f}"
            )


def test_ball_tool_at_crown_tangent_height():
    """At the crown center (peak of the surface), the safe tip is the
    surface Z exactly because the ball's deepest point sits there."""
    tool = Tool(diameter=4.0, kind="ball")
    z = safe_tip_z(FB, tool, xc=200.0, yc=0.0, sample_step=0.1)
    assert z == pytest.approx(FB.surface_z(200.0, 0.0), abs=0.01)


def test_safe_tip_z_lifts_for_tighter_radius():
    """Same tool, same Y. The nut end has a tighter cross-section, so
    the surface peaks higher relative to the tool's edge samples,
    pushing the safe tip Z down (more material remains to cut)."""
    tool = Tool(diameter=8.0, kind="ball")
    z_nut = safe_tip_z(FB, tool, xc=0.0, yc=15.0, sample_step=0.5)
    z_heel = safe_tip_z(FB, tool, xc=FB.length, yc=15.0, sample_step=0.5)
    assert z_nut < z_heel  # tighter radius at nut → deeper at Y=15


def test_raster_visits_full_x_range():
    params = CamParams(stepover=10.0, sample_step=1.0, margin_xy=0.0)
    tool = Tool(diameter=6.0, kind="ball")
    xs = sorted({round(x, 3) for x, _, _ in raster_positions(FB, tool, params)})
    assert xs[0] == pytest.approx(0.0)
    assert xs[-1] >= FB.length


def test_raster_alternates_direction():
    params = CamParams(stepover=50.0, sample_step=1.0, margin_xy=0.0)
    tool = Tool(diameter=6.0, kind="ball")
    rows: dict[float, list[float]] = {}
    for x, y, _ in raster_positions(FB, tool, params):
        rows.setdefault(round(x, 3), []).append(y)
    ordered_xs = sorted(rows.keys())
    # Adjacent rows should sweep in opposite Y directions.
    for i in range(len(ordered_xs) - 1):
        ys_a = rows[ordered_xs[i]]
        ys_b = rows[ordered_xs[i + 1]]
        sign_a = ys_a[-1] - ys_a[0]
        sign_b = ys_b[-1] - ys_b[0]
        assert sign_a * sign_b < 0


def test_generate_gcode_emits_program():
    params = CamParams(stepover=20.0, sample_step=1.0, safe_z=10.0,
                       margin_xy=0.0)
    tool = Tool(diameter=6.0, kind="ball")
    text = generate_gcode(FB, tool, params)
    assert "G21" in text
    assert "M3 S18000" in text
    assert "M30" in text
    # Must include some XY feed moves.
    feed_lines = [ln for ln in text.splitlines() if ln.startswith("G1 ")]
    assert len(feed_lines) > 20
    # And rapids on entry.
    assert any(ln.startswith("G0 ") for ln in text.splitlines())


def test_collect_rows_alternates_y_endpoint_sign():
    """Each consecutive pair of cutting rows must end on the same side
    of the centerline they started — zigzag invariant required for the
    rainbow arc construction."""
    params = CamParams(stepover=20.0, sample_step=1.0, margin_xy=2.0)
    tool = Tool(diameter=6.0, kind="ball")
    rows = collect_rows(FB, tool, params)
    assert len(rows) >= 4
    for i in range(len(rows) - 1):
        end_y = rows[i][-1][1]
        start_y = rows[i + 1][0][1]
        # Both endpoints should sit on the same side: this is what
        # makes the rainbow stay outside the part on one side.
        assert (end_y > 0) == (start_y > 0), (
            f"row {i}→{i + 1}: end_y={end_y}, start_y={start_y}"
        )


def test_arc_clears_part_when_outside():
    # Center well past the heel-side edge of the part.
    tool = Tool(diameter=6.0, kind="ball")
    cx = FB.length / 2
    cy = FB.heel_width / 2 + tool.radius + 5.0
    radius = 5.0
    assert _arc_clears_part(FB, tool, cx, cy, radius, pad=0.5)


def test_arc_flags_intersection_when_inside():
    tool = Tool(diameter=6.0, kind="ball")
    # Center sitting right at the edge: with a non-trivial radius the
    # arc will dip into the part.
    cx = FB.length / 2
    cy = FB.half_width_at(cx) + tool.radius - 0.1
    radius = 5.0
    assert not _arc_clears_part(FB, tool, cx, cy, radius, pad=0.5)


def test_gcode_with_rainbow_emits_arcs():
    params = CamParams(
        stepover=20.0, sample_step=1.0, margin_xy=2.0,
        rainbow_transitions=True, rainbow_pad=1.0,
    )
    tool = Tool(diameter=6.0, kind="ball")
    text = generate_gcode(FB, tool, params)
    arc_lines = [
        ln for ln in text.splitlines()
        if ln.startswith("G2 ") or ln.startswith("G3 ")
    ]
    assert len(arc_lines) > 0
    # G2 (CW) on the negative side, G3 (CCW) on the positive side. The
    # zigzag alternates rows, so both flavors should appear.
    assert any(ln.startswith("G2 ") for ln in arc_lines)
    assert any(ln.startswith("G3 ") for ln in arc_lines)


def test_rainbow_arcs_pass_boundary_check():
    """Parse every G2/G3 in the emitted program and re-verify it
    clears the part. End-to-end guarantee."""
    params = CamParams(
        stepover=10.0, sample_step=0.5, margin_xy=2.0,
        rainbow_transitions=True, rainbow_pad=1.0,
    )
    tool = Tool(diameter=6.0, kind="ball")
    text = generate_gcode(FB, tool, params)
    prev_x = prev_y = 0.0
    for ln in text.splitlines():
        if ln.startswith(("G0 ", "G1 ", "G2 ", "G3 ")):
            tokens = {}
            for tok in ln.split()[1:]:
                if tok and tok[0].isalpha():
                    tokens[tok[0]] = float(tok[1:])
            if ln.startswith(("G2 ", "G3 ")):
                i = tokens.get("I", 0.0)
                j = tokens.get("J", 0.0)
                cx = prev_x + i
                cy = prev_y + j
                radius = math.hypot(i, j)
                assert _arc_clears_part(
                    FB, tool, cx, cy, radius, pad=0.0
                ), f"arc violates boundary: {ln}"
            prev_x = tokens.get("X", prev_x)
            prev_y = tokens.get("Y", prev_y)


def test_gcode_without_rainbow_uses_safe_z_rapids():
    params = CamParams(
        stepover=20.0, sample_step=1.0, margin_xy=2.0,
        rainbow_transitions=False,
    )
    tool = Tool(diameter=6.0, kind="ball")
    text = generate_gcode(FB, tool, params)
    arc_lines = [
        ln for ln in text.splitlines()
        if ln.startswith("G2 ") or ln.startswith("G3 ")
    ]
    assert arc_lines == []
    # Several rapid-up-to-safe lines for row transitions.
    rapid_z_lines = [
        ln for ln in text.splitlines()
        if ln.startswith("G0 ") and "Z" in ln
    ]
    assert len(rapid_z_lines) > 4


def test_gcode_has_no_negative_z_through_table():
    """Sanity: no programmed Z below an extreme negative — catches sign
    flips. The surface sits near z=27 so Z should be in that ballpark."""
    params = CamParams(stepover=20.0, sample_step=1.0, safe_z=10.0)
    tool = Tool(diameter=6.0, kind="ball")
    text = generate_gcode(FB, tool, params)
    for ln in text.splitlines():
        if "Z" not in ln or ln.startswith("("):
            continue
        # Crude parse: pull the Z token.
        for tok in ln.split():
            if tok.startswith("Z"):
                z = float(tok[1:])
                assert z > -100.0, f"suspicious Z in line: {ln}"
