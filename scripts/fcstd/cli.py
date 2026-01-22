"""
Command-line interface for FCStd file management.

Usage:
    python -m scripts.fcstd explode <file.FCStd>
    python -m scripts.fcstd pack <directory.fcstd.d>
    python -m scripts.fcstd status [path]
"""

import sys
from pathlib import Path
from typing import Optional

from scripts.fcstd.types import Ok, Err, SyncStatus, SyncState
from scripts.fcstd.explode import explode_fcstd
from scripts.fcstd.pack import pack_fcstd


def _get_sync_status(base_path: Path) -> SyncStatus:
    """
    Determine sync status for an FCStd/directory pair.

    Args:
        base_path: Either an FCStd file or .fcstd.d directory

    Returns:
        SyncStatus indicating current state
    """
    base_path = Path(base_path).resolve()

    if base_path.suffix.lower() == ".fcstd":
        fcstd_path = base_path
        dir_path = base_path.parent / f"{base_path.stem.lower()}.fcstd.d"
    elif base_path.name.endswith(".fcstd.d"):
        dir_path = base_path
        stem = base_path.name[:-8]
        fcstd_path = base_path.parent / f"{stem}.FCStd"
    else:
        fcstd_path = base_path.with_suffix(".FCStd")
        dir_path = base_path.parent / f"{base_path.stem.lower()}.fcstd.d"

    fcstd_exists = fcstd_path.exists()
    dir_exists = dir_path.exists()

    fcstd_mtime: Optional[float] = None
    dir_mtime: Optional[float] = None

    if fcstd_exists:
        fcstd_mtime = fcstd_path.stat().st_mtime

    if dir_exists:
        dir_mtime = _get_newest_mtime(dir_path)

    if not fcstd_exists and not dir_exists:
        state = SyncState.BOTH_MISSING
    elif not fcstd_exists:
        state = SyncState.FCSTD_MISSING
    elif not dir_exists:
        state = SyncState.DIRECTORY_MISSING
    elif fcstd_mtime is not None and dir_mtime is not None:
        if abs(fcstd_mtime - dir_mtime) < 1.0:
            state = SyncState.IN_SYNC
        elif fcstd_mtime > dir_mtime:
            state = SyncState.FCSTD_NEWER
        else:
            state = SyncState.DIRECTORY_NEWER
    else:
        state = SyncState.IN_SYNC

    return SyncStatus(
        fcstd_path=fcstd_path,
        directory_path=dir_path,
        state=state,
        fcstd_mtime=fcstd_mtime,
        directory_mtime=dir_mtime,
    )


def _get_newest_mtime(directory: Path) -> float:
    """Get the newest modification time of any file in directory."""
    newest = 0.0
    for path in directory.rglob("*"):
        if path.is_file():
            mtime = path.stat().st_mtime
            if mtime > newest:
                newest = mtime
    return newest


def _find_fcstd_pairs(search_path: Path) -> list[Path]:
    """
    Find all FCStd/directory pairs under search_path.

    Returns deduplicated list, normalizing directories to their FCStd path.
    """
    seen_stems = set()
    results = []

    for fcstd in search_path.rglob("*.FCStd"):
        stem = fcstd.stem.lower()
        key = (fcstd.parent, stem)
        if key not in seen_stems:
            seen_stems.add(key)
            results.append(fcstd)

    for fcstd_d in search_path.rglob("*.fcstd.d"):
        if fcstd_d.is_dir():
            stem = fcstd_d.name[:-8]
            key = (fcstd_d.parent, stem)
            if key not in seen_stems:
                seen_stems.add(key)
                results.append(fcstd_d)

    return sorted(results)


def cmd_explode(args: list[str]) -> int:
    """Handle the explode command."""
    if not args:
        print("Usage: python -m scripts.fcstd explode <file.FCStd>")
        return 1

    fcstd_path = Path(args[0])
    result = explode_fcstd(fcstd_path)

    if isinstance(result, Err):
        print(f"Error: {result.message}")
        return 1

    explode_result = result.value
    print(f"Exploded: {explode_result.manifest.source_path}")
    print(f"      To: {explode_result.output_dir}")
    print(f"   Files: {explode_result.files_written}")
    print(f"     XML: {explode_result.xml_files_prettified} prettified")
    return 0


def cmd_pack(args: list[str]) -> int:
    """Handle the pack command."""
    if not args:
        print("Usage: python -m scripts.fcstd pack <directory.fcstd.d>")
        return 1

    directory = Path(args[0])
    result = pack_fcstd(directory)

    if isinstance(result, Err):
        print(f"Error: {result.message}")
        return 1

    pack_result = result.value
    ratio = pack_result.compressed_size / pack_result.total_size
    print(f"Packed: {directory}")
    print(f"    To: {pack_result.output_path}")
    print(f" Files: {pack_result.files_packed}")
    print(f"  Size: {pack_result.total_size:,} -> {pack_result.compressed_size:,} ({ratio:.1%})")
    return 0


def cmd_status(args: list[str]) -> int:
    """Handle the status command."""
    search_path = Path(args[0]) if args else Path.cwd()

    if search_path.is_file() or search_path.name.endswith(".fcstd.d"):
        pairs = [search_path]
    else:
        pairs = _find_fcstd_pairs(search_path)

    if not pairs:
        print(f"No FCStd files found in {search_path}")
        return 0

    for pair_path in pairs:
        status = _get_sync_status(pair_path)
        state_str = {
            SyncState.IN_SYNC: "in sync",
            SyncState.FCSTD_NEWER: "FCStd newer (needs explode)",
            SyncState.DIRECTORY_NEWER: "directory newer (needs pack)",
            SyncState.FCSTD_MISSING: "FCStd missing (needs pack)",
            SyncState.DIRECTORY_MISSING: "directory missing (needs explode)",
            SyncState.BOTH_MISSING: "both missing",
        }[status.state]

        fcstd_name = status.fcstd_path.name
        print(f"{fcstd_name}: {state_str}")

    return 0


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.fcstd <command> [args]")
        print("")
        print("Commands:")
        print("  explode <file.FCStd>     Extract to .fcstd.d directory")
        print("  pack <dir.fcstd.d>       Pack into .FCStd file")
        print("  status [path]            Show sync status")
        return 1

    command = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        "explode": cmd_explode,
        "pack": cmd_pack,
        "status": cmd_status,
    }

    if command not in commands:
        print(f"Unknown command: {command}")
        return 1

    return commands[command](args)


if __name__ == "__main__":
    sys.exit(main())
