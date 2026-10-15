"""iPhone HEIC photos, which need the optional pillow-heif package. These
tests skip when it is absent, except in the CI job that installs it, where
REQUIRE_HEIF=1 turns a skip into a failure."""
import os

import pytest
from PIL import ExifTags, Image

from conftest import make_image, read_manifest, run_script

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HAVE_HEIF = True
except ImportError:
    HAVE_HEIF = False

if not HAVE_HEIF and os.environ.get("REQUIRE_HEIF"):
    raise RuntimeError("REQUIRE_HEIF is set but pillow-heif is not installed")

pytestmark = pytest.mark.skipif(not HAVE_HEIF, reason="pillow-heif not installed")


def write_heic(path, seed, date_original=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    exif = Image.Exif()
    if date_original:
        exif.get_ifd(ExifTags.IFD.Exif)[ExifTags.Base.DateTimeOriginal] = date_original
    make_image(seed, (640, 480)).save(path, "HEIF", exif=exif if date_original else None)
    return path


def test_heic_capture_date_is_read_and_filed(library):
    src, out = library
    write_heic(src / "IMG_0101.HEIC", seed=1, date_original="2023:07:04 12:30:00")
    proc = run_script("--source", src, "--output", out)
    rows = read_manifest(out)
    assert len(rows) == 1
    assert rows[0]["date_taken"] == "2023-07-04 12:30:00 (exif-original)"
    assert rows[0]["destination_path"].endswith(os.path.join("2023", "07", "20230704_123000.heic"))
    assert "NOT INCLUDED" not in proc.stdout


def test_heic_without_a_date_goes_to_review(library):
    src, out = library
    write_heic(src / "IMG_0102.HEIC", seed=2)
    run_script("--source", src, "--output", out)
    assert os.path.join("_review", "photos") + os.sep in read_manifest(out)[0]["destination_path"]


def test_identical_heic_files_are_duplicates(library):
    src, out = library
    first = write_heic(src / "a.heic", seed=3, date_original="2023:07:04 12:30:00")
    (src / "b.heic").write_bytes(first.read_bytes())
    run_script("--source", src, "--output", out)
    assert sorted(r["status"] for r in read_manifest(out)) == ["copied", "duplicate"]
