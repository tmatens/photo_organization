#!/usr/bin/env python3
"""
evaluate.py: measure one candidate against the labelled set.

Step 2 of docs/categorization-plan.md. A candidate is anything that labels
photos: a set of rules, a model, or both. Every candidate plugs in the same
way. It is an object with

    name                a short name, used in the result file names
    predict(paths)      given a list of image paths, returns one
                        (label, confidence) pair per path, in the same order

where confidence is a number from 0 to 1. A candidate that cannot decide
about a file returns (None, 0.0) for it; rules do this for most files.

For each candidate this reports, per label and at several confidence
thresholds, precision (of the files given this label, how many were right)
and recall (of the files that truly have this label, how many were found);
a confusion table; images per second including the time to open each file;
and the size of anything extra the candidate needs installed.

Two files are written into eval_data/results/: totals, and a per-file list
of mistakes for a person to read. The mistakes name real files and stay in
eval_data. Only totals go into the plan's results table.

The final-check half is run once per candidate. A second run is refused.

Usage:
  python experiments/evaluate.py --candidate rules --half tuning
  python experiments/evaluate.py --candidate rules --half final
"""
import argparse
import importlib
import importlib.metadata
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

THRESHOLDS = (0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99)
UNDECIDED = "(undecided)"

# The step 5 bars from the plan. A label ships only if a candidate clears
# all of them on the final-check half at one fixed threshold.
MIN_PRECISION = 0.95
MIN_RECALL = 0.60
MIN_IMAGES_PER_SECOND = 5.0
MAX_EXTRA_INSTALL_MB = 500.0

TOTALS_COLUMNS = ["candidate", "half", "label", "threshold", "actual", "labelled",
                  "correct", "precision", "recall"]
MISTAKE_COLUMNS = ["id", "rel_path", "true_label", "predicted_label", "confidence"]


def check_predictions(predictions, count):
    """Stop early, with a clear message, if a candidate breaks the interface."""
    if len(predictions) != count:
        raise ValueError("candidate returned %d answers for %d files" % (len(predictions), count))
    for label, confidence in predictions:
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1, got %r" % (confidence,))
        if label is None and confidence != 0.0:
            raise ValueError("an undecided answer must have confidence 0")


def decided(prediction, threshold):
    """The label a candidate commits to at this threshold, or None."""
    label, confidence = prediction
    return label if label is not None and confidence >= threshold else None


def score(truth, predictions, labels, thresholds=THRESHOLDS):
    """Precision and recall per label at each threshold.

    Returns one dict per (label, threshold). precision is None when the
    candidate gave nothing that label; recall is None when no file truly
    has it. Neither is reported as 0 or 1 in that case, because both would
    be made-up numbers."""
    rows = []
    for label in labels:
        actual = sum(1 for t in truth if t == label)
        for threshold in thresholds:
            given = [decided(p, threshold) == label for p in predictions]
            labelled = sum(given)
            correct = sum(1 for g, t in zip(given, truth) if g and t == label)
            rows.append({
                "label": label, "threshold": threshold, "actual": actual,
                "labelled": labelled, "correct": correct,
                "precision": correct / labelled if labelled else None,
                "recall": correct / actual if actual else None,
            })
    return rows


def confusion(truth, predictions, threshold=0.0):
    """{(true label, label given): count}. Files the candidate left alone
    are counted under UNDECIDED."""
    table = {}
    for t, p in zip(truth, predictions):
        key = (t, decided(p, threshold) or UNDECIDED)
        table[key] = table.get(key, 0) + 1
    return table


def best_at_precision(score_rows, label, min_precision=MIN_PRECISION):
    """The row for this label with the highest recall among the thresholds
    that reach min_precision, or None if no threshold does. This is the
    'share decided at the step 5 precision' of step 2b."""
    good = [r for r in score_rows if r["label"] == label and r["precision"] is not None
            and r["precision"] >= min_precision and r["recall"] is not None]
    return max(good, key=lambda r: (r["recall"], -r["threshold"])) if good else None


def timed_predict(candidate, paths):
    """(predictions, images per second). The clock covers everything the
    candidate does, including opening and shrinking each image."""
    start = time.perf_counter()
    predictions = list(candidate.predict(paths))
    elapsed = time.perf_counter() - start
    check_predictions(predictions, len(paths))
    return predictions, (len(paths) / elapsed if elapsed > 0 else float("inf"))


def installed_megabytes(packages, base=("pillow",)):
    """Size on disk of the named pip packages and everything they pull in,
    leaving out what the base install already has. This is the 'extra
    install' a user would pay for a candidate."""
    seen, queue, total = set(), [p.lower() for p in packages], 0
    skip = {b.lower() for b in base}
    while queue:
        name = re.sub(r"[-_.]+", "-", queue.pop())
        if name in seen or name in skip:
            continue
        seen.add(name)
        try:
            dist = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        for f in dist.files or []:
            try:
                total += dist.locate_file(f).stat().st_size
            except OSError:
                pass
        for requirement in dist.requires or []:
            if "extra ==" in requirement:
                continue        # an optional extra, not installed by default
            queue.append(re.match(r"[A-Za-z0-9._-]+", requirement).group(0).lower())
    return total / 1e6


def load_candidate(spec):
    """'module' or 'module:attribute'. The module is looked up in this
    folder; the attribute defaults to CANDIDATE."""
    module_name, _, attribute = spec.partition(":")
    return getattr(importlib.import_module(module_name), attribute or "CANDIDATE")


def labelled_rows(eval_data, half):
    """The sampled files of one half that a person has given a label, each
    with its path on disk and that label. Unreviewed files are left out and
    counted, never treated as if the first guess were right."""
    # In the final-check half only labels a person looked at count; a guess
    # accepted unseen is not an answer key.
    confirmed = {r["id"]: r["confirmed_label"] for r in
                 common.read_csv(common.inside(eval_data, "labels", "labels.csv"))
                 if r.get("confirmed_label") and (half == "tuning" or r.get("reviewed") == "yes")}
    rows, unreviewed = [], 0
    for row in common.load_sample(eval_data):
        if row["half"] != half:
            continue
        if row["id"] not in confirmed:
            unreviewed += 1
            continue
        rows.append(dict(row, true_label=confirmed[row["id"]],
                         path=str(common.sample_file(eval_data, row))))
    return rows, unreviewed


def evaluate(candidate, rows, half, labels=None, packages=(), model_files=()):
    """Run one candidate over the labelled rows. Returns (totals, summary,
    mistakes): the three things written to disk."""
    truth = [r["true_label"] for r in rows]
    labels = labels or sorted(set(truth))
    predictions, speed = timed_predict(candidate, [r["path"] for r in rows])
    totals = [dict(r, candidate=candidate.name, half=half)
              for r in score(truth, predictions, labels)]
    summary = {
        "candidate": candidate.name, "half": half, "files": len(rows),
        "images_per_second": round(speed, 2),
        "extra_install_mb": round(installed_megabytes(packages), 1),
        "model_download_mb": round(sum(Path(f).stat().st_size for f in model_files) / 1e6, 1),
        "left_undecided": sum(1 for p in predictions if p[0] is None),
        "confusion": [{"true_label": t, "labelled": p, "files": n}
                      for (t, p), n in sorted(confusion(truth, predictions).items())],
        "at_step5_precision": {
            label: best_at_precision(totals, label) for label in labels},
    }
    mistakes = [{"id": r["id"], "rel_path": r["rel_path"], "true_label": r["true_label"],
                 "predicted_label": p[0], "confidence": "%.3f" % p[1]}
                for r, p in zip(rows, predictions) if p[0] is not None and p[0] != r["true_label"]]
    return totals, summary, mistakes


def percent(value):
    return "  n/a" if value is None else "%4.0f%%" % (100 * value)


def print_report(totals, summary):
    print("%s on the %s half: %d files, %.1f images/s, %d left undecided"
          % (summary["candidate"], summary["half"], summary["files"],
             summary["images_per_second"], summary["left_undecided"]))
    print("  %-18s %6s  %s" % ("label", "files", "at the %d%% precision bar" % (100 * MIN_PRECISION)))
    for label, best in summary["at_step5_precision"].items():
        actual = next(r["actual"] for r in totals if r["label"] == label)
        if best is None:
            print("  %-18s %6d  never reaches it" % (label, actual))
        else:
            print("  %-18s %6d  finds %s of them, %s right (threshold %.2f)"
                  % (label, actual, percent(best["recall"]).strip(),
                     percent(best["precision"]).strip(), best["threshold"]))


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Measure one candidate against the labelled set.")
    p.add_argument("--candidate", required=True,
                   help="Module in experiments/ holding the candidate, as module or module:attribute.")
    p.add_argument("--half", choices=("tuning", "final"), default="tuning",
                   help="Which half to measure on. The final-check half runs once per candidate.")
    p.add_argument("--packages", nargs="*", default=[],
                   help="pip packages this candidate needs beyond Pillow, to measure their size.")
    p.add_argument("--model-files", nargs="*", default=[],
                   help="Model files this candidate downloads, to measure their size.")
    p.add_argument("--eval-data", default=str(common.DEFAULT_EVAL_DATA))
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    candidate = load_candidate(args.candidate)
    if hasattr(candidate, "configure"):
        candidate.configure(args.eval_data)
    stem = "%s_%s" % (re.sub(r"[^A-Za-z0-9_-]+", "-", candidate.name), args.half)
    summary_file = common.inside(args.eval_data, "results", stem + "_summary.json")
    if args.half == "final" and summary_file.exists():
        sys.exit("%s has already had its one run on the final-check half." % candidate.name)

    rows, unreviewed = labelled_rows(args.eval_data, args.half)
    if not rows:
        sys.exit("No confirmed labels for the %s half yet. Run review.py first." % args.half)
    if unreviewed:
        print("Note: %d files in this half have no confirmed label and are left out." % unreviewed)
        if args.half == "final":
            sys.exit("Every file in the final-check half must be reviewed before it is used.")

    totals, summary, mistakes = evaluate(candidate, rows, args.half,
                                         packages=args.packages, model_files=args.model_files)
    common.write_csv(common.inside(args.eval_data, "results", stem + "_totals.csv"),
                     TOTALS_COLUMNS, totals)
    common.write_csv(common.inside(args.eval_data, "results", stem + "_mistakes.csv"),
                     MISTAKE_COLUMNS, mistakes)
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print_report(totals, summary)
    print("Totals, summary and mistakes are in %s" % summary_file.parent)


if __name__ == "__main__":
    main()
