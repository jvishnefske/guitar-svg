"""
Immutable data types for SVG path clustering.

All types are frozen dataclasses to enforce immutability.
State transitions return new instances rather than mutating.
"""

from dataclasses import dataclass
from typing import Tuple
import math


@dataclass(frozen=True)
class Point:
    """
    2D point with tolerance-based comparison.

    Coordinates are stored as floats. Equality comparison uses
    a tolerance to handle floating-point imprecision in SVG coordinates.
    """
    x: float
    y: float

    def distance_to(self, other: "Point") -> float:
        """Compute Euclidean distance to another point."""
        dx = self.x - other.x
        dy = self.y - other.y
        return math.sqrt(dx * dx + dy * dy)

    def is_near(self, other: "Point", tolerance: float) -> bool:
        """Check if another point is within tolerance distance."""
        return self.distance_to(other) <= tolerance

    def as_tuple(self) -> Tuple[float, float]:
        """Return coordinates as a tuple."""
        return (self.x, self.y)


@dataclass(frozen=True)
class VisualAttrs:
    """
    Visual attributes for grouping paths.

    Paths with identical visual attributes can be grouped together
    in the output SVG.
    """
    stroke_width: float
    stroke_color: str

    def to_svg_attrs(self) -> dict:
        """Convert to SVG attribute dictionary."""
        return {
            "stroke-width": str(self.stroke_width),
            "stroke": self.stroke_color,
        }


@dataclass(frozen=True)
class PathSegment:
    """
    A single path segment extracted from an SVG path element.

    Represents the essential geometry and visual attributes of a path.
    The segment_id is used for tracking during clustering.
    """
    segment_id: int
    start: Point
    end: Point
    d_attribute: str
    visual_attrs: VisualAttrs
    is_closed: bool

    def reversed_endpoints(self) -> "PathSegment":
        """
        Return a new segment with start and end swapped.

        Note: This only swaps the endpoint references, not the d_attribute.
        Use merging.reverse_path_d() to reverse the actual path commands.
        """
        return PathSegment(
            segment_id=self.segment_id,
            start=self.end,
            end=self.start,
            d_attribute=self.d_attribute,
            visual_attrs=self.visual_attrs,
            is_closed=self.is_closed,
        )


@dataclass(frozen=True)
class PathChain:
    """
    A chain of connected path segments forming a continuous polyline.

    The segment_ids are ordered for traversal. The merged_d attribute
    contains the combined path commands for all segments in order.
    """
    chain_id: int
    segment_ids: Tuple[int, ...]
    merged_d: str
    visual_attrs: VisualAttrs
    is_loop: bool

    @property
    def segment_count(self) -> int:
        """Number of segments in this chain."""
        return len(self.segment_ids)


@dataclass(frozen=True)
class ClusterStats:
    """Statistics about the clustering operation."""
    total_input_segments: int
    total_chains: int
    orphan_count: int
    loop_count: int
    max_chain_length: int
    avg_chain_length: float


@dataclass(frozen=True)
class ClusterResult:
    """
    Complete result of a clustering operation.

    Contains all formed chains, segments that couldn't be joined,
    and statistics about the operation.
    """
    chains: Tuple[PathChain, ...]
    orphan_segments: Tuple[PathSegment, ...]
    stats: ClusterStats

    @staticmethod
    def create(
        chains: list["PathChain"],
        orphans: list["PathSegment"],
        total_input: int,
    ) -> "ClusterResult":
        """
        Factory method to create a ClusterResult with computed stats.

        Args:
            chains: List of formed chains
            orphans: List of segments not in any chain
            total_input: Total number of input segments

        Returns:
            New ClusterResult with computed statistics
        """
        chain_lengths = [c.segment_count for c in chains]
        loop_count = sum(1 for c in chains if c.is_loop)

        stats = ClusterStats(
            total_input_segments=total_input,
            total_chains=len(chains),
            orphan_count=len(orphans),
            loop_count=loop_count,
            max_chain_length=max(chain_lengths) if chain_lengths else 0,
            avg_chain_length=(
                sum(chain_lengths) / len(chain_lengths) if chain_lengths else 0.0
            ),
        )

        return ClusterResult(
            chains=tuple(chains),
            orphan_segments=tuple(orphans),
            stats=stats,
        )
