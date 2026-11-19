"""experiments/sample.py, facts.py, label_first_guess.py and review.py,
checked on synthetic images. Nothing here needs real photos, a model, the
anthropic package or a network connection."""
import base64
import io
import json
import random
import sys
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer
from types import SimpleNamespace

import pytest
from PIL import Image

from conftest import REPO_ROOT, sha256_tree, write_photo, write_screenshot

sys.path.insert(0, str(REPO_ROOT / "experiments"))
import common  # noqa: E402
import facts  # noqa: E402
import label_first_guess as labeller  # noqa: E402
import review  # noqa: E402
import sample  # noqa: E402


def write_noisy_photo(path, seed, size=(640, 480)):
    """A picture with sensor-like noise in every pixel, which is what a real
    camera file looks like to the pixel facts. conftest's make_image draws
    flat rectangles, which look like a graphic."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    Image.frombytes("RGB", size, bytes(rng.getrandbits(8) for _ in range(size[0] * size[1] * 3))) \
        .save(path, "JPEG", quality=92)
    return path


# --- common ----------------------------------------------------------------

def test_writes_are_refused_outside_the_eval_data_folder(tmp_path):
    eval_data = tmp_path / "eval_data"
    assert common.inside(eval_data, "labels", "x.csv") == (eval_data / "labels" / "x.csv").resolve()
    with pytest.raises(ValueError):
        common.inside(eval_data, "..", "escaped.csv")
    with pytest.raises(ValueError):
        common.inside(eval_data, "files", "..", "..", "escaped.jpg")


def test_eval_data_is_ignored_by_git_and_experiments_are_not_in_the_release_zip():
    assert "eval_data/" in (REPO_ROOT / ".gitignore").read_text().splitlines()
    assert "experiments" not in (REPO_ROOT / "scripts" / "build_zip.py").read_text()


# --- sampler ---------------------------------------------------------------

def test_pick_evenly_reaches_from_first_to_last():
    assert sample.pick_evenly(list(range(10)), 5) == [0, 2, 4, 6, 8]
    assert sample.pick_evenly(list(range(3)), 5) == [0, 1, 2]


def test_only_photo_files_outside_hidden_and_system_folders_are_wanted():
    assert sample.wanted("2020/trip/IMG_0001.JPG")
    assert sample.wanted("a.heic")
    assert not sample.wanted("clip.mp4")
    assert not sample.wanted("@eaDir/IMG_0001.jpg/thumb.jpg")
    assert not sample.wanted(".hidden/a.jpg") and not sample.wanted("x/._a.jpg")


def test_a_host_and_folder_means_ssh_but_a_windows_drive_does_not():
    assert sample.REMOTE.match("nas:/photos/sorted").groups() == ("nas", "/photos/sorted")
    assert sample.REMOTE.match("me@nas:/photos").group(1) == "me@nas"
    assert sample.REMOTE.match("C:/photos") is None
    assert sample.REMOTE.match("/photos/sorted") is None


def two_sources(tmp_path):
    undated, camera = tmp_path / "undated", tmp_path / "camera"
    for i in range(12):
        write_photo(undated / ("saved_%02d.jpg" % i), seed=i)
    for i in range(20):
        write_photo(camera / "2021" / ("2021_%02d" % (i % 4 + 1)) / ("IMG_%04d.jpg" % i),
                    seed=100 + i, date_original="2021:0%d:01 10:00:00" % (i % 4 + 1))
    (camera / "2021" / "clip.mp4").write_bytes(b"not a photo")
    return undated, camera


def test_sampler_copies_an_even_spread_keeps_folders_and_splits_once(tmp_path, capsys):
    undated, camera = two_sources(tmp_path)
    before = sha256_tree(tmp_path / "undated"), sha256_tree(tmp_path / "camera")
    eval_data = tmp_path / "eval_data"
    argv = ["--source", "undated=%s" % undated, "--source", "camera=%s" % camera,
            "--count", "16", "--seed", "7", "--eval-data", str(eval_data)]
    sample.main(argv)

    rows = common.load_sample(eval_data)
    assert len(rows) == 16
    for name in ("undated", "camera"):
        mine = [r for r in rows if r["source"] == name]
        assert len(mine) == 8
        assert sorted(r["half"] for r in mine) == ["final"] * 4 + ["tuning"] * 4
    cam = [r for r in rows if r["source"] == "camera"]
    assert {r["folder"] for r in cam} == {"2021/2021_0%d" % m for m in (1, 2, 3, 4)}
    assert all(r["camera_dated"] == "yes" for r in cam)
    assert all(r["camera_dated"] == "no" for r in rows if r["source"] == "undated")
    for row in rows:        # each copy sits at its original folder path
        assert common.sample_file(eval_data, row).is_file()
    assert len({r["id"] for r in rows}) == 16

    # The sources are exactly as they were, and a second run redraws nothing.
    assert (sha256_tree(tmp_path / "undated"), sha256_tree(tmp_path / "camera")) == before
    with pytest.raises(SystemExit, match="not redrawn"):
        sample.main(argv)


def test_an_interrupted_sampler_run_finishes_the_same_draw(tmp_path, monkeypatch, capsys):
    undated, camera = two_sources(tmp_path)
    eval_data = tmp_path / "eval_data"
    argv = ["--source", "undated=%s" % undated, "--count", "6", "--eval-data", str(eval_data)]
    monkeypatch.setattr(sample, "copy_missing", lambda *a: (_ for _ in ()).throw(KeyboardInterrupt))
    with pytest.raises(KeyboardInterrupt):
        sample.main(argv)
    drawn = common.read_csv(eval_data / "draw.csv")
    monkeypatch.undo()
    sample.main(argv)
    assert [r["rel_path"] for r in common.load_sample(eval_data)] == [r["rel_path"] for r in drawn]


def test_a_file_that_is_not_an_image_is_left_out_and_counted(tmp_path, capsys):
    source = tmp_path / "src"
    write_photo(source / "a.jpg", seed=1)
    (source / "b.jpg").write_bytes(b"this is not a jpeg")
    eval_data = tmp_path / "eval_data"
    sample.main(["--source", "src=%s" % source, "--eval-data", str(eval_data)])
    assert [r["rel_path"] for r in common.load_sample(eval_data)] == ["a.jpg"]
    assert json.loads((eval_data / "sample_info.json").read_text())["could_not_be_opened"] == 1


# --- facts -----------------------------------------------------------------

def test_name_patterns_and_folder_hints():
    assert facts.name_pattern("IMG_1234.JPG") == "camera"
    assert facts.name_pattern("PXL_20220314_100000123.jpg") == "camera"
    assert facts.name_pattern("Screenshot_20220314-100000.png") == "screenshot"
    assert facts.name_pattern("IMG-20220314-WA0007.jpg") == "messaging"
    assert facts.name_pattern("0f8fad5b-d9cb-469f-a165-70867728950e.jpg") == "uuid"
    assert facts.name_pattern("1234567.jpg") == "digits"
    assert facts.name_pattern("holiday.jpg") == "other"
    assert facts.folder_hint("Phone/WhatsApp Images") == "messaging"
    assert facts.folder_hint("Pictures/Screenshots") == "screenshots"
    assert facts.folder_hint("2021/2021_03") == "none"


def test_a_screen_capture_and_a_camera_photo_differ_on_the_pixel_facts(tmp_path):
    shot = facts.compute(write_screenshot(tmp_path / "Screenshot_1.png", 1, 2, size=(1170, 2532)))
    photo = facts.compute(write_noisy_photo(tmp_path / "IMG_0001.jpg", seed=3))
    assert shot["screen_sized"] == "yes" and photo["screen_sized"] == "no"
    assert shot["flat_share"] > 0.5 > photo["flat_share"]
    assert shot["distinct_colours"] < photo["distinct_colours"]
    assert shot["type"] == "png" and photo["type"] == "jpg"
    assert set(facts.FACT_COLUMNS) - {"id"} == set(shot)


def test_a_page_of_text_has_quiet_rows_between_busy_ones(tmp_path):
    page = Image.new("RGB", (400, 600), "white")
    for y in range(40, 560, 24):                # 'lines of text': dashed dark rows
        for x in range(30, 370, 14):
            page.paste((20, 20, 20), (x, y, x + 9, y + 10))
    page.save(tmp_path / "page.png")
    text = facts.compute(tmp_path / "page.png")
    photo = facts.compute(write_noisy_photo(tmp_path / "photo.jpg", seed=5))
    assert text["near_white"] > 0.6 and text["quiet_rows"] > 0.3 and text["row_changes"] > 5
    assert photo["quiet_rows"] < 0.1


def test_camera_exif_fields_are_reported_as_present_or_absent(tmp_path):
    from PIL import ExifTags
    exif = Image.Exif()
    exif[ExifTags.Base.Make] = "TestCam"
    exif[ExifTags.Base.Software] = "Instagram 1.2"
    exif.get_ifd(ExifTags.IFD.Exif)[ExifTags.Base.DateTimeOriginal] = "2022:03:14 10:00:00"
    Image.new("RGB", (64, 48), "red").save(tmp_path / "a.jpg", exif=exif)
    got = facts.compute(tmp_path / "a.jpg", folder="Phone/DCIM/Camera")
    assert (got["has_make"], got["has_model"], got["has_date_taken"]) == ("yes", "no", "yes")
    assert got["software"] == "instagram" and got["folder_hint"] == "camera"
    assert got["folder_depth"] == 3


def test_fact_table_is_written_for_one_half_and_read_back_as_numbers(tmp_path, capsys):
    eval_data = tmp_path / "eval_data"
    source = tmp_path / "src"
    for i in range(4):
        write_noisy_photo(source / "album" / ("IMG_%04d.jpg" % i), seed=i, size=(64, 48))
    sample.main(["--source", "src=%s" % source, "--seed", "1", "--eval-data", str(eval_data)])
    facts.main(["--half", "tuning", "--eval-data", str(eval_data)])
    table = facts.load(eval_data, "tuning")
    assert len(table) == 2 and all(isinstance(r["flat_share"], float) for r in table)
    assert not (eval_data / "facts" / "facts_final.csv").exists()


# --- first-guess labeller --------------------------------------------------

def test_the_copy_that_would_be_sent_is_small_and_carries_no_exif(tmp_path):
    path = write_photo(tmp_path / "a.jpg", seed=1, size=(2000, 1000),
                       date_original="2022:03:14 10:00:00")
    data, size = labeller.encode_image(path, 768)
    assert size == (768, 384)
    sent = Image.open(io.BytesIO(base64.standard_b64decode(data)))
    assert sent.format == "JPEG" and len(sent.getexif()) == 0
    assert labeller.image_tokens(size) == 28 * 14


def test_a_request_names_the_file_only_by_its_sample_id():
    one = labeller.build_request("s0007", "QUJD", 1, labeller.starting_categories(), "some-model")
    assert one["custom_id"] == "s0007"
    image, text = one["params"]["messages"][0]["content"]
    assert image["source"] == {"type": "base64", "media_type": "image/jpeg", "data": "QUJD"}
    schema = one["params"]["output_config"]["format"]["schema"]
    assert schema["properties"]["label"]["enum"][-1] == "other"
    assert set(schema["required"]) == {"description", "kind", "label"}

    settled = {"labels": [{"label": "receipt", "what_counts": "a till receipt"},
                          {"label": "photo", "what_counts": "anything else"}],
               "when_two_apply": "receipt wins"}
    two = labeller.build_request("s0007", "QUJD", 2, settled, "some-model")
    schema = two["params"]["output_config"]["format"]["schema"]
    assert schema["properties"] == {"label": {"type": "string", "enum": ["receipt", "photo"]}}
    assert "receipt wins" in two["params"]["messages"][0]["content"][1]["text"]


def test_requests_are_split_into_batches_by_count(monkeypatch):
    monkeypatch.setattr(labeller, "MAX_BATCH_REQUESTS", 2)
    requests = [labeller.build_request("s%04d" % i, "QUJD", 1, labeller.starting_categories(), "m")
                for i in range(5)]
    assert [len(b) for b in labeller.split_into_batches(requests)] == [2, 2, 1]


def fake_result(custom_id, kind="succeeded", stop_reason="end_turn", text='{"label": "photo"}'):
    message = SimpleNamespace(stop_reason=stop_reason,
                              content=[SimpleNamespace(type="text", text=text)])
    return SimpleNamespace(custom_id=custom_id, result=SimpleNamespace(type=kind, message=message))


def test_only_a_clean_answer_becomes_a_label():
    columns = labeller.PASS2_COLUMNS
    assert labeller.read_answer(fake_result("s0001"), columns) == \
        {"id": "s0001", "label": "photo", "error": ""}
    assert labeller.read_answer(fake_result("s0002", kind="errored"), columns)["error"] == "errored"
    assert labeller.read_answer(fake_result("s0003", stop_reason="refusal"), columns)["error"] == "refusal"
    assert labeller.read_answer(fake_result("s0004", text="not json"), columns)["error"] == "unreadable answer"


def sampled(tmp_path, count=6):
    eval_data = tmp_path / "eval_data"
    source = tmp_path / "src"
    for i in range(count):
        write_photo(source / ("IMG_%04d.jpg" % i), seed=i, size=(64, 48))
    sample.main(["--source", "src=%s" % source, "--seed", "1", "--eval-data", str(eval_data)])
    return eval_data


def test_dry_run_says_what_would_be_sent_and_sends_nothing(tmp_path, capsys, monkeypatch):
    eval_data = sampled(tmp_path)
    monkeypatch.setitem(sys.modules, "anthropic", None)     # importing it would now fail
    capsys.readouterr()
    labeller.main(["--pass", "1", "--dry-run", "--eval-data", str(eval_data)])
    out = capsys.readouterr().out
    assert "would send 6 files" in out and "3 from source 'src', tuning half" in out
    assert "nothing was sent" in out
    assert not (eval_data / "labels").exists()


def test_files_already_answered_are_not_sent_again(tmp_path, capsys):
    eval_data = sampled(tmp_path)
    common.write_csv(eval_data / "labels" / "pass1.csv", labeller.PASS1_COLUMNS,
                     [{"id": "s0001", "label": "photo", "error": ""},
                      {"id": "s0002", "label": "", "error": "errored"}])
    assert [r["id"] for r in labeller.still_to_do(eval_data, 1, None)] == \
        ["s0002", "s0003", "s0004", "s0005", "s0006"]


def test_pass_two_waits_for_a_settled_list_of_labels(tmp_path, capsys):
    eval_data = sampled(tmp_path)
    with pytest.raises(SystemExit):                 # pass 2 must be told which field
        labeller.main(["--pass", "2", "--dry-run", "--eval-data", str(eval_data)])
    argv = ["--pass", "2", "--field", "made", "--dry-run", "--eval-data", str(eval_data)]
    with pytest.raises(SystemExit, match="No settled list"):
        labeller.main(argv)
    path = eval_data / "labels" / "made" / "categories.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(labeller.starting_categories("made")))
    with pytest.raises(SystemExit, match="not marked as settled"):
        labeller.main(argv)


def test_tally_groups_similar_kinds_largest_first_and_writes_the_grids(tmp_path, capsys):
    eval_data = sampled(tmp_path)
    rows = [{"id": "s0001", "description": "a", "kind": "Till  receipt", "label": "receipt", "error": ""},
            {"id": "s0002", "description": "b", "kind": "till receipt", "label": "receipt", "error": ""},
            {"id": "s0003", "description": "c", "kind": "family photo", "label": "photo", "error": ""},
            {"id": "s0004", "description": "", "kind": "", "label": "", "error": "errored"}]
    assert [(g, len(r)) for g, r in labeller.tally_groups(rows)] == \
        [("till receipt", 2), ("family photo", 1)]
    merged = {"till receipt": "paperwork", "family photo": "people"}
    assert [g for g, _ in labeller.tally_groups(rows, merged)] == ["paperwork", "people"]

    common.write_csv(eval_data / "labels" / "pass1.csv", labeller.PASS1_COLUMNS, rows)
    labeller.main(["--tally", "--eval-data", str(eval_data)])
    page = (eval_data / "labels" / "pass1_tally.html").read_text()
    assert page.index("till receipt") < page.index("family photo")
    assert (eval_data / "thumbs" / "s0001.jpg").is_file()
    for field in common.FIELDS:
        started = json.loads((eval_data / "labels" / field / "categories.json").read_text())
        assert started["settled"] is False and started["when_two_apply"] == common.FIELD_TIE_RULE[field]
        assert [c["label"] for c in started["labels"]][-1] == common.FIELD_DEFAULT[field]


# --- review ----------------------------------------------------------------

def guesses(eval_data):
    sample_rows = common.load_sample(eval_data)
    rows = [{"id": r["id"], "rel_path": r["rel_path"], "confirmed_label": "", "reviewed": "",
             "guessed_label": "receipt" if i < 2 else "photo"} for i, r in enumerate(sample_rows)]
    common.write_csv(eval_data / "labels" / "shows" / "labels.csv", common.LABEL_COLUMNS, rows)
    return rows, {r["id"]: r["half"] for r in sample_rows}


def test_confirming_a_grid_records_corrections_and_accepts_the_rest(tmp_path, capsys):
    eval_data = sampled(tmp_path, count=8)
    rows, half_of = guesses(eval_data)
    for row in rows:
        half_of[row["id"]] = "tuning"
    shown = [r["id"] for r in review.waiting(rows, half_of, "tuning", "photo")]
    assert len(shown) == 6
    review.apply_grid(rows, shown[:4], {shown[0]: "document"}, ["document", "photo", "receipt"])
    by_id = {r["id"]: r for r in rows}
    assert by_id[shown[0]]["confirmed_label"] == "document"
    assert by_id[shown[1]]["confirmed_label"] == "photo" and by_id[shown[1]]["reviewed"] == "yes"
    assert by_id[shown[4]]["confirmed_label"] == ""             # not shown, not confirmed
    with pytest.raises(ValueError):
        review.apply_grid(rows, shown[:4], {shown[5]: "document"}, ["document"])   # not in the grid
    with pytest.raises(ValueError):
        review.apply_grid(rows, shown[:4], {shown[0]: "made-up"}, ["document"])    # not a label

    line = next(s for s in review.stats(rows, half_of) if s["guessed_label"] == "photo")
    assert (line["guessed"], line["looked_at"], line["changed"], line["not_reviewed"]) == (6, 4, 1, 2)
    assert line["changed_share"] == "0.250"


def test_spot_check_offers_the_same_files_each_time_and_the_rest_can_be_accepted_unseen(tmp_path, capsys):
    eval_data = sampled(tmp_path, count=8)
    rows, half_of = guesses(eval_data)
    for row in rows:
        half_of[row["id"]] = "tuning"
    first = [r["id"] for r in review.waiting(rows, half_of, "tuning", "photo", spot_check=3, seed=5)]
    again = [r["id"] for r in review.waiting(rows, half_of, "tuning", "photo", spot_check=3, seed=5)]
    assert len(first) == 3 and first == again
    review.apply_grid(rows, first, {}, ["photo"])
    assert review.waiting(rows, half_of, "tuning", "photo", spot_check=3, seed=5) == []
    assert review.accept_rest(rows, half_of, "tuning", "photo") == 3
    unseen = next(s for s in review.stats(rows, half_of) if s["guessed_label"] == "photo")
    assert unseen["accepted_unseen"] == 3 and unseen["looked_at"] == 3
    with pytest.raises(ValueError):
        review.accept_rest(rows, half_of, "final", "photo")


def test_the_review_page_serves_locally_and_saves_a_confirmed_grid(tmp_path, capsys):
    eval_data = sampled(tmp_path, count=4)
    guesses(eval_data)
    session = review.Review(eval_data, "shows", "tuning", ["document", "photo", "receipt"], None, 0)
    server = HTTPServer(("127.0.0.1", 0), review.make_handler(session))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:%d" % server.server_address[1]
    try:
        page = urllib.request.urlopen(base + "/grid?label=receipt").read().decode()
        shown = [r["id"] for r in review.waiting(review.load_labels(eval_data, "shows"), session.half_of,
                                                 "tuning", "receipt")]
        assert shown and all("data-id='%s'" % i in page for i in shown)
        assert urllib.request.urlopen(base + "/thumb/" + shown[0]).read()[:2] == b"\xff\xd8"

        def post(body):
            request = urllib.request.Request(base + "/confirm", data=json.dumps(body).encode(),
                                             headers={"Content-Type": "application/json"})
            return urllib.request.urlopen(request).status

        with pytest.raises(urllib.error.HTTPError):         # no token: refused
            post({"token": "guess", "shown": shown, "corrections": {}})
        assert post({"token": session.token, "shown": shown,
                     "corrections": {shown[0]: "document"}}) == 200
        with pytest.raises(urllib.error.HTTPError):         # only sample ids are served
            urllib.request.urlopen(base + "/thumb/../../sample.csv")
    finally:
        server.shutdown()
        server.server_close()
    saved = {r["id"]: r for r in review.load_labels(eval_data, "shows")}
    assert saved[shown[0]]["confirmed_label"] == "document" and saved[shown[0]]["reviewed"] == "yes"


def test_a_second_opinion_splits_each_label_into_disagree_and_agree_piles(tmp_path, capsys):
    eval_data = sampled(tmp_path, count=8)
    rows, half_of = guesses(eval_data)
    for row in rows:
        half_of[row["id"]] = "tuning"
    photos = [r["id"] for r in rows if r["guessed_label"] == "photo"]
    opinions = {i: {"id": i, "label": "photo", "look": ""} for i in photos}
    opinions[photos[0]]["label"] = "receipt"        # the second opinion differs
    opinions[photos[1]]["look"] = "yes"             # same label, but someone was unsure
    del opinions[photos[2]]                         # no second opinion at all
    assert review.pile_of(rows[0], None) == "all"

    def pile(name, **more):
        return [r["id"] for r in review.waiting(rows, half_of, "tuning", "photo", opinions=opinions,
                                                pile=name, **more)]
    assert sorted(pile("disagree")) == sorted(photos[:3])
    assert sorted(pile("agree")) == sorted(photos[3:])

    # Accepting the rest never takes a file the labellers disagree on.
    assert review.accept_rest(rows, half_of, "tuning", "photo", opinions) == 3
    assert sorted(pile("disagree")) == sorted(photos[:3]) and pile("agree") == []
    review.apply_grid(rows, photos[:3], {photos[0]: "receipt"}, ["photo", "receipt"])
    by_pile = {s["pile"]: s for s in review.stats(rows, half_of, opinions) if s["guessed_label"] == "photo"}
    assert (by_pile["disagree"]["looked_at"], by_pile["disagree"]["changed"]) == (3, 1)
    assert (by_pile["agree"]["accepted_unseen"], by_pile["agree"]["looked_at"]) == (3, 0)


def test_the_review_page_shows_the_second_opinion_on_the_disagree_pile(tmp_path, capsys):
    eval_data = sampled(tmp_path, count=4)
    rows, _half_of = guesses(eval_data)
    half = common.load_sample(eval_data)[0]["half"]
    mine = [r for r in rows if r["guessed_label"] == "photo"]
    common.write_csv(eval_data / "labels" / "shows" / "second_opinion.csv", review.OPINION_COLUMNS,
                     [{"id": r["id"], "label": "receipt", "look": ""} for r in mine])
    session = review.Review(eval_data, "shows", half, ["document", "photo", "receipt"], None, 0)
    assert "Labellers disagree" in session.index_page()
    page = session.grid_page("photo", "disagree")
    if any(session.half_of[r["id"]] == half for r in mine):
        assert "second opinion: receipt" in page and "<option selected>receipt</option>" in page
    assert "all confirmed" in session.grid_page("photo", "agree")
