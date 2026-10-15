"""Screenshots are never camera photos. Whatever date they carry, they go to
the review folder, sorted by month inside it. The example matching, when
used, still takes precedence."""
import os

from conftest import read_manifest, run_script, write_photo, write_screenshot


def rows(out):
    return {os.path.basename(r["source_path"]): r for r in read_manifest(out)}


def test_png_goes_to_review_even_with_a_date(library):
    src, out = library
    write_screenshot(src / "Screenshot_20220314-100000.png", chrome_seed=1, middle_seed=1)
    write_screenshot(src / "IMG_0042.PNG", chrome_seed=2, middle_seed=2)       # iPhone style
    write_photo(src / "IMG_0043.jpg", seed=3, date_original="2022:03:14 10:00:00")
    proc = run_script("--source", src, "--output", out)
    r = rows(out)
    assert r["Screenshot_20220314-100000.png"]["destination_path"].endswith(
        os.path.join("_review", "2022", "03", "20220314_100000.png"))
    assert os.sep + "_review" + os.sep in r["IMG_0042.PNG"]["destination_path"]
    assert os.sep + "_review" + os.sep not in r["IMG_0043.jpg"]["destination_path"]
    assert "to _review/: 2 screenshots, 0 with no date" in proc.stdout


def test_samsung_jpeg_screenshot_goes_to_review_by_name(library):
    src, out = library
    write_photo(src / "Screenshot_20220314-100000_Music.jpg", seed=1)
    write_photo(src / "Screen Shot 2022-03-14 at 10.00.00.jpg", seed=2)
    run_script("--source", src, "--output", out)
    for name, r in rows(out).items():
        assert os.sep + "_review" + os.sep in r["destination_path"], name


def test_png_is_photo_turns_the_rule_off(library):
    src, out = library
    write_screenshot(src / "Screenshot_20220314-100000.png", chrome_seed=1, middle_seed=1)
    run_script("--source", src, "--output", out, "--png-is-photo")
    r = rows(out)["Screenshot_20220314-100000.png"]
    assert r["destination_path"].endswith(os.path.join("2022", "03", "20220314_100000.png"))
    assert "_review" not in r["destination_path"]


def test_example_match_still_wins_over_the_screenshot_rule(library):
    src, out = library
    example = write_screenshot(src / "example.png", chrome_seed=100, middle_seed=1)
    write_screenshot(src / "Screenshot_20220314-100000.png", chrome_seed=100, middle_seed=2)
    write_screenshot(src / "other_app.png", chrome_seed=200, middle_seed=3)
    run_script("--source", src, "--output", out, "--example", example, "--example-chrome")
    r = rows(out)
    assert r["Screenshot_20220314-100000.png"]["status"] == "matched-example"
    assert os.sep + "matched_example" + os.sep in r["Screenshot_20220314-100000.png"]["destination_path"]
    assert os.sep + "_review" + os.sep in r["other_app.png"]["destination_path"]


def test_review_folder_is_sorted_by_month_inside(library):
    src, out = library
    write_screenshot(src / "Screenshot_20220314-100000.png", chrome_seed=1, middle_seed=1)
    write_screenshot(src / "Screenshot_20210101-000000.png", chrome_seed=1, middle_seed=2)
    run_script("--source", src, "--output", out)
    assert (out / "_review" / "2022" / "03").is_dir()
    assert (out / "_review" / "2021" / "01").is_dir()
