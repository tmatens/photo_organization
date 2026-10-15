"""Build the release zip: python scripts/build_zip.py 1.2.1

The zip is FLAT (files at the top level, no folder inside) so that Windows'
"Extract All..." into C:\\photo_organizer puts organize_photos.py directly
there, which is what the README's walkthrough assumes.
"""
import sys
import zipfile
from pathlib import Path

FILES = ["organize_photos.py", "sort_screenshots.py", "README.md", "CHANGELOG.md",
         "requirements.txt", "requirements-optional.txt"]


def main(version):
    root = Path(__file__).resolve().parent.parent
    out = root / ("photo_organizer-%s.zip" % version)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name in FILES:
            z.write(root / name, name)
    print(out)
    print("\n".join(zipfile.ZipFile(out).namelist()))


if __name__ == "__main__":
    main(sys.argv[1])
