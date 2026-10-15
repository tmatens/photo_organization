"""Videos are organized alongside photos: dated from the filename, then from
the MOV/MP4 header, then sent to the review folder."""
import os
from datetime import datetime, timezone

from conftest import read_manifest, run_script, write_mp4


def rows(out):
    return {os.path.basename(r["source_path"]): r for r in read_manifest(out)}


def local(dt_utc):
    """What the script will file a UTC header time as, on this machine."""
    return dt_utc.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)


def test_video_is_dated_from_its_header(library):
    src, out = library
    created = datetime(2021, 5, 4, 15, 11, 12)         # stored as UTC in the file
    write_mp4(src / "IMG_0042.MOV", created=created)
    proc = run_script("--source", src, "--output", out)
    row = rows(out)["IMG_0042.MOV"]
    expect = local(created)
    assert row["status"] == "copied"
    assert row["date_taken"] == expect.strftime("%Y-%m-%d %H:%M:%S") + " (video-metadata)"
    assert row["destination_path"].endswith(
        os.path.join(expect.strftime("%Y"), expect.strftime("%m"),
                     expect.strftime("%Y%m%d_%H%M%S") + ".mov"))
    assert "(videos among the above: 1)" in proc.stdout


def test_video_filename_date_wins_over_header(library):
    src, out = library
    write_mp4(src / "VID_20220314_100000.mp4", created=datetime(2021, 5, 4, 15, 11, 12))
    run_script("--source", src, "--output", out)
    assert rows(out)["VID_20220314_100000.mp4"]["date_taken"] == "2022-03-14 10:00:00 (filename)"


def test_video_with_no_date_goes_to_review(library):
    src, out = library
    write_mp4(src / "clip.mp4")                          # header says unknown
    (src / "old.avi").write_bytes(b"RIFF....AVI LIST")   # no header we read
    run_script("--source", src, "--output", out)
    r = rows(out)
    for name in ("clip.mp4", "old.avi"):
        assert r[name]["date_taken"].endswith("(file-date)")
        assert os.path.join("_review", "videos") + os.sep in r[name]["destination_path"]


def test_identical_videos_are_copied_once(library):
    src, out = library
    first = write_mp4(src / "a.mov", created=datetime(2021, 5, 4, 15, 11, 12))
    (src / "a copy.mov").write_bytes(first.read_bytes())
    run_script("--source", src, "--output", out)
    r = rows(out)
    assert sorted(x["status"] for x in r.values()) == ["copied", "duplicate"]
    assert len(list(out.rglob("*.mov"))) == 1


def test_truncated_video_is_still_copied(library):
    src, out = library
    good = write_mp4(src / "good.mp4", created=datetime(2021, 5, 4, 15, 11, 12))
    (src / "cut.mp4").write_bytes(good.read_bytes()[:40])   # ends inside mdat
    run_script("--source", src, "--output", out)
    assert rows(out)["cut.mp4"]["status"] == "copied"
    assert rows(out)["cut.mp4"]["date_taken"].endswith("(file-date)")
