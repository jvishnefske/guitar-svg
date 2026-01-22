"""
SVG output generation for clustered paths.

Generates organized SVG files with paths grouped by visual attributes.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from .types import PathChain, PathSegment, ClusterResult, VisualAttrs


SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"


def create_svg_root(
    width: str,
    height: str,
    viewbox: str,
) -> ET.Element:
    """
    Create an SVG root element with proper namespaces.

    Args:
        width: SVG width attribute
        height: SVG height attribute
        viewbox: SVG viewBox attribute

    Returns:
        SVG root Element
    """
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)

    root = ET.Element("svg")
    root.set("xmlns", SVG_NS)
    root.set("xmlns:xlink", XLINK_NS)
    root.set("width", width)
    root.set("height", height)
    if viewbox:
        root.set("viewBox", viewbox)

    return root


def create_path_element(
    d: str,
    visual_attrs: VisualAttrs,
    transform: Optional[str] = None,
) -> ET.Element:
    """
    Create a path element with given attributes.

    Args:
        d: Path d attribute
        visual_attrs: Visual styling attributes
        transform: Optional transform attribute

    Returns:
        Path Element
    """
    elem = ET.Element("path")
    elem.set("d", d)
    elem.set("fill", "none")
    elem.set("stroke", visual_attrs.stroke_color)
    elem.set("stroke-width", str(visual_attrs.stroke_width))
    elem.set("stroke-linecap", "round")
    elem.set("stroke-linejoin", "round")

    if transform:
        elem.set("transform", transform)

    return elem


def create_group_element(
    group_id: str,
    visual_attrs: VisualAttrs,
) -> ET.Element:
    """
    Create a group element for organizing paths.

    Args:
        group_id: ID for the group
        visual_attrs: Visual attributes for the group label

    Returns:
        Group Element
    """
    group = ET.Element("g")
    group.set("id", group_id)

    # Add a comment-like title for identification
    title = ET.SubElement(group, "title")
    title.text = f"stroke={visual_attrs.stroke_color}, width={visual_attrs.stroke_width}"

    return group


def group_chains_by_attrs(
    chains: list[PathChain],
) -> dict[VisualAttrs, list[PathChain]]:
    """
    Group chains by their visual attributes.

    Args:
        chains: List of path chains

    Returns:
        Dict mapping VisualAttrs -> list of chains with those attributes
    """
    grouped: dict[VisualAttrs, list[PathChain]] = {}

    for chain in chains:
        if chain.visual_attrs not in grouped:
            grouped[chain.visual_attrs] = []
        grouped[chain.visual_attrs].append(chain)

    return grouped


def write_clustered_svg(
    output_path: Path,
    cluster_result: ClusterResult,
    width: str,
    height: str,
    viewbox: str,
    transform: Optional[str] = None,
) -> None:
    """
    Write clustered paths to an SVG file.

    Organizes paths into groups by visual attributes.

    Args:
        output_path: Path to write the SVG file
        cluster_result: Clustering result containing chains and orphans
        width: SVG width
        height: SVG height
        viewbox: SVG viewBox
        transform: Optional transform to apply to all paths
    """
    root = create_svg_root(width, height, viewbox)

    # Group chains by visual attributes
    grouped_chains = group_chains_by_attrs(list(cluster_result.chains))

    # Sort groups for consistent output (by stroke width, then color)
    sorted_attrs = sorted(
        grouped_chains.keys(),
        key=lambda a: (a.stroke_width, a.stroke_color),
    )

    # Add each group
    for i, attrs in enumerate(sorted_attrs):
        chains = grouped_chains[attrs]

        # Create group for these attributes
        group_id = f"group-{i}-w{attrs.stroke_width:.2f}"
        group = create_group_element(group_id, attrs)
        root.append(group)

        # Add paths for each chain
        for chain in chains:
            path_elem = create_path_element(chain.merged_d, attrs, transform)
            path_elem.set("id", f"chain-{chain.chain_id}")
            group.append(path_elem)

    # Add orphan segments in a separate group if any
    if cluster_result.orphan_segments:
        orphan_group = ET.SubElement(root, "g")
        orphan_group.set("id", "orphans")
        orphan_title = ET.SubElement(orphan_group, "title")
        orphan_title.text = "Unconnected segments"

        for segment in cluster_result.orphan_segments:
            path_elem = create_path_element(
                segment.d_attribute,
                segment.visual_attrs,
                transform,
            )
            path_elem.set("id", f"orphan-{segment.segment_id}")
            orphan_group.append(path_elem)

    # Write to file
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")

    with open(output_path, "wb") as f:
        tree.write(f, encoding="UTF-8", xml_declaration=True)


def write_clustered_svg_by_attrs(
    output_path: Path,
    results_by_attrs: dict[VisualAttrs, ClusterResult],
    width: str,
    height: str,
    viewbox: str,
    transform: Optional[str] = None,
) -> None:
    """
    Write clustered paths to an SVG file, organized by visual attribute groups.

    Args:
        output_path: Path to write the SVG file
        results_by_attrs: Dict mapping VisualAttrs -> ClusterResult
        width: SVG width
        height: SVG height
        viewbox: SVG viewBox
        transform: Optional transform to apply to all paths
    """
    root = create_svg_root(width, height, viewbox)

    # Sort attribute groups for consistent output
    sorted_attrs = sorted(
        results_by_attrs.keys(),
        key=lambda a: (a.stroke_width, a.stroke_color),
    )

    group_num = 0
    for attrs in sorted_attrs:
        result = results_by_attrs[attrs]

        # Create group for this attribute set
        group_id = f"group-{group_num}-w{attrs.stroke_width:.2f}"
        group = create_group_element(group_id, attrs)
        root.append(group)
        group_num += 1

        # Add chains
        for chain in result.chains:
            path_elem = create_path_element(chain.merged_d, attrs, transform)
            path_elem.set("id", f"chain-{chain.chain_id}")
            group.append(path_elem)

        # Add orphans within the same group
        for segment in result.orphan_segments:
            path_elem = create_path_element(
                segment.d_attribute,
                segment.visual_attrs,
                transform,
            )
            path_elem.set("id", f"orphan-{segment.segment_id}")
            group.append(path_elem)

    # Write to file
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")

    with open(output_path, "wb") as f:
        tree.write(f, encoding="UTF-8", xml_declaration=True)


def print_cluster_stats(result: ClusterResult, label: str = "") -> None:
    """
    Print statistics about a clustering result.

    Args:
        result: ClusterResult to report on
        label: Optional label for the output
    """
    stats = result.stats
    prefix = f"{label}: " if label else ""

    print(f"{prefix}Input segments: {stats.total_input_segments}")
    print(f"{prefix}Output chains: {stats.total_chains}")
    print(f"{prefix}Orphan segments: {stats.orphan_count}")
    print(f"{prefix}Loops detected: {stats.loop_count}")
    print(f"{prefix}Max chain length: {stats.max_chain_length}")
    print(f"{prefix}Avg chain length: {stats.avg_chain_length:.2f}")

    reduction = (
        (1 - (stats.total_chains + stats.orphan_count) / stats.total_input_segments) * 100
        if stats.total_input_segments > 0
        else 0
    )
    print(f"{prefix}Path count reduction: {reduction:.1f}%")
