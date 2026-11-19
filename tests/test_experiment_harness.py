"""experiments/evaluate.py, rules.py and fact_review.py: the arithmetic of
the categorization experiment, checked on made-up answers and synthetic
images. No real photos, no model and no network are involved."""
import json
import sys

import pytest

from conftest import REPO_ROOT, write_photo

sys.path.insert(0, str(REPO_ROOT / "experiments"))
import common  # noqa: E402
import evaluate  # noqa: E402
import fact_review  # noqa: E402
import rules  # noqa: E402


class Fixed:
    """A candidate that gives back a prepared list of answers."""

    def __init__(self, answers, name="fixed"):
        self.answers = answers
        self.name = name

    def predict(self, paths):
        return self.answers[:len(paths)]


def by(rows, label, threshold):
    return next(r for r in rows if r["label"] == label and r["threshold"] == threshold)


def test_precision_and_recall_are_counted_per_label():
    truth = ["receipt", "receipt", "receipt", "photo", "photo", "photo"]
    answers = [("receipt", 0.9), ("receipt", 0.9), ("photo", 0.9),
               ("receipt", 0.9), ("photo", 0.9), ("photo", 0.9)]
    rows = evaluate.score(truth, answers, ["receipt", "photo"], thresholds=(0.5,))
    receipt = by(rows, "receipt", 0.5)
    assert (receipt["labelled"], receipt["correct"], receipt["actual"]) == (3, 2, 3)
    assert receipt["precision"] == pytest.approx(2 / 3)
    assert receipt["recall"] == pytest.approx(2 / 3)


def test_a_higher_threshold_trades_recall_for_precision():
    truth = ["receipt", "receipt", "photo"]
    answers = [("receipt", 0.95), ("receipt", 0.6), ("receipt", 0.7)]
    rows = evaluate.score(truth, answers, ["receipt"], thresholds=(0.5, 0.9))
    assert by(rows, "receipt", 0.5)["precision"] == pytest.approx(2 / 3)
    assert by(rows, "receipt", 0.5)["recall"] == 1.0
    assert by(rows, "receipt", 0.9)["precision"] == 1.0
    assert by(rows, "receipt", 0.9)["recall"] == 0.5


def test_no_answers_and_no_examples_are_reported_as_unknown_not_as_a_number():
    rows = evaluate.score(["photo"], [(None, 0.0)], ["photo", "receipt"], thresholds=(0.5,))
    assert by(rows, "photo", 0.5)["precision"] is None      # nothing was given this label
    assert by(rows, "photo", 0.5)["recall"] == 0.0
    assert by(rows, "receipt", 0.5)["recall"] is None       # no file truly has it


def test_confusion_table_counts_undecided_files_separately():
    table = evaluate.confusion(["receipt", "receipt", "photo"],
                               [("receipt", 1.0), (None, 0.0), ("receipt", 1.0)])
    assert table == {("receipt", "receipt"): 1, ("receipt", evaluate.UNDECIDED): 1,
                     ("photo", "receipt"): 1}


def test_best_at_precision_picks_the_threshold_that_finds_most_while_staying_precise():
    truth = ["receipt"] * 4 + ["photo"] * 2
    answers = [("receipt", 0.99), ("receipt", 0.9), ("receipt", 0.7), ("receipt", 0.6),
               ("receipt", 0.65), ("photo", 0.9)]
    rows = evaluate.score(truth, answers, ["receipt"])
    best = evaluate.best_at_precision(rows, "receipt", 0.95)
    assert best["threshold"] == 0.7 and best["recall"] == 0.75
    assert evaluate.best_at_precision(rows, "receipt", 1.01) is None


@pytest.mark.parametrize("answers", [
    [("photo", 1.0)],                       # one answer short
    [("photo", 1.5), ("photo", 0.5)],       # confidence out of range
    [(None, 0.4), ("photo", 0.5)],          # undecided but confident
])
def test_a_candidate_that_breaks_the_interface_is_stopped(answers):
    with pytest.raises(ValueError):
        evaluate.check_predictions(answers, 2)


def labelled_set(tmp_path, labels):
    """A tiny eval_data folder: one synthetic photo per label given, all in
    one half, all confirmed by a person."""
    eval_data = tmp_path / "eval_data"
    sample, confirmed = [], []
    for i, (label, half) in enumerate(labels, 1):
        file_id = "s%04d" % i
        write_photo(eval_data / "files" / "src" / "album" / ("%s.jpg" % file_id), seed=i)
        sample.append({"id": file_id, "source": "src", "rel_path": "album/%s.jpg" % file_id,
                       "folder": "album", "half": half, "camera_dated": "no",
                       "date_source": "file-date", "bytes": 1})
        confirmed.append({"id": file_id, "rel_path": "album/%s.jpg" % file_id,
                          "guessed_label": label, "confirmed_label": label, "reviewed": "yes"})
    common.write_csv(eval_data / "sample.csv", common.SAMPLE_COLUMNS, sample)
    common.write_csv(eval_data / "labels" / "labels.csv", common.LABEL_COLUMNS, confirmed)
    return eval_data


def test_evaluate_writes_totals_and_a_mistakes_list_inside_eval_data(tmp_path):
    eval_data = labelled_set(tmp_path, [("receipt", "tuning"), ("photo", "tuning"),
                                        ("photo", "final")])
    rows, unreviewed = evaluate.labelled_rows(eval_data, "tuning")
    assert [r["true_label"] for r in rows] == ["receipt", "photo"] and unreviewed == 0
    totals, summary, mistakes = evaluate.evaluate(
        Fixed([("receipt", 0.9), ("receipt", 0.9)]), rows, "tuning")
    assert summary["files"] == 2 and summary["images_per_second"] > 0
    assert summary["extra_install_mb"] == 0.0
    assert [(m["id"], m["true_label"], m["predicted_label"]) for m in mistakes] == \
        [("s0002", "photo", "receipt")]
    assert by(totals, "receipt", 0.5)["precision"] == 0.5


def test_unconfirmed_files_are_left_out_not_trusted(tmp_path):
    eval_data = labelled_set(tmp_path, [("receipt", "tuning"), ("photo", "tuning")])
    rows = common.read_csv(eval_data / "labels" / "labels.csv")
    rows[1]["confirmed_label"] = ""
    common.write_csv(eval_data / "labels" / "labels.csv", common.LABEL_COLUMNS, rows)
    kept, unreviewed = evaluate.labelled_rows(eval_data, "tuning")
    assert len(kept) == 1 and unreviewed == 1


def test_a_guess_accepted_unseen_does_not_count_in_the_final_check_half(tmp_path):
    eval_data = labelled_set(tmp_path, [("photo", "final"), ("photo", "final")])
    rows = common.read_csv(eval_data / "labels" / "labels.csv")
    rows[0]["reviewed"] = "no"
    common.write_csv(eval_data / "labels" / "labels.csv", common.LABEL_COLUMNS, rows)
    kept, unreviewed = evaluate.labelled_rows(eval_data, "final")
    assert len(kept) == 1 and unreviewed == 1


def test_the_final_check_half_runs_once_per_candidate(tmp_path, capsys):
    eval_data = labelled_set(tmp_path, [("photo", "final")])
    argv = ["--candidate", "rules", "--half", "final", "--eval-data", str(eval_data)]
    evaluate.main(argv)
    assert json.loads((eval_data / "results" / "rules_final_summary.json").read_text())["files"] == 1
    with pytest.raises(SystemExit, match="already had its one run"):
        evaluate.main(argv)


def test_installed_size_leaves_out_the_base_install():
    assert evaluate.installed_megabytes(["pillow"]) == 0.0
    assert evaluate.installed_megabytes(["pytest"]) > 0.0
    assert evaluate.installed_megabytes(["no-such-package-xyz"]) == 0.0


# --- rules -----------------------------------------------------------------

def test_the_first_rule_that_applies_decides_and_no_rule_means_undecided():
    flat = rules.Rule("mostly flat colour: screenshot", "screenshot",
                      lambda f: f["flat_share"] > 0.3, confidence=0.97)
    wide = rules.Rule("very wide: graphic", "meme-or-graphic", lambda f: f["aspect"] > 3)
    assert rules.decide([flat, wide], {"flat_share": 0.5, "aspect": 4})[:2] == ("screenshot", 0.97)
    assert rules.decide([flat, wide], {"flat_share": 0.1, "aspect": 4})[:2] == ("meme-or-graphic", 1.0)
    assert rules.decide([flat, wide], {"flat_share": 0.1, "aspect": 1})[:2] == (None, 0.0)


def test_a_rule_can_say_only_what_a_file_is_not():
    not_shot = rules.Rule("has a camera make: not a screenshot", None,
                          lambda f: f["has_make"] == "yes", rules_out="screenshot")
    flat = rules.Rule("mostly flat colour: screenshot", "screenshot", lambda f: f["flat_share"] > 0.3)
    assert rules.decide([not_shot, flat], {"has_make": "yes", "flat_share": 0.9})[0] is None
    assert rules.decide([not_shot, flat], {"has_make": "no", "flat_share": 0.9})[0] == "screenshot"


def test_each_rule_is_measured_alone():
    rule = rules.Rule("wide", "receipt", lambda f: f["aspect"] > 2)
    facts = [{"id": "a", "aspect": 3}, {"id": "b", "aspect": 3}, {"id": "c", "aspect": 1},
             {"id": "d", "aspect": 3}]           # d has no confirmed label and is ignored
    report = rules.measure_each([rule], facts, {"a": "receipt", "b": "photo", "c": "receipt"})
    assert report[0]["decides"] == 2 and report[0]["right"] == 1
    assert report[0]["precision"] == 0.5 and report[0]["recall"] == 0.5


def test_the_rules_candidate_plugs_into_the_harness(tmp_path):
    eval_data = labelled_set(tmp_path, [("photo", "tuning"), ("photo", "tuning")])
    candidate = rules.RulesCandidate(
        [rules.Rule("in a folder called album: photo", "photo",
                    lambda f: f["folder_depth"] == 1, confidence=0.96)], name="one-rule")
    candidate.configure(eval_data)
    rows, _ = evaluate.labelled_rows(eval_data, "tuning")
    totals, summary, mistakes = evaluate.evaluate(candidate, rows, "tuning")
    assert summary["left_undecided"] == 0 and mistakes == []
    assert summary["at_step5_precision"]["photo"]["recall"] == 1.0


# --- fact review -----------------------------------------------------------

def test_ranking_score_runs_from_no_separation_to_perfect():
    assert fact_review.ranking_score([5, 6, 7], [1, 2, 3]) == 1.0
    assert fact_review.ranking_score([1, 2, 3], [5, 6, 7]) == 0.0
    assert fact_review.ranking_score([1, 2], [1, 2]) == 0.5


def test_best_cut_on_a_number_respects_the_precision_bar():
    mine, others = [0.8, 0.9, 0.95, 0.2], [0.1, 0.15, 0.3, 0.85]
    text, precision, recall = fact_review.best_number_cut(mine, others, min_precision=0.95)
    assert (text, precision, recall) == ("at least 0.9", 1.0, 0.5)
    assert fact_review.best_number_cut([0.5], [0.5], min_precision=0.95) == (None, None, 0.0)


def test_best_cut_on_a_word_collects_the_values_that_are_precise_enough():
    mine, others = ["png", "png", "webp", "jpg"], ["jpg", "jpg", "jpg"]
    text, precision, recall = fact_review.best_value_cut(mine, others)
    assert text == "is png or webp" and precision == 1.0 and recall == 0.75


def test_verdicts():
    assert fact_review.verdict(0.97, 0.7, 0.9) == "clean"
    assert fact_review.verdict(0.97, 0.2, 0.6) == "partly"
    assert fact_review.verdict(None, 0.0, 0.85) == "partly"     # leans, but no precise cut
    assert fact_review.verdict(None, 0.0, 0.55) == "no"
