"""A dry run must show exactly what a real run would do, and a real run must
be safe to repeat: re-running picks up where the manifest left off instead of
copying everything a second time."""
import csv
import os
import sys
from pathlib import Path

import pytest

from conftest import read_manifest, run_script, write_photo


def read_dryrun_manifest(output):
    with open(Path(output) / "manifest_dryrun.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_dry_run_writes_a_preview_manifest_and_no_photos(library):
    src, out = library
    write_photo(src / "one.jpg", seed=1, date_original="2021:05:04 10:11:12")
    write_photo(src / "two.jpg", seed=2, date_original="2020:01:02 03:04:05")
    run_script("--source", src, "--output", out, "--dry-run")
    assert not list(out.rglob("*.jpg"))
    assert not (out / "manifest.csv").exists()
    rows = {os.path.basename(r["source_path"]): r for r in read_dryrun_manifest(out)}
    assert rows["one.jpg"]["destination_path"].endswith(
        os.path.join("2021", "05", "20210504_101112.jpg"))
    assert rows["two.jpg"]["status"] == "copied"


def test_dry_run_predicts_the_real_run_exactly(library):
    src, out = library
    # Three photos taken in the same second: the real run numbers them _2, _3.
    for seed in (1, 2, 3):
        write_photo(src / ("burst%d.jpg" % seed), seed=seed,
                    date_original="2021:05:04 10:11:12")
    run_script("--source", src, "--output", out, "--dry-run")
    preview = {r["source_path"]: r["destination_path"] for r in read_dryrun_manifest(out)}
    run_script("--source", src, "--output", out)
    real = {r["source_path"]: r["destination_path"] for r in read_manifest(out)}
    assert preview == real
    names = sorted(os.path.basename(d) for d in real.values())
    assert names == ["20210504_101112.jpg", "20210504_101112_2.jpg", "20210504_101112_3.jpg"]


def test_rerun_copies_nothing_twice(library):
    src, out = library
    write_photo(src / "one.jpg", seed=1, date_original="2021:05:04 10:11:12")
    write_photo(src / "two.jpg", seed=2, date_original="2020:01:02 03:04:05")
    run_script("--source", src, "--output", out)
    first = sorted(str(p.relative_to(out)) for p in out.rglob("*.jpg"))
    proc = run_script("--source", src, "--output", out)
    second = sorted(str(p.relative_to(out)) for p in out.rglob("*.jpg"))
    assert first == second
    assert len(read_manifest(out)) == 2
    assert "Resuming: 2 already in manifest, 0 still to do." in proc.stdout


def test_rerun_picks_up_new_photos_and_still_catches_their_duplicates(library):
    src, out = library
    original = write_photo(src / "one.jpg", seed=1, date_original="2021:05:04 10:11:12")
    run_script("--source", src, "--output", out)
    # Later: a new photo arrives, and so does a second copy of the old one.
    write_photo(src / "new.jpg", seed=9, date_original="2023:07:08 09:10:11")
    (src / "one again.jpg").write_bytes(original.read_bytes())
    run_script("--source", src, "--output", out)
    rows = {os.path.basename(r["source_path"]): r for r in read_manifest(out)}
    assert rows["one.jpg"]["status"] == "copied"
    assert rows["new.jpg"]["status"] == "copied"
    assert rows["one again.jpg"]["status"] == "duplicate"
    assert rows["one again.jpg"]["duplicate_of"].endswith("one.jpg")
    assert len(list(out.rglob("*.jpg"))) == 2


def test_manifest_rows_are_written_as_the_run_progresses(library):
    """If the run dies after the first copy, the manifest already has that
    row. Simulated by making the second photo's destination folder unwritable."""
    if os.name == "nt" or os.geteuid() == 0:
        pytest.skip("needs POSIX permissions and a non-root user")
    src, out = library
    write_photo(src / "ok.jpg", seed=1, date_original="2021:05:04 10:11:12")
    write_photo(src / "blocked.jpg", seed=2, date_original="2020:01:02 03:04:05")
    (out / "2020" / "01").mkdir(parents=True)
    (out / "2020" / "01").chmod(0o500)
    try:
        proc = run_script("--source", src, "--output", out, check=False)
    finally:
        (out / "2020" / "01").chmod(0o700)
    assert proc.returncode != 0, "a failed copy must be reported, not hidden"
    rows = {os.path.basename(r["source_path"]): r["status"] for r in read_manifest(out)}
    assert rows == {"ok.jpg": "copied", "blocked.jpg": "error-copy"}
    assert (out / "2021" / "05" / "20210504_101112.jpg").is_file()
