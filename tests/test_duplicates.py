"""Duplicate handling. "Duplicate" means byte-identical. Photos that merely
look the same are a separate, opt-in case, and when they are grouped the
largest version must be the one that survives into the main library."""
import os

from conftest import read_manifest, run_script, write_photo, write_resized


def statuses(out):
    return {os.path.basename(r["source_path"]): r for r in read_manifest(out)}


def test_a_thumbnail_is_not_a_duplicate_by_default(library):
    src, out = library
    full = write_photo(src / "b_full.jpg", seed=1, size=(1600, 1200),
                       date_original="2021:05:04 10:11:12")
    write_resized(full, src / "a_thumb.jpg", (320, 240))
    run_script("--source", src, "--output", out)
    rows = statuses(out)
    assert rows["a_thumb.jpg"]["status"] == "copied"
    assert rows["b_full.jpg"]["status"] == "copied"
    assert len(list((out / "2021").rglob("*.jpg"))) == 1   # the full-res one
    assert len(list(out.rglob("*.jpg"))) == 2


def test_visual_grouping_keeps_the_largest_version(library):
    src, out = library
    # The thumbnail sorts FIRST ("a_" < "b_"). Whichever is seen first must
    # not matter: the full-resolution original has to win.
    full = write_photo(src / "b_full.jpg", seed=1, size=(1600, 1200),
                       date_original="2021:05:04 10:11:12")
    write_resized(full, src / "a_thumb.jpg", (320, 240))
    run_script("--source", src, "--output", out, "--dup-threshold", "4")
    rows = statuses(out)
    assert rows["b_full.jpg"]["status"] == "copied"
    assert rows["b_full.jpg"]["destination_path"].endswith(
        os.path.join("2021", "05", "20210504_101112.jpg"))
    assert rows["a_thumb.jpg"]["status"] == "near-duplicate"
    assert rows["a_thumb.jpg"]["duplicate_of"].endswith("b_full.jpg")
    # The thumbnail is kept for review, not thrown away.
    assert rows["a_thumb.jpg"]["destination_path"].endswith(
        os.path.join("_duplicates", "a_thumb.jpg"))
    assert (out / "_duplicates" / "a_thumb.jpg").is_file()


def test_near_duplicates_are_reviewable_not_lost(library):
    src, out = library
    # A recompressed copy looks identical but is not byte-identical.
    full = write_photo(src / "photo.jpg", seed=2, size=(1600, 1200))
    write_resized(full, src / "photo_whatsapp.jpg", (1600, 1200), quality=25)
    run_script("--source", src, "--output", out, "--dup-threshold", "2")
    rows = statuses(out)
    assert rows["photo_whatsapp.jpg"]["status"] == "near-duplicate"
    assert sorted(p.name for p in out.rglob("*.jpg")) == [
        os.path.basename(rows["photo.jpg"]["destination_path"]), "photo_whatsapp.jpg"]


def test_exact_duplicates_are_still_just_listed(library):
    src, out = library
    first = write_photo(src / "one.jpg", seed=3)
    (src / "two.jpg").write_bytes(first.read_bytes())
    run_script("--source", src, "--output", out, "--dup-threshold", "0")
    rows = statuses(out)
    assert rows["two.jpg"]["status"] == "duplicate"
    assert rows["two.jpg"]["destination_path"] == ""
    assert rows["two.jpg"]["content_hash"] == rows["one.jpg"]["content_hash"]


def test_keeper_choice_is_deterministic_on_a_tie(library):
    src, out = library
    full = write_photo(src / "zed.jpg", seed=4, size=(800, 600))
    write_resized(full, src / "alpha.jpg", (800, 600))   # same pixel count
    run_script("--source", src, "--output", out, "--dup-threshold", "0")
    rows = statuses(out)
    assert rows["alpha.jpg"]["status"] == "copied"       # first in path order
    assert rows["zed.jpg"]["status"] == "near-duplicate"


def test_resume_treats_earlier_copy_as_the_keeper(library):
    src, out = library
    write_resized(write_photo(src / "scratch.jpg", seed=5, size=(1600, 1200)),
                  src / "small.jpg", (400, 300))
    (src / "scratch.jpg").unlink()
    run_script("--source", src, "--output", out, "--dup-threshold", "4")
    assert statuses(out)["small.jpg"]["status"] == "copied"
    # A bigger version turns up on the next run. The earlier copy stays put;
    # the newcomer is filed as a near-duplicate rather than swapped in.
    write_photo(src / "big.jpg", seed=5, size=(1600, 1200))
    run_script("--source", src, "--output", out, "--dup-threshold", "4")
    rows = statuses(out)
    assert rows["small.jpg"]["status"] == "copied"
    assert rows["big.jpg"]["status"] == "near-duplicate"
    assert rows["big.jpg"]["duplicate_of"].endswith("small.jpg")


def test_dup_threshold_is_validated(library):
    src, out = library
    write_photo(src / "one.jpg", seed=1)
    assert run_script("--source", src, "--output", out,
                      "--dup-threshold", "65", check=False).returncode != 0
