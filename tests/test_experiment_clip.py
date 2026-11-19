"""experiments/clip_local.py and label_local.py: the local model's
arithmetic and the first-guess flow, with a stand-in for the model itself.
No model file is downloaded and nothing touches the network.

The arithmetic needs numpy, which arrives with the packages in
experiments/requirements.txt. Those tests skip when it is absent, except in
the CI job that installs them, where REQUIRE_EXPERIMENT_DEPS=1 turns a skip
into a failure."""
import hashlib
import json
import os
import sys

import pytest
from PIL import Image

from conftest import REPO_ROOT, write_photo

sys.path.insert(0, str(REPO_ROOT / "experiments"))
import clip_local  # noqa: E402
import common  # noqa: E402
import label_local  # noqa: E402
import sample  # noqa: E402

try:
    import numpy as np
    import onnxruntime  # noqa: F401
    import tokenizers  # noqa: F401
    HAVE_DEPS = True
except ImportError:
    HAVE_DEPS = False

if not HAVE_DEPS and os.environ.get("REQUIRE_EXPERIMENT_DEPS"):
    raise RuntimeError("REQUIRE_EXPERIMENT_DEPS is set but experiments/requirements.txt is not installed")

needs_numpy = pytest.mark.skipif(not HAVE_DEPS, reason="experiments/requirements.txt not installed")


# --- the pinned model files (no numpy needed) --------------------------------

def tiny_model(content=b"model bytes"):
    return {"name": "tiny", "base_url": "https://example.invalid/",
            "files": {"model.onnx": ("onnx/model.onnx", hashlib.sha256(content).hexdigest())}}


def test_a_missing_model_file_is_downloaded_once_and_checked(tmp_path):
    calls = []

    def download(url, dest):
        calls.append(url)
        with open(dest, "wb") as f:
            f.write(b"model bytes")
    folder = clip_local.fetch_model(tmp_path / "eval_data", tiny_model(), download)
    assert (folder / "model.onnx").read_bytes() == b"model bytes"
    assert folder == (tmp_path / "eval_data" / "models" / "tiny").resolve()
    clip_local.fetch_model(tmp_path / "eval_data", tiny_model(), download)
    assert calls == ["https://example.invalid/onnx/model.onnx"]     # not fetched twice


def test_a_model_file_with_the_wrong_hash_is_removed_and_never_used(tmp_path, capsys):
    def download(url, dest):
        with open(dest, "wb") as f:
            f.write(b"something else entirely")
    with pytest.raises(SystemExit, match="not the pinned model file"):
        clip_local.fetch_model(tmp_path / "eval_data", tiny_model(), download)
    assert not (tmp_path / "eval_data" / "models" / "tiny" / "model.onnx").exists()


def test_the_pinned_model_names_one_revision_and_a_hash_per_file():
    assert len(clip_local.MODEL["base_url"].rstrip("/").split("/")[-1]) == 40    # a full commit id
    assert all(len(sha) == 64 for _remote, sha in clip_local.MODEL["files"].values())


def test_every_starting_label_has_descriptions_and_a_label_without_any_is_refused():
    texts, labels_of = clip_local.descriptions_from(label_local.starting_categories())
    assert set(labels_of) == {label for label, _ in common.STARTING_CATEGORIES}
    assert len(texts) == len(labels_of)
    with pytest.raises(SystemExit, match="no descriptions"):
        clip_local.descriptions_from({"labels": [{"label": "drawing", "what_counts": "x"}]})


# --- the arithmetic ------------------------------------------------------------

@needs_numpy
def test_a_picture_is_cut_to_the_middle_square_the_model_expects():
    wide = Image.new("RGB", (800, 400), "black")
    wide.paste((255, 255, 255), (300, 0, 500, 400))         # a white band in the middle
    pixels = clip_local.prepare(wide)
    assert pixels.shape == (3, 224, 224) and pixels.dtype == np.float32
    assert pixels[:, 112, 112].min() > 1.5                  # the middle is white
    assert pixels[:, 112, 2].max() < -1.4                   # the edges of the cut are black


@needs_numpy
def test_a_label_wins_if_any_one_of_its_descriptions_matches_best():
    descriptions = clip_local.unit(np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]))
    labels_of = ["photo", "receipt", "photo"]
    images = clip_local.unit(np.array([[0.0, 0.0, 1.0], [0.1, 1.0, 0.0], [1.0, 0.1, 0.0]]))
    labels, share_rows = clip_local.shares(images, descriptions, labels_of)
    assert labels == ["photo", "receipt"]
    assert np.allclose(share_rows.sum(axis=1), 1.0)
    guesses = clip_local.best_labels(share_rows, labels)
    assert [label for label, _ in guesses] == ["photo", "receipt", "photo"]
    assert all(0.5 < confidence <= 1.0 for _, confidence in guesses)


@needs_numpy
def test_similar_pictures_end_up_in_the_same_group_and_the_seed_fixes_the_result():
    rng = np.random.default_rng(1)
    near_a = np.array([1.0, 0.0, 0.0]) + 0.01 * rng.standard_normal((10, 3))
    near_b = np.array([0.0, 1.0, 0.0]) + 0.01 * rng.standard_normal((10, 3))
    vectors = clip_local.unit(np.vstack([near_a, near_b]))
    groups = clip_local.group_similar(vectors, 2, seed=3)
    assert len(set(groups[:10])) == 1 and len(set(groups[10:])) == 1 and groups[0] != groups[10]
    assert groups == clip_local.group_similar(vectors, 2, seed=3)
    assert len(set(clip_local.group_similar(vectors[:3], 30, seed=3))) <= 3     # more groups than files


@needs_numpy
def test_a_group_is_named_after_the_kinds_closest_to_its_average_picture():
    vectors = clip_local.unit(np.array([[1.0, 0.1, 0.0], [1.0, 0.0, 0.1], [0.0, 0.1, 1.0]]))
    kind_vectors = clip_local.unit(np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]))
    names = clip_local.name_groups(vectors, [0, 0, 1], kind_vectors, ["receipt", "map", "selfie"], top=2)
    assert names[0][0] == "receipt" and names[1][0] == "selfie" and len(names[0]) == 2


def test_the_list_of_kinds_is_wide_and_has_no_repeats():
    assert len(clip_local.KINDS) > 80 and len(set(clip_local.KINDS)) == len(clip_local.KINDS)


# --- the first-guess flow, with a stand-in model ------------------------------

class FakeClip:
    """Stands in for the real model: a picture's 'numbers' are just its
    average red, green and blue; a sentence's are picked by a key word."""

    def __init__(self, eval_data):
        pass

    def embed_images(self, paths):
        rows = []
        for path in paths:
            r, g, b = Image.open(path).convert("RGB").resize((1, 1)).getpixel((0, 0))
            rows.append([r + 1.0, g + 1.0, b + 1.0])
        return clip_local.unit(np.array(rows, dtype=np.float32))

    def embed_texts(self, texts):
        return clip_local.unit(np.array(
            [[1.0, 0.1, 0.1] if "receipt" in t else [0.1, 0.1, 1.0] for t in texts], dtype=np.float32))


@needs_numpy
def test_local_first_guesses_run_in_two_passes_and_upload_nothing(tmp_path, capsys, monkeypatch):
    source = tmp_path / "src"
    source.mkdir()
    for i in range(3):
        Image.new("RGB", (64, 48), (250, 10, 10)).save(source / ("red_%d.png" % i))
        Image.new("RGB", (64, 48), (10, 10, 250)).save(source / ("blue_%d.png" % i))
    eval_data = tmp_path / "eval_data"
    sample.main(["--source", "src=%s" % source, "--seed", "1", "--eval-data", str(eval_data)])
    monkeypatch.setattr(clip_local, "Clip", FakeClip)
    monkeypatch.setitem(sys.modules, "anthropic", None)         # importing it would fail

    label_local.main(["--pass", "1", "--groups", "2", "--eval-data", str(eval_data)])
    first = common.read_csv(eval_data / "labels" / "local_pass1.csv")
    assert len(first) == 6 and len({r["group"] for r in first}) == 2
    page = (eval_data / "labels" / "local_pass1_tally.html").read_text()
    assert "Group 1: " in page and "Group 2: " in page and "Group 3" not in page
    assert (eval_data / "embeddings" / "clip-vit-b32.npz").is_file()
    categories = eval_data / "labels" / "categories.json"
    assert json.loads(categories.read_text())["settled"] is False

    with pytest.raises(SystemExit, match="not marked as settled"):
        label_local.main(["--pass", "2", "--eval-data", str(eval_data)])
    categories.write_text(json.dumps({
        "settled": True, "when_two_apply": "receipt wins",
        "labels": [{"label": "receipt", "what_counts": "r", "descriptions": ["a till receipt"]},
                   {"label": "photo", "what_counts": "p", "descriptions": ["a photo"]}]}))
    label_local.main(["--pass", "2", "--eval-data", str(eval_data)])

    rows = common.read_csv(eval_data / "labels" / "labels.csv")
    guessed = {os.path.basename(r["rel_path"])[:3]: r["guessed_label"] for r in rows}
    assert guessed == {"red": "receipt", "blu": "photo"}
    assert all(r["confirmed_label"] == "" for r in rows)
    assert "zero-shot" in json.loads((eval_data / "labels" / "first_guess.json").read_text())["first_guess_by"]
