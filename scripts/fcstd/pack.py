"""
Pack exploded directories back into FCStd archives.

Creates valid FCStd (ZIP) files from .fcstd.d directories.
Uses DEFLATE compression for all files.
"""

import zipfile
from pathlib import Path
from typing import Union

from scripts.fcstd.types import (
    PackResult,
    Ok,
    Err,
    FCStdError,
)


def _collect_files(directory: Path) -> list[tuple[Path, str]]:
    """
    Collect all files in directory with their archive paths.

    Returns list of (filesystem_path, archive_path) tuples.
    Excludes the thumbnails/ directory.
    """
    files = []
    for path in directory.rglob("*"):
        if path.is_dir():
            continue
        relative = path.relative_to(directory)
        if relative.parts[0] == "thumbnails":
            continue
        files.append((path, str(relative)))
    return files


def pack_fcstd(directory: Path) -> Union[Ok, Err]:
    """
    Pack a .fcstd.d directory into an FCStd file.

    The output FCStd is created alongside the directory by removing
    the .fcstd.d suffix and adding .FCStd.

    Args:
        directory: Path to the .fcstd.d directory

    Returns:
        Ok(PackResult) on success, Err on failure
    """
    directory = Path(directory).resolve()

    if not directory.exists():
        return Err(
            FCStdError.DIRECTORY_NOT_FOUND,
            f"Directory not found: {directory}",
        )

    if not directory.is_dir():
        return Err(
            FCStdError.DIRECTORY_NOT_FOUND,
            f"Not a directory: {directory}",
        )

    document_xml = directory / "Document.xml"
    if not document_xml.exists():
        return Err(
            FCStdError.MISSING_DOCUMENT_XML,
            f"Missing Document.xml in {directory}",
        )

    dir_name = directory.name
    if not dir_name.endswith(".fcstd.d"):
        return Err(
            FCStdError.INVALID_FCSTD,
            f"Directory must end with .fcstd.d: {directory}",
        )

    stem = dir_name[:-8]
    output_path = directory.parent / f"{stem}.FCStd"

    try:
        files = _collect_files(directory)

        total_size = 0
        compressed_size = 0

        with zipfile.ZipFile(
            output_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as zf:
            for fs_path, archive_path in files:
                content = fs_path.read_bytes()
                total_size += len(content)

                zf.writestr(archive_path, content)

        compressed_size = output_path.stat().st_size

        result = PackResult(
            output_path=output_path,
            files_packed=len(files),
            total_size=total_size,
            compressed_size=compressed_size,
        )
        return Ok(result)

    except OSError as e:
        return Err(FCStdError.WRITE_FAILED, f"Write failed: {e}")
