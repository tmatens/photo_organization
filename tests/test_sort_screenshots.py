"""sort_screenshots.py: pull one app's screenshots out of _review/screenshots
by comparing the top and bottom bands with example screenshots."""
import csv
import os
import subprocess
import sys
from pathlib import Path

from conftest import REPO_ROOT, read_manifest, run_script, write_photo, write_screenshot

SORTER = REPO_ROOT / "sort_screenshots.py"


def run_sorter(*args, check=True):
    proc = subprocess.run([sys.executable, "-I", str(SORTER)] + [str(a) for a in args],
                          capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise AssertionError("sorter failed (%d)\n%s\n%s" % (proc.returncode, proc.stdout, proc.stderr))
    return proc


def organized_library(tmp_path):
    """An organized output holding screenshots of two apps at several screen
    sizes, from several months, plus a photo in the main library."""
    src, out, examples = tmp_path / "src", tmp_path / "out", tmp_path / "examples"
    app = 100
    other = 200
    write_screenshot(src / "Screenshot_20120314-100000.png", chrome_seed=app, middle_seed=1, size=(640, 1136))
    write_screenshot(src / "Screenshot_20180314-100000.png", chrome_seed=app, middle_seed=2, size=(750, 1334))
    write_screenshot(src / "Screenshot_20220314-100000.png", chrome_seed=app, middle_seed=3, size=(1170, 2532))
    write_screenshot(src / "Screenshot_20220315-100000.png", chrome_seed=other, middle_seed=4, size=(1170, 2532))
    write_screenshot(src / "Screenshot_20220316-100000.png", chrome_seed=other + 1, middle_seed=5, size=(1080, 2340))
    write_photo(src / "IMG_0001.jpg", seed=9, date_original="2022:03:14 10:00:00")
    run_script("--source", src, "--output", out)
    write_screenshot(examples / "pandora.png", chrome_seed=app, middle_seed=42, size=(1170, 2532))
    return out, examples


def test_matches_across_screen_sizes_and_moves_them(tmp_path):
    out, examples = organized_library(tmp_path)
    proc = run_sorter("--output", out, "--examples", examples, "--name", "pandora")
    assert "matched:   3 of 5" in proc.stdout
    moved = sorted(str(p.relative_to(out)).replace(os.sep, "/") for p in (out / "_review" / "pandora").rglob("*.png"))
    assert moved == ["_review/pandora/2012/03/20120314_100000.png",
                     "_review/pandora/2018/03/20180314_100000.png",
                     "_review/pandora/2022/03/20220314_100000.png"]
    left = sorted(p.name for p in (out / "_review" / "screenshots").rglob("*.png"))
    assert left == ["20220315_100000.png", "20220316_100000.png"]
    assert (out / "2022" / "03" / "20220314_100000.jpg").is_file()   # main library untouched


def test_manifest_follows_the_moves(tmp_path):
    out, examples = organized_library(tmp_path)
    run_sorter("--output", out, "--examples", examples, "--name", "pandora")
    for r in read_manifest(out):
        assert os.path.isfile(r["destination_path"]) or r["status"] == "duplicate", r
    pandora_rows = [r for r in read_manifest(out) if os.sep + "pandora" + os.sep in r["destination_path"]]
    assert len(pandora_rows) == 3


def test_dry_run_moves_nothing_but_logs_the_plan(tmp_path):
    out, examples = organized_library(tmp_path)
    before = sorted(str(p) for p in out.rglob("*.png"))
    proc = run_sorter("--output", out, "--examples", examples, "--name", "pandora", "--dry-run")
    assert "nothing moved" in proc.stdout
    assert sorted(str(p) for p in out.rglob("*.png")) == before
    with open(out / "_review" / "pandora_sort_dryrun.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3
    assert all(r["matched_example"] == "pandora.png" for r in rows)
    assert all(float(r["distance"]) < 12 for r in rows)


def test_second_run_with_a_new_example_catches_the_leftovers(tmp_path):
    out, examples = organized_library(tmp_path)
    run_sorter("--output", out, "--examples", examples, "--name", "pandora")
    # The owner finds one of the "other" layout still in screenshots and adds it.
    write_screenshot(examples / "pandora_old_look.png", chrome_seed=200, middle_seed=99, size=(750, 1334))
    proc = run_sorter("--output", out, "--examples", examples, "--name", "pandora")
    assert "Loaded 2 example screenshot(s)." in proc.stdout
    assert "matched:   1 of 2" in proc.stdout
    assert len(list((out / "_review" / "pandora").rglob("*.png"))) == 4
    assert [p.name for p in (out / "_review" / "screenshots").rglob("*.png")] == ["20220316_100000.png"]


def test_rerun_with_nothing_new_is_a_no_op(tmp_path):
    out, examples = organized_library(tmp_path)
    run_sorter("--output", out, "--examples", examples, "--name", "pandora")
    proc = run_sorter("--output", out, "--examples", examples, "--name", "pandora")
    assert "matched:   0 of 2" in proc.stdout


def test_refuses_without_a_screenshots_folder_or_examples(tmp_path):
    out, examples = organized_library(tmp_path)
    assert run_sorter("--output", tmp_path / "nowhere", "--examples", examples, check=False).returncode != 0
    assert run_sorter("--output", out, "--examples", tmp_path / "noexamples", check=False).returncode != 0
    empty = tmp_path / "empty"; empty.mkdir()
    assert run_sorter("--output", out, "--examples", empty, check=False).returncode != 0
