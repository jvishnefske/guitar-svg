"""Generate CAM toolpaths for the Stratocaster guitar body.

Creates a CAM Job with:
- 1/2" (12.7mm) endmill tool
- Profile operation for perimeter through-cut (45mm)
- Pocket operations for each PartDesign::Pocket feature

Run with: flatpak run --command=FreeCADCmd org.freecad.FreeCAD cam.py
"""

import sys
import FreeCAD
import Path.Main.Job as PathJob
import Path.Tool.Controller as PathToolController
import Path.Tool.Bit as PathToolBit
import Path.Op.Profile as PathProfile
import Path.Op.Pocket as PathPocket

DOC_PATH = "/home/j/Documents/guitar/3d/stratocaster.FCStd"
ENDMILL_SHAPE = "/app/freecad/Mod/CAM/Tools/Shape/endmill.fcstd"

TOOL_DIAMETER = 12.7       # mm (1/2 inch)
TOOL_LENGTH = 50.0         # mm
CUTTING_EDGE_HEIGHT = 30.0 # mm
SHANK_DIAMETER = 12.7      # mm
STEP_DOWN = 6.0            # mm per pass
STEP_OVER = 50             # percent of tool diameter
CLEARANCE_HEIGHT = 55.0    # mm
SAFE_HEIGHT = 50.0         # mm
HORIZ_FEED = 1500.0        # mm/min
VERT_FEED = 500.0          # mm/min
SPINDLE_SPEED = 18000.0    # RPM
BOTTOM_MARGIN = 1.0        # mm left uncut at bottom for bottom-side pockets


def find_faces_at_z(body_shape, target_z, tolerance=0.5):
    """Find all horizontal faces at a given Z height on the body shape."""
    faces = []
    for i, face in enumerate(body_shape.Faces):
        bb = face.BoundBox
        if abs(bb.ZMin - target_z) < tolerance and abs(bb.ZMax - target_z) < tolerance:
            faces.append(f"Face{i + 1}")
    return faces


def find_pocket_wall_faces(body_shape, start_z, pocket_depth):
    """Find vertical wall faces belonging to a pocket.

    Looks for faces that span from the pocket bottom up to start_z,
    indicating they are pocket walls for a through-cut.
    """
    target_bottom = start_z - pocket_depth
    walls = []
    for i, face in enumerate(body_shape.Faces):
        bb = face.BoundBox
        z_span = bb.ZMax - bb.ZMin
        # Wall face: spans from near pocket bottom up to start_z
        if (abs(bb.ZMax - start_z) < 0.5
                and abs(bb.ZMin - target_bottom) < 0.5
                and z_span > 1.0):
            walls.append(f"Face{i + 1}")
    return walls


def find_top_edges_for_sketch(body_shape, sketch_shape, pad_height):
    """Find edges on the top face matching a sketch's XY outline.

    Returns edge names at Z=pad_height within the sketch bounding box,
    used as pocket base for bottom-side features machined from top.
    """
    sbb = sketch_shape.BoundBox
    edges = []
    for i, edge in enumerate(body_shape.Edges):
        bb = edge.BoundBox
        if (abs(bb.ZMin - pad_height) < 0.5
                and abs(bb.ZMax - pad_height) < 0.5
                and bb.XMin >= sbb.XMin - 1.0
                and bb.XMax <= sbb.XMax + 1.0
                and bb.YMin >= sbb.YMin - 1.0
                and bb.YMax <= sbb.YMax + 1.0):
            edges.append(f"Edge{i + 1}")
    return edges


def create_operation(doc, type_class, name, job, tc, start_depth, final_depth):
    """Create a CAM operation with DoNotSetDefaultValues to avoid TC lookup bug."""
    obj = doc.addObject("Path::FeaturePython", name)
    obj.addProperty("App::PropertyBool", "DoNotSetDefaultValues")
    obj.DoNotSetDefaultValues = True
    obj.Proxy = type_class(obj, name, job)
    obj.DoNotSetDefaultValues = False
    obj.ToolController = tc
    obj.StartDepth = start_depth
    obj.FinalDepth = final_depth
    obj.StepDown = STEP_DOWN
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

    # Also remove orphaned endmill shape bodies from prior runs
    for obj in doc.Objects:
        if (obj.TypeId in ("PartDesign::Body", "Part::FeaturePython")
                and "ndmill" in obj.Label
                and obj.Name != "Body"):
            to_remove.append(obj.Name)

    for name in to_remove:
        if doc.getObject(name):
            doc.removeObject(name)
    if to_remove:
        doc.recompute()
        print(f"Removed {len(to_remove)} existing CAM objects")


def main():
    doc = FreeCAD.openDocument(DOC_PATH)
    body = doc.getObject("Body")
    pad = doc.getObject("Pad")
    pad_height = pad.Length.Value

    print(f"Pad height: {pad_height} mm")

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

    # Remove default tool controller created by Job
    default_tc = None
    for obj in job.Tools.Group:
        if obj.Name != tc.Name and obj.TypeId == "Path::FeaturePython":
            default_tc = obj
            break
    if default_tc is not None:
        default_tool = getattr(default_tc, "Tool", None)
        job.Tools.removeObject(default_tc)
        doc.removeObject(default_tc.Name)
        if default_tool is not None:
            doc.removeObject(default_tool.Name)
        doc.recompute()

    # --- Profile operation (perimeter through-cut) ---
    profile = create_operation(
        doc, PathProfile.ObjectProfile, "Perimeter",
        job, tc, pad_height, 0.0
    )
    profile.Side = "Outside"
    profile.Direction = "CW"
    profile.UseComp = True

    # Empty Base triggers contour mode: profiles the model outline
    profile.Base = []
    profile.processPerimeter = True
    print(f"Profile: contour mode, depth={pad_height}mm through-cut")

    job.Operations.addObject(profile)

    # --- Pocket operations ---
    pockets = [obj for obj in doc.Objects if obj.TypeId == "PartDesign::Pocket"]
    print(f"Found {len(pockets)} pocket features")

    for pocket in pockets:
        pocket_name = f"CAMPocket_{pocket.Label}"

        # Compute pocket floor Z from sketch placement and feature tree
        sketch = pocket.Profile[0]
        sketch_z = sketch.Placement.Base.z

        if abs(sketch_z - pad_height) < 1.0:
            # Standard pocket: sketch on top face, cuts down by Length
            start_depth = pad_height
            final_depth = pad_height - pocket.Length.Value
        else:
            # Bottom-side pocket: profile inside the slot outline from top
            start_depth = pad_height
            final_depth = BOTTOM_MARGIN
            edge_refs = find_top_edges_for_sketch(
                body.Shape, sketch.Shape, pad_height
            )
            profile_op = create_operation(
                doc, PathProfile.ObjectProfile, pocket_name,
                job, tc, start_depth, final_depth
            )
            profile_op.Side = "Inside"
            profile_op.Direction = "CW"
            profile_op.UseComp = True
            if edge_refs:
                profile_op.Base = [(body, edge_refs)]
                print(f"Pocket '{pocket.Label}': profile slot from top, "
                      f"final_z={final_depth:.2f}mm, "
                      f"base={len(edge_refs)} edges")
            else:
                print(f"Pocket '{pocket.Label}': slot from top, "
                      f"WARNING: no outline edges found")
            job.Operations.addObject(profile_op)
            continue

        through_cut = final_depth < 0.5
        if through_cut:
            final_depth = 0.0

        # Find all floor faces at the computed Z level
        face_names = find_faces_at_z(body.Shape, final_depth)

        pocket_op = create_operation(
            doc, PathPocket.ObjectPocket, pocket_name,
            job, tc, start_depth, final_depth
        )
        pocket_op.CutMode = "Conventional"
        pocket_op.StepOver = STEP_OVER
        pocket_op.OffsetPattern = "Offset"

        if face_names:
            pocket_op.Base = [(body, face_names)]
            print(f"Pocket '{pocket.Label}': start_z={start_depth:.2f}mm, "
                  f"final_z={final_depth:.2f}mm, base={face_names}")
        else:
            # Through-cut pocket - find wall faces
            wall_faces = find_pocket_wall_faces(
                body.Shape, start_depth, start_depth - final_depth
            )
            if wall_faces:
                pocket_op.Base = [(body, wall_faces)]
                print(f"Pocket '{pocket.Label}': through-cut from "
                      f"z={start_depth:.2f}mm, base={wall_faces}")
            else:
                print(f"Pocket '{pocket.Label}': through-cut from "
                      f"z={start_depth:.2f}mm, "
                      f"WARNING: no geometry found (assign face in GUI)")

        job.Operations.addObject(pocket_op)

    doc.recompute()

    doc.save()
    print(f"\nSaved {DOC_PATH}")
    print(f"Operations: {len(job.Operations.Group)}")
    has_paths = False
    for op in job.Operations.Group:
        cmd_count = len(op.Path.Commands)
        motion_cmds = [c for c in op.Path.Commands
                       if c.Name in ("G0", "G1", "G2", "G3")]
        print(f"  {op.Label}: commands={cmd_count}, motions={len(motion_cmds)}")
        if len(motion_cmds) == 0:
            print(f"    WARNING: no toolpath computed for {op.Label}")
        else:
            has_paths = True

    # Post-process to ShopBot .sbp format
    if not has_paths:
        print("\nWARNING: No motion commands in any operation. "
              "Skipping .sbp export.")
        print("Operations may need Base geometry assigned in the GUI.")
        return

    post_script = "/app/freecad/Mod/CAM/Path/Post/scripts/opensbp_post.py"
    sys.path.insert(0, "/app/freecad/Mod/CAM/Path/Post/scripts")
    import importlib.util
    spec = importlib.util.spec_from_file_location("opensbp_post", post_script)
    opensbp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(opensbp)

    sbp_path = "/home/j/Documents/guitar/3d/stratocaster.sbp"
    # Pass the operations directly since they hold the Path data
    ops_with_paths = [op for op in job.Operations.Group
                      if len(op.Path.Commands) > 2]
    opensbp.export(ops_with_paths, sbp_path, "--no-show-editor --comments")
    print(f"\nExported ShopBot file: {sbp_path}")


if __name__ in ("__main__", "cam"):
    main()
