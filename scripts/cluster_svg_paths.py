#!/usr/bin/env python3
"""
SVG Path Clustering Tool

Clusters connected path segments in an SVG file into continuous polylines,
reducing path count and organizing by visual attributes.

Usage:
    python cluster_svg_paths.py <input.svg> [output.svg] [--tolerance=0.5]
"""

import argparse
import sys
from pathlib import Path

from svg_path_clustering import (
    parse_svg_paths,
    cluster_segments,
    cluster_by_visual_attrs,
    write_clustered_svg,
    write_clustered_svg_by_attrs,
)
from svg_path_clustering.parsing import get_svg_dimensions
from svg_path_clustering.output import print_cluster_stats


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Cluster connected SVG path segments into polylines"
    )
    parser.add_argument("input", help="Input SVG file")
    parser.add_argument("output", nargs="?", help="Output SVG file (default: input-clustered.svg)")
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.5,
        help="Endpoint matching tolerance (default: 0.5)",
    )
    parser.add_argument(
        "--keep-white",
        action="store_true",
        help="Keep white stroke paths (background halos)",
    )
    parser.add_argument(
        "--by-attrs",
        action="store_true",
        help="Cluster each visual attribute group separately",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        return 1

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_stem(input_path.stem + "-clustered")

    print(f"Input: {input_path}")
    print(f"Output: {output_path}")
    print(f"Tolerance: {args.tolerance}")
    print()

    # Parse SVG
    print("Parsing SVG paths...")
    segments, common_transform = parse_svg_paths(input_path, skip_white=not args.keep_white)
    print(f"Extracted {len(segments)} path segments")

    if not segments:
        print("No segments found to cluster")
        return 1

    # Get SVG dimensions
    width, height, viewbox = get_svg_dimensions(input_path)

    if args.by_attrs:
        # Cluster each visual attribute group separately
        print("\nClustering by visual attributes...")
        results_by_attrs = cluster_by_visual_attrs(segments, args.tolerance)

        total_chains = 0
        total_orphans = 0
        for attrs, result in results_by_attrs.items():
            print(f"\n{attrs.stroke_color} (width {attrs.stroke_width}):")
            print_cluster_stats(result, "  ")
            total_chains += result.stats.total_chains
            total_orphans += result.stats.orphan_count

        print(f"\nTotal output paths: {total_chains + total_orphans}")

        # Write output
        print(f"\nWriting output to {output_path}...")
        write_clustered_svg_by_attrs(
            output_path,
            results_by_attrs,
            width,
            height,
            viewbox,
            common_transform,
        )
    else:
        # Cluster all segments together
        print("\nClustering segments...")
        result = cluster_segments(segments, args.tolerance)

        print("\nClustering results:")
        print_cluster_stats(result)

        # Write output
        print(f"\nWriting output to {output_path}...")
        write_clustered_svg(
            output_path,
            result,
            width,
            height,
            viewbox,
            common_transform,
        )

    print("Done!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
