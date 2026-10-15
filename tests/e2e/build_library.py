"""Build a realistic three-drive mess for the end-to-end check.

Usage: python tests/e2e/build_library.py DRIVE1 DRIVE2 DRIVE3 [EXAMPLES]

Each drive gets the kinds of things old backup drives accumulate: camera
photos with real dates, the same photo on two drives, a thumbnail of one,
a phone video, an Android screenshot, an undated meme, a folder tree deeper
than 260 characters, macOS sidecar files and a Recycle Bin. Prints nothing
on success; the checker knows what to expect.
"""
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))          # tests/  (conftest helpers)
sys.path.insert(0, str(HERE.parent.parent))   # repo root (organize_photos)
from conftest import write_mp4, write_photo, write_resized, write_screenshot  # noqa: E402
from organize_photos import longpath  # noqa: E402


def main(d1, d2, d3, examples=None):
    d1, d2, d3 = Path(d1), Path(d2), Path(d3)
    if examples:
        # One example of the music app's look, as the owner would supply it.
        write_screenshot(Path(examples) / "music_app.png", chrome_seed=100, middle_seed=77,
                         size=(1170, 2532))

    # Drive 1: the phone backup.
    cam = write_photo(d1 / "DCIM" / "IMG_0001.jpg", seed=1, size=(1600, 1200),
                      date_original="2021:05:04 10:11:12")
    write_photo(d1 / "DCIM" / "IMG_0002.jpg", seed=2, size=(1600, 1200),
                date_original="2021:05:04 10:11:12")        # same second: _2
    write_photo(d1 / "DCIM" / "IMG_0003.jpg", seed=3, size=(1600, 1200),
                date_original="2019:12:25 08:00:00")
    write_mp4(d1 / "DCIM" / "IMG_0004.MOV", created=datetime(2021, 5, 4, 15, 30, 0))
    write_screenshot(d1 / "Screenshots" / "Screenshot_20220314-100000.png",
                     chrome_seed=100, middle_seed=1)
    write_screenshot(d1 / "Screenshots" / "Screenshot_20220315-110000.png",
                     chrome_seed=100, middle_seed=2)
    (d1 / "DCIM" / "._IMG_0001.jpg").write_bytes(b"\x00\x05\x16\x07" + b"\x00" * 50)

    # Drive 2: an older copy of the same backup, plus edits and downloads.
    (d2 / "Backup 2022" / "DCIM").mkdir(parents=True)
    (d2 / "Backup 2022" / "DCIM" / "IMG_0001.jpg").write_bytes(cam.read_bytes())   # exact dup
    write_resized(cam, d2 / "Backup 2022" / "thumbs" / "IMG_0001_small.jpg", (320, 240))
    write_photo(d2 / "Backup 2022" / "edited" / "IMG_0003_edit.jpg", seed=3,
                date_original="2019:12:25 08:00:00", date_modified="2024:01:01 00:00:00")
    write_photo(d2 / "Downloads" / "funny.jpg", seed=50)                          # undated
    write_photo(d2 / "$RECYCLE.BIN" / "S-1-5-21" / "deleted.jpg", seed=60)
    deep = d2
    while len(str(deep)) < 300:
        deep = deep / ("a_very_long_folder_name_from_an_old_backup_" * 2)
    os.makedirs(longpath(str(deep)), exist_ok=True)
    write_photo(longpath(str(deep / "IMG_20200101_120000.jpg")), seed=70)

    # Drive 3: mostly screenshots.
    write_screenshot(d3 / "Screenshots" / "Screenshot_20220316-120000.png",
                     chrome_seed=100, middle_seed=3)
    write_screenshot(d3 / "Screenshots" / "IMG_0099.PNG", chrome_seed=100, middle_seed=9)
    write_screenshot(d3 / "Screenshots" / "other_app.png", chrome_seed=200, middle_seed=1)
    write_mp4(d3 / "Videos" / "VID_20220314_100000.mp4", created=datetime(2021, 1, 1, 0, 0, 0))
    write_mp4(d3 / "Videos" / "clip.mp4")                                           # undated


if __name__ == "__main__":
    main(*sys.argv[1:5])
