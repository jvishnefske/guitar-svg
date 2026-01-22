"""
Immutable data types for FCStd file operations.

All types are frozen dataclasses to enforce immutability.
Operations return Result types for explicit error handling.
"""

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Tuple, Optional


class FCStdError(Enum):
    """Error types for FCStd operations."""
    FILE_NOT_FOUND = auto()
    NOT_A_ZIP = auto()
    INVALID_FCSTD = auto()
    WRITE_FAILED = auto()
    XML_PARSE_ERROR = auto()
    DIRECTORY_NOT_FOUND = auto()
    MISSING_DOCUMENT_XML = auto()


@dataclass(frozen=True)
class FileEntry:
    """
    Metadata for a single file within an FCStd archive.

    Tracks the relative path, size, and compression info.
    """
    relative_path: str
    size_bytes: int
    compressed_size: int
    is_xml: bool

    @property
    def compression_ratio(self) -> float:
        """Compute compression ratio (1.0 = no compression)."""
        if self.size_bytes == 0:
            return 1.0
        return self.compressed_size / self.size_bytes


@dataclass(frozen=True)
class FCStdManifest:
    """
    Catalog of files within an FCStd archive.

    Provides immutable access to archive contents without extraction.
    """
    source_path: Path
    entries: Tuple[FileEntry, ...]

    @property
    def total_size(self) -> int:
        """Sum of uncompressed file sizes."""
        return sum(e.size_bytes for e in self.entries)

    @property
    def xml_files(self) -> Tuple[FileEntry, ...]:
        """Filter to XML files only."""
        return tuple(e for e in self.entries if e.is_xml)

    @property
    def has_document_xml(self) -> bool:
        """Check if Document.xml exists (required for valid FCStd)."""
        return any(e.relative_path == "Document.xml" for e in self.entries)


@dataclass(frozen=True)
class ExplodeResult:
    """
    Result of exploding an FCStd file to a directory.

    Contains the manifest and output location on success.
    """
    manifest: FCStdManifest
    output_dir: Path
    files_written: int
    xml_files_prettified: int


@dataclass(frozen=True)
class PackResult:
    """
    Result of packing a directory into an FCStd file.

    Contains the output path and file statistics.
    """
    output_path: Path
    files_packed: int
    total_size: int
    compressed_size: int


class SyncState(Enum):
    """Synchronization state between FCStd and directory."""
    IN_SYNC = auto()
    FCSTD_NEWER = auto()
    DIRECTORY_NEWER = auto()
    FCSTD_MISSING = auto()
    DIRECTORY_MISSING = auto()
    BOTH_MISSING = auto()


@dataclass(frozen=True)
class SyncStatus:
    """
    Synchronization status for an FCStd/directory pair.

    Tracks which is newer and what action is needed.
    """
    fcstd_path: Path
    directory_path: Path
    state: SyncState
    fcstd_mtime: Optional[float]
    directory_mtime: Optional[float]

    @property
    def needs_explode(self) -> bool:
        """True if FCStd should be exploded to update directory."""
        return self.state == SyncState.FCSTD_NEWER

    @property
    def needs_pack(self) -> bool:
        """True if directory should be packed to update FCStd."""
        return self.state == SyncState.DIRECTORY_NEWER


@dataclass(frozen=True)
class Ok:
    """Success result wrapper."""
    value: object


@dataclass(frozen=True)
class Err:
    """Error result wrapper."""
    error: FCStdError
    message: str
