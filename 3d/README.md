# 3D / CAM

**Warning:** G-code output is untested and has known and possibly unknown errors. The perimeter profile operation does not compensate for tool width — the cut follows the exact model outline rather than offsetting by the tool radius.

## Scripts

- `fix_pockets.py` — Fixes pocket sketch attachments to XY_Plane with a Z offset, then creates the NeckPocket and ControlsPocket features in the PartDesign body.
- `cam.py` — Generates CAM toolpaths (profile and pocket operations) and exports to ShopBot `.sbp` format.
- `conic_fretboard_cam.py` — Stand-alone G-code generator for a compound-radius (conical) fretboard. Uses top-down projection sampling of the conic surface under each tool footprint to compute a safe tip Z so the endmill cannot intersect the surface. Emits half-circle "rainbow" XY arcs between raster rows (G2/G3) at constant transit Z, swinging outside the part boundary to meter engagement on re-entry. A boundary-clearance check rejects any arc that would touch the part. Supports flat and ball-nose tools. Run with `python3 conic_fretboard_cam.py`; tests in `test_conic_fretboard_cam.py`.
- `fretboard_cam.ts` / `fretboard_cam.js` / `fretboard_cam.html` — Static air-gapped port of `conic_fretboard_cam.py`. The TypeScript source (strict mode, no implicit any) is the authoritative implementation; `tsconfig.json` builds it to plain `fretboard_cam.js`, which the HTML loads via `<script src="fretboard_cam.js">`. Open `fretboard_cam.html` directly from a thumb drive (file:// works) or serve with any static server. No network calls, no external libraries, no bundler. UI provides geometry/tool/CAM parameter fields, a top-down preview canvas (cutting moves in blue, rainbow arcs in red, part outline dashed), and a "Download .nc" button.

  Rebuild: `cd 3d && npx --yes -p typescript@5 tsc` (only needed when editing `.ts`).
  Thumb-drive bundle: copy `fretboard_cam.html` + `fretboard_cam.js`. The `.ts` is the source of truth but not required at runtime.

Run `fix_pockets.py` first (it creates the pocket features that `cam.py` references).

### Execution

```
flatpak run --command=FreeCADCmd org.freecad.FreeCAD fix_pockets.py
flatpak run --command=FreeCADCmd org.freecad.FreeCAD cam.py
```

## Tool Parameters

| Parameter         | Value            |
|-------------------|------------------|
| Endmill diameter  | 12.7 mm (1/2")   |
| Cutting edge      | 30 mm            |
| Spindle speed     | 18000 RPM        |
| Horizontal feed   | 1500 mm/min      |
| Vertical feed     | 500 mm/min       |
| Step down          | 6 mm per pass    |
| Step over (pocket) | 50%             |

## CAM Operations

- **Perimeter profile** — Through-cut (45 mm) with outside contour, CW direction. Empty Base triggers contour mode which profiles the full model outline.
- **Pocket operations** — One per `PartDesign::Pocket` feature. Uses face detection at the pocket floor Z level to assign base geometry. Through-cut pockets fall back to wall-face detection.
- **Bottom-side pockets** — Profiled from the top face as inside-contour slots, leaving a 1 mm margin at the bottom.

Output format is ShopBot `.sbp` via the `opensbp_post.py` post-processor.

## Sketch Documentation

The FreeCAD model uses auto-generated sketch names. Their actual purposes:

| Sketch Name  | Purpose                          | Pocket Depth  |
|--------------|----------------------------------|---------------|
| `Sketch`     | Body perimeter (used for Pad)    | N/A           |
| `Sketch001`  | Neck pocket                      | 15.875 mm     |
| `Sketch003`  | Controls cavity                  | 38.1 mm       |

Sketch attachment offsets use identity quaternions `(0, 0, 0, 1)` — no actual rotation is applied.

## Known Limitations

- Perimeter profile does not offset by tool radius; the resulting cut will be undersized by one tool diameter.
- Some pocket operations may produce no toolpath if face detection fails — these need manual base geometry assignment in the FreeCAD GUI.
