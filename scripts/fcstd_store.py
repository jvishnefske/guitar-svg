"""Rewrite FCStd files with ZIP_STORED (no compression) for all entries."""
import zipfile, sys, tempfile, shutil, os

for path in sys.argv[1:]:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".FCStd")
    try:
        with zipfile.ZipFile(path, "r") as src, \
             zipfile.ZipFile(tmp.name, "w", compression=zipfile.ZIP_STORED) as dst:
            for info in src.infolist():
                data = src.read(info.filename)
                info.compress_type = zipfile.ZIP_STORED
                dst.writestr(info, data)
        shutil.move(tmp.name, path)
    except:
        os.unlink(tmp.name)
        raise
    print(f"Stored: {path}")
