"""
Spatial indexing for efficient endpoint matching.

Uses a grid-based spatial hash for O(1) average-case lookup of
endpoints within a tolerance distance.
"""

from typing import Iterator, Tuple
from collections import defaultdict
import math

from .types import Point, PathSegment


class SpatialIndex:
    """
    Grid-based spatial hash for endpoint lookups.

    Divides the coordinate space into cells of size (2 * tolerance).
    Each endpoint is stored in its containing cell. To find nearby
    points, we check the containing cell plus all 8 neighbors.
    """

    def __init__(self, tolerance: float):
        """
        Initialize spatial index with given tolerance.

        Args:
            tolerance: Maximum distance for two points to be considered connected
        """
        self.tolerance = tolerance
        self.cell_size = tolerance * 2.0

        # Maps (cell_x, cell_y) -> list of (point, segment_id, is_start)
        self._grid: dict[Tuple[int, int], list[Tuple[Point, int, bool]]] = defaultdict(list)

        # Maps segment_id -> PathSegment for quick lookup
        self._segments: dict[int, PathSegment] = {}

    def _cell_coords(self, point: Point) -> Tuple[int, int]:
        """Compute the grid cell coordinates for a point."""
        cell_x = int(math.floor(point.x / self.cell_size))
        cell_y = int(math.floor(point.y / self.cell_size))
        return (cell_x, cell_y)

    def add_segment(self, segment: PathSegment) -> None:
        """
        Add a segment's endpoints to the spatial index.

        Both start and end points are indexed separately.

        Args:
            segment: The path segment to index
        """
        self._segments[segment.segment_id] = segment

        # Index start point
        start_cell = self._cell_coords(segment.start)
        self._grid[start_cell].append((segment.start, segment.segment_id, True))

        # Index end point (unless it's a closed path back to start)
        if not segment.is_closed or not segment.start.is_near(segment.end, self.tolerance):
            end_cell = self._cell_coords(segment.end)
            self._grid[end_cell].append((segment.end, segment.segment_id, False))

    def add_segments(self, segments: list[PathSegment]) -> None:
        """
        Add multiple segments to the index.

        Args:
            segments: List of path segments to index
        """
        for segment in segments:
            self.add_segment(segment)

    def _neighboring_cells(self, cell: Tuple[int, int]) -> Iterator[Tuple[int, int]]:
        """Yield the cell and its 8 neighbors."""
        cx, cy = cell
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                yield (cx + dx, cy + dy)

    def find_nearby_endpoints(
        self,
        point: Point,
        exclude_segment_id: int = -1,
    ) -> Iterator[Tuple[int, bool, float]]:
        """
        Find all endpoints within tolerance of a point.

        Args:
            point: The query point
            exclude_segment_id: Segment ID to exclude from results (typically
                               the segment containing the query point)

        Yields:
            Tuples of (segment_id, is_start_endpoint, distance) for each
            nearby endpoint, sorted by distance.
        """
        results: list[Tuple[int, bool, float]] = []
        cell = self._cell_coords(point)

        for neighbor_cell in self._neighboring_cells(cell):
            for indexed_point, segment_id, is_start in self._grid.get(neighbor_cell, []):
                if segment_id == exclude_segment_id:
                    continue

                distance = point.distance_to(indexed_point)
                if distance <= self.tolerance:
                    results.append((segment_id, is_start, distance))

        # Sort by distance for deterministic ordering
        results.sort(key=lambda x: (x[2], x[0]))
        yield from results

    def find_connections(
        self,
        segment: PathSegment,
    ) -> Tuple[list[Tuple[int, bool]], list[Tuple[int, bool]]]:
        """
        Find all segments connected to a given segment's endpoints.

        Args:
            segment: The segment to find connections for

        Returns:
            Tuple of (start_connections, end_connections) where each is a list
            of (segment_id, connected_at_start) tuples indicating which segments
            connect and whether they connect at their start or end point.
        """
        start_connections = [
            (seg_id, is_start)
            for seg_id, is_start, _ in self.find_nearby_endpoints(
                segment.start, segment.segment_id
            )
        ]

        end_connections = [
            (seg_id, is_start)
            for seg_id, is_start, _ in self.find_nearby_endpoints(
                segment.end, segment.segment_id
            )
        ]

        return (start_connections, end_connections)

    def get_segment(self, segment_id: int) -> PathSegment:
        """
        Retrieve a segment by its ID.

        Args:
            segment_id: The segment ID

        Returns:
            The PathSegment

        Raises:
            KeyError: If segment_id not found
        """
        return self._segments[segment_id]

    def get_all_segments(self) -> list[PathSegment]:
        """Return all indexed segments."""
        return list(self._segments.values())

    @property
    def segment_count(self) -> int:
        """Number of segments in the index."""
        return len(self._segments)
