"""
Unit tests for SVG path clustering module.

Tests cover immutable types, path parsing, spatial indexing,
clustering algorithms, path merging, and output generation.
"""

import unittest
from pathlib import Path
import tempfile
import os

from svg_path_clustering.types import (
    Point,
    VisualAttrs,
    PathSegment,
    PathChain,
    ClusterResult,
)
from svg_path_clustering.parsing import (
    parse_path_d,
    extract_endpoints,
    rgb_percent_to_hex,
    is_white_stroke,
    is_path_closed,
)
from svg_path_clustering.spatial_index import SpatialIndex
from svg_path_clustering.clustering import (
    UnionFind,
    cluster_segments,
    build_adjacency_graph,
)
from svg_path_clustering.merging import (
    reverse_path_d,
    merge_chain_paths,
    strip_leading_move,
    commands_to_d,
    parse_path_commands,
)
from svg_path_clustering.output import (
    create_svg_root,
    create_path_element,
    group_chains_by_attrs,
)


class TestPoint(unittest.TestCase):
    """Tests for Point immutable type."""

    def test_point_creation(self):
        """Point stores x and y coordinates."""
        p = Point(1.5, 2.5)
        self.assertEqual(p.x, 1.5)
        self.assertEqual(p.y, 2.5)

    def test_point_immutable(self):
        """Point is frozen and cannot be modified."""
        p = Point(1.0, 2.0)
        with self.assertRaises(AttributeError):
            p.x = 3.0

    def test_point_distance(self):
        """Distance calculation is correct."""
        p1 = Point(0.0, 0.0)
        p2 = Point(3.0, 4.0)
        self.assertAlmostEqual(p1.distance_to(p2), 5.0)

    def test_point_is_near(self):
        """Near detection works within tolerance."""
        p1 = Point(0.0, 0.0)
        p2 = Point(0.3, 0.4)
        self.assertTrue(p1.is_near(p2, 0.5))
        self.assertFalse(p1.is_near(p2, 0.4))

    def test_point_as_tuple(self):
        """Tuple conversion works."""
        p = Point(1.0, 2.0)
        self.assertEqual(p.as_tuple(), (1.0, 2.0))


class TestVisualAttrs(unittest.TestCase):
    """Tests for VisualAttrs immutable type."""

    def test_visual_attrs_creation(self):
        """VisualAttrs stores stroke properties."""
        attrs = VisualAttrs(stroke_width=2.0, stroke_color="#000000")
        self.assertEqual(attrs.stroke_width, 2.0)
        self.assertEqual(attrs.stroke_color, "#000000")

    def test_visual_attrs_to_svg(self):
        """SVG attribute conversion works."""
        attrs = VisualAttrs(stroke_width=1.5, stroke_color="#FF0000")
        svg_attrs = attrs.to_svg_attrs()
        self.assertEqual(svg_attrs["stroke-width"], "1.5")
        self.assertEqual(svg_attrs["stroke"], "#FF0000")

    def test_visual_attrs_hashable(self):
        """VisualAttrs can be used as dict key."""
        attrs1 = VisualAttrs(stroke_width=1.0, stroke_color="#000")
        attrs2 = VisualAttrs(stroke_width=1.0, stroke_color="#000")
        d = {attrs1: "value"}
        self.assertEqual(d[attrs2], "value")


class TestPathSegment(unittest.TestCase):
    """Tests for PathSegment immutable type."""

    def test_segment_creation(self):
        """PathSegment stores all required fields."""
        attrs = VisualAttrs(stroke_width=1.0, stroke_color="#000")
        segment = PathSegment(
            segment_id=0,
            start=Point(0.0, 0.0),
            end=Point(10.0, 10.0),
            d_attribute="M 0 0 L 10 10",
            visual_attrs=attrs,
            is_closed=False,
        )
        self.assertEqual(segment.segment_id, 0)
        self.assertEqual(segment.start.x, 0.0)
        self.assertEqual(segment.end.x, 10.0)

    def test_segment_reversed_endpoints(self):
        """Endpoint reversal swaps start and end."""
        attrs = VisualAttrs(stroke_width=1.0, stroke_color="#000")
        segment = PathSegment(
            segment_id=0,
            start=Point(0.0, 0.0),
            end=Point(10.0, 10.0),
            d_attribute="M 0 0 L 10 10",
            visual_attrs=attrs,
            is_closed=False,
        )
        reversed_seg = segment.reversed_endpoints()
        self.assertEqual(reversed_seg.start.x, 10.0)
        self.assertEqual(reversed_seg.end.x, 0.0)


class TestParsePathD(unittest.TestCase):
    """Tests for path d attribute parsing."""

    def test_parse_simple_line(self):
        """Parse simple M L path."""
        commands = parse_path_d("M 10 20 L 30 40")
        self.assertEqual(len(commands), 2)
        self.assertEqual(commands[0], ("M", [10.0, 20.0]))
        self.assertEqual(commands[1], ("L", [30.0, 40.0]))

    def test_parse_negative_coords(self):
        """Parse paths with negative coordinates."""
        commands = parse_path_d("M -10 -20 L -30 40")
        self.assertEqual(commands[0], ("M", [-10.0, -20.0]))
        self.assertEqual(commands[1], ("L", [-30.0, 40.0]))

    def test_parse_cubic_bezier(self):
        """Parse cubic bezier command."""
        commands = parse_path_d("M 0 0 C 10 20 30 40 50 60")
        self.assertEqual(len(commands), 2)
        self.assertEqual(commands[1][0], "C")
        self.assertEqual(len(commands[1][1]), 6)

    def test_parse_close_path(self):
        """Parse path with close command."""
        commands = parse_path_d("M 0 0 L 10 0 L 10 10 Z")
        self.assertEqual(commands[-1], ("Z", []))


class TestExtractEndpoints(unittest.TestCase):
    """Tests for endpoint extraction from paths."""

    def test_simple_line_endpoints(self):
        """Extract endpoints from simple line."""
        endpoints = extract_endpoints("M 10 20 L 30 40")
        self.assertIsNotNone(endpoints)
        start, end = endpoints
        self.assertEqual(start.x, 10.0)
        self.assertEqual(start.y, 20.0)
        self.assertEqual(end.x, 30.0)
        self.assertEqual(end.y, 40.0)

    def test_multiline_endpoints(self):
        """Extract endpoints from multi-segment line."""
        endpoints = extract_endpoints("M 0 0 L 10 0 L 20 10 L 30 10")
        self.assertIsNotNone(endpoints)
        start, end = endpoints
        self.assertEqual(start.as_tuple(), (0.0, 0.0))
        self.assertEqual(end.as_tuple(), (30.0, 10.0))

    def test_closed_path_endpoints(self):
        """Closed path returns to start."""
        endpoints = extract_endpoints("M 0 0 L 10 0 L 10 10 Z")
        self.assertIsNotNone(endpoints)
        start, end = endpoints
        self.assertEqual(start.as_tuple(), end.as_tuple())

    def test_horizontal_vertical(self):
        """H and V commands work correctly."""
        endpoints = extract_endpoints("M 0 0 H 10 V 20")
        self.assertIsNotNone(endpoints)
        start, end = endpoints
        self.assertEqual(end.as_tuple(), (10.0, 20.0))

    def test_relative_commands(self):
        """Relative commands (lowercase) work correctly."""
        endpoints = extract_endpoints("M 10 10 l 5 5 h 10 v 10")
        self.assertIsNotNone(endpoints)
        start, end = endpoints
        self.assertEqual(start.as_tuple(), (10.0, 10.0))
        self.assertEqual(end.as_tuple(), (25.0, 25.0))


class TestColorParsing(unittest.TestCase):
    """Tests for color format conversion."""

    def test_rgb_percent_to_hex_black(self):
        """Convert black from rgb percent to hex."""
        result = rgb_percent_to_hex("rgb(0%, 0%, 0%)")
        self.assertEqual(result, "#000000")

    def test_rgb_percent_to_hex_white(self):
        """Convert white from rgb percent to hex."""
        result = rgb_percent_to_hex("rgb(100%, 100%, 100%)")
        self.assertEqual(result, "#FFFFFF")

    def test_rgb_percent_to_hex_gray(self):
        """Convert gray from rgb percent to hex."""
        result = rgb_percent_to_hex("rgb(50%, 50%, 50%)")
        self.assertEqual(result, "#7F7F7F")

    def test_is_white_stroke(self):
        """Detect white stroke colors."""
        self.assertTrue(is_white_stroke("rgb(100%, 100%, 100%)"))
        self.assertFalse(is_white_stroke("rgb(0%, 0%, 0%)"))

    def test_is_path_closed(self):
        """Detect closed paths."""
        self.assertTrue(is_path_closed("M 0 0 L 10 10 Z"))
        self.assertTrue(is_path_closed("M 0 0 L 10 10 z"))
        self.assertFalse(is_path_closed("M 0 0 L 10 10"))


class TestSpatialIndex(unittest.TestCase):
    """Tests for spatial indexing."""

    def test_add_and_find_segment(self):
        """Add segment and find it via spatial lookup."""
        index = SpatialIndex(tolerance=0.5)
        attrs = VisualAttrs(stroke_width=1.0, stroke_color="#000")
        segment = PathSegment(
            segment_id=0,
            start=Point(0.0, 0.0),
            end=Point(10.0, 10.0),
            d_attribute="M 0 0 L 10 10",
            visual_attrs=attrs,
            is_closed=False,
        )
        index.add_segment(segment)

        # Find near start point
        nearby = list(index.find_nearby_endpoints(Point(0.1, 0.1)))
        self.assertEqual(len(nearby), 1)
        self.assertEqual(nearby[0][0], 0)  # segment_id
        self.assertTrue(nearby[0][1])  # is_start

    def test_find_nearby_excludes_self(self):
        """Finding nearby excludes the query segment."""
        index = SpatialIndex(tolerance=0.5)
        attrs = VisualAttrs(stroke_width=1.0, stroke_color="#000")
        segment = PathSegment(
            segment_id=0,
            start=Point(0.0, 0.0),
            end=Point(10.0, 10.0),
            d_attribute="M 0 0 L 10 10",
            visual_attrs=attrs,
            is_closed=False,
        )
        index.add_segment(segment)

        # Find near start point, excluding self
        nearby = list(index.find_nearby_endpoints(Point(0.0, 0.0), exclude_segment_id=0))
        self.assertEqual(len(nearby), 0)

    def test_find_connections(self):
        """Find connected segments."""
        index = SpatialIndex(tolerance=0.5)
        attrs = VisualAttrs(stroke_width=1.0, stroke_color="#000")

        seg1 = PathSegment(0, Point(0.0, 0.0), Point(10.0, 0.0), "M 0 0 L 10 0", attrs, False)
        seg2 = PathSegment(1, Point(10.0, 0.0), Point(20.0, 0.0), "M 10 0 L 20 0", attrs, False)

        index.add_segment(seg1)
        index.add_segment(seg2)

        start_conns, end_conns = index.find_connections(seg1)
        # seg1's end should connect to seg2's start
        self.assertEqual(len(end_conns), 1)
        self.assertEqual(end_conns[0][0], 1)  # segment_id
        self.assertTrue(end_conns[0][1])  # connected at seg2's start


class TestUnionFind(unittest.TestCase):
    """Tests for Union-Find data structure."""

    def test_initial_state(self):
        """Each element starts in its own component."""
        uf = UnionFind(5)
        for i in range(5):
            self.assertEqual(uf.find(i), i)

    def test_union_joins_components(self):
        """Union joins two components."""
        uf = UnionFind(5)
        uf.union(0, 1)
        self.assertEqual(uf.find(0), uf.find(1))

    def test_transitive_union(self):
        """Unions are transitive."""
        uf = UnionFind(5)
        uf.union(0, 1)
        uf.union(1, 2)
        self.assertEqual(uf.find(0), uf.find(2))

    def test_get_components(self):
        """Get all components correctly."""
        uf = UnionFind(5)
        uf.union(0, 1)
        uf.union(2, 3)
        components = uf.get_components()
        self.assertEqual(len(components), 3)  # {0,1}, {2,3}, {4}


class TestClustering(unittest.TestCase):
    """Tests for segment clustering."""

    def test_cluster_single_segment(self):
        """Single segment becomes orphan if open."""
        attrs = VisualAttrs(stroke_width=1.0, stroke_color="#000")
        segment = PathSegment(0, Point(0.0, 0.0), Point(10.0, 10.0), "M 0 0 L 10 10", attrs, False)

        result = cluster_segments([segment], tolerance=0.5)
        self.assertEqual(result.stats.total_input_segments, 1)
        self.assertEqual(len(result.orphan_segments), 1)
        self.assertEqual(len(result.chains), 0)

    def test_cluster_two_connected_segments(self):
        """Two connected segments form one chain."""
        attrs = VisualAttrs(stroke_width=1.0, stroke_color="#000")
        seg1 = PathSegment(0, Point(0.0, 0.0), Point(10.0, 0.0), "M 0 0 L 10 0", attrs, False)
        seg2 = PathSegment(1, Point(10.0, 0.0), Point(20.0, 0.0), "M 10 0 L 20 0", attrs, False)

        result = cluster_segments([seg1, seg2], tolerance=0.5)
        self.assertEqual(len(result.chains), 1)
        self.assertEqual(result.chains[0].segment_count, 2)
        self.assertEqual(len(result.orphan_segments), 0)

    def test_cluster_three_segment_chain(self):
        """Three connected segments form one chain."""
        attrs = VisualAttrs(stroke_width=1.0, stroke_color="#000")
        seg1 = PathSegment(0, Point(0.0, 0.0), Point(10.0, 0.0), "M 0 0 L 10 0", attrs, False)
        seg2 = PathSegment(1, Point(10.0, 0.0), Point(20.0, 0.0), "M 10 0 L 20 0", attrs, False)
        seg3 = PathSegment(2, Point(20.0, 0.0), Point(30.0, 0.0), "M 20 0 L 30 0", attrs, False)

        result = cluster_segments([seg1, seg2, seg3], tolerance=0.5)
        self.assertEqual(len(result.chains), 1)
        self.assertEqual(result.chains[0].segment_count, 3)

    def test_cluster_disconnected_segments(self):
        """Disconnected segments don't cluster."""
        attrs = VisualAttrs(stroke_width=1.0, stroke_color="#000")
        seg1 = PathSegment(0, Point(0.0, 0.0), Point(10.0, 0.0), "M 0 0 L 10 0", attrs, False)
        seg2 = PathSegment(1, Point(100.0, 0.0), Point(110.0, 0.0), "M 100 0 L 110 0", attrs, False)

        result = cluster_segments([seg1, seg2], tolerance=0.5)
        self.assertEqual(len(result.chains), 0)
        self.assertEqual(len(result.orphan_segments), 2)

    def test_cluster_closed_loop(self):
        """Closed loop is detected."""
        attrs = VisualAttrs(stroke_width=1.0, stroke_color="#000")
        seg1 = PathSegment(0, Point(0.0, 0.0), Point(10.0, 0.0), "M 0 0 L 10 0", attrs, False)
        seg2 = PathSegment(1, Point(10.0, 0.0), Point(10.0, 10.0), "M 10 0 L 10 10", attrs, False)
        seg3 = PathSegment(2, Point(10.0, 10.0), Point(0.0, 10.0), "M 10 10 L 0 10", attrs, False)
        seg4 = PathSegment(3, Point(0.0, 10.0), Point(0.0, 0.0), "M 0 10 L 0 0", attrs, False)

        result = cluster_segments([seg1, seg2, seg3, seg4], tolerance=0.5)
        self.assertEqual(len(result.chains), 1)
        self.assertTrue(result.chains[0].is_loop)


class TestMerging(unittest.TestCase):
    """Tests for path merging."""

    def test_reverse_simple_line(self):
        """Reverse a simple line path."""
        d = "M 0 0 L 10 10"
        reversed_d = reverse_path_d(d)
        # Should start at (10, 10) and go to (0, 0)
        commands = parse_path_commands(reversed_d)
        self.assertEqual(commands[0][0], "M")
        self.assertEqual(commands[0][1], [10.0, 10.0])
        self.assertEqual(commands[1][0], "L")
        self.assertEqual(commands[1][1], [0.0, 0.0])

    def test_strip_leading_move(self):
        """Strip M command from path start."""
        d = "M 0 0 L 10 10"
        stripped = strip_leading_move(d)
        commands = parse_path_commands(stripped)
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][0], "L")

    def test_merge_two_segments(self):
        """Merge two connected segments."""
        attrs = VisualAttrs(stroke_width=1.0, stroke_color="#000")
        seg1 = PathSegment(0, Point(0.0, 0.0), Point(10.0, 0.0), "M 0 0 L 10 0", attrs, False)
        seg2 = PathSegment(1, Point(10.0, 0.0), Point(20.0, 0.0), "M 10 0 L 20 0", attrs, False)

        segments_by_id = {0: seg1, 1: seg2}
        ordered = [(0, False), (1, False)]

        merged = merge_chain_paths(ordered, segments_by_id)

        # Should have M 0 0 L 10 0 L 20 0
        commands = parse_path_commands(merged)
        # First M, then L for first segment end, then L for second segment end
        self.assertEqual(commands[0][0], "M")
        self.assertEqual(commands[0][1], [0.0, 0.0])

    def test_commands_to_d(self):
        """Convert commands back to d string."""
        commands = [("M", [0.0, 0.0]), ("L", [10.0, 10.0])]
        d = commands_to_d(commands)
        self.assertIn("M", d)
        self.assertIn("L", d)


class TestOutput(unittest.TestCase):
    """Tests for SVG output generation."""

    def test_create_svg_root(self):
        """Create SVG root with correct attributes."""
        root = create_svg_root("100", "200", "0 0 100 200")
        self.assertEqual(root.get("width"), "100")
        self.assertEqual(root.get("height"), "200")
        self.assertEqual(root.get("viewBox"), "0 0 100 200")

    def test_create_path_element(self):
        """Create path element with correct attributes."""
        attrs = VisualAttrs(stroke_width=2.0, stroke_color="#FF0000")
        elem = create_path_element("M 0 0 L 10 10", attrs)
        self.assertEqual(elem.get("d"), "M 0 0 L 10 10")
        self.assertEqual(elem.get("stroke"), "#FF0000")
        self.assertEqual(elem.get("stroke-width"), "2.0")
        self.assertEqual(elem.get("fill"), "none")

    def test_create_path_element_with_transform(self):
        """Transform is applied to path element."""
        attrs = VisualAttrs(stroke_width=1.0, stroke_color="#000")
        elem = create_path_element("M 0 0 L 10 10", attrs, "rotate(45)")
        self.assertEqual(elem.get("transform"), "rotate(45)")

    def test_group_chains_by_attrs(self):
        """Chains are grouped by visual attributes."""
        attrs1 = VisualAttrs(stroke_width=1.0, stroke_color="#000")
        attrs2 = VisualAttrs(stroke_width=2.0, stroke_color="#F00")

        chain1 = PathChain(0, (0,), "M 0 0 L 10 10", attrs1, False)
        chain2 = PathChain(1, (1,), "M 20 20 L 30 30", attrs1, False)
        chain3 = PathChain(2, (2,), "M 40 40 L 50 50", attrs2, False)

        grouped = group_chains_by_attrs([chain1, chain2, chain3])
        self.assertEqual(len(grouped), 2)
        self.assertEqual(len(grouped[attrs1]), 2)
        self.assertEqual(len(grouped[attrs2]), 1)


if __name__ == "__main__":
    unittest.main()
