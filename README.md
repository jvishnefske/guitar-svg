# Guitar CAD Project

FreeCAD-based guitar design with Git-friendly version control.

## FreeCAD Setup

Set compression level to 0 so git can delta-compress FCStd files efficiently:

**Edit > Preferences > General > Document > Compression level = 0**

FCStd files are ZIP archives. At compression level 0 (STORED), the XML
content inside is uncompressed, which lets git's packfile delta compression
detect byte-level similarities between revisions without any extra tooling.

## Git Setup

Configure the textconv diff driver to see meaningful diffs of FCStd files:

```bash
git config diff.fcstd.textconv 'python3 -c "import zipfile,sys;z=zipfile.ZipFile(sys.argv[1]);[print(z.read(f).decode()) for f in sorted(z.namelist()) if f.endswith(\".xml\")]"'
```

This extracts and prints all XML files from the FCStd archive, letting
`git diff` show text diffs of the underlying Document.xml and GuiDocument.xml.

## Directory Structure

```
3d/
  stratocaster.FCStd   # FreeCAD model (tracked, zip level 0)
  cam.py               # CAM toolpath generation script
reference/             # Reference drawings and measurements
templates/             # Templates and patterns
```
