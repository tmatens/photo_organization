#!/usr/bin/env python3
"""
combined.py: rules first, then a model on what the rules leave open.

Candidate 5 of docs/categorization-plan.md, and the expected shape of
anything that ships with a model. For each file:

  1. If a rule gives a label and was right often enough on the tuning half
     (its confidence reaches SURE), that is the answer.
  2. Otherwise the model answers, but only among the labels the rules have
     not ruled out for this file. A file with a camera make, for instance,
     is never offered `text-thread`.

Usage:
  python experiments/evaluate.py --candidate combined --field shows --half tuning
  python experiments/evaluate.py --candidate combined:SHOWS_EXAMPLES --field shows --half tuning
  python experiments/evaluate.py --candidate combined:SHOWS_BLEND --field shows --half tuning

SHOWS_BLEND is descriptions and examples together, without rules: see Blend.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip_examples  # noqa: E402
import clip_local  # noqa: E402
import evaluate  # noqa: E402
import facts as facts_module  # noqa: E402
import rules as rules_module  # noqa: E402

SURE = evaluate.MIN_PRECISION      # a rule this reliable decides without the model


def narrowed(shares, labels, not_possible):
    """(label, confidence): the strongest label that is still possible,
    with its share of what is left after the ruled-out labels are dropped."""
    left = [(share, label) for share, label in zip(shares, labels) if label not in not_possible]
    total = sum(share for share, _ in left)
    if not left or total <= 0:
        return None, 0.0
    share, label = max(left)
    return label, float(share / total)


class RulesThenModel:
    def __init__(self, rule_list, model, field):
        self.rules = rule_list
        self.model = model
        self.field = field
        self.name = "rules+" + model.name
        self.inner = rules_module.RulesCandidate(rule_list, field=field)

    def use_model(self, model):
        """Switch the model behind the rules to another entry of
        clip_local.MODELS."""
        self.model.use_model(model)
        self.name = "rules+" + self.model.name

    def configure(self, eval_data):
        self.inner.configure(eval_data)
        self.model.configure(eval_data)

    def predict(self, paths):
        labels, share_rows = self.model.scores(paths)
        answers = []
        for path, shares in zip(paths, share_rows):
            try:
                file_facts = facts_module.compute(path, self.inner.folder_of(path))
            except Exception:
                answers.append(narrowed(shares, labels, set()))
                continue
            label, confidence, _rule = rules_module.decide(self.rules, file_facts)
            if label is not None and confidence >= SURE:
                answers.append((label, confidence))
            else:
                answers.append(narrowed(shares, labels,
                                        rules_module.ruled_out(self.rules, file_facts)))
        return answers


def blend(shares_a, labels_a, shares_b, labels_b):
    """(labels, shares): the average of two models' shares for one picture.

    Only labels that model B knows take part. For the examples model that
    means labels with at least one confirmed picture: a label nobody has an
    example of is switched off, because with descriptions alone an empty
    label still attracts files that belong elsewhere. Model A's shares are
    rescaled over the labels that remain, so both add up to 1."""
    total = sum(share for share, label in zip(shares_a, labels_a) if label in labels_b)
    a = {label: (share / total if total > 0 else 0.0)
         for share, label in zip(shares_a, labels_a) if label in labels_b}
    return list(labels_b), [(a.get(label, 0.0) + share) / 2 for share, label in zip(shares_b, labels_b)]


class Blend:
    """Descriptions and examples together: each picture gets the average of
    the two models' shares. Descriptions carry the labels with few
    examples; examples carry the ones with many."""

    def __init__(self, described, by_example, field):
        self.described = described
        self.by_example = by_example
        self.field = field
        self.name = "%s+%s" % (described.name, by_example.name.rsplit("-", 1)[-1])

    def use_model(self, model):
        self.described.use_model(model)
        self.by_example.use_model(model)
        self.name = "%s+%s" % (self.described.name, self.by_example.name.rsplit("-", 1)[-1])

    def configure(self, eval_data):
        self.described.configure(eval_data)
        self.by_example.configure(eval_data)

    def scores(self, paths):
        labels_a, rows_a = self.described.scores(paths)
        labels_b, rows_b = self.by_example.scores(paths)
        rows = [blend(a, labels_a, b, labels_b)[1] for a, b in zip(rows_a, rows_b)]
        return list(labels_b), rows

    def predict(self, paths):
        labels, rows = self.scores(paths)
        return [narrowed(row, labels, set()) for row in rows]


MADE = RulesThenModel(rules_module.RULES["made"], clip_local.ClipZeroShot("made"), "made")
SHOWS = RulesThenModel(rules_module.RULES["shows"], clip_local.ClipZeroShot("shows"), "shows")
MADE_EXAMPLES = RulesThenModel(rules_module.RULES["made"], clip_examples.ClipExamples("made"), "made")
SHOWS_EXAMPLES = RulesThenModel(rules_module.RULES["shows"], clip_examples.ClipExamples("shows"), "shows")
SHOWS_BLEND = Blend(clip_local.ClipZeroShot("shows"), clip_examples.ClipExamples("shows"), "shows")
MADE_BLEND = Blend(clip_local.ClipZeroShot("made"), clip_examples.ClipExamples("made"), "made")
SHOWS_RULES_BLEND = RulesThenModel(rules_module.RULES["shows"], SHOWS_BLEND, "shows")
