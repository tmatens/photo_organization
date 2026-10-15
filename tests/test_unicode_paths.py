"""Folder and file names in any language, on any platform, including when
the output is piped (which is how the tests run and how a log file would
be written)."""
import os

from conftest import read_manifest, run_script, write_photo


def test_non_ascii_folders_and_files_are_handled_end_to_end(library):
    src, out = library
    folder = src / "Fotos de María" / "日本旅行"
    write_photo(folder / "写真 №1 – café.jpg", seed=1, date_original="2021:05:04 10:11:12")
    write_photo(folder / "Ünïcödé.jpg", seed=2)                      # undated -> review
    out = out.parent / "Organisé"
    proc = run_script("--source", src, "--output", out)
    rows = {os.path.basename(r["source_path"]): r for r in read_manifest(out)}
    assert rows["写真 №1 – café.jpg"]["status"] == "copied"
    assert (out / "2021" / "05" / "20210504_101112.jpg").is_file()
    assert os.path.join("_review", "photos") + os.sep in rows["Ünïcödé.jpg"]["destination_path"]
    assert "Traceback" not in proc.stderr


def test_copy_failure_message_with_non_ascii_path_does_not_crash(library):
    """The error path prints the source path; make sure that print itself
    cannot be the thing that kills the run."""
    if os.name == "nt" or os.geteuid() == 0:
        import pytest
        pytest.skip("needs POSIX permissions and a non-root user")
    src, out = library
    write_photo(src / "日本" / "写真.jpg", seed=1, date_original="2021:05:04 10:11:12")
    (out / "2021" / "05").mkdir(parents=True)
    (out / "2021" / "05").chmod(0o500)
    try:
        proc = run_script("--source", src, "--output", out, check=False)
    finally:
        (out / "2021" / "05").chmod(0o700)
    assert proc.returncode == 1
    assert "could not copy" in proc.stderr
    assert "Traceback" not in proc.stderr
