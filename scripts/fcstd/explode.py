"""
Extract FCStd archives to trackable directories.

FCStd files are ZIP archives. This module extracts them while:
- Pretty-printing XML for better git diffs
- Preserving binary files exactly
- Tracking extraction metadata
"""

import zipfile
import xml.dom.minidom
from pathlib import Path
from typing import Union

from scripts.fcstd.types import (
    FCStdManifest,
    FileEntry,
    ExplodeResult,
    Ok,
    Err,
    FCStdError,
)


def _is_xml_file(filename: str) -> bool:
    """Check if a file should be treated as XML."""
    return filename.endswith(".xml") or filename.endswith(".XML")


def _prettify_xml(content: bytes) -> bytes:
    """
    Pretty-print XML content for better diffs.

    Returns original content if parsing fails.
    """
    try:
        dom = xml.dom.minidom.parseString(content)
        pretty = dom.toprettyxml(indent="  ", encoding="utf-8")
        lines = pretty.split(b"\n")
        non_empty = [line for line in lines if line.strip()]
        return b"\n".join(non_empty) + b"\n"
    except Exception:
        return content


def _build_manifest(fcstd_path: Path, zf: zipfile.ZipFile) -> FCStdManifest:
    """Build manifest from open ZIP file."""
    entries = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        entry = FileEntry(
            relative_path=info.filename,
            size_bytes=info.file_size,
            compressed_size=info.compress_size,
            is_xml=_is_xml_file(info.filename),
        )
        entries.append(entry)
    return FCStdManifest(source_path=fcstd_path, entries=tuple(entries))


def explode_fcstd(fcstd_path: Path) -> Union[Ok, Err]:
    """
    Extract FCStd archive to a .fcstd.d directory.

    The output directory is created alongside the FCStd file with
    a .fcstd.d suffix. XML files are pretty-printed for better diffs.

    Args:
        fcstd_path: Path to the FCStd file

    Returns:
        Ok(ExplodeResult) on success, Err on failure
    """
    fcstd_path = Path(fcstd_path).resolve()

    if not fcstd_path.exists():
        return Err(FCStdError.FILE_NOT_FOUND, f"File not found: {fcstd_path}")

    if not zipfile.is_zipfile(fcstd_path):
        return Err(FCStdError.NOT_A_ZIP, f"Not a valid ZIP file: {fcstd_path}")

    stem = fcstd_path.stem.lower()
    output_dir = fcstd_path.parent / f"{stem}.fcstd.d"

    try:
        with zipfile.ZipFile(fcstd_path, "r") as zf:
            manifest = _build_manifest(fcstd_path, zf)

            if not manifest.has_document_xml:
                return Err(
                    FCStdError.INVALID_FCSTD,
                    f"Missing Document.xml in {fcstd_path}",
                )

            files_written = 0
            xml_prettified = 0

            for entry in manifest.entries:
                content = zf.read(entry.relative_path)
                out_path = output_dir / entry.relative_path

                out_path.parent.mkdir(parents=True, exist_ok=True)

                if entry.is_xml:
                    content = _prettify_xml(content)
                    xml_prettified += 1

                out_path.write_bytes(content)
                files_written += 1

            result = ExplodeResult(
                manifest=manifest,
                output_dir=output_dir,
                files_written=files_written,
                xml_files_prettified=xml_prettified,
            )
            return Ok(result)

    except zipfile.BadZipFile as e:
        return Err(FCStdError.NOT_A_ZIP, f"Corrupt ZIP file: {e}")
    except OSError as e:
        return Err(FCStdError.WRITE_FAILED, f"Write failed: {e}")
