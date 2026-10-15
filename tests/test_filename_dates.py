"""Phones write the capture time into the filename. When the EXIF date is
missing or is only a save time, that filename timestamp is the best evidence."""
import os
import sys
from datetime import datetime

from conftest import REPO_ROOT, read_manifest, run_script, write_photo

sys.path.insert(0, str(REPO_ROOT))
from organize_photos import date_from_filename  # noqa: E402


def test_common_phone_and_app_filenames_are_recognised():
    expect = datetime(2022, 3, 14, 10, 0, 0)
    for name in ("IMG_20220314_100000.jpg", "PXL_20220314_100000123.jpg",
                 "20220314_100000.jpg", "Screenshot_20220314-100000.png",
                 "Screenshot_20220314-100000_Music.jpg", "2022-03-14 10.00.00.jpg",
                 "2022-03-14_10-00-00.jpg", "2022-03-14T10:00:00.jpeg",
                 "VID_20220314_100000 (2).jpg"):
        assert date_from_filename(name) == expect, name


def test_numbers_that_are_not_dates_are_ignored():
    for name in ("IMG_1234.jpg", "DSC_0001.jpg", "photo.jpg", "20231399_999999.jpg",
                 "12345678_123456.jpg", "IMG_20220314_250000.jpg", "1234567890123456.jpg"):
        assert date_from_filename(name) is None, name


def test_filename_date_sorts_the_review_folder_but_does_not_prove_a_camera(library):
    src, out = library
    # A Telegram-style save: dated name, no EXIF. The date is when it was
    # sent, not taken, so it must not enter the main library.
    write_photo(src / "photo_2022-03-14_10-00-00.jpg", seed=1)
    run_script("--source", src, "--output", out)
    row = read_manifest(out)[0]
    assert row["date_taken"] == "2022-03-14 10:00:00 (filename)"
    assert row["destination_path"].endswith(
        os.path.join("_review", "photos", "2022", "03", "20220314_100000.jpg"))
    assert not (out / "2022").exists()


def test_filename_date_beats_a_save_date_but_not_a_capture_date(library):
    src, out = library
    write_photo(src / "IMG_20220314_100000.jpg", seed=1, date_modified="2024:12:25 18:00:00")
    write_photo(src / "IMG_20220314_100000 copy.jpg", seed=2,
                date_original="2019:06:01 09:30:00")
    run_script("--source", src, "--output", out)
    rows = {os.path.basename(r["source_path"]): r for r in read_manifest(out)}
    assert rows["IMG_20220314_100000.jpg"]["date_taken"] == "2022-03-14 10:00:00 (filename)"
    assert rows["IMG_20220314_100000 copy.jpg"]["date_taken"] == "2019-06-01 09:30:00 (exif-original)"
    # Only the one with a capture date is in the main library.
    assert os.sep + "_review" + os.sep in rows["IMG_20220314_100000.jpg"]["destination_path"]
    assert os.sep + "_review" + os.sep not in rows["IMG_20220314_100000 copy.jpg"]["destination_path"]
