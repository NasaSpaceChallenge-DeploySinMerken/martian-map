"""Build the analysis VM release without the 5.8 GB DEM."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


root = Path(__file__).resolve().parents[2]
destination = Path(__file__).with_name("analysis-release.zip")
files = [path for path in (root / "analysis").glob("*.py")
         if not path.name.startswith("test_")]
files.append(root / "analysis" / "requirements.txt")

with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
    for path in sorted(files):
        archive.write(path, path.relative_to(root).as_posix())

print(f"{destination}: {len(files)} files, {destination.stat().st_size} bytes")
