"""
SVG Path Clustering Module

Clusters connected SVG path segments into continuous polylines,
reducing path count and organizing by visual attributes.
"""

from .types import Point, PathSegment, PathChain, ClusterResult, VisualAttrs
from .parsing import parse_svg_paths, extract_endpoints
from .spatial_index import SpatialIndex
from .clustering import cluster_segments, cluster_by_visual_attrs
from .merging import merge_chain_paths
from .output import write_clustered_svg, write_clustered_svg_by_attrs

__all__ = [
    "Point",
    "PathSegment",
    "PathChain",
    "ClusterResult",
    "VisualAttrs",
    "parse_svg_paths",
    "extract_endpoints",
    "SpatialIndex",
    "cluster_segments",
    "cluster_by_visual_attrs",
    "merge_chain_paths",
    "write_clustered_svg",
    "write_clustered_svg_by_attrs",
]
