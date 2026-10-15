"""Check the organized copy produced from build_library.py's three drives.

Usage: python tests/e2e/check_results.py OUTPUT_FOLDER [--sorted]
--sorted: the music-app screenshots have been moved by sort_screenshots.py
Exits non-zero with a message on the first expectation that fails.
"""
import csv
import os
import sys
from pathlib import Path


def main(output, sorted_flag=False):
    out = Path(output)
    with open(out / "manifest.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    by_name = {}
    for r in rows:
        by_name.setdefault(os.path.basename(r["source_path"]), []).append(r)

    def one(name):
        assert name in by_name, "missing from manifest: %s" % name
        assert len(by_name[name]) == 1, "listed more than once: %s" % name
        return by_name[name][0]

    def rel(r):
        return os.path.relpath(r["destination_path"], out).replace("\\", "/")

    # Camera photos filed by capture date; same-second pair numbered.
    dests = sorted(rel(r) for r in by_name["IMG_0001.jpg"] + by_name["IMG_0002.jpg"]
                   if r["status"] == "copied")
    assert dests == ["2021/05/20210504_101112.jpg", "2021/05/20210504_101112_2.jpg"], dests
    assert one("IMG_0003.jpg")["date_taken"] == "2019-12-25 08:00:00 (exif-original)"

    # Cross-drive exact duplicate copied once; thumbnail is a separate copy
    # and lands in _review (no date).
    statuses = sorted(r["status"] for r in by_name["IMG_0001.jpg"])
    assert statuses == ["copied", "duplicate"], statuses
    assert rel(one("IMG_0001_small.jpg")).startswith("_review/photos/")

    # Edited copy keeps its capture date, not its 2024 save date.
    assert rel(one("IMG_0003_edit.jpg")).startswith("2019/12/")

    # Video dated from header; video dated from filename; undated video to review.
    assert one("IMG_0004.MOV")["date_taken"].endswith("(video-metadata)")
    assert rel(one("IMG_0004.MOV")).startswith("2021/05/")
    assert rel(one("VID_20220314_100000.mp4")) == "2022/03/20220314_100000.mp4"
    assert rel(one("clip.mp4")).startswith("_review/videos/")

    # Every screenshot goes to review: Android ones under their filename month,
    # iPhone-style and unknown ones under their file date.
    music = "_review/music/" if sorted_flag else "_review/screenshots/"
    for name in ("Screenshot_20220314-100000.png", "Screenshot_20220315-110000.png",
                 "Screenshot_20220316-120000.png", "IMG_0099.PNG"):
        r = one(name)
        assert r["status"] == "copied", (name, r["status"])
        assert rel(r).startswith(music), (name, rel(r))
        assert Path(r["destination_path"]).is_file(), name
    assert rel(one("other_app.png")).startswith("_review/screenshots/2"), rel(one("other_app.png"))
    for name in ("IMG_0001.jpg", "IMG_0002.jpg", "IMG_0003.jpg", "IMG_0004.MOV"):
        for r in by_name[name]:
            if r["status"] == "copied":
                assert not rel(r).startswith("_review/"), (name, rel(r))

    # Undated download to review; a dated name alone is not camera evidence,
    # so the deep-path photo sorts the review folder; junk ignored.
    assert rel(one("funny.jpg")).startswith("_review/photos/")
    assert rel(one("IMG_20200101_120000.jpg")) == "_review/photos/2020/01/20200101_120000.jpg"
    assert not one("IMG_20200101_120000.jpg")["source_path"].startswith("\\\\?\\")
    assert "deleted.jpg" not in by_name, "Recycle Bin was scanned"
    assert "._IMG_0001.jpg" not in by_name, "macOS sidecar was scanned"
    assert not any(r["status"].startswith("error") for r in rows), \
        [r for r in rows if r["status"].startswith("error")]

    # Nothing copied twice: every destination unique, and file count matches.
    dests = [r["destination_path"] for r in rows if r["destination_path"]]
    assert len(dests) == len(set(dests)), "a destination was used twice"
    on_disk = [p for p in out.rglob("*") if p.is_file() and p.suffix.lower() != ".csv"]
    assert len(on_disk) == len(dests), (len(on_disk), len(dests))
    print("end-to-end check passed: %d manifest rows, %d files on disk" % (len(rows), len(on_disk)))


if __name__ == "__main__":
    main(sys.argv[1], "--sorted" in sys.argv[2:])
