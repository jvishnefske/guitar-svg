"""
Path segment clustering using Union-Find.

Groups connected segments into chains and orders segments
within each chain for path merging.
"""

from typing import Optional, Tuple
from collections import defaultdict

from .types import Point, PathSegment, PathChain, ClusterResult, VisualAttrs
from .spatial_index import SpatialIndex
from .merging import merge_chain_paths


class UnionFind:
    """
    Union-Find data structure for connected component detection.

    Uses path compression and union by rank for O(α(n)) operations.
    """

    def __init__(self, n: int):
        """
        Initialize with n elements (0 to n-1).

        Args:
            n: Number of elements
        """
        self._parent = list(range(n))
        self._rank = [0] * n

    def find(self, x: int) -> int:
        """
        Find the root of element x with path compression.

        Args:
            x: Element to find root of

        Returns:
            Root element of x's component
        """
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])
        return self._parent[x]

    def union(self, x: int, y: int) -> bool:
        """
        Union the components containing x and y.

        Args:
            x: First element
            y: Second element

        Returns:
            True if a union was performed (elements were in different components)
        """
        root_x = self.find(x)
        root_y = self.find(y)

        if root_x == root_y:
            return False

        # Union by rank
        if self._rank[root_x] < self._rank[root_y]:
            self._parent[root_x] = root_y
        elif self._rank[root_x] > self._rank[root_y]:
            self._parent[root_y] = root_x
        else:
            self._parent[root_y] = root_x
            self._rank[root_x] += 1

        return True

    def get_components(self) -> dict[int, list[int]]:
        """
        Get all connected components.

        Returns:
            Dict mapping root element -> list of all elements in that component
        """
        components: dict[int, list[int]] = defaultdict(list)
        for i in range(len(self._parent)):
            components[self.find(i)].append(i)
        return dict(components)


def build_adjacency_graph(
    segments: list[PathSegment],
    spatial_index: SpatialIndex,
) -> dict[int, list[Tuple[int, bool, bool]]]:
    """
    Build an adjacency graph for segments based on endpoint connectivity.

    Args:
        segments: List of path segments
        spatial_index: Spatial index with all segments added

    Returns:
        Dict mapping segment_id -> list of (connected_segment_id, this_at_start, other_at_start)
        where this_at_start indicates if connection is at this segment's start point,
        and other_at_start indicates if connection is at other segment's start point.
    """
    adjacency: dict[int, list[Tuple[int, bool, bool]]] = defaultdict(list)

    for segment in segments:
        start_conns, end_conns = spatial_index.find_connections(segment)

        # Connections at this segment's start
        for other_id, other_at_start in start_conns:
            adjacency[segment.segment_id].append((other_id, True, other_at_start))

        # Connections at this segment's end
        for other_id, other_at_start in end_conns:
            adjacency[segment.segment_id].append((other_id, False, other_at_start))

    return dict(adjacency)


def find_connected_components(
    segments: list[PathSegment],
    adjacency: dict[int, list[Tuple[int, bool, bool]]],
) -> dict[int, list[int]]:
    """
    Find connected components among segments.

    Args:
        segments: List of all segments
        adjacency: Adjacency graph from build_adjacency_graph

    Returns:
        Dict mapping component root -> list of segment_ids in component
    """
    # Create mapping from segment_id to index for Union-Find
    id_to_idx = {seg.segment_id: i for i, seg in enumerate(segments)}
    idx_to_id = {i: seg.segment_id for i, seg in enumerate(segments)}

    uf = UnionFind(len(segments))

    # Union connected segments
    for seg_id, connections in adjacency.items():
        for other_id, _, _ in connections:
            uf.union(id_to_idx[seg_id], id_to_idx[other_id])

    # Convert back to segment IDs
    idx_components = uf.get_components()
    return {
        idx_to_id[root]: [idx_to_id[i] for i in members]
        for root, members in idx_components.items()
    }


def order_chain_segments(
    component_ids: list[int],
    adjacency: dict[int, list[Tuple[int, bool, bool]]],
    segments_by_id: dict[int, PathSegment],
    tolerance: float,
) -> Tuple[list[Tuple[int, bool]], bool]:
    """
    Order segments within a connected component for traversal.

    Walks the adjacency graph to produce an ordered sequence of segments,
    tracking whether each segment needs to be reversed.

    Args:
        component_ids: Segment IDs in this component
        adjacency: Adjacency graph
        segments_by_id: Mapping of segment_id -> PathSegment
        tolerance: Distance tolerance for endpoint matching

    Returns:
        Tuple of (ordered_segments, is_loop) where ordered_segments is a list
        of (segment_id, needs_reversal) tuples and is_loop indicates if the
        chain forms a closed loop.
    """
    if len(component_ids) == 1:
        return ([(component_ids[0], False)], False)

    component_set = set(component_ids)

    # Build degree map (how many connections each segment has within component)
    degree: dict[int, int] = defaultdict(int)
    for seg_id in component_ids:
        for other_id, _, _ in adjacency.get(seg_id, []):
            if other_id in component_set:
                degree[seg_id] += 1

    # Find endpoint segments (degree 1) to start traversal
    # If none exist, it's a loop - start anywhere
    endpoints = [seg_id for seg_id in component_ids if degree[seg_id] == 1]
    is_loop = len(endpoints) == 0

    if is_loop:
        start_id = component_ids[0]
        start_at_end = False  # Arbitrary starting orientation
    else:
        start_id = endpoints[0]
        # Check which end is the "free" end (not connected)
        conns_at_start = sum(
            1 for other_id, this_at_start, _ in adjacency.get(start_id, [])
            if this_at_start and other_id in component_set
        )
        start_at_end = conns_at_start > 0  # If connected at start, begin from end

    # Walk the chain
    ordered: list[Tuple[int, bool]] = []
    visited: set[int] = set()
    current_id = start_id
    current_exit_from_end = not start_at_end  # We enter at start, exit from end

    while current_id not in visited:
        visited.add(current_id)

        # Determine if this segment needs reversal
        # We want to traverse start->end, so if we're entering at end, reverse
        needs_reversal = not current_exit_from_end
        ordered.append((current_id, needs_reversal))

        # Find next segment
        next_id: Optional[int] = None
        next_enters_at_start: Optional[bool] = None

        for other_id, this_at_start, other_at_start in adjacency.get(current_id, []):
            if other_id in component_set and other_id not in visited:
                # Check if this connection is from our current exit point
                # If exiting from end (current_exit_from_end=True), want this_at_start=False
                # If exiting from start (current_exit_from_end=False), want this_at_start=True
                if this_at_start == current_exit_from_end:
                    continue
                next_id = other_id
                next_enters_at_start = other_at_start
                break

        if next_id is None:
            break

        current_id = next_id
        # We enter the next segment at next_enters_at_start
        # If entering at start, we exit from end (and vice versa)
        current_exit_from_end = next_enters_at_start

    return (ordered, is_loop)


def cluster_segments(
    segments: list[PathSegment],
    tolerance: float = 0.5,
) -> ClusterResult:
    """
    Cluster connected path segments into chains.

    Groups segments that share endpoints (within tolerance) into chains,
    orders them for traversal, and merges their path data.

    Args:
        segments: List of path segments to cluster
        tolerance: Maximum distance for two endpoints to be considered connected

    Returns:
        ClusterResult containing chains, orphans, and statistics
    """
    if not segments:
        return ClusterResult.create([], [], 0)

    # Build spatial index
    spatial_index = SpatialIndex(tolerance)
    spatial_index.add_segments(segments)

    # Build adjacency graph
    adjacency = build_adjacency_graph(segments, spatial_index)

    # Find connected components
    components = find_connected_components(segments, adjacency)

    # Create lookup for segments by ID
    segments_by_id = {seg.segment_id: seg for seg in segments}

    # Process each component into a chain
    chains: list[PathChain] = []
    orphans: list[PathSegment] = []
    chain_id = 0

    for _, component_ids in sorted(components.items()):
        if len(component_ids) == 1:
            # Single segment - check if it's actually orphaned or self-connected
            seg = segments_by_id[component_ids[0]]
            if seg.is_closed or seg.start.is_near(seg.end, tolerance):
                # Self-closing segment - treat as single-segment chain
                chain = PathChain(
                    chain_id=chain_id,
                    segment_ids=(seg.segment_id,),
                    merged_d=seg.d_attribute,
                    visual_attrs=seg.visual_attrs,
                    is_loop=True,
                )
                chains.append(chain)
                chain_id += 1
            else:
                orphans.append(seg)
            continue

        # Get the visual attributes from first segment (all should match for valid chains)
        first_seg = segments_by_id[component_ids[0]]
        visual_attrs = first_seg.visual_attrs

        # Order segments for traversal
        ordered_segments, is_loop = order_chain_segments(
            component_ids, adjacency, segments_by_id, tolerance
        )

        # Merge path data
        merged_d = merge_chain_paths(ordered_segments, segments_by_id)

        chain = PathChain(
            chain_id=chain_id,
            segment_ids=tuple(seg_id for seg_id, _ in ordered_segments),
            merged_d=merged_d,
            visual_attrs=visual_attrs,
            is_loop=is_loop,
        )
        chains.append(chain)
        chain_id += 1

    return ClusterResult.create(chains, orphans, len(segments))


def cluster_by_visual_attrs(
    segments: list[PathSegment],
    tolerance: float = 0.5,
) -> dict[VisualAttrs, ClusterResult]:
    """
    Cluster segments separately for each unique set of visual attributes.

    Args:
        segments: List of path segments to cluster
        tolerance: Maximum distance for endpoint matching

    Returns:
        Dict mapping VisualAttrs -> ClusterResult for that attribute group
    """
    # Group segments by visual attributes
    by_attrs: dict[VisualAttrs, list[PathSegment]] = defaultdict(list)
    for segment in segments:
        by_attrs[segment.visual_attrs].append(segment)

    # Cluster each group separately
    results: dict[VisualAttrs, ClusterResult] = {}
    for attrs, group_segments in by_attrs.items():
        results[attrs] = cluster_segments(group_segments, tolerance)

    return results
