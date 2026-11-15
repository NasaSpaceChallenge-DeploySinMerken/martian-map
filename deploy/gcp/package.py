"""Build the analysis VM release without the 5.8 GB DEM."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


root = Path(__file__).resolve().parents[2]
destination = Path(__file__).with_name("analysis-release.zip")
files = [path for path in (root / "analysis").glob("*.py")
         if not path.name.startswith("test_")]
files.append(root / "analysis" / "requirements.txt")

with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
    for path in sorted(files):
        info = ZipInfo(path.relative_to(root).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        archive.writestr(info, path.read_bytes())

print(f"{destination}: {len(files)} files, {destination.stat().st_size} bytes")
