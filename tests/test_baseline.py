"""Behaviour the original script already gets right. These must keep passing
through every later change: they are the promises the README makes."""
import os

from conftest import (read_manifest, run_script, sha256_tree, write_photo,
                      write_screenshot)


def test_originals_are_never_modified(library):
    src, out = library
    write_photo(src / "a" / "one.jpg", seed=1, date_original="2021:05:04 10:00:00",
                date_modified="2021:05:04 10:00:00")
    write_photo(src / "b" / "two.jpg", seed=2)
    before = sha256_tree(src)
    run_script("--source", src, "--output", out)
    assert sha256_tree(src) == before


def test_photos_are_sorted_into_year_month_folders(library):
    src, out = library
    write_photo(src / "one.jpg", seed=1, date_original="2021:05:04 10:11:12",
                date_modified="2021:05:04 10:11:12")
    run_script("--source", src, "--output", out)
    assert (out / "2021" / "05" / "20210504_101112.jpg").is_file()
    rows = read_manifest(out)
    assert len(rows) == 1
    assert rows[0]["status"] == "copied"
    assert rows[0]["date_taken"].startswith("2021-05-04 10:11:12")


def test_byte_identical_duplicate_is_copied_once(library):
    src, out = library
    first = write_photo(src / "one.jpg", seed=3)
    (src / "copy of one.jpg").write_bytes(first.read_bytes())
    run_script("--source", src, "--output", out)
    copied = [p for p in out.rglob("*.jpg")]
    assert len(copied) == 1
    statuses = sorted(r["status"] for r in read_manifest(out))
    assert statuses == ["copied", "duplicate"]
    dupe = next(r for r in read_manifest(out) if r["status"] == "duplicate")
    assert dupe["duplicate_of"].endswith("one.jpg")


def test_keep_dupes_puts_duplicates_in_review_folder(library):
    src, out = library
    first = write_photo(src / "one.jpg", seed=3)
    (src / "again.jpg").write_bytes(first.read_bytes())
    run_script("--source", src, "--output", out, "--keep-dupes")
    assert len(list((out / "_duplicates").glob("*.jpg"))) == 1


def test_dry_run_copies_nothing(library):
    src, out = library
    write_photo(src / "one.jpg", seed=1)
    run_script("--source", src, "--output", out, "--dry-run")
    assert not out.exists() or not list(out.rglob("*.jpg"))


def test_output_inside_source_is_refused(library):
    src, _ = library
    write_photo(src / "one.jpg", seed=1)
    proc = run_script("--source", src, "--output", src / "Organized", check=False)
    assert proc.returncode != 0
    assert not (src / "Organized").exists()


def test_unreadable_file_is_reported_not_fatal(library):
    src, out = library
    write_photo(src / "good.jpg", seed=1)
    (src / "broken.jpg").write_bytes(b"not really a jpeg")
    run_script("--source", src, "--output", out)
    by_status = {r["status"]: r for r in read_manifest(out)}
    assert "copied" in by_status
    assert by_status["error-unreadable"]["source_path"].endswith("broken.jpg")


def test_example_chrome_matching_pulls_out_app_screenshots(library):
    src, out = library
    example = write_screenshot(src / "shot_a.png", chrome_seed=100, middle_seed=1)
    write_screenshot(src / "shot_b.png", chrome_seed=100, middle_seed=2)
    write_screenshot(src / "shot_c.png", chrome_seed=100, middle_seed=3)
    write_photo(src / "real_photo.jpg", seed=7)
    run_script("--source", src, "--output", out,
               "--example", example, "--example-chrome")
    rows = {os.path.basename(r["source_path"]): r["status"] for r in read_manifest(out)}
    assert rows["shot_b.png"] == "matched-example"
    assert rows["shot_c.png"] == "matched-example"
    assert rows["real_photo.jpg"] == "copied"
    assert list((out / "matched_example").rglob("*.png"))
