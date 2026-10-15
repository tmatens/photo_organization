"""Several drives into one library, and the path rules that differ on
Windows: drive roots, case, and the 260-character limit."""
import ntpath
import os
import posixpath
import sys

import pytest

from conftest import REPO_ROOT, read_manifest, run_script, write_photo

sys.path.insert(0, str(REPO_ROOT))
from organize_photos import is_inside, longpath, plainpath  # noqa: E402


def test_several_sources_become_one_library_with_cross_drive_duplicates(tmp_path):
    drive1, drive2, out = tmp_path / "drive1", tmp_path / "drive2", tmp_path / "ssd"
    a = write_photo(drive1 / "a.jpg", seed=1, date_original="2021:05:04 10:11:12")
    write_photo(drive2 / "b.jpg", seed=2, date_original="2020:01:02 03:04:05")
    (drive2 / "a again.jpg").write_bytes(a.read_bytes())
    proc = run_script("--source", drive1, "--source", drive2, "--output", out)
    rows = {os.path.basename(r["source_path"]): r for r in read_manifest(out)}
    assert rows["a.jpg"]["status"] == "copied"
    assert rows["b.jpg"]["status"] == "copied"
    assert rows["a again.jpg"]["status"] == "duplicate"
    assert rows["a again.jpg"]["duplicate_of"] == str(a)
    assert len(list(out.rglob("*.jpg"))) == 2
    assert "Found 3 image files." in proc.stdout


def test_output_inside_one_of_several_sources_is_not_rescanned(tmp_path):
    drive1, drive2 = tmp_path / "drive1", tmp_path / "drive2"
    out = drive2 / "Organized"
    write_photo(drive1 / "a.jpg", seed=1, date_original="2021:05:04 10:11:12")
    write_photo(drive2 / "b.jpg", seed=2, date_original="2020:01:02 03:04:05")
    run_script("--source", drive1, "--source", drive2, "--output", out)
    run_script("--source", drive1, "--source", drive2, "--output", out)
    assert len(read_manifest(out)) == 2
    assert len(list(out.rglob("*.jpg"))) == 2


def test_a_source_inside_the_output_is_refused(tmp_path):
    out = tmp_path / "ssd"
    write_photo(out / "old" / "a.jpg", seed=1)
    assert run_script("--source", out / "old", "--output", out, check=False).returncode != 0


def test_is_inside_handles_windows_drive_roots_and_case():
    assert is_inside(r"E:\Organized", "E:\\", ntpath)
    assert is_inside(r"E:\Photos\2021\x.jpg", r"E:\Photos", ntpath)
    assert is_inside(r"e:\photos", r"E:\Photos", ntpath)       # case-insensitive
    assert not is_inside("E:\\", r"E:\Organized", ntpath)
    assert not is_inside(r"F:\Organized", "E:\\", ntpath)      # different drive
    assert not is_inside(r"E:\Photos2", r"E:\Photos", ntpath)  # prefix, not child
    assert is_inside("/a/b", "/a", posixpath)
    assert not is_inside("/ab", "/a", posixpath)


def test_plainpath_strips_the_windows_long_path_prefix():
    assert plainpath(r"\\?\C:\photos\a.jpg") == r"C:\photos\a.jpg"
    assert plainpath(r"\\?\UNC\nas\share\a.jpg") == r"\\nas\share\a.jpg"
    assert plainpath("/unix/path") == "/unix/path"


@pytest.mark.skipif(os.name != "nt", reason="Windows path prefix")
def test_longpath_adds_the_prefix_on_windows():
    assert longpath(r"C:\photos\a.jpg") == r"\\?\C:\photos\a.jpg"
    assert longpath(r"\\nas\share\a.jpg") == r"\\?\UNC\nas\share\a.jpg"
    assert longpath(r"\\?\C:\x") == r"\\?\C:\x"


@pytest.mark.skipif(os.name != "nt", reason="the 260-character limit is a Windows rule")
def test_photos_beyond_260_characters_are_found_and_copied(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    deep = src
    while len(str(deep)) < 300:
        deep = deep / ("a_very_long_folder_name_from_an_old_backup_" * 2)
    os.makedirs(longpath(str(deep)))
    write_photo(longpath(str(deep / "IMG_20220314_100000.jpg")), seed=1)
    run_script("--source", src, "--output", out)
    rows = read_manifest(out)
    assert len(rows) == 1 and rows[0]["status"] == "copied"
    assert rows[0]["source_path"].endswith("IMG_20220314_100000.jpg")
    assert not rows[0]["source_path"].startswith("\\\\?\\")
    assert (out / "2022" / "03" / "20220314_100000.jpg").is_file()
