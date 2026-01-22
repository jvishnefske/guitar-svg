"""
SVG Template Processor for Guitar Body Templates

Processes technical drawing SVGs and generates laser-cut ready templates
with red cut lines and blue reference lines.

Usage:
    python svg_template_processor.py <input.svg> <output_prefix>
"""

import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

NAMESPACES = {
    "svg": SVG_NS,
    "xlink": XLINK_NS,
}

# Color constants for laser cutting
CUT_COLOR = "#FF0000"      # Red for cuts
REFERENCE_COLOR = "#0000FF"  # Blue for reference
STROKE_WIDTH = "0.25pt"      # Standard laser-compatible width


@dataclass
class BoundingBox:
    """Axis-aligned bounding box for path geometry."""
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center_x(self) -> float:
        return (self.min_x + self.max_x) / 2

    @property
    def center_y(self) -> float:
        return (self.min_y + self.max_y) / 2


@dataclass
class PathInfo:
    """Metadata about an SVG path element."""
    element: ET.Element
    d_attribute: str
    stroke_color: str
    bounding_box: Optional[BoundingBox]
    is_closed: bool


def rgb_percent_to_hex(rgb_str: str) -> str:
    """
    Convert rgb(x%, y%, z%) format to hex color.

    Args:
        rgb_str: Color in format 'rgb(x%, y%, z%)'

    Returns:
        Hex color string like '#RRGGBB'
    """
    match = re.match(r"rgb\(([0-9.]+)%,\s*([0-9.]+)%,\s*([0-9.]+)%\)", rgb_str)
    if not match:
        return rgb_str

    r = int(float(match.group(1)) * 255 / 100)
    g = int(float(match.group(2)) * 255 / 100)
    b = int(float(match.group(3)) * 255 / 100)

    return f"#{r:02X}{g:02X}{b:02X}"


def parse_path_d(d: str) -> list[tuple[str, list[float]]]:
    """
    Parse SVG path d attribute into commands.

    Args:
        d: The d attribute string from an SVG path

    Returns:
        List of (command, [args]) tuples
    """
    commands = []
    pattern = r"([MmLlHhVvCcSsQqTtAaZz])([^MmLlHhVvCcSsQqTtAaZz]*)"

    for match in re.finditer(pattern, d):
        cmd = match.group(1)
        args_str = match.group(2).strip()

        if args_str:
            args = [float(x) for x in re.findall(r"-?[0-9.]+", args_str)]
        else:
            args = []

        commands.append((cmd, args))

    return commands


def compute_bounding_box(d: str) -> Optional[BoundingBox]:
    """
    Compute approximate bounding box from path d attribute.

    Only handles M, L, H, V commands for simplicity.
    Curves are approximated by their control points.

    Args:
        d: SVG path d attribute

    Returns:
        BoundingBox or None if path is empty
    """
    commands = parse_path_d(d)
    if not commands:
        return None

    points_x = []
    points_y = []
    current_x, current_y = 0.0, 0.0

    for cmd, args in commands:
        if cmd == "M" and len(args) >= 2:
            current_x, current_y = args[0], args[1]
            points_x.append(current_x)
            points_y.append(current_y)
        elif cmd == "m" and len(args) >= 2:
            current_x += args[0]
            current_y += args[1]
            points_x.append(current_x)
            points_y.append(current_y)
        elif cmd == "L" and len(args) >= 2:
            current_x, current_y = args[0], args[1]
            points_x.append(current_x)
            points_y.append(current_y)
        elif cmd == "l" and len(args) >= 2:
            current_x += args[0]
            current_y += args[1]
            points_x.append(current_x)
            points_y.append(current_y)
        elif cmd == "H" and len(args) >= 1:
            current_x = args[0]
            points_x.append(current_x)
        elif cmd == "h" and len(args) >= 1:
            current_x += args[0]
            points_x.append(current_x)
        elif cmd == "V" and len(args) >= 1:
            current_y = args[0]
            points_y.append(current_y)
        elif cmd == "v" and len(args) >= 1:
            current_y += args[0]
            points_y.append(current_y)
        elif cmd == "C" and len(args) >= 6:
            # Cubic bezier - use all control points for bbox
            for i in range(0, len(args), 6):
                if i + 5 < len(args):
                    points_x.extend([args[i], args[i+2], args[i+4]])
                    points_y.extend([args[i+1], args[i+3], args[i+5]])
                    current_x, current_y = args[i+4], args[i+5]
        elif cmd == "c" and len(args) >= 6:
            for i in range(0, len(args), 6):
                if i + 5 < len(args):
                    points_x.extend([current_x + args[i], current_x + args[i+2], current_x + args[i+4]])
                    points_y.extend([current_y + args[i+1], current_y + args[i+3], current_y + args[i+5]])
                    current_x += args[i+4]
                    current_y += args[i+5]

    if not points_x or not points_y:
        return None

    return BoundingBox(
        min_x=min(points_x),
        min_y=min(points_y),
        max_x=max(points_x),
        max_y=max(points_y),
    )


def is_path_closed(d: str) -> bool:
    """Check if a path ends with Z/z (close path command)."""
    d_stripped = d.strip()
    return d_stripped.endswith("Z") or d_stripped.endswith("z")


def extract_paths(svg_root: ET.Element) -> list[PathInfo]:
    """
    Extract all path elements from SVG.

    Args:
        svg_root: Root element of parsed SVG

    Returns:
        List of PathInfo objects
    """
    paths = []

    for elem in svg_root.iter():
        if elem.tag == f"{{{SVG_NS}}}path" or elem.tag == "path":
            d = elem.get("d", "")
            stroke = elem.get("stroke", "")

            if not d:
                continue

            bbox = compute_bounding_box(d)
            closed = is_path_closed(d)

            paths.append(PathInfo(
                element=elem,
                d_attribute=d,
                stroke_color=stroke,
                bounding_box=bbox,
                is_closed=closed,
            ))

    return paths


def is_black_path(path: PathInfo) -> bool:
    """Check if path has black stroke (the main drawing paths)."""
    return "0%, 0%, 0%" in path.stroke_color


def is_gray_path(path: PathInfo) -> bool:
    """Check if path has gray stroke (dimension/annotation paths)."""
    return "50" in path.stroke_color and "%" in path.stroke_color


def classify_path_by_position(
    path: PathInfo,
    body_bbox: BoundingBox,
    overall_bbox: BoundingBox,
) -> str:
    """
    Classify a path based on its position relative to body outline.

    Stratocaster body regions - SVG coordinates have neck pointing left.
    The body_bbox represents the main body area; paths outside are reference.

    Args:
        path: PathInfo to classify
        body_bbox: Bounding box of the body outline
        overall_bbox: Bounding box of entire drawing

    Returns:
        Classification string: 'body', 'neck_pocket', 'pickup', 'bridge',
        'control_cavity', 'spring_cavity', 'screw_hole', 'reference'
    """
    if path.bounding_box is None:
        return "reference"

    bbox = path.bounding_box

    # Check if path is within body area (with margin)
    margin = body_bbox.width * 0.1
    within_body_x = (
        bbox.center_x >= body_bbox.min_x - margin and
        bbox.center_x <= body_bbox.max_x + margin
    )
    within_body_y = (
        bbox.center_y >= body_bbox.min_y - margin and
        bbox.center_y <= body_bbox.max_y + margin
    )

    if not (within_body_x and within_body_y):
        return "reference"

    # Relative position within body (0-1 range)
    rel_x = (bbox.center_x - body_bbox.min_x) / body_bbox.width
    rel_y = (bbox.center_y - body_bbox.min_y) / body_bbox.height

    # Size relative to body
    rel_width = bbox.width / body_bbox.width
    rel_height = bbox.height / body_bbox.height
    rel_area = bbox.area / body_bbox.area

    # Very large path - likely body outline itself
    if rel_area > 0.3:
        return "body"

    # Paths that touch the body edge - likely body outline segments
    touches_left = abs(bbox.min_x - body_bbox.min_x) < margin
    touches_right = abs(bbox.max_x - body_bbox.max_x) < margin
    touches_top = abs(bbox.min_y - body_bbox.min_y) < margin
    touches_bottom = abs(bbox.max_y - body_bbox.max_y) < margin

    if touches_left or touches_right or touches_top or touches_bottom:
        return "body"

    # Small circular paths - likely screw holes
    if rel_area < 0.002:
        aspect = bbox.width / bbox.height if bbox.height > 0 else 1
        if 0.7 < aspect < 1.4:
            return "screw_hole"

    # Neck pocket - at neck end (left side of body in this coordinate system)
    if rel_x < 0.25 and rel_width > 0.08:
        return "neck_pocket"

    # Pickup cavities - elongated shapes in pickup zone
    if 0.25 < rel_x < 0.65 and rel_height > rel_width * 0.8:
        return "pickup"

    # Bridge/tremolo area - center to right of body
    if 0.5 < rel_x < 0.8 and rel_area > 0.005:
        return "bridge"

    # Control cavity - lower portion of body (high Y in these coords)
    if rel_y > 0.6:
        return "control_cavity"

    # Spring cavity - behind bridge, central area
    if 0.4 < rel_x < 0.7 and 0.3 < rel_y < 0.7:
        return "spring_cavity"

    # Default: paths inside body but not classified go to front
    return "pickup"


def find_body_outline(paths: list[PathInfo]) -> Optional[PathInfo]:
    """
    Find the main body outline path (largest black path by bounding box).

    Args:
        paths: List of all paths

    Returns:
        PathInfo of body outline or None
    """
    black_paths_with_bbox = [
        p for p in paths
        if is_black_path(p) and p.bounding_box is not None
    ]

    if not black_paths_with_bbox:
        return None

    # Return path with largest bounding box area
    return max(black_paths_with_bbox, key=lambda p: p.bounding_box.area)


def create_template_svg(
    original_root: ET.Element,
    paths_to_include: list[PathInfo],
    reference_paths: list[PathInfo],
    output_path: Path,
) -> None:
    """
    Create a new SVG template with specified paths.

    Args:
        original_root: Original SVG root for viewBox/dimensions
        paths_to_include: Paths to include as cut lines (red)
        reference_paths: Paths to include as reference (blue)
        output_path: Where to save the new SVG
    """
    # Get original SVG attributes
    width = original_root.get("width", "2448")
    height = original_root.get("height", "1584")
    viewbox = original_root.get("viewBox", f"0 0 {width} {height}")

    # Create new SVG root
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)

    new_root = ET.Element("svg")
    new_root.set("xmlns", SVG_NS)
    new_root.set("xmlns:xlink", XLINK_NS)
    new_root.set("width", width)
    new_root.set("height", height)
    new_root.set("viewBox", viewbox)

    # Add reference paths first (background)
    for path in reference_paths:
        new_elem = ET.SubElement(new_root, "path")
        new_elem.set("d", path.d_attribute)
        new_elem.set("fill", "none")
        new_elem.set("stroke", REFERENCE_COLOR)
        new_elem.set("stroke-width", STROKE_WIDTH)

        # Preserve transform if present
        transform = path.element.get("transform")
        if transform:
            new_elem.set("transform", transform)

    # Add cut paths (foreground)
    for path in paths_to_include:
        new_elem = ET.SubElement(new_root, "path")
        new_elem.set("d", path.d_attribute)
        new_elem.set("fill", "none")
        new_elem.set("stroke", CUT_COLOR)
        new_elem.set("stroke-width", STROKE_WIDTH)

        # Preserve transform if present
        transform = path.element.get("transform")
        if transform:
            new_elem.set("transform", transform)

    # Write output
    tree = ET.ElementTree(new_root)
    ET.indent(tree, space="  ")

    with open(output_path, "wb") as f:
        tree.write(f, encoding="UTF-8", xml_declaration=True)

    print(f"Created: {output_path}")
    print(f"  Cut paths (red): {len(paths_to_include)}")
    print(f"  Reference paths (blue): {len(reference_paths)}")


def process_strat_svg(input_path: Path, output_prefix: str) -> None:
    """
    Process a Stratocaster SVG and generate front/back templates.

    Args:
        input_path: Path to source SVG
        output_prefix: Prefix for output files
    """
    print(f"Processing: {input_path}")

    # Parse SVG
    tree = ET.parse(input_path)
    root = tree.getroot()

    # Extract all paths
    all_paths = extract_paths(root)
    print(f"Total paths found: {len(all_paths)}")

    # Filter to black paths (the main drawing)
    black_paths = [p for p in all_paths if is_black_path(p)]
    gray_paths = [p for p in all_paths if is_gray_path(p)]
    print(f"Black paths: {len(black_paths)}")
    print(f"Gray paths (dimensions): {len(gray_paths)}")

    # Find body outline
    body_outline = find_body_outline(black_paths)
    if body_outline is None or body_outline.bounding_box is None:
        print("ERROR: Could not identify body outline")
        sys.exit(1)

    print(f"Body outline bbox: {body_outline.bounding_box}")

    # Compute overall bounding box for all paths
    all_bboxes = [p.bounding_box for p in black_paths if p.bounding_box is not None]
    overall_bbox = BoundingBox(
        min_x=min(b.min_x for b in all_bboxes),
        min_y=min(b.min_y for b in all_bboxes),
        max_x=max(b.max_x for b in all_bboxes),
        max_y=max(b.max_y for b in all_bboxes),
    )
    print(f"Overall bbox: {overall_bbox}")

    # Classify all black paths
    classifications = {}
    for path in black_paths:
        if path is body_outline:
            classifications[id(path)] = "body"
        else:
            classifications[id(path)] = classify_path_by_position(
                path, body_outline.bounding_box, overall_bbox
            )

    # Count classifications
    class_counts = {}
    for cls in classifications.values():
        class_counts[cls] = class_counts.get(cls, 0) + 1
    print(f"Path classifications: {class_counts}")

    # For templates, include all non-reference paths (paths within body region)
    # Front template: all paths within body region (excluding dimensions)
    all_body_categories = {
        "body", "pickup", "bridge", "screw_hole", "neck_pocket",
        "control_cavity", "spring_cavity"
    }
    all_body_paths = [
        p for p in black_paths
        if classifications[id(p)] in all_body_categories
    ]

    # For specialized templates, separate front and back features
    # Front: body outline, pickups, bridge, screw holes
    front_categories = {"body", "pickup", "bridge", "screw_hole", "neck_pocket"}
    front_cuts = [p for p in black_paths if classifications[id(p)] in front_categories]
    front_reference = gray_paths + [
        p for p in black_paths
        if classifications[id(p)] in {"control_cavity", "spring_cavity"}
    ]

    # Back template: body, control cavity, spring cavity, neck pocket
    back_categories = {"body", "control_cavity", "spring_cavity", "neck_pocket"}
    back_cuts = [p for p in black_paths if classifications[id(p)] in back_categories]
    back_reference = gray_paths + [
        p for p in black_paths
        if classifications[id(p)] in {"pickup", "bridge"}
    ]

    print(f"All body paths: {len(all_body_paths)}")
    print(f"Front cuts: {len(front_cuts)}, reference: {len(front_reference)}")
    print(f"Back cuts: {len(back_cuts)}, reference: {len(back_reference)}")

    # Create output directory
    output_dir = Path("templates")
    output_dir.mkdir(exist_ok=True)

    # Generate templates
    create_template_svg(
        root,
        front_cuts,
        front_reference,
        output_dir / f"{output_prefix}-front.svg",
    )

    # Combined template: all body paths (useful for overview)
    create_template_svg(
        root,
        all_body_paths,
        gray_paths,
        output_dir / f"{output_prefix}-combined.svg",
    )

    create_template_svg(
        root,
        back_cuts,
        back_reference,
        output_dir / f"{output_prefix}-back.svg",
    )


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 3:
        print("Usage: python svg_template_processor.py <input.svg> <output_prefix>")
        print("Example: python svg_template_processor.py source.svg strat-62")
        return 1

    input_path = Path(sys.argv[1])
    output_prefix = sys.argv[2]

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        return 1

    process_strat_svg(input_path, output_prefix)
    return 0


if __name__ == "__main__":
    sys.exit(main())
