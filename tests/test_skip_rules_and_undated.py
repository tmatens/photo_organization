"""What the scan leaves alone, what it reports leaving behind, and where
photos with no real date end up."""
import os
import sys

import pytest

from conftest import read_manifest, run_script, write_photo

try:
    import pillow_heif  # noqa: F401
    HAVE_HEIF = True
except ImportError:
    HAVE_HEIF = False


def names(out):
    return {os.path.basename(r["source_path"]): r for r in read_manifest(out)}


def test_hidden_files_and_system_folders_are_ignored(library):
    src, out = library
    write_photo(src / "real.jpg", seed=1, date_original="2021:05:04 10:11:12")
    (src / "._real.jpg").write_bytes(b"\x00\x05\x16\x07" + b"\x00" * 100)
    (src / ".DS_Store").write_bytes(b"junk")
    for d in ("@eaDir", ".Trashes", "$RECYCLE.BIN", "System Volume Information"):
        write_photo(src / d / "cached.jpg", seed=2)
    proc = run_script("--source", src, "--output", out)
    assert list(names(out)) == ["real.jpg"]
    assert "ignored 2 hidden/system files" in proc.stdout


def test_output_may_live_inside_the_source_without_being_rescanned(library):
    src, _ = library
    out = src / "Organized"
    write_photo(src / "one.jpg", seed=1, date_original="2021:05:04 10:11:12")
    run_script("--source", src, "--output", out)
    proc = run_script("--source", src, "--output", out)
    assert len(read_manifest(out)) == 1
    assert len(list(out.rglob("*.jpg"))) == 1
    assert "Found 1 photo and video files." in proc.stdout


def test_source_inside_output_is_refused(library):
    src, _ = library
    inner = src / "photos"
    write_photo(inner / "one.jpg", seed=1)
    assert run_script("--source", inner, "--output", src, check=False).returncode != 0


def test_unknown_file_types_are_left_alone(library):
    src, out = library
    write_photo(src / "one.jpg", seed=1, date_original="2021:05:04 10:11:12")
    (src / "notes.txt").write_text("not media")
    (src / "album.pdf").write_bytes(b"%PDF")
    run_script("--source", src, "--output", out)
    assert list(names(out)) == ["one.jpg"]


@pytest.mark.skipif(HAVE_HEIF, reason="pillow-heif is installed, so HEIC is handled")
def test_heic_without_the_optional_package_is_reported_not_silent(library):
    src, out = library
    write_photo(src / "one.jpg", seed=1, date_original="2021:05:04 10:11:12")
    (src / "IMG_0001.HEIC").write_bytes(b"pretend")
    proc = run_script("--source", src, "--output", out)
    assert "NOT INCLUDED: 1 HEIC/HEIF photos" in proc.stdout
    assert "requirements-optional.txt" in proc.stdout


def test_photos_without_an_exif_date_go_to_their_own_tree(library):
    src, out = library
    write_photo(src / "camera.jpg", seed=1, date_original="2021:05:04 10:11:12")
    write_photo(src / "meme.jpg", seed=2)
    proc = run_script("--source", src, "--output", out)
    rows = names(out)
    assert os.sep + "_review" + os.sep in rows["meme.jpg"]["destination_path"]
    assert rows["meme.jpg"]["date_taken"].endswith("(file-date)")
    assert os.sep + "_review" + os.sep not in rows["camera.jpg"]["destination_path"]
    assert "to _review/: 0 screenshots, 1 with no date" in proc.stdout


def test_review_folder_name_and_mix_undated(library):
    src, out = library
    write_photo(src / "meme.jpg", seed=2)
    run_script("--source", src, "--output", out, "--review-folder", "guessed")
    assert os.sep + "guessed" + os.sep in names(out)["meme.jpg"]["destination_path"]

    out2 = out.parent / "output2"
    run_script("--source", src, "--output", out2, "--mix-undated")
    dest = names(out2)["meme.jpg"]["destination_path"]
    assert os.sep + "_review" + os.sep not in os.path.relpath(dest, out2)
    year = os.path.relpath(dest, out2).split(os.sep)[0]
    assert year.isdigit() and len(year) == 4
