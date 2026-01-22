"""
Path d-attribute merging for clustered segments.

Handles the synthesis of merged path commands from ordered segment chains,
including reversing path directions when needed.
"""

import re
from typing import Tuple

from .types import PathSegment


def parse_path_commands(d: str) -> list[Tuple[str, list[float]]]:
    """
    Parse SVG path d attribute into commands.

    Args:
        d: The d attribute string

    Returns:
        List of (command, [args]) tuples
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


def reverse_path_commands(commands: list[Tuple[str, list[float]]]) -> list[Tuple[str, list[float]]]:
    """
    Reverse a sequence of path commands.

    Transforms path commands to traverse in the opposite direction.
    The result starts with M at the original end point and traces
    back to the original start point.

    Args:
        commands: List of (command, args) tuples

    Returns:
        Reversed list of commands
    """
    if not commands:
        return []

    # Track points through the path to build reversal
    points: list[Tuple[float, float]] = []
    current_x, current_y = 0.0, 0.0
    subpath_start_x, subpath_start_y = 0.0, 0.0

    # Extended command info: (cmd, args, start_point, end_point)
    extended: list[Tuple[str, list[float], Tuple[float, float], Tuple[float, float]]] = []

    for cmd, args in commands:
        start_point = (current_x, current_y)

        if cmd == "M":
            if len(args) >= 2:
                current_x, current_y = args[0], args[1]
                subpath_start_x, subpath_start_y = current_x, current_y
                # Handle implicit lineto
                for i in range(2, len(args) - 1, 2):
                    start_point = (current_x, current_y)
                    current_x, current_y = args[i], args[i + 1]
                    extended.append(("L", [current_x, current_y], start_point, (current_x, current_y)))
                extended.append(("M", [args[0], args[1]], start_point, (args[0], args[1])))
                continue

        elif cmd == "m":
            if len(args) >= 2:
                current_x += args[0]
                current_y += args[1]
                subpath_start_x, subpath_start_y = current_x, current_y
                extended.append(("M", [current_x, current_y], start_point, (current_x, current_y)))
                continue

        elif cmd == "L":
            for i in range(0, len(args) - 1, 2):
                start_point = (current_x, current_y)
                current_x, current_y = args[i], args[i + 1]
                extended.append(("L", [current_x, current_y], start_point, (current_x, current_y)))
            continue

        elif cmd == "l":
            for i in range(0, len(args) - 1, 2):
                start_point = (current_x, current_y)
                current_x += args[i]
                current_y += args[i + 1]
                extended.append(("L", [current_x, current_y], start_point, (current_x, current_y)))
            continue

        elif cmd == "H":
            for val in args:
                start_point = (current_x, current_y)
                current_x = val
                extended.append(("L", [current_x, current_y], start_point, (current_x, current_y)))
            continue

        elif cmd == "h":
            for val in args:
                start_point = (current_x, current_y)
                current_x += val
                extended.append(("L", [current_x, current_y], start_point, (current_x, current_y)))
            continue

        elif cmd == "V":
            for val in args:
                start_point = (current_x, current_y)
                current_y = val
                extended.append(("L", [current_x, current_y], start_point, (current_x, current_y)))
            continue

        elif cmd == "v":
            for val in args:
                start_point = (current_x, current_y)
                current_y += val
                extended.append(("L", [current_x, current_y], start_point, (current_x, current_y)))
            continue

        elif cmd == "C":
            for i in range(0, len(args) - 5, 6):
                start_point = (current_x, current_y)
                x1, y1 = args[i], args[i + 1]
                x2, y2 = args[i + 2], args[i + 3]
                x, y = args[i + 4], args[i + 5]
                current_x, current_y = x, y
                # Store control points for reversal
                extended.append(("C", [x1, y1, x2, y2, x, y], start_point, (x, y)))
            continue

        elif cmd == "c":
            for i in range(0, len(args) - 5, 6):
                start_point = (current_x, current_y)
                x1, y1 = current_x + args[i], current_y + args[i + 1]
                x2, y2 = current_x + args[i + 2], current_y + args[i + 3]
                x, y = current_x + args[i + 4], current_y + args[i + 5]
                current_x, current_y = x, y
                extended.append(("C", [x1, y1, x2, y2, x, y], start_point, (x, y)))
            continue

        elif cmd == "Q":
            for i in range(0, len(args) - 3, 4):
                start_point = (current_x, current_y)
                x1, y1 = args[i], args[i + 1]
                x, y = args[i + 2], args[i + 3]
                current_x, current_y = x, y
                extended.append(("Q", [x1, y1, x, y], start_point, (x, y)))
            continue

        elif cmd == "q":
            for i in range(0, len(args) - 3, 4):
                start_point = (current_x, current_y)
                x1, y1 = current_x + args[i], current_y + args[i + 1]
                x, y = current_x + args[i + 2], current_y + args[i + 3]
                current_x, current_y = x, y
                extended.append(("Q", [x1, y1, x, y], start_point, (x, y)))
            continue

        elif cmd == "A":
            for i in range(0, len(args) - 6, 7):
                start_point = (current_x, current_y)
                rx, ry = args[i], args[i + 1]
                rotation = args[i + 2]
                large_arc = args[i + 3]
                sweep = args[i + 4]
                x, y = args[i + 5], args[i + 6]
                current_x, current_y = x, y
                extended.append(("A", [rx, ry, rotation, large_arc, sweep, x, y], start_point, (x, y)))
            continue

        elif cmd == "a":
            for i in range(0, len(args) - 6, 7):
                start_point = (current_x, current_y)
                rx, ry = args[i], args[i + 1]
                rotation = args[i + 2]
                large_arc = args[i + 3]
                sweep = args[i + 4]
                x, y = current_x + args[i + 5], current_y + args[i + 6]
                current_x, current_y = x, y
                extended.append(("A", [rx, ry, rotation, large_arc, sweep, x, y], start_point, (x, y)))
            continue

        elif cmd in ("Z", "z"):
            extended.append(("Z", [], (current_x, current_y), (subpath_start_x, subpath_start_y)))
            current_x, current_y = subpath_start_x, subpath_start_y
            continue

        end_point = (current_x, current_y)
        extended.append((cmd, args, start_point, end_point))

    # Now reverse: start from the last point, work backwards
    if not extended:
        return []

    # Filter out M commands (we'll add new ones)
    non_m_commands = [(cmd, args, sp, ep) for cmd, args, sp, ep in extended if cmd != "M"]

    if not non_m_commands:
        # Only M commands - just return move to last point
        last_cmd = extended[-1]
        return [("M", [last_cmd[3][0], last_cmd[3][1]])]

    reversed_commands: list[Tuple[str, list[float]]] = []

    # Start with M to the endpoint of the last drawing command
    last_end = non_m_commands[-1][3]
    reversed_commands.append(("M", [last_end[0], last_end[1]]))

    # Reverse each drawing command
    for cmd, args, start_point, end_point in reversed(non_m_commands):
        if cmd == "L":
            reversed_commands.append(("L", [start_point[0], start_point[1]]))

        elif cmd == "C":
            # Reverse cubic bezier: swap control points and endpoint
            # Original: C x1 y1 x2 y2 x y (from start to end)
            # Reversed: C x2 y2 x1 y1 start_x start_y
            x1, y1, x2, y2 = args[0], args[1], args[2], args[3]
            reversed_commands.append(("C", [x2, y2, x1, y1, start_point[0], start_point[1]]))

        elif cmd == "Q":
            # Quadratic bezier reversal: control point stays, swap endpoints
            x1, y1 = args[0], args[1]
            reversed_commands.append(("Q", [x1, y1, start_point[0], start_point[1]]))

        elif cmd == "A":
            # Arc reversal: swap sweep flag
            rx, ry, rotation, large_arc, sweep = args[0], args[1], args[2], args[3], args[4]
            new_sweep = 1.0 - sweep  # Flip sweep direction
            reversed_commands.append(("A", [rx, ry, rotation, large_arc, new_sweep, start_point[0], start_point[1]]))

        elif cmd == "Z":
            # Z becomes L to the start of the subpath when reversed
            reversed_commands.append(("L", [start_point[0], start_point[1]]))

    return reversed_commands


def commands_to_d(commands: list[Tuple[str, list[float]]]) -> str:
    """
    Convert command list back to d attribute string.

    Args:
        commands: List of (command, args) tuples

    Returns:
        SVG path d attribute string
    """
    parts = []
    for cmd, args in commands:
        if args:
            args_str = " ".join(f"{a:g}" for a in args)
            parts.append(f"{cmd} {args_str}")
        else:
            parts.append(cmd)
    return " ".join(parts)


def reverse_path_d(d: str) -> str:
    """
    Reverse a path d attribute.

    Args:
        d: Original d attribute

    Returns:
        Reversed d attribute
    """
    commands = parse_path_commands(d)
    reversed_commands = reverse_path_commands(commands)
    return commands_to_d(reversed_commands)


def get_path_end_point(d: str) -> Tuple[float, float]:
    """
    Get the endpoint of a path.

    Args:
        d: Path d attribute

    Returns:
        (x, y) tuple of the endpoint
    """
    commands = parse_path_commands(d)
    current_x, current_y = 0.0, 0.0
    subpath_start_x, subpath_start_y = 0.0, 0.0

    for cmd, args in commands:
        if cmd == "M" and len(args) >= 2:
            current_x, current_y = args[0], args[1]
            subpath_start_x, subpath_start_y = current_x, current_y
            for i in range(2, len(args) - 1, 2):
                current_x, current_y = args[i], args[i + 1]
        elif cmd == "m" and len(args) >= 2:
            current_x += args[0]
            current_y += args[1]
            subpath_start_x, subpath_start_y = current_x, current_y
        elif cmd == "L":
            for i in range(0, len(args) - 1, 2):
                current_x, current_y = args[i], args[i + 1]
        elif cmd == "l":
            for i in range(0, len(args) - 1, 2):
                current_x += args[i]
                current_y += args[i + 1]
        elif cmd == "H" and args:
            current_x = args[-1]
        elif cmd == "h":
            for val in args:
                current_x += val
        elif cmd == "V" and args:
            current_y = args[-1]
        elif cmd == "v":
            for val in args:
                current_y += val
        elif cmd == "C":
            for i in range(0, len(args) - 5, 6):
                current_x, current_y = args[i + 4], args[i + 5]
        elif cmd == "c":
            for i in range(0, len(args) - 5, 6):
                current_x += args[i + 4]
                current_y += args[i + 5]
        elif cmd == "Q":
            for i in range(0, len(args) - 3, 4):
                current_x, current_y = args[i + 2], args[i + 3]
        elif cmd == "q":
            for i in range(0, len(args) - 3, 4):
                current_x += args[i + 2]
                current_y += args[i + 3]
        elif cmd == "A":
            for i in range(0, len(args) - 6, 7):
                current_x, current_y = args[i + 5], args[i + 6]
        elif cmd == "a":
            for i in range(0, len(args) - 6, 7):
                current_x += args[i + 5]
                current_y += args[i + 6]
        elif cmd in ("Z", "z"):
            current_x, current_y = subpath_start_x, subpath_start_y

    return (current_x, current_y)


def strip_leading_move(d: str) -> str:
    """
    Remove the leading M command from a path.

    Used when joining paths where the continuation point is already established.

    Args:
        d: Path d attribute

    Returns:
        Path without leading M command
    """
    commands = parse_path_commands(d)
    if not commands:
        return d

    # Skip initial M command
    if commands[0][0] in ("M", "m"):
        commands = commands[1:]

    return commands_to_d(commands)


def merge_chain_paths(
    ordered_segments: list[Tuple[int, bool]],
    segments_by_id: dict[int, PathSegment],
) -> str:
    """
    Merge ordered segments into a single path d attribute.

    Args:
        ordered_segments: List of (segment_id, needs_reversal) tuples in traversal order
        segments_by_id: Mapping of segment_id -> PathSegment

    Returns:
        Merged d attribute string
    """
    if not ordered_segments:
        return ""

    parts: list[str] = []

    for i, (seg_id, needs_reversal) in enumerate(ordered_segments):
        segment = segments_by_id[seg_id]
        d = segment.d_attribute

        if needs_reversal:
            d = reverse_path_d(d)

        if i == 0:
            # First segment: include full path including M
            parts.append(d)
        else:
            # Subsequent segments: skip M command, just add the drawing commands
            continuation = strip_leading_move(d)
            if continuation:
                parts.append(continuation)

    return " ".join(parts)
