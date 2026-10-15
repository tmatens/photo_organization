"""Re-running after the owner has been through the output, and resuming
from manifests written by earlier versions."""
import csv
import os

from conftest import read_manifest, run_script, write_photo


def test_files_the_owner_deleted_from_the_output_are_not_copied_back(library):
    src, out = library
    write_photo(src / "keep.jpg", seed=1, date_original="2021:05:04 10:11:12")
    write_photo(src / "junk.jpg", seed=2)                            # -> _review/photos
    run_script("--source", src, "--output", out)
    junk = next(p for p in out.rglob("*.jpg") if "_review" in str(p))
    junk.unlink()                                                    # owner combs through and deletes
    write_photo(src / "new.jpg", seed=3, date_original="2022:01:01 00:00:00")
    proc = run_script("--source", src, "--output", out)
    assert "Resuming: 2 already in manifest, 1 still to do." in proc.stdout
    assert not junk.exists(), "a deleted file came back"
    assert len(read_manifest(out)) == 3


def test_stale_part_file_from_an_interrupted_copy_is_cleaned_up(library):
    src, out = library
    write_photo(src / "one.jpg", seed=1, date_original="2021:05:04 10:11:12")
    dest_dir = out / "2021" / "05"
    dest_dir.mkdir(parents=True)
    (dest_dir / "20210504_101112.jpg.part").write_bytes(b"half a file")
    run_script("--source", src, "--output", out)
    assert (dest_dir / "20210504_101112.jpg").is_file()
    assert not list(out.rglob("*.part"))
    assert read_manifest(out)[0]["destination_path"].endswith("20210504_101112.jpg")


def test_resume_from_a_version_1_0_manifest(library):
    """1.0.0 wrote these columns and no content_hash. Such a manifest must
    still be honoured: listed files are skipped, and the run continues."""
    src, out = library
    old = write_photo(src / "old.jpg", seed=1, date_original="2021:05:04 10:11:12")
    write_photo(src / "new.jpg", seed=2, date_original="2022:01:01 00:00:00")
    out.mkdir()
    with open(out / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source_path", "destination_path", "date_taken",
                    "perceptual_hash", "dimensions", "duplicate_of", "status"])
        w.writerow([str(old), str(out / "2021" / "05" / "20210504_101112.jpg"),
                    "2021-05-04 10:11:12 (exif)", "abcd", "640x480", "", "copied"])
    proc = run_script("--source", src, "--output", out)
    assert "Resuming: 1 already in manifest, 1 still to do." in proc.stdout
    rows = {os.path.basename(r["source_path"]): r for r in read_manifest(out)}
    assert set(rows) == {"old.jpg", "new.jpg"}
    assert rows["new.jpg"]["status"] == "copied"


def test_uppercase_extension_is_processed_and_lowercased(library):
    src, out = library
    write_photo(src / "IMG_0001.JPG", seed=1, date_original="2021:05:04 10:11:12")
    run_script("--source", src, "--output", out)
    assert (out / "2021" / "05" / "20210504_101112.jpg").is_file()


def test_keep_dupes_with_two_duplicates_sharing_a_name(library):
    src, out = library
    first = write_photo(src / "a" / "pic.jpg", seed=1)
    (src / "b" / "pic.jpg").parent.mkdir()
    (src / "b" / "pic.jpg").write_bytes(first.read_bytes())
    (src / "c" / "pic.jpg").parent.mkdir()
    (src / "c" / "pic.jpg").write_bytes(first.read_bytes())
    run_script("--source", src, "--output", out, "--keep-dupes")
    names = sorted(p.name for p in (out / "_duplicates").glob("*.jpg"))
    assert names == ["pic.jpg", "pic_2.jpg"]


def test_help_runs(library):
    proc = run_script("--help")
    assert proc.returncode == 0
    assert "--sample" in proc.stdout
