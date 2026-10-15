"""Check the organized copy produced from build_library.py's three drives.

Usage: python tests/e2e/check_results.py OUTPUT_FOLDER
Exits non-zero with a message on the first expectation that fails.
"""
import csv
import os
import sys
from pathlib import Path


def main(output):
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
    # (no --dup-threshold was used) and lands in _review (no date).
    statuses = sorted(r["status"] for r in by_name["IMG_0001.jpg"])
    assert statuses == ["copied", "duplicate"], statuses
    assert rel(one("IMG_0001_small.jpg")).startswith("_review/")

    # Edited copy keeps its capture date, not its 2024 save date.
    assert rel(one("IMG_0003_edit.jpg")).startswith("2019/12/")

    # Video dated from header; video dated from filename; undated video to review.
    assert one("IMG_0004.MOV")["date_taken"].endswith("(video-metadata)")
    assert rel(one("IMG_0004.MOV")).startswith("2021/05/")
    assert rel(one("VID_20220314_100000.mp4")) == "2022/03/20220314_100000.mp4"
    assert rel(one("clip.mp4")).startswith("_review/")

    # Android screenshots dated from filename, and matched to the example.
    for name in ("Screenshot_20220314-100000.png", "Screenshot_20220315-110000.png",
                 "Screenshot_20220316-120000.png"):
        r = one(name)
        assert r["status"] == "matched-example", (name, r["status"])
        assert rel(r).startswith("matched_example/2022/03/"), rel(r)
    assert one("other_app.png")["status"] == "copied"
    assert "example.png" not in by_name, "the example itself must not be processed"

    # Undated download to review; deep path found; junk ignored.
    assert rel(one("funny.jpg")).startswith("_review/")
    assert rel(one("IMG_20200101_120000.jpg")) == "2020/01/20200101_120000.jpg"
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
    main(sys.argv[1])
