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
    common.write_csv(eval_data / "labels" / "shows" / "labels.csv", common.LABEL_COLUMNS, confirmed)
    return eval_data


def test_evaluate_writes_totals_and_a_mistakes_list_inside_eval_data(tmp_path):
    eval_data = labelled_set(tmp_path, [("receipt", "tuning"), ("photo", "tuning"),
                                        ("photo", "final")])
    rows, unreviewed = evaluate.labelled_rows(eval_data, "tuning", "shows")
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
    rows = common.read_csv(eval_data / "labels" / "shows" / "labels.csv")
    rows[1]["confirmed_label"] = ""
    common.write_csv(eval_data / "labels" / "shows" / "labels.csv", common.LABEL_COLUMNS, rows)
    kept, unreviewed = evaluate.labelled_rows(eval_data, "tuning", "shows")
    assert len(kept) == 1 and unreviewed == 1


def test_a_guess_accepted_unseen_does_not_count_in_the_final_check_half(tmp_path):
    eval_data = labelled_set(tmp_path, [("photo", "final"), ("photo", "final")])
    rows = common.read_csv(eval_data / "labels" / "shows" / "labels.csv")
    rows[0]["reviewed"] = "no"
    common.write_csv(eval_data / "labels" / "shows" / "labels.csv", common.LABEL_COLUMNS, rows)
    kept, unreviewed = evaluate.labelled_rows(eval_data, "final", "shows")
    assert len(kept) == 1 and unreviewed == 1


def test_the_final_check_half_runs_once_per_candidate(tmp_path, capsys):
    eval_data = labelled_set(tmp_path, [("photo", "final")])
    argv = ["--candidate", "rules", "--field", "shows", "--half", "final", "--eval-data", str(eval_data)]
    evaluate.main(argv)
    assert json.loads((eval_data / "results" / "shows" / "rules_final_summary.json").read_text())["files"] == 1
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
    rows, _ = evaluate.labelled_rows(eval_data, "tuning", "shows")
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


def test_a_label_with_too_few_files_gets_no_verdict_however_good_a_cut_looks():
    columns = fact_review.facts_module.FACT_COLUMNS[1:]
    facts = [dict({c: 1.0 for c in columns}, id="a"), dict({c: 0.0 for c in columns}, id="b")]
    for c in columns:
        if not fact_review.facts_module.is_number(c):
            facts[0][c], facts[1][c] = "yes", "no"
    results = fact_review.review(facts, {"a": "receipt", "b": "photo"})
    assert results and all(r["verdict"] == "too few" for r in results)
    assert fact_review.verdict(1.0, 1.0, 1.0, examples=39) == "too few"
    assert fact_review.verdict(1.0, 1.0, 1.0, examples=40) == "clean"


def test_a_candidate_is_picked_for_the_field_and_refused_for_the_other(tmp_path):
    assert evaluate.load_candidate("rules", "made") is rules.MADE
    assert evaluate.load_candidate("rules", "shows") is rules.SHOWS
    assert rules.MADE.rules is rules.RULES["made"]
    with pytest.raises(SystemExit, match="answers the 'made' question"):
        evaluate.load_candidate("rules:MADE", "shows")
    with pytest.raises(ValueError):
        common.field_file(tmp_path / "eval_data", "colour", "labels.csv")


def test_each_field_keeps_its_own_labels_and_results(tmp_path, capsys):
    eval_data = labelled_set(tmp_path, [("receipt", "tuning"), ("photo", "tuning")])
    made = [dict(r, guessed_label="screen-capture", confirmed_label="screen-capture")
            for r in common.read_csv(eval_data / "labels" / "shows" / "labels.csv")]
    common.write_csv(eval_data / "labels" / "made" / "labels.csv", common.LABEL_COLUMNS, made)
    assert {r["true_label"] for r in evaluate.labelled_rows(eval_data, "tuning", "made")[0]} == \
        {"screen-capture"}
    assert {r["true_label"] for r in evaluate.labelled_rows(eval_data, "tuning", "shows")[0]} == \
        {"receipt", "photo"}
    evaluate.main(["--candidate", "rules", "--field", "made", "--eval-data", str(eval_data)])
    assert (eval_data / "results" / "made" / "rules_tuning_summary.json").is_file()
    assert not (eval_data / "results" / "shows").exists()


# --- top-ups ---------------------------------------------------------------

def test_a_topped_up_label_counts_for_less_in_precision_but_not_in_recall():
    # Two receipts were drawn evenly and six were added, among 10 photos.
    truth = ["receipt"] * 8 + ["photo"] * 10
    topped_up = [False] * 2 + [True] * 6 + [False] * 10
    assert evaluate.weights(truth, topped_up) == [0.25] * 8 + [1.0] * 10
    # The candidate finds every receipt and calls one photo a receipt.
    answers = [("receipt", 0.9)] * 9 + [("photo", 0.9)] * 9
    plain = by(evaluate.score(truth, answers, ["receipt"]), "receipt", 0.5)
    fair = by(evaluate.score(truth, answers, ["receipt"], topped_up=topped_up), "receipt", 0.5)
    assert plain["precision"] == pytest.approx(8 / 9)
    assert fair["precision"] == pytest.approx(2 / 3)     # 2 real receipts to 1 mistake
    assert fair["recall"] == plain["recall"] == 1.0
    assert (fair["actual"], fair["topped_up"], fair["correct"], fair["labelled"]) == (8, 6, 8, 9)


def test_a_label_found_only_by_topping_up_counts_as_one_file():
    assert evaluate.weights(["receipt"] * 4 + ["photo"], [True] * 4 + [False]) == [0.25] * 4 + [1.0]


def test_the_best_cut_and_single_rules_use_the_same_weight():
    mine, others = [9, 9, 9, 9], [1, 1, 1, 9]
    assert fact_review.best_number_cut(mine, others, min_precision=0.8)[0] == "at least 9"
    assert fact_review.best_number_cut(mine, others, min_precision=0.8, weight=0.25)[0] is None
    assert fact_review.best_value_cut(["png"] * 4, ["png", "jpg"], min_precision=0.8)[0] == "is png"
    assert fact_review.best_value_cut(["png"] * 4, ["png", "jpg"], min_precision=0.8, weight=0.25)[0] is None
    truth = {"a": "receipt", "b": "receipt", "c": "receipt", "d": "receipt", "e": "photo"}
    rule = rules.Rule("every file is a receipt", "receipt", lambda row: True)
    report = rules.measure_each([rule], [{"id": i} for i in truth], truth, topped_up={"b", "c", "d"})
    assert report[0]["precision"] == pytest.approx(0.5) and report[0]["recall"] == 1.0


# --- examples and rules with a model ---------------------------------------

import clip_examples  # noqa: E402
import combined  # noqa: E402


def test_the_most_similar_examples_vote_and_a_closer_one_counts_for_more():
    labels = ["photo", "receipt"]
    examples = ["receipt", "receipt", "photo", "photo", "photo"]
    shares = clip_examples.vote([0.9, 0.8, 0.3, 0.2, 0.1], examples, labels, neighbours=3)
    assert shares[1] == pytest.approx(1.7 / 2.0) and sum(shares) == pytest.approx(1.0)
    assert clip_examples.vote([0.9, 0.8, 0.3, 0.2, 0.1], examples, labels, neighbours=5)[1] > 0.5
    # Nothing alike at all: no label is favoured.
    assert clip_examples.vote([-1.0, -1.0], ["photo", "receipt"], labels) == [0.5, 0.5]


def test_examples_can_be_limited_per_label_and_the_pick_is_repeatable():
    rows = [{"id": "s%02d" % i, "true_label": "photo" if i < 8 else "receipt"} for i in range(10)]
    picked = clip_examples.pick_examples(rows, per_label=3)
    assert sorted(r["true_label"] for r in picked) == ["photo"] * 3 + ["receipt"] * 2
    assert picked == clip_examples.pick_examples(list(reversed(rows)), per_label=3)
    assert len(clip_examples.pick_examples(rows)) == 10


def test_a_model_only_chooses_among_the_labels_the_rules_leave_possible():
    labels = ["text-thread", "photo", "thing"]
    assert combined.narrowed([0.5, 0.3, 0.2], labels, set()) == ("text-thread", 0.5)
    label, confidence = combined.narrowed([0.5, 0.3, 0.2], labels, {"text-thread"})
    assert label == "photo" and confidence == pytest.approx(0.6)
    assert combined.narrowed([0.5, 0.3, 0.2], labels, set(labels)) == (None, 0.0)


class FixedShares:
    """A model that gives every picture the same shares."""
    name = "fixed"

    def __init__(self, labels, shares):
        self.labels, self.shares = labels, shares

    def configure(self, eval_data):
        pass

    def scores(self, paths):
        return self.labels, [self.shares for _ in paths]


def test_a_sure_rule_decides_and_an_unsure_one_leaves_it_to_the_model(tmp_path):
    eval_data = labelled_set(tmp_path, [("photo", "tuning"), ("photo", "tuning")])
    rows, _ = evaluate.labelled_rows(eval_data, "tuning", "shows")
    model = FixedShares(["text-thread", "photo"], [0.6, 0.4])
    not_thread = rules.Rule("every file: not a text thread", None, lambda f: True,
                            rules_out="text-thread")
    assert rules.ruled_out([not_thread], {}) == {"text-thread"}
    sure = rules.Rule("every file is a receipt", "receipt", lambda f: True, confidence=0.99)
    unsure = rules.Rule("every file is a receipt", "receipt", lambda f: True, confidence=0.80)
    paths = [r["path"] for r in rows]
    for rule_list, expected in (([sure], "receipt"), ([unsure], "text-thread"),
                                ([not_thread, unsure], "photo"), ([], "text-thread")):
        candidate = combined.RulesThenModel(rule_list, model, "shows")
        candidate.configure(eval_data)
        assert [label for label, _ in candidate.predict(paths)] == [expected, expected]


def test_two_models_are_averaged_and_a_label_without_examples_is_switched_off():
    described = (["cart", "photo", "receipt"], [0.5, 0.25, 0.25])
    by_example = (["photo", "receipt"], [0.9, 0.1])
    labels, shares = combined.blend(described[1], described[0], by_example[1], by_example[0])
    assert labels == ["photo", "receipt"]            # nobody has an example of a cart
    assert shares == pytest.approx([(0.5 + 0.9) / 2, (0.5 + 0.1) / 2])
    assert sum(shares) == pytest.approx(1.0)
    both = combined.Blend(FixedShares(*described), FixedShares(*by_example), "shows")
    assert both.predict(["a.jpg"]) == [("photo", pytest.approx(0.7))]
