"""The date a photo is filed under must be when it was TAKEN, not when the
file was last saved. Edited or exported photos carry both, and they differ."""
import sys
from pathlib import Path

from conftest import REPO_ROOT, read_manifest, run_script, write_photo

sys.path.insert(0, str(REPO_ROOT))
import organize_photos  # noqa: E402


def test_capture_date_wins_over_save_date(library):
    src, out = library
    write_photo(src / "edited.jpg", seed=1,
                date_original="2019:06:01 09:30:00",
                date_modified="2024:12:25 18:00:00")
    run_script("--source", src, "--output", out)
    assert (out / "2019" / "06" / "20190601_093000.jpg").is_file()
    assert not (out / "2024").exists()
    row = read_manifest(out)[0]
    assert row["date_taken"] == "2019-06-01 09:30:00 (exif-original)"


def test_save_date_is_used_only_when_nothing_better_exists(library):
    src, out = library
    write_photo(src / "saved_only.jpg", seed=2, date_modified="2022:03:14 10:00:00")
    run_script("--source", src, "--output", out)
    assert (out / "2022" / "03" / "20220314_100000.jpg").is_file()
    assert read_manifest(out)[0]["date_taken"].endswith("(exif-modified)")


def test_no_exif_at_all_falls_back_to_file_date(library):
    src, out = library
    write_photo(src / "screenshot_like.jpg", seed=3)
    run_script("--source", src, "--output", out)
    assert read_manifest(out)[0]["date_taken"].endswith("(file-date)")


def test_parser_tolerates_padding_and_placeholders():
    parse = organize_photos.parse_exif_datetime
    assert parse("2019:06:01 09:30:00\x00\x00").isoformat() == "2019-06-01T09:30:00"
    assert parse(b"2019:06:01 09:30:00") is not None
    assert parse("0000:00:00 00:00:00") is None
    assert parse("") is None
    assert parse(None) is None
    assert parse(12345) is None
