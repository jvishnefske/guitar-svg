"""
SVG path parsing and extraction.

Extracts path elements from SVG files and parses their geometry
to determine start and end points for clustering.
"""

import re
import xml.etree.ElementTree as ET
from typing import Optional, Tuple
from pathlib import Path

from .types import Point, PathSegment, VisualAttrs


SVG_NS = "http://www.w3.org/2000/svg"


def parse_path_d(d: str) -> list[Tuple[str, list[float]]]:
    """
    Parse SVG path d attribute into commands.

    Args:
        d: The d attribute string from an SVG path

    Returns:
        List of (command, [args]) tuples where command is a single
        character (M, L, C, etc.) and args is a list of float parameters.
    """
    commands = []
    pattern = r"([MmLlHhVvCcSsQqTtAaZz])([^MmLlHhVvCcSsQqTtAaZz]*)"

    for match in re.finditer(pattern, d):
        cmd = match.group(1)
        args_str = match.group(2).strip()

        if args_str:
            args = [float(x) for x in re.findall(r"-?[0-9.]+(?:[eE][+-]?[0-9]+)?", args_str)]
        else:
            args = []

        commands.append((cmd, args))

    return commands


def rgb_percent_to_hex(rgb_str: str) -> str:
    """
    Convert rgb(x%, y%, z%) format to hex color.

    Args:
        rgb_str: Color in format 'rgb(x%, y%, z%)'

    Returns:
        Hex color string like '#RRGGBB', or original string if not matched.
    """
    match = re.match(r"rgb\(([0-9.]+)%,\s*([0-9.]+)%,\s*([0-9.]+)%\)", rgb_str)
    if not match:
        return rgb_str

    r = int(float(match.group(1)) * 255 / 100)
    g = int(float(match.group(2)) * 255 / 100)
    b = int(float(match.group(3)) * 255 / 100)

    return f"#{r:02X}{g:02X}{b:02X}"


def is_white_stroke(stroke: str) -> bool:
    """Check if stroke color is white (100%, 100%, 100%)."""
    return "100%" in stroke and stroke.count("100%") >= 3


def is_path_closed(d: str) -> bool:
    """Check if a path ends with Z/z (close path command)."""
    d_stripped = d.strip()
    return d_stripped.endswith("Z") or d_stripped.endswith("z")


def extract_endpoints(d: str) -> Optional[Tuple[Point, Point]]:
    """
    Extract start and end points from a path d attribute.

    Executes path commands to track the current point through the path,
    returning the first and last positions.

    Args:
        d: SVG path d attribute string

    Returns:
        Tuple of (start_point, end_point) or None if path has no points.
    """
    commands = parse_path_d(d)
    if not commands:
        return None

    start_point: Optional[Point] = None
    current_x, current_y = 0.0, 0.0
    subpath_start_x, subpath_start_y = 0.0, 0.0

    for cmd, args in commands:
        if cmd == "M":
            if len(args) >= 2:
                current_x, current_y = args[0], args[1]
                subpath_start_x, subpath_start_y = current_x, current_y
                if start_point is None:
                    start_point = Point(current_x, current_y)
                # Handle implicit lineto after M
                for i in range(2, len(args) - 1, 2):
                    current_x, current_y = args[i], args[i + 1]

        elif cmd == "m":
            if len(args) >= 2:
                current_x += args[0]
                current_y += args[1]
                subpath_start_x, subpath_start_y = current_x, current_y
                if start_point is None:
                    start_point = Point(current_x, current_y)
                for i in range(2, len(args) - 1, 2):
                    current_x += args[i]
                    current_y += args[i + 1]

        elif cmd == "L":
            for i in range(0, len(args) - 1, 2):
                current_x, current_y = args[i], args[i + 1]

        elif cmd == "l":
            for i in range(0, len(args) - 1, 2):
                current_x += args[i]
                current_y += args[i + 1]

        elif cmd == "H":
            if args:
                current_x = args[-1]

        elif cmd == "h":
            for val in args:
                current_x += val

        elif cmd == "V":
            if args:
                current_y = args[-1]

        elif cmd == "v":
            for val in args:
                current_y += val

        elif cmd == "C":
            # Cubic bezier: x1 y1 x2 y2 x y
            for i in range(0, len(args) - 5, 6):
                current_x, current_y = args[i + 4], args[i + 5]

        elif cmd == "c":
            for i in range(0, len(args) - 5, 6):
                current_x += args[i + 4]
                current_y += args[i + 5]

        elif cmd == "S":
            # Smooth cubic: x2 y2 x y
            for i in range(0, len(args) - 3, 4):
                current_x, current_y = args[i + 2], args[i + 3]

        elif cmd == "s":
            for i in range(0, len(args) - 3, 4):
                current_x += args[i + 2]
                current_y += args[i + 3]

        elif cmd == "Q":
            # Quadratic bezier: x1 y1 x y
            for i in range(0, len(args) - 3, 4):
                current_x, current_y = args[i + 2], args[i + 3]

        elif cmd == "q":
            for i in range(0, len(args) - 3, 4):
                current_x += args[i + 2]
                current_y += args[i + 3]

        elif cmd == "T":
            # Smooth quadratic: x y
            for i in range(0, len(args) - 1, 2):
                current_x, current_y = args[i], args[i + 1]

        elif cmd == "t":
            for i in range(0, len(args) - 1, 2):
                current_x += args[i]
                current_y += args[i + 1]

        elif cmd == "A":
            # Arc: rx ry rotation large-arc sweep x y
            for i in range(0, len(args) - 6, 7):
                current_x, current_y = args[i + 5], args[i + 6]

        elif cmd == "a":
            for i in range(0, len(args) - 6, 7):
                current_x += args[i + 5]
                current_y += args[i + 6]

        elif cmd in ("Z", "z"):
            current_x, current_y = subpath_start_x, subpath_start_y

    if start_point is None:
        return None

    return (start_point, Point(current_x, current_y))


def parse_svg_paths(
    svg_path: Path,
    skip_white: bool = True,
) -> Tuple[list[PathSegment], Optional[str]]:
    """
    Parse all path elements from an SVG file.

    Args:
        svg_path: Path to the SVG file
        skip_white: If True, skip white stroke paths (background halos)

    Returns:
        Tuple of (list of PathSegments, transform attribute if common to all paths)
    """
    tree = ET.parse(svg_path)
    root = tree.getroot()

    segments: list[PathSegment] = []
    segment_id = 0
    common_transform: Optional[str] = None
    first_transform_seen = False

    for elem in root.iter():
        tag = elem.tag
        if tag == f"{{{SVG_NS}}}path" or tag == "path":
            d = elem.get("d", "")
            if not d:
                continue

            stroke = elem.get("stroke", "")
            stroke_width_str = elem.get("stroke-width", "1")
            transform = elem.get("transform")

            # Track common transform
            if not first_transform_seen:
                common_transform = transform
                first_transform_seen = True
            elif common_transform != transform:
                common_transform = None

            # Skip white strokes if requested
            if skip_white and is_white_stroke(stroke):
                continue

            # Parse stroke width
            try:
                stroke_width = float(stroke_width_str)
            except ValueError:
                stroke_width = 1.0

            # Normalize stroke color
            stroke_color = rgb_percent_to_hex(stroke)

            # Extract endpoints
            endpoints = extract_endpoints(d)
            if endpoints is None:
                continue

            start, end = endpoints
            closed = is_path_closed(d)

            visual_attrs = VisualAttrs(
                stroke_width=stroke_width,
                stroke_color=stroke_color,
            )

            segment = PathSegment(
                segment_id=segment_id,
                start=start,
                end=end,
                d_attribute=d,
                visual_attrs=visual_attrs,
                is_closed=closed,
            )
            segments.append(segment)
            segment_id += 1

    return (segments, common_transform)


def get_svg_dimensions(svg_path: Path) -> Tuple[str, str, str]:
    """
    Extract SVG dimensions from file.

    Args:
        svg_path: Path to the SVG file

    Returns:
        Tuple of (width, height, viewBox) attribute values
    """
    tree = ET.parse(svg_path)
    root = tree.getroot()

    width = root.get("width", "100%")
    height = root.get("height", "100%")
    viewbox = root.get("viewBox", "")

    return (width, height, viewbox)
