"""
rules.py: the rules-only candidate.

Step 2b and candidate 1 of docs/categorization-plan.md. A rule is one
sentence a person can read, a label, and a test on the facts from facts.py.
Rules are tried in order and the first one whose test passes decides the
file. A file no rule matches is left undecided.

A rule may also say only what a file is NOT (label None, with `rules_out`
set): it decides nothing by itself, but later rules for that label are
skipped for the file.

The rules below are found by reading eval_data/facts/review.html for the
tuning half, and each is measured with evaluate.py before it stays. Until
the labelled set exists the list is empty, and this candidate leaves every
file undecided.

There is one list of rules per field: how the file was made, and what it
shows.

Measure all rules of a field together, then each one alone:
  python experiments/evaluate.py --candidate rules --field made --half tuning
  python experiments/rules.py --field made --half tuning
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import evaluate  # noqa: E402
import facts as facts_module  # noqa: E402


class Rule:
    """One readable rule. `test` takes the dict of facts for a file and
    returns True when the rule applies. `confidence` is how often the rule
    was right on the tuning half, so thresholds mean the same thing for
    rules as for models."""

    def __init__(self, sentence, label, test, confidence=1.0, rules_out=None):
        self.sentence = sentence
        self.label = label
        self.test = test
        self.confidence = confidence
        self.rules_out = rules_out


def decide(rules, file_facts):
    """(label, confidence, rule) for one file: the first rule that applies,
    or (None, 0.0, None) when none does."""
    ruled_out = set()
    for rule in rules:
        if rule.label in ruled_out or not rule.test(file_facts):
            continue
        if rule.label is None:
            ruled_out.add(rule.rules_out)
            continue
        return rule.label, rule.confidence, rule
    return None, 0.0, None


class RulesCandidate:
    """Plugs a list of rules into evaluate.py."""

    def __init__(self, rules, name="rules", field=None):
        self.rules = rules
        self.name = name
        if field is not None:
            self.field = field
        self.files_root = None

    def configure(self, eval_data):
        self.files_root = common.inside(eval_data, "files")

    def folder_of(self, path):
        """The folder a sampled file originally came from: its path under
        eval_data/files/<source>/, without the file name."""
        if self.files_root is None:
            return ""
        try:
            parts = Path(path).resolve().relative_to(self.files_root).parts
        except ValueError:
            return ""
        return "/".join(parts[1:-1])

    def predict(self, paths):
        answers = []
        for path in paths:
            try:
                file_facts = facts_module.compute(path, self.folder_of(path))
            except Exception:
                answers.append((None, 0.0))
                continue
            label, confidence, _rule = decide(self.rules, file_facts)
            answers.append((label, confidence))
        return answers


# Filled in from the tuning-half review. Each entry is measured before it
# is kept, and its totals go in the plan.
RULES = {"made": [], "shows": []}

MADE = RulesCandidate(RULES["made"], field="made")
SHOWS = RulesCandidate(RULES["shows"], field="shows")


def measure_each(rules, fact_rows, truth_by_id):
    """How many files each rule decides by itself and how often it is right.
    Returns one dict per rule that gives a label."""
    report = []
    for rule in rules:
        if rule.label is None:
            continue
        hits = [row for row in fact_rows if row["id"] in truth_by_id and rule.test(row)]
        right = sum(1 for row in hits if truth_by_id[row["id"]] == rule.label)
        actual = sum(1 for label in truth_by_id.values() if label == rule.label)
        report.append({"sentence": rule.sentence, "label": rule.label, "decides": len(hits),
                       "right": right,
                       "precision": right / len(hits) if hits else None,
                       "recall": right / actual if actual else None})
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description="Measure each rule alone on one half.")
    p.add_argument("--field", choices=common.FIELDS, required=True,
                   help="Which question's rules: how the file was made, or what it shows.")
    p.add_argument("--half", choices=("tuning",), default="tuning",
                   help="Single rules are only ever looked at on the tuning half.")
    p.add_argument("--eval-data", default=str(common.DEFAULT_EVAL_DATA))
    args = p.parse_args(argv)
    rows, _unreviewed = evaluate.labelled_rows(args.eval_data, args.half, args.field)
    truth = {r["id"]: r["true_label"] for r in rows}
    report = measure_each(RULES[args.field], facts_module.load(args.eval_data, args.half), truth)
    if not report:
        print("No rules yet.")
    for line in report:
        print("%-18s decides %4d, %s right, finds %s  | %s"
              % (line["label"], line["decides"], evaluate.percent(line["precision"]).strip(),
                 evaluate.percent(line["recall"]).strip(), line["sentence"]))


if __name__ == "__main__":
    main()
