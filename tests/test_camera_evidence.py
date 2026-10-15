"""Only camera evidence places a file in the main library: an EXIF capture
or digitized date for a photo, a header creation time for a video. Every
other date is used to sort the review folder and nothing more."""
import os
from datetime import datetime

from conftest import read_manifest, run_script, write_mp4, write_photo


def rows(out):
    return {os.path.basename(r["source_path"]): r for r in read_manifest(out)}


def in_review(r, out):
    return os.path.relpath(r["destination_path"], out).startswith("_review" + os.sep)


def test_camera_video_with_filename_and_header_stays_in_the_library(library):
    src, out = library
    write_mp4(src / "VID_20220314_100000.mp4", created=datetime(2022, 3, 14, 15, 0, 0))
    run_script("--source", src, "--output", out)
    r = rows(out)["VID_20220314_100000.mp4"]
    assert r["date_taken"] == "2022-03-14 10:00:00 (filename)"   # local, from the name
    assert not in_review(r, out)                                  # proven by the header


def test_video_with_a_dated_name_but_no_header_goes_to_review(library):
    src, out = library
    write_mp4(src / "VID_20220314_100000.mp4")                    # header says unknown
    run_script("--source", src, "--output", out)
    r = rows(out)["VID_20220314_100000.mp4"]
    assert r["date_taken"].endswith("(filename)")
    assert in_review(r, out)
    assert os.path.join("_review", "videos", "2022", "03") in r["destination_path"]


def test_messaging_app_video_with_a_header_is_not_camera_dated(library):
    src, out = library
    # Telegram and WhatsApp re-encode on send, so the header time is real but
    # it is the send time; their names are never camera names.
    write_mp4(src / "video_2022-03-14_10-00-00.mp4", created=datetime(2022, 3, 14, 15, 0, 0), body=b"a" * 64)
    write_mp4(src / "VID-20220314-WA0007.mp4", created=datetime(2022, 3, 14, 15, 0, 0), body=b"b" * 64)
    run_script("--source", src, "--output", out)
    for name, r in rows(out).items():
        assert in_review(r, out), name
        assert os.sep + "videos" + os.sep in r["destination_path"], name


def test_camera_style_names_from_several_makers_count(library):
    src, out = library
    for i, name in enumerate(("IMG_0042.MOV", "PXL_20220314_100000123.mp4", "20220314_100000.mp4",
                              "MVI_1234.MP4", "DSC_0001.MOV", "DJI_0001.MP4", "GX010001.MP4")):
        write_mp4(src / name, created=datetime(2022, 3, 14, 15, 0, 0), body=bytes([i]) * 64)
    run_script("--source", src, "--output", out)
    for name, r in rows(out).items():
        assert not in_review(r, out), name


def test_digitized_date_counts_as_camera_evidence(library):
    src, out = library
    from PIL import ExifTags, Image
    from conftest import make_image
    exif = Image.Exif()
    exif.get_ifd(ExifTags.IFD.Exif)[ExifTags.Base.DateTimeDigitized] = "2015:08:01 12:00:00"
    (src / "scan").mkdir()
    make_image(1).save(src / "scan" / "scan001.jpg", "JPEG", exif=exif)
    run_script("--source", src, "--output", out)
    r = rows(out)["scan001.jpg"]
    assert r["date_taken"].endswith("(exif-digitized)")
    assert not in_review(r, out)


def test_mix_undated_puts_everything_in_the_library(library):
    src, out = library
    write_photo(src / "photo_2022-03-14_10-00-00.jpg", seed=1)
    write_photo(src / "nodate.jpg", seed=2)
    run_script("--source", src, "--output", out, "--mix-undated")
    assert not (out / "_review").exists()
    assert len(list(out.rglob("*.jpg"))) == 2
