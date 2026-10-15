"""Duplicate handling. "Duplicate" means byte-identical, nothing looser: a
thumbnail or a re-saved copy is a different file and is copied too (and,
having no EXIF, usually lands in the review folder)."""
import os

from conftest import read_manifest, run_script, write_photo, write_resized


def statuses(out):
    return {os.path.basename(r["source_path"]): r for r in read_manifest(out)}


def test_a_thumbnail_is_not_a_duplicate(library):
    src, out = library
    full = write_photo(src / "b_full.jpg", seed=1, size=(1600, 1200),
                       date_original="2021:05:04 10:11:12")
    write_resized(full, src / "a_thumb.jpg", (320, 240))
    run_script("--source", src, "--output", out)
    rows = statuses(out)
    assert rows["a_thumb.jpg"]["status"] == "copied"
    assert rows["b_full.jpg"]["status"] == "copied"
    assert len(list((out / "2021").rglob("*.jpg"))) == 1          # the full-res one
    assert os.sep + "_review" + os.sep in rows["a_thumb.jpg"]["destination_path"]


def test_exact_duplicates_are_listed_with_their_content_hash(library):
    src, out = library
    first = write_photo(src / "one.jpg", seed=3)
    (src / "two.jpg").write_bytes(first.read_bytes())
    run_script("--source", src, "--output", out)
    rows = statuses(out)
    assert rows["two.jpg"]["status"] == "duplicate"
    assert rows["two.jpg"]["destination_path"] == ""
    assert rows["two.jpg"]["content_hash"] == rows["one.jpg"]["content_hash"]
    assert "perceptual_hash" not in rows["one.jpg"]


def test_first_in_path_order_is_the_one_kept(library):
    src, out = library
    first = write_photo(src / "zed.jpg", seed=4)
    (src / "alpha.jpg").write_bytes(first.read_bytes())
    run_script("--source", src, "--output", out)
    rows = statuses(out)
    assert rows["alpha.jpg"]["status"] == "copied"
    assert rows["zed.jpg"]["duplicate_of"].endswith("alpha.jpg")


def test_resume_recognises_a_duplicate_of_an_earlier_copy(library):
    src, out = library
    first = write_photo(src / "one.jpg", seed=5)
    run_script("--source", src, "--output", out)
    (src / "later copy.jpg").write_bytes(first.read_bytes())
    run_script("--source", src, "--output", out)
    rows = statuses(out)
    assert rows["later copy.jpg"]["status"] == "duplicate"
    assert rows["later copy.jpg"]["duplicate_of"].endswith("one.jpg")
    assert len(list(out.rglob("*.jpg"))) == 1
