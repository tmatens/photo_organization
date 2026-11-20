#!/usr/bin/env python3
"""
clip_examples.py: label a picture by the labelled pictures it looks most like.

Candidate 4 of docs/categorization-plan.md. It uses the same small model as
clip_local.py but no descriptions. Each picture is compared with the
confirmed pictures of the tuning half, and the labels of the few most
similar ones vote. This is the sort_screenshots.py idea with a model behind
it: show it some examples and it finds the rest.

Nothing is trained. The examples are the confirmed labels of the tuning
half, so on that half every picture is judged without itself among the
examples; otherwise each would simply find itself. On the final-check half
all tuning examples are used.

Usage:
  python experiments/evaluate.py --candidate clip_examples --field shows --half tuning
  python experiments/evaluate.py --candidate clip_examples:SHOWS_20 --field shows --half tuning
"""
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip_local  # noqa: E402
import common  # noqa: E402

NEIGHBOURS = 5      # how many of the most similar examples vote


def vote(similarities, example_labels, labels, neighbours=NEIGHBOURS):
    """Shares per label for one picture, adding up to 1.

    similarities[i] is how alike the picture is to example i (-1 to 1) and
    example_labels[i] is that example's label. The `neighbours` most
    similar examples vote, each with its similarity as weight, so a close
    match counts for more than a distant one."""
    nearest = sorted(range(len(example_labels)), key=lambda i: -similarities[i])[:neighbours]
    weight = {label: 0.0 for label in labels}
    for i in nearest:
        weight[example_labels[i]] += max(float(similarities[i]), 0.0)
    total = sum(weight.values())
    if total <= 0:
        return [1.0 / len(labels)] * len(labels)
    return [weight[label] / total for label in labels]


def pick_examples(rows, per_label=None, seed=0):
    """The rows to use as examples: all of them, or at most per_label of
    each label, picked at random but the same ones every time."""
    if per_label is None:
        return list(rows)
    by_label = {}
    for row in sorted(rows, key=lambda r: r["id"]):
        by_label.setdefault(row["true_label"], []).append(row)
    out = []
    for label in sorted(by_label):
        mine = by_label[label]
        random.Random(seed).shuffle(mine)
        out += mine[:per_label]
    return out


class ClipExamples:
    """The candidate. per_label limits how many examples of each label are
    used, to measure how few are enough."""

    def __init__(self, field, per_label=None):
        self.field = field
        self.per_label = per_label
        self.name = "%s-examples%s" % (clip_local.MODEL["name"],
                                       "" if per_label is None else "-%d" % per_label)
        self.eval_data = common.DEFAULT_EVAL_DATA
        self.loaded = None

    def configure(self, eval_data):
        self.eval_data = eval_data

    def load(self):
        import evaluate
        rows, _unreviewed = evaluate.labelled_rows(self.eval_data, "tuning", self.field)
        examples = pick_examples(rows, self.per_label)
        clip = clip_local.Clip(self.eval_data)
        vectors = clip.embed_images([r["path"] for r in examples])
        labels = list(dict.fromkeys(r["true_label"] for r in sorted(rows, key=lambda r: r["true_label"])))
        self.loaded = (clip, vectors, [r["true_label"] for r in examples],
                       [str(Path(r["path"]).resolve()) for r in examples], labels)

    def scores(self, paths):
        """(labels, one row of shares per path)."""
        import numpy as np
        if self.loaded is None:
            self.load()
        clip, vectors, example_labels, example_paths, labels = self.loaded
        similarities = clip.embed_images(list(paths)) @ vectors.T
        rows = []
        for path, row in zip(paths, similarities):
            row = row.copy()
            me = str(Path(path).resolve())
            for i, example in enumerate(example_paths):
                if example == me:
                    row[i] = -1.0       # a picture is never its own example
            rows.append(vote(row, example_labels, labels))
        return labels, np.array(rows)

    def predict(self, paths):
        labels, share_rows = self.scores(paths)
        return clip_local.best_labels(share_rows, labels)


MADE = ClipExamples("made")
SHOWS = ClipExamples("shows")
SHOWS_5 = ClipExamples("shows", per_label=5)
SHOWS_20 = ClipExamples("shows", per_label=20)
