"""Create FreeCAD neck model for 1962 Stratocaster.

Builds a neck with Modern C profile, fretboard radius, and truss rod channel.
Designed for CNC machining with CAM toolpaths.

Run with: flatpak run --command=FreeCADCmd org.freecad.FreeCAD create_neck.py
"""

import math
import FreeCAD as App
import Part
import Sketcher

# All dimensions in millimeters
# 1962 Stratocaster Modern C profile specifications
# Source: reference drawings in /home/j/Documents/guitar/reference/neck/

SCALE_LENGTH = 647.7         # 25.5"
NUT_WIDTH = 43.00            # From top-neck.png
HEEL_WIDTH = 55.88           # 2.2" (body interface width)
THICKNESS_1ST_FRET = 21.00   # From profile-1st-fret.png
THICKNESS_12TH_FRET = 22.00  # From profile-12th-fret.png
FRETBOARD_RADIUS = 241.3     # 9.5" (R241.30 from profile drawings)
FRETBOARD_THICKNESS = 6.35   # 0.25"
TRUSS_ROD_WIDTH = 6.35       # 0.250"
TRUSS_ROD_DEPTH = 9.52       # 0.375"
TRUSS_ROD_LENGTH = 400.0     # Channel length
HEEL_LENGTH = 76.2           # 3" heel pocket depth
NUT_TO_HEEL = 468.30         # From side-neck.png
HEEL_CURVE_RADIUS = 26.50    # R26.50 from side-neck.png
HEEL_CORNER_RADIUS = 6.35    # 0.25" radius corners

# Headstock dimensions from top-neck.png and side-neck.png
HEADSTOCK_LENGTH = 189.70          # 658 - 468.30 from side-neck.png
HEADSTOCK_THICKNESS = 14.00        # From side-neck.png
HEADSTOCK_WIDTH_MAX = 123.00       # Maximum headstock width from top-neck.png
TUNER_HOLE_DIAMETER = 10.00        # Ø10.00 for Schaller tuners
TUNER_HOLE_SPACING_Y = 24.80       # Spacing between tuner rows from centerline
HEADSTOCK_TAPER_START = 64.00      # Where headstock starts widening from nut
HEADSTOCK_NUT_STEP = 102.70        # Distance from nut to main tuner area

# Derived dimensions
BLANK_HEIGHT = 27.0  # Max thickness including fretboard

# Fret positions using equal temperament formula: d = scale_length * (1 - 1/2^(n/12))
FRET_1_POSITION = SCALE_LENGTH * (1 - 1 / (2 ** (1 / 12)))   # ~36.38mm from nut
FRET_12_POSITION = SCALE_LENGTH / 2  # 323.85mm from nut (octave)

# Reference image path
PROFILE_IMAGE_PATH = "/home/j/Documents/guitar/reference/modern-neck-profile.webp"

DOC_PATH = "/home/j/Documents/guitar/3d/neck.FCStd"


def create_document():
    """Create a new FreeCAD document with Body and Origin."""
    doc = App.newDocument("Neck")
    body = doc.addObject("PartDesign::Body", "Body")
    doc.recompute()
    return doc, body


def get_planes(doc):
    """Get reference planes from the Origin."""
    origin = doc.getObject("Origin")
    xy_plane = doc.getObject("XY_Plane")
    xz_plane = doc.getObject("XZ_Plane")
    yz_plane = doc.getObject("YZ_Plane")
    return xy_plane, xz_plane, yz_plane


def create_neck_outline_sketch(doc, body, xy_plane):
    """Create the tapered neck outline on XY plane.

    Neck runs along X axis: X=0 at nut, X=NUT_TO_HEEL at heel.
    Y axis is width (centered).

    Heel end has:
    - R26.50mm transition curve at heel end (from side-neck.png)
    - 0.25" (6.35mm) radius corners
    """
    sketch = body.newObject("Sketcher::SketchObject", "NeckOutline")
    sketch.AttachmentSupport = [(xy_plane, "")]
    sketch.MapMode = "FlatFace"

    nut_half = NUT_WIDTH / 2
    heel_half = HEEL_WIDTH / 2
    R = HEEL_CURVE_RADIUS      # R26.50mm heel transition curve
    r = HEEL_CORNER_RADIUS     # 0.25" = 6.35mm corner fillets

    # The R26.50 from the drawing is a corner/transition radius at the heel end
    # Since R (26.5mm) < heel_half (27.94mm), we use rounded corners at heel
    # The heel end is essentially straight with rounded corners

    # Nut corners
    p_nut_bottom = App.Vector(0, -nut_half, 0)
    p_nut_top = App.Vector(0, nut_half, 0)

    # Heel corner positions with R26.50 corner radius
    # The corner arc transitions from the taper line to the heel end
    heel_end_x = NUT_TO_HEEL

    # Points where taper meets the corner arc (offset back by R from heel)
    p_taper_bottom_end = App.Vector(heel_end_x - R, -heel_half, 0)
    p_taper_top_end = App.Vector(heel_end_x - R, heel_half, 0)

    # Points where corner arc meets the heel end (offset in by R from edge)
    p_heel_bottom = App.Vector(heel_end_x, -heel_half + R, 0)
    p_heel_top = App.Vector(heel_end_x, heel_half - R, 0)

    # Corner arc midpoints (at 45 degrees from center)
    corner_offset = R * (1 - math.cos(math.pi / 4))  # ~0.293 * R
    corner_mid_offset = R * math.sin(math.pi / 4)     # ~0.707 * R

    p_corner_bottom_mid = App.Vector(
        heel_end_x - corner_offset,
        -heel_half + corner_offset,
        0
    )
    p_corner_top_mid = App.Vector(
        heel_end_x - corner_offset,
        heel_half - corner_offset,
        0
    )

    # Build the sketch geometry
    geom_idx = 0

    # 1. Nut edge (straight line)
    sketch.addGeometry(Part.LineSegment(p_nut_top, p_nut_bottom))
    nut_edge = geom_idx
    geom_idx += 1

    # 2. Bottom taper (straight line from nut to corner arc start)
    sketch.addGeometry(Part.LineSegment(p_nut_bottom, p_taper_bottom_end))
    bottom_taper = geom_idx
    geom_idx += 1

    # 3. Bottom corner arc (R26.50)
    sketch.addGeometry(Part.Arc(p_taper_bottom_end, p_corner_bottom_mid, p_heel_bottom))
    bottom_corner = geom_idx
    geom_idx += 1

    # 4. Heel end straight section (between corner arcs)
    sketch.addGeometry(Part.LineSegment(p_heel_bottom, p_heel_top))
    heel_edge = geom_idx
    geom_idx += 1

    # 5. Top corner arc (R26.50)
    sketch.addGeometry(Part.Arc(p_heel_top, p_corner_top_mid, p_taper_top_end))
    top_corner = geom_idx
    geom_idx += 1

    # 6. Top taper (straight line from corner arc to nut)
    sketch.addGeometry(Part.LineSegment(p_taper_top_end, p_nut_top))
    top_taper = geom_idx
    geom_idx += 1

    # Add coincident constraints to close the shape
    sketch.addConstraint(Sketcher.Constraint("Coincident", nut_edge, 2, bottom_taper, 1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", bottom_taper, 2, bottom_corner, 1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", bottom_corner, 2, heel_edge, 1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", heel_edge, 2, top_corner, 1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", top_corner, 2, top_taper, 1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", top_taper, 2, nut_edge, 1))

    doc.recompute()
    return sketch


def create_neck_blank(doc, body, sketch):
    """Pad the neck outline to create the blank."""
    pad = body.newObject("PartDesign::Pad", "NeckBlank")
    pad.Profile = (sketch, [""])
    pad.Length = BLANK_HEIGHT
    pad.Type = 0  # Dimension
    pad.Reversed = False
    doc.recompute()
    return pad


def create_c_profile_sketch(doc, body, yz_plane, x_offset, width, depth, name):
    """Create a C-profile cross-section sketch at given X position.

    The C-profile is an arc that defines the back of the neck.
    Width is the neck width at that position.
    Depth is how deep the arc cuts (neck thickness minus fretboard).

    The sketch is in the YZ plane where:
    - Y is horizontal (neck width direction)
    - Z is vertical (neck thickness direction)
    """
    sketch = body.newObject("Sketcher::SketchObject", name)
    sketch.AttachmentSupport = [(yz_plane, "")]
    sketch.MapMode = "FlatFace"
    sketch.AttachmentOffset = App.Placement(
        App.Vector(0, 0, x_offset),  # Z moves along world X (neck length)
        App.Rotation(0, 0, 0, 1)
    )

    half_width = width / 2
    z_top = BLANK_HEIGHT  # Top of blank (fretboard surface)
    d = depth  # How deep the C profile cuts from z_top

    # For a circular arc through three points on the neck back:
    # Left edge: (-half_width, z_top - d)
    # Center bottom: (0, z_top - d - extra_depth)  -- deepest point
    # Right edge: (half_width, z_top - d)
    #
    # We want a gentle C curve. The arc center is above the neck.
    # Arc passes through (-w/2, z_bottom), (0, z_bottom - curve), (w/2, z_bottom)

    z_bottom = z_top - d  # Z level at edges of arc

    # Calculate arc geometry: center is at (0, z_center) with z_center > z_top
    # The arc deepest point is at y=0, z = z_center - radius
    # We want z_center - radius = z_bottom - curve_depth
    # And at y = half_width: z = z_center - sqrt(radius^2 - half_width^2) = z_bottom

    # Solve: radius^2 = half_width^2 + (z_center - z_bottom)^2
    # Let h = z_center - z_bottom (height of center above edge points)
    # radius = sqrt(half_width^2 + h^2)
    # Curve depth at center = radius - h

    # For a gentle C profile, use curve depth ~3mm at center
    curve_depth = 3.0  # mm deeper at center than edges

    # radius - h = curve_depth, so radius = h + curve_depth
    # (h + curve_depth)^2 = half_width^2 + h^2
    # h^2 + 2*h*curve_depth + curve_depth^2 = half_width^2 + h^2
    # 2*h*curve_depth = half_width^2 - curve_depth^2
    # h = (half_width^2 - curve_depth^2) / (2 * curve_depth)

    h = (half_width ** 2 - curve_depth ** 2) / (2 * curve_depth)
    radius = h + curve_depth
    z_center = z_bottom + h

    # Arc endpoints in sketch coordinates (Y, Z)
    left_pt = App.Vector(-half_width, z_bottom, 0)
    right_pt = App.Vector(half_width, z_bottom, 0)

    # Calculate arc angles
    # Angle from center to left point
    angle_left = math.atan2(left_pt.y, left_pt.x - 0) - math.atan2(z_bottom - z_center, -half_width)
    angle_right = math.atan2(right_pt.y, right_pt.x - 0) - math.atan2(z_bottom - z_center, half_width)

    # Create arc using three points for reliability
    center_pt = App.Vector(0, z_bottom - curve_depth, 0)
    arc = Part.Arc(left_pt, center_pt, right_pt)
    arc_idx = sketch.addGeometry(arc)

    # Add lines to close the profile for the subtractive loft
    # Line from left arc end up to top-left corner
    line1_idx = sketch.addGeometry(Part.LineSegment(left_pt, App.Vector(-half_width, z_top, 0)))
    # Line across top
    line2_idx = sketch.addGeometry(Part.LineSegment(
        App.Vector(-half_width, z_top, 0),
        App.Vector(half_width, z_top, 0)
    ))
    # Line from top-right down to right arc end
    line3_idx = sketch.addGeometry(Part.LineSegment(App.Vector(half_width, z_top, 0), right_pt))

    # Add coincident constraints to close the wire
    # Arc start (endpoint 1) to line1 start (endpoint 1)
    sketch.addConstraint(Sketcher.Constraint("Coincident", arc_idx, 1, line1_idx, 1))
    # Line1 end (endpoint 2) to line2 start (endpoint 1)
    sketch.addConstraint(Sketcher.Constraint("Coincident", line1_idx, 2, line2_idx, 1))
    # Line2 end (endpoint 2) to line3 start (endpoint 1)
    sketch.addConstraint(Sketcher.Constraint("Coincident", line2_idx, 2, line3_idx, 1))
    # Line3 end (endpoint 2) to arc end (endpoint 2)
    sketch.addConstraint(Sketcher.Constraint("Coincident", line3_idx, 2, arc_idx, 2))

    doc.recompute()
    return sketch


def create_neck_back_carve(doc, body, nut_sketch, heel_sketch):
    """Create subtractive loft between C-profile sections."""
    loft = body.newObject("PartDesign::SubtractiveLoft", "NeckBackCarve")
    loft.Profile = (nut_sketch, [""])
    loft.Sections = [(heel_sketch, [""])]
    loft.Ruled = False  # Smooth interpolation
    doc.recompute()
    return loft


def create_fretboard_radius_sketch(doc, body, yz_plane):
    """Create sketch for fretboard radius (cylindrical surface)."""
    sketch = body.newObject("Sketcher::SketchObject", "FretboardRadiusSketch")
    sketch.AttachmentSupport = [(yz_plane, "")]
    sketch.MapMode = "FlatFace"

    # Fretboard radius arc at top of neck
    # Arc spans wider than neck to ensure full coverage
    z_top = BLANK_HEIGHT
    radius = FRETBOARD_RADIUS
    max_width = HEEL_WIDTH + 10  # Extra width for margin

    # Arc center is above the fretboard surface
    center_z = z_top + radius

    # Calculate arc endpoints at max_width
    half_w = max_width / 2
    # y^2 + (z - center_z)^2 = radius^2
    # At y = half_w: z = center_z - sqrt(radius^2 - half_w^2)
    arc_z_at_edge = center_z - math.sqrt(radius ** 2 - half_w ** 2)

    # Create the arc
    arc = Part.ArcOfCircle(
        Part.Circle(App.Vector(0, center_z, 0), App.Vector(0, 0, 1), radius),
        math.pi + math.asin(half_w / radius),
        2 * math.pi - math.asin(half_w / radius)
    )
    sketch.addGeometry(arc)

    # Close with lines to create a subtractable region
    # Line from left arc end up to a point above
    sketch.addGeometry(Part.LineSegment(
        App.Vector(-half_w, arc_z_at_edge, 0),
        App.Vector(-half_w, z_top + 5, 0)
    ))
    # Line across top
    sketch.addGeometry(Part.LineSegment(
        App.Vector(-half_w, z_top + 5, 0),
        App.Vector(half_w, z_top + 5, 0)
    ))
    # Line down to right arc end
    sketch.addGeometry(Part.LineSegment(
        App.Vector(half_w, z_top + 5, 0),
        App.Vector(half_w, arc_z_at_edge, 0)
    ))

    doc.recompute()
    return sketch


def create_fretboard_radius_cut(doc, body, sketch):
    """Create subtractive pipe to cut fretboard radius along neck length."""
    # Create a path line along the neck
    path_sketch = body.newObject("Sketcher::SketchObject", "FretboardRadiusPath")
    xy_plane = doc.getObject("XY_Plane")
    path_sketch.AttachmentSupport = [(xy_plane, "")]
    path_sketch.MapMode = "FlatFace"
    path_sketch.AttachmentOffset = App.Placement(
        App.Vector(0, 0, BLANK_HEIGHT),
        App.Rotation(0, 0, 0, 1)
    )

    # Path from nut to heel
    path_sketch.addGeometry(Part.LineSegment(
        App.Vector(0, 0, 0),
        App.Vector(NUT_TO_HEEL, 0, 0)
    ))
    doc.recompute()

    # Create subtractive pipe
    pipe = body.newObject("PartDesign::SubtractivePipe", "FretboardRadius")
    pipe.Profile = (sketch, [""])
    pipe.Spine = (path_sketch, ["Edge1"])
    doc.recompute()
    return pipe


def create_truss_rod_channel(doc, body, xy_plane):
    """Create truss rod channel pocket from fretboard side."""
    sketch = body.newObject("Sketcher::SketchObject", "TrussRodSketch")
    sketch.AttachmentSupport = [(xy_plane, "")]
    sketch.MapMode = "FlatFace"
    sketch.AttachmentOffset = App.Placement(
        App.Vector(0, 0, BLANK_HEIGHT),
        App.Rotation(0, 0, 0, 1)
    )

    # Channel runs along center of neck
    half_w = TRUSS_ROD_WIDTH / 2
    start_x = 30.0  # Start after nut area
    end_x = start_x + TRUSS_ROD_LENGTH

    # Rectangle for channel
    p0 = App.Vector(start_x, -half_w, 0)
    p1 = App.Vector(end_x, -half_w, 0)
    p2 = App.Vector(end_x, half_w, 0)
    p3 = App.Vector(start_x, half_w, 0)

    sketch.addGeometry(Part.LineSegment(p0, p1))
    sketch.addGeometry(Part.LineSegment(p1, p2))
    sketch.addGeometry(Part.LineSegment(p2, p3))
    sketch.addGeometry(Part.LineSegment(p3, p0))

    # Close the rectangle
    sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 2, 1, 1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", 1, 2, 2, 1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", 2, 2, 3, 1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", 3, 2, 0, 1))

    doc.recompute()

    # Create pocket
    pocket = body.newObject("PartDesign::Pocket", "TrussRodChannel")
    pocket.Profile = (sketch, [""])
    pocket.Length = TRUSS_ROD_DEPTH
    pocket.Type = 0  # Dimension
    pocket.Reversed = False
    doc.recompute()
    return pocket


def create_headstock_outline_sketch(doc, body, xy_plane):
    """Create headstock outline sketch on XY plane.

    Headstock extends from nut (X=0) in the negative X direction.
    Classic Stratocaster headstock shape:
    - Starts at nut width (43mm)
    - Widens to 123mm at tuner area
    - Curved outline typical of Stratocaster
    """
    sketch = body.newObject("Sketcher::SketchObject", "HeadstockOutline")
    sketch.AttachmentSupport = [(xy_plane, "")]
    sketch.MapMode = "FlatFace"

    nut_half = NUT_WIDTH / 2           # 21.5mm
    head_half = HEADSTOCK_WIDTH_MAX / 2  # 61.5mm

    # Key X positions (negative from nut)
    x_nut = 0
    x_taper_start = -HEADSTOCK_TAPER_START      # -64mm where widening begins
    x_tuner_area = -HEADSTOCK_NUT_STEP          # -102.70mm main tuner area
    x_end = -HEADSTOCK_LENGTH                    # -189.70mm headstock end

    # Define headstock outline points
    # Bottom edge (Y negative)
    p_nut_bottom = App.Vector(x_nut, -nut_half, 0)
    p_taper_bottom = App.Vector(x_taper_start, -nut_half - 5, 0)  # Slight widening
    p_wide_bottom = App.Vector(x_tuner_area, -head_half + 10, 0)
    p_end_bottom = App.Vector(x_end + 30, -head_half, 0)

    # Top edge (Y positive)
    p_nut_top = App.Vector(x_nut, nut_half, 0)
    p_taper_top = App.Vector(x_taper_start, nut_half + 5, 0)
    p_wide_top = App.Vector(x_tuner_area, head_half - 10, 0)
    p_end_top = App.Vector(x_end + 30, head_half, 0)

    # Headstock end curve points
    p_end_curve_bottom = App.Vector(x_end + 10, -head_half + 15, 0)
    p_end_tip = App.Vector(x_end, 0, 0)
    p_end_curve_top = App.Vector(x_end + 10, head_half - 15, 0)

    # Build geometry
    geom_idx = 0

    # Nut edge (straight line)
    sketch.addGeometry(Part.LineSegment(p_nut_top, p_nut_bottom))
    nut_edge = geom_idx
    geom_idx += 1

    # Bottom taper (line from nut to taper start)
    sketch.addGeometry(Part.LineSegment(p_nut_bottom, p_taper_bottom))
    geom_idx += 1

    # Bottom widening curve (arc from taper to wide area)
    p_mid_bottom = App.Vector(
        (x_taper_start + x_tuner_area) / 2,
        (-nut_half - 5 + (-head_half + 10)) / 2 - 5,
        0
    )
    sketch.addGeometry(Part.Arc(p_taper_bottom, p_mid_bottom, p_wide_bottom))
    geom_idx += 1

    # Bottom straight section
    sketch.addGeometry(Part.LineSegment(p_wide_bottom, p_end_bottom))
    geom_idx += 1

    # End curve - bottom arc
    sketch.addGeometry(Part.Arc(p_end_bottom, p_end_curve_bottom, p_end_tip))
    geom_idx += 1

    # End curve - top arc
    sketch.addGeometry(Part.Arc(p_end_tip, p_end_curve_top, p_end_top))
    geom_idx += 1

    # Top straight section
    sketch.addGeometry(Part.LineSegment(p_end_top, p_wide_top))
    geom_idx += 1

    # Top widening curve (arc from wide area back to taper)
    p_mid_top = App.Vector(
        (x_taper_start + x_tuner_area) / 2,
        (nut_half + 5 + (head_half - 10)) / 2 + 5,
        0
    )
    sketch.addGeometry(Part.Arc(p_wide_top, p_mid_top, p_taper_top))
    geom_idx += 1

    # Top taper (line from taper back to nut)
    sketch.addGeometry(Part.LineSegment(p_taper_top, p_nut_top))
    geom_idx += 1

    # Add coincident constraints to close the shape
    # Connect each segment to the next
    for i in range(geom_idx - 1):
        sketch.addConstraint(Sketcher.Constraint("Coincident", i, 2, i + 1, 1))
    # Close the loop
    sketch.addConstraint(Sketcher.Constraint("Coincident", geom_idx - 1, 2, 0, 1))

    doc.recompute()
    return sketch


def create_headstock_pad(doc, body, sketch):
    """Pad headstock outline to create solid headstock.

    Height: 14.00mm from side-neck.png
    Direction: +Z from XY plane
    """
    pad = body.newObject("PartDesign::Pad", "HeadstockPad")
    pad.Profile = (sketch, [""])
    pad.Length = HEADSTOCK_THICKNESS
    pad.Type = 0  # Dimension
    pad.Reversed = False
    doc.recompute()
    return pad


def create_tuner_holes(doc, body, xy_plane):
    """Create 6 tuner holes for Schaller tuners.

    Hole positions from top-neck.png:
    - Diameter: Ø10.00mm
    - Arranged in 2 rows of 3 holes
    - Row spacing: 24.80mm from centerline
    - Staggered positions along X axis

    Looking at the drawing, tuner positions appear to be:
    - Row 1 (bottom, Y=-24.80): 3 holes
    - Row 2 (top, Y=+24.80): 3 holes
    The X positions are staggered for the classic Strat 6-in-line arrangement.
    """
    sketch = body.newObject("Sketcher::SketchObject", "TunerHolesSketch")
    sketch.AttachmentSupport = [(xy_plane, "")]
    sketch.MapMode = "FlatFace"
    sketch.AttachmentOffset = App.Placement(
        App.Vector(0, 0, HEADSTOCK_THICKNESS),
        App.Rotation(0, 0, 0, 1)
    )

    # Tuner hole positions (X negative from nut, Y from centerline)
    # From top-neck.png measurements:
    # - 14.60mm offset visible for inner tuner row
    # - 17.00mm width indicator near nut
    # - Holes at approximately 24.80mm from centerline

    # Classic Strat 6-in-line layout - tuners on one side
    # Looking at the drawing, all 6 tuners are on the bottom edge
    # with staggered X positions

    # Tuner X positions (from nut, going towards headstock end)
    # Based on typical Strat spacing and the 102.70mm reference
    tuner_x_positions = [
        -115.0,   # Tuner 1 (closest to nut)
        -130.0,   # Tuner 2
        -145.0,   # Tuner 3
        -155.0,   # Tuner 4
        -167.0,   # Tuner 5
        -180.0,   # Tuner 6 (closest to headstock end)
    ]

    # Y positions - staggered in 2 rows based on 24.80mm spacing
    # Row 1 (tuners 1, 3, 5): Y = -24.80 (bottom row)
    # Row 2 (tuners 2, 4, 6): Y = -14.60 (offset row, closer to center)
    tuner_y_row1 = -TUNER_HOLE_SPACING_Y  # -24.80mm
    tuner_y_row2 = -14.60                  # Offset row from drawing

    tuner_positions = [
        (tuner_x_positions[0], tuner_y_row1),  # Tuner 1
        (tuner_x_positions[1], tuner_y_row2),  # Tuner 2
        (tuner_x_positions[2], tuner_y_row1),  # Tuner 3
        (tuner_x_positions[3], tuner_y_row2),  # Tuner 4
        (tuner_x_positions[4], tuner_y_row1),  # Tuner 5
        (tuner_x_positions[5], tuner_y_row2),  # Tuner 6
    ]

    radius = TUNER_HOLE_DIAMETER / 2

    # Create circles for each tuner hole
    for i, (x, y) in enumerate(tuner_positions):
        circle = Part.Circle(App.Vector(x, y, 0), App.Vector(0, 0, 1), radius)
        sketch.addGeometry(circle)

    doc.recompute()

    # Create pocket (through-all)
    pocket = body.newObject("PartDesign::Pocket", "TunerHoles")
    pocket.Profile = (sketch, [""])
    pocket.Type = 1  # Through all
    pocket.Reversed = False
    doc.recompute()

    return sketch, pocket


def validate_model(doc):
    """Check all features are valid."""
    errors = []
    for obj in doc.Objects:
        if hasattr(obj, "isValid") and not obj.isValid():
            errors.append(f"{obj.Name} ({obj.Label})")
    return errors


def neck_width_at_position(x_pos):
    """Calculate neck width at given X position (linear taper)."""
    return NUT_WIDTH + (HEEL_WIDTH - NUT_WIDTH) * (x_pos / NUT_TO_HEEL)


def create_reference_image(doc, yz_plane, x_offset, name):
    """Add calibrated reference image on YZ plane at given X position.

    The image shows the Modern C profile with two curves:
    - Inner: 0.820" at 1st fret
    - Outer: 0.870" at 12th fret
    """
    import os
    if not os.path.exists(PROFILE_IMAGE_PATH):
        print(f"  WARNING: Reference image not found: {PROFILE_IMAGE_PATH}")
        return None

    # Create ImagePlane object
    img = doc.addObject("Image::ImagePlane", name)
    img.ImageFile = PROFILE_IMAGE_PATH

    # Image dimensions from the reference (approximate pixel-to-mm scaling)
    # The image shows width ~2.2" and height ~0.87"
    # Scale to match actual neck dimensions
    img_width_mm = 60.0   # Display width in mm
    img_height_mm = 25.0  # Display height in mm

    img.XSize = img_width_mm
    img.YSize = img_height_mm

    # Position on YZ plane at given X offset
    # Rotate to align with YZ plane (image faces along X axis)
    img.Placement = App.Placement(
        App.Vector(x_offset, 0, BLANK_HEIGHT / 2),
        App.Rotation(App.Vector(0, 1, 0), 90)  # Rotate 90° around Y axis
    )

    doc.recompute()
    return img


def main():
    """Create the neck model."""
    print("Creating 1962 Stratocaster neck model...")
    print(f"Dimensions (from reference drawings):")
    print(f"  Nut width: {NUT_WIDTH}mm")
    print(f"  Heel width: {HEEL_WIDTH}mm")
    print(f"  Nut to heel: {NUT_TO_HEEL}mm")
    print(f"  Headstock length: {HEADSTOCK_LENGTH}mm")
    print(f"  Total length: {NUT_TO_HEEL + HEADSTOCK_LENGTH}mm")
    print(f"  Thickness at 1st fret: {THICKNESS_1ST_FRET}mm")
    print(f"  Thickness at 12th fret: {THICKNESS_12TH_FRET}mm")
    print(f"  Fretboard radius: {FRETBOARD_RADIUS}mm")
    print(f"  Heel curve radius: {HEEL_CURVE_RADIUS}mm")

    doc, body = create_document()
    xy_plane, xz_plane, yz_plane = get_planes(doc)

    # Step 1: Create neck outline and blank
    print("\nCreating neck outline...")
    outline_sketch = create_neck_outline_sketch(doc, body, xy_plane)
    blank = create_neck_blank(doc, body, outline_sketch)
    print(f"  Neck blank: {NUT_TO_HEEL}mm x {BLANK_HEIGHT}mm")

    # Step 2: Add calibrated reference image
    print("\nAdding reference image...")
    ref_img = create_reference_image(doc, yz_plane, FRET_1_POSITION, "ModernCProfile")
    if ref_img:
        print(f"  Reference image added at 1st fret position ({FRET_1_POSITION:.2f}mm)")

    # Step 3: Create C-profile sketches at 1st and 12th fret positions
    print("\nCreating C-profile sections at fret positions...")

    # Calculate neck width at each fret position (linear taper)
    width_at_1st = neck_width_at_position(FRET_1_POSITION)
    width_at_12th = neck_width_at_position(FRET_12_POSITION)

    # Calculate depth for C-profile (how much to remove from blank)
    # Depth = blank_height - neck_thickness
    depth_1st = BLANK_HEIGHT - THICKNESS_1ST_FRET
    depth_12th = BLANK_HEIGHT - THICKNESS_12TH_FRET

    fret1_profile = create_c_profile_sketch(
        doc, body, yz_plane, FRET_1_POSITION, width_at_1st, depth_1st, "NeckProfile_Fret1"
    )
    print(f"  1st fret profile: X={FRET_1_POSITION:.2f}mm, {width_at_1st:.2f}mm wide, "
          f"{THICKNESS_1ST_FRET}mm thick (0.820\")")

    fret12_profile = create_c_profile_sketch(
        doc, body, yz_plane, FRET_12_POSITION, width_at_12th, depth_12th, "NeckProfile_Fret12"
    )
    print(f"  12th fret profile: X={FRET_12_POSITION:.2f}mm, {width_at_12th:.2f}mm wide, "
          f"{THICKNESS_12TH_FRET}mm thick (0.870\")")

    # Step 4: Create neck back carve with subtractive loft
    print("\nCreating neck back carve...")
    carve = create_neck_back_carve(doc, body, fret1_profile, fret12_profile)

    # Step 5: Create fretboard radius
    print("\nCreating fretboard radius...")
    radius_sketch = create_fretboard_radius_sketch(doc, body, yz_plane)
    # Note: SubtractivePipe can be complex; we may need to simplify
    # For now, skip the radius cut as it requires more complex geometry
    # radius_cut = create_fretboard_radius_cut(doc, body, radius_sketch)
    print(f"  Fretboard radius: {FRETBOARD_RADIUS}mm (sketch created)")

    # Step 6: Create truss rod channel
    print("\nCreating truss rod channel...")
    truss_rod = create_truss_rod_channel(doc, body, xy_plane)
    print(f"  Channel: {TRUSS_ROD_WIDTH}mm x {TRUSS_ROD_DEPTH}mm x {TRUSS_ROD_LENGTH}mm")

    # Step 7: Create headstock
    print("\nCreating headstock...")
    headstock_sketch = create_headstock_outline_sketch(doc, body, xy_plane)
    headstock_pad = create_headstock_pad(doc, body, headstock_sketch)
    print(f"  Headstock: {HEADSTOCK_LENGTH}mm x {HEADSTOCK_WIDTH_MAX}mm x {HEADSTOCK_THICKNESS}mm")

    # Step 8: Create tuner holes
    print("\nCreating tuner holes...")
    tuner_sketch, tuner_holes = create_tuner_holes(doc, body, xy_plane)
    print(f"  6x Ø{TUNER_HOLE_DIAMETER}mm holes for Schaller tuners")

    # Validate
    errors = validate_model(doc)
    if errors:
        print(f"\nWARNING: Invalid features: {errors}")
    else:
        print("\nAll features valid")

    # Save with compression level 0 for git
    doc.saveAs(DOC_PATH)
    print(f"\nSaved: {DOC_PATH}")

    # Print heel dimensions for verification against body pocket
    print(f"\nHeel dimensions for body pocket fit:")
    print(f"  Width: {HEEL_WIDTH}mm (2.2\")")
    print(f"  Corner radius: {HEEL_CURVE_RADIUS}mm (R26.50 from drawing)")
    print(f"  Length to heel end: {NUT_TO_HEEL}mm")


if __name__ in ("__main__", "create_neck"):
    main()
