"""--sample N processes N files spread evenly across everything found, so a
preview of a big library takes minutes. A later full run picks up the rest."""
import os

from conftest import read_manifest, run_script, write_photo


def test_sample_takes_every_kth_file_across_all_sources(tmp_path):
    d1, d2, out = tmp_path / "d1", tmp_path / "d2", tmp_path / "out"
    for i in range(10):
        write_photo(d1 / ("a%02d.jpg" % i), seed=i, date_original="2021:05:04 10:00:%02d" % i)
    for i in range(10):
        write_photo(d2 / ("b%02d.jpg" % i), seed=100 + i, date_original="2022:01:01 10:00:%02d" % i)
    proc = run_script("--source", d1, "--source", d2, "--output", out, "--sample", "4", "--dry-run")
    assert "Found 20 photo and video files." in proc.stdout
    assert "Sampling 4 of them, spread evenly." in proc.stdout
    with open(out / "manifest_dryrun.csv", newline="") as f:
        import csv
        names = [os.path.basename(r["source_path"]) for r in csv.DictReader(f)]
    assert names == ["a00.jpg", "a05.jpg", "b00.jpg", "b05.jpg"]


def test_sample_larger_than_library_processes_everything(library):
    src, out = library
    for i in range(3):
        write_photo(src / ("p%d.jpg" % i), seed=i, date_original="2021:05:04 10:00:%02d" % i)
    proc = run_script("--source", src, "--output", out, "--sample", "50")
    assert "Sampling" not in proc.stdout
    assert len(read_manifest(out)) == 3


def test_full_run_after_a_sample_does_not_copy_the_sample_again(library):
    src, out = library
    for i in range(6):
        write_photo(src / ("p%d.jpg" % i), seed=i, date_original="2021:05:04 10:00:%02d" % i)
    run_script("--source", src, "--output", out, "--sample", "2")
    assert len(read_manifest(out)) == 2
    proc = run_script("--source", src, "--output", out)
    assert "Resuming: 2 already in manifest, 4 still to do." in proc.stdout
    rows = read_manifest(out)
    assert len(rows) == 6
    assert len(list(out.rglob("*.jpg"))) == 6
    assert len({r["destination_path"] for r in rows}) == 6


def test_sample_must_be_positive(library):
    src, out = library
    write_photo(src / "p.jpg", seed=1)
    assert run_script("--source", src, "--output", out, "--sample", "0", check=False).returncode != 0
