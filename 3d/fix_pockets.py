import FreeCAD
import FreeCAD as App

doc = FreeCAD.openDocument("/home/j/Documents/guitar/3d/1962-electric-guitar.FCStd")
body = doc.getObject("Body")
pad = doc.getObject("Pad")
xy_plane = doc.getObject("XY_Plane")

pickup_sketch = doc.getObject("Sketch")      # "pickup"
neck_sketch = doc.getObject("Sketch001")     # "neckPocket"
controls_sketch = doc.getObject("Sketch003") # "controls"

# Step 1: Fix all pocket sketch attachments to XY_Plane + Z offset
for sketch in [pickup_sketch, neck_sketch, controls_sketch]:
    sketch.AttachmentSupport = [(xy_plane, "")]
    sketch.MapMode = "FlatFace"
    offset = App.Placement(
        App.Vector(0, 0, 45.0),
        App.Rotation(0, 0, 0, 1)
    )
    sketch.AttachmentOffset = offset

doc.recompute()

# Step 2: Verify existing Pocket is valid
existing_pocket = doc.getObject("Pocket")

# Step 3: Create Pocket for neckPocket
neck_pocket = body.newObject("PartDesign::Pocket", "NeckPocket")
neck_pocket.Profile = (neck_sketch, [""])
neck_pocket.Length = 15.875  # 0.625 in
neck_pocket.Type = 0  # Dimension
neck_pocket.Reversed = False

# Step 4: Create Pocket for controls
controls_pocket = body.newObject("PartDesign::Pocket", "ControlsPocket")
controls_pocket.Profile = (controls_sketch, [""])
controls_pocket.Length = 38.1  # 1.5 in
controls_pocket.Type = 0  # Dimension
controls_pocket.Reversed = False

# Step 5: Recompute and validate
doc.recompute()

errors = []
for obj in doc.Objects:
    if hasattr(obj, 'isValid') and not obj.isValid():
        errors.append(f"{obj.Name} ({obj.Label})")
if errors:
    print("ERRORS:", errors)
else:
    print("All features valid")

doc.save()
print("Saved 1962-electric-guitar.FCStd")
