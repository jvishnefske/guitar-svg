"""
FreeCAD FCStd file management for git workflows.

FCStd files are ZIP archives containing XML and geometry data.
This module provides tools to explode them into trackable directories
and repack them for FreeCAD.
"""

from scripts.fcstd.types import (
    FCStdManifest,
    FileEntry,
    ExplodeResult,
    PackResult,
    SyncStatus,
    FCStdError,
)
from scripts.fcstd.explode import explode_fcstd
from scripts.fcstd.pack import pack_fcstd

__all__ = [
    "FCStdManifest",
    "FileEntry",
    "ExplodeResult",
    "PackResult",
    "SyncStatus",
    "FCStdError",
    "explode_fcstd",
    "pack_fcstd",
]
