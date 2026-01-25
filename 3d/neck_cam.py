"""Generate CAM toolpaths for the 1962 Stratocaster neck.

Creates a CAM Job with operations for:
- Setup 1 (Back Face Up): 3D surface operation for C-profile carving
- Setup 2 (Fretboard Up): Truss rod channel pocket, perimeter profile

Run with: flatpak run --command=FreeCADCmd org.freecad.FreeCAD neck_cam.py
"""

import sys
import FreeCAD
import Path.Main.Job as PathJob
import Path.Tool.Controller as PathToolController
import Path.Tool.Bit as PathToolBit
import Path.Op.Profile as PathProfile
import Path.Op.Pocket as PathPocket

DOC_PATH = "/home/j/Documents/guitar/3d/neck.FCStd"
ENDMILL_SHAPE = "/app/freecad/Mod/CAM/Tools/Shape/endmill.fcstd"
BALLEND_SHAPE = "/app/freecad/Mod/CAM/Tools/Shape/ballend.fcstd"

# Tool parameters - 1/2" endmill for profiles
TOOL_DIAMETER = 12.7       # mm (1/2 inch)
TOOL_LENGTH = 50.0         # mm
CUTTING_EDGE_HEIGHT = 30.0 # mm
SHANK_DIAMETER = 12.7      # mm

# Small tool for truss rod channel - 1/4" endmill
SMALL_TOOL_DIAMETER = 6.0  # mm (slightly under 1/4" to fit 6.35mm channel)
SMALL_TOOL_LENGTH = 40.0   # mm
SMALL_CUTTING_HEIGHT = 15.0 # mm
SMALL_SHANK_DIAMETER = 6.35 # mm (1/4")

# Neck dimensions (must match create_neck.py)
BLANK_HEIGHT = 27.0        # mm
NUT_TO_HEEL = 466.73       # mm
TRUSS_ROD_DEPTH = 9.52     # mm

# CAM parameters
STEP_DOWN = 3.0            # mm per pass (finer for neck curves)
STEP_OVER_SURFACE = 1.5    # mm for surface finishing (11.8% of tool)
STEP_OVER_POCKET = 50      # percent for pockets
CLEARANCE_HEIGHT = 35.0    # mm
SAFE_HEIGHT = 30.0         # mm
HORIZ_FEED = 1500.0        # mm/min
VERT_FEED = 500.0          # mm/min
SPINDLE_SPEED = 18000.0    # RPM


def find_faces_at_z(body_shape, target_z, tolerance=0.5):
    """Find all horizontal faces at a given Z height on the body shape."""
    faces = []
    for i, face in enumerate(body_shape.Faces):
        bb = face.BoundBox
        if abs(bb.ZMin - target_z) < tolerance and abs(bb.ZMax - target_z) < tolerance:
            faces.append(f"Face{i + 1}")
    return faces


def find_pocket_faces(body_shape, pocket_name):
    """Find faces belonging to a pocket feature (floor faces)."""
    faces = []
    for i, face in enumerate(body_shape.Faces):
        bb = face.BoundBox
        # Look for small horizontal faces (pocket floors)
        z_span = bb.ZMax - bb.ZMin
        if z_span < 1.0:  # Horizontal face
            faces.append((f"Face{i + 1}", bb.ZMin))
    return faces


def create_operation(doc, type_class, name, job, tc, start_depth, final_depth, step_down):
    """Create a CAM operation with DoNotSetDefaultValues to avoid TC lookup bug."""
    obj = doc.addObject("Path::FeaturePython", name)
    obj.addProperty("App::PropertyBool", "DoNotSetDefaultValues")
    obj.DoNotSetDefaultValues = True
    obj.Proxy = type_class(obj, name, job)
    obj.DoNotSetDefaultValues = False
    obj.ToolController = tc
    obj.StartDepth = start_depth
    obj.FinalDepth = final_depth
    obj.StepDown = step_down
    obj.ClearanceHeight = CLEARANCE_HEIGHT
    obj.SafeHeight = SAFE_HEIGHT
    obj.Active = True
    return obj


def remove_existing_cam(doc):
    """Remove any existing CAM Job and its children for a clean slate."""
    to_remove = []
    for obj in doc.Objects:
        if obj.TypeId == "Path::FeaturePython" and hasattr(obj, "Operations"):
            # This is a Job - collect all its children
            for child in obj.Tools.Group:
                if hasattr(child, "Tool") and child.Tool:
                    to_remove.append(child.Tool.Name)
                to_remove.append(child.Name)
            for child in obj.Operations.Group:
                to_remove.append(child.Name)
            for child in obj.Model.Group:
                to_remove.append(child.Name)
            stock = getattr(obj, "Stock", None)
            if stock:
                to_remove.append(stock.Name)
            to_remove.append(obj.SetupSheet.Name)
            to_remove.append(obj.Operations.Name)
            to_remove.append(obj.Tools.Name)
            to_remove.append(obj.Model.Name)
            to_remove.append(obj.Name)

    for name in to_remove:
        if doc.getObject(name):
            doc.removeObject(name)
    if to_remove:
        doc.recompute()
        print(f"Removed {len(to_remove)} existing CAM objects")


def main():
    """Generate CAM toolpaths for the neck."""
    doc = FreeCAD.openDocument(DOC_PATH)
    body = doc.getObject("Body")

    print(f"Loaded: {DOC_PATH}")
    print(f"Body shape valid: {body.Shape.isValid()}")

    remove_existing_cam(doc)

    # Create Job
    job = PathJob.Create("Job", [body])
    doc.recompute()

    # Create tool bit (1/2" endmill)
    tool = PathToolBit.Factory.Create("Endmill_12_7mm", ENDMILL_SHAPE)
    tool.Diameter = TOOL_DIAMETER
    tool.CuttingEdgeHeight = CUTTING_EDGE_HEIGHT
    tool.Length = TOOL_LENGTH
    tool.ShankDiameter = SHANK_DIAMETER

    # Create tool controller
    tc = PathToolController.Create("TC_Endmill", tool=tool, toolNumber=1)
    tc.HorizFeed = HORIZ_FEED
    tc.VertFeed = VERT_FEED
    tc.SpindleSpeed = SPINDLE_SPEED
    job.Tools.addObject(tc)
    doc.recompute()

    # Create small tool bit (6mm endmill for truss rod channel)
    small_tool = PathToolBit.Factory.Create("Endmill_6mm", ENDMILL_SHAPE)
    small_tool.Diameter = SMALL_TOOL_DIAMETER
    small_tool.CuttingEdgeHeight = SMALL_CUTTING_HEIGHT
    small_tool.Length = SMALL_TOOL_LENGTH
    small_tool.ShankDiameter = SMALL_SHANK_DIAMETER

    # Create tool controller for small endmill
    tc_small = PathToolController.Create("TC_Endmill_6mm", tool=small_tool, toolNumber=2)
    tc_small.HorizFeed = HORIZ_FEED
    tc_small.VertFeed = VERT_FEED
    tc_small.SpindleSpeed = SPINDLE_SPEED
    job.Tools.addObject(tc_small)
    doc.recompute()

    # Remove default tool controller
    default_tc = None
    for obj in job.Tools.Group:
        if obj.Name not in (tc.Name, tc_small.Name) and obj.TypeId == "Path::FeaturePython":
            default_tc = obj
            break
    if default_tc is not None:
        default_tool = getattr(default_tc, "Tool", None)
        job.Tools.removeObject(default_tc)
        doc.removeObject(default_tc.Name)
        if default_tool is not None:
            doc.removeObject(default_tool.Name)
        doc.recompute()

    # --- Setup 1: Fretboard face up (machining from top) ---

    # Operation 1: Truss rod channel pocket (uses 6mm endmill to fit 6.35mm channel)
    truss_rod_pocket = doc.getObject("TrussRodChannel")
    if truss_rod_pocket:
        pocket_op = create_operation(
            doc, PathPocket.ObjectPocket, "TrussRodChannel",
            job, tc_small, BLANK_HEIGHT, BLANK_HEIGHT - TRUSS_ROD_DEPTH, STEP_DOWN
        )
        pocket_op.CutMode = "Conventional"
        pocket_op.StepOver = STEP_OVER_POCKET
        pocket_op.OffsetPattern = "Offset"

        # Find the pocket floor face (horizontal face at channel bottom)
        floor_z = BLANK_HEIGHT - TRUSS_ROD_DEPTH
        floor_faces = []
        for i, face in enumerate(body.Shape.Faces):
            bb = face.BoundBox
            # Look for horizontal face at channel depth within channel X range
            if (abs(bb.ZMax - floor_z) < 0.5 and abs(bb.ZMin - floor_z) < 0.5
                    and bb.XMin >= 25.0 and bb.XMax <= 450.0  # Channel region
                    and abs(bb.YMax - bb.YMin) < 10.0):  # Narrow in Y
                floor_faces.append(f"Face{i + 1}")

        if floor_faces:
            pocket_op.Base = [(body, floor_faces)]
            print(f"TrussRodChannel: depth={TRUSS_ROD_DEPTH}mm, faces={floor_faces}")
        else:
            # Try to find any horizontal face at pocket depth
            all_floor = find_faces_at_z(body.Shape, floor_z)
            if all_floor:
                pocket_op.Base = [(body, all_floor)]
                print(f"TrussRodChannel: depth={TRUSS_ROD_DEPTH}mm, all faces={all_floor}")
            else:
                print("TrussRodChannel: WARNING - no floor faces found")

        job.Operations.addObject(pocket_op)
    else:
        print("TrussRodChannel pocket not found in model")

    # Operation 2: Perimeter profile (outline cut)
    profile = create_operation(
        doc, PathProfile.ObjectProfile, "Perimeter",
        job, tc, BLANK_HEIGHT, 0.0, STEP_DOWN
    )
    profile.Side = "Outside"
    profile.Direction = "CW"
    profile.UseComp = True
    profile.Base = []  # Contour mode
    profile.processPerimeter = True
    print(f"Perimeter: through-cut {BLANK_HEIGHT}mm")

    job.Operations.addObject(profile)

    # --- Setup 2: Back face up (neck back carving) ---
    # Note: 3D surface operations for the C-profile carve require
    # Path.Op.Surface which needs more complex setup.
    # For now, we create a placeholder note.
    print("\nNote: Neck back carving requires 3D Surface operation")
    print("  This must be configured in FreeCAD GUI with:")
    print("  - Path > 3D Surface or Path > Waterline")
    print("  - Select the curved back faces of the neck")
    print("  - Use 1/2\" endmill with 1.5mm stepover")

    doc.recompute()
    doc.save()
    print(f"\nSaved {DOC_PATH}")

    # Report on operations
    print(f"\nOperations: {len(job.Operations.Group)}")
    has_paths = False
    for op in job.Operations.Group:
        cmd_count = len(op.Path.Commands)
        motion_cmds = [c for c in op.Path.Commands
                       if c.Name in ("G0", "G1", "G2", "G3")]
        print(f"  {op.Label}: commands={cmd_count}, motions={len(motion_cmds)}")
        if len(motion_cmds) > 0:
            has_paths = True

    if not has_paths:
        print("\nWARNING: No motion commands generated.")
        print("Operations may need Base geometry assigned in the GUI.")
        return

    # Post-process to ShopBot .sbp format
    post_script = "/app/freecad/Mod/CAM/Path/Post/scripts/opensbp_post.py"
    sys.path.insert(0, "/app/freecad/Mod/CAM/Path/Post/scripts")
    import importlib.util
    spec = importlib.util.spec_from_file_location("opensbp_post", post_script)
    opensbp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(opensbp)

    sbp_path = "/home/j/Documents/guitar/3d/neck.sbp"
    ops_with_paths = [op for op in job.Operations.Group
                      if len(op.Path.Commands) > 2]
    if ops_with_paths:
        opensbp.export(ops_with_paths, sbp_path, "--no-show-editor --comments")
        print(f"\nExported ShopBot file: {sbp_path}")
    else:
        print("\nNo operations with paths to export")


if __name__ in ("__main__", "neck_cam"):
    main()
