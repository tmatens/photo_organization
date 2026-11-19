#!/usr/bin/env python3
"""
label_local.py: first-guess labels from a model on this computer.

Step 1 of docs/categorization-plan.md, for when the sampled photos may not
be sent to a hosted model. Nothing is uploaded: a small CLIP model (see
clip_local.py) runs here on the CPU. Its model files are downloaded once.

It mirrors the two passes of label_first_guess.py:

  --pass 1   Works out the model's numbers for every sampled file, sorts
             the files into groups of similar-looking ones, and writes a
             page with a thumbnail grid per group, largest first, so a
             person can see what is in the library and settle the list of
             labels. This model cannot describe a picture in words, so the
             groups stand in for the hosted model's free descriptions. Each
             group shows which starting labels the model would give.
  --pass 2   Labels every file against the settled list in
             eval_data/labels/categories.json and writes labels.csv for
             review.py.

Each label in categories.json needs "descriptions": a few short sentences
of the kind "a photo of a till receipt" that the model scores pictures
against.

Because this same model is also candidate 2 of the plan, its score will
read a little high: reviewers tend to accept a suggestion. That it made the
first guesses is recorded in eval_data/labels/first_guess.json.

Usage:
  python experiments/label_local.py --pass 1
  python experiments/label_local.py --pass 2
"""
import argparse
import html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip_local  # noqa: E402
import common  # noqa: E402
import label_first_guess  # noqa: E402

PASS1_COLUMNS = ["id", "group", "label", "confidence"]


def starting_categories():
    """The starting list, with the descriptions this model scores against."""
    categories = label_first_guess.starting_categories()
    for entry in categories["labels"]:
        entry["descriptions"] = clip_local.STARTING_DESCRIPTIONS[entry["label"]]
    return categories


def image_vectors(eval_data, clip, rows):
    """The model's numbers for every sampled file, worked out once and kept
    in eval_data/embeddings/ so a second run is instant."""
    import numpy as np
    cache = common.inside(eval_data, "embeddings", clip_local.MODEL["name"] + ".npz")
    ids = [r["id"] for r in rows]
    if cache.exists():
        saved = np.load(cache)
        if list(saved["ids"]) == ids:
            return saved["vectors"]
    vectors = clip.embed_images([str(common.sample_file(eval_data, r)) for r in rows])
    cache.parent.mkdir(parents=True, exist_ok=True)
    # numpy adds .npz to a name that lacks it, so the temporary name keeps it.
    tmp = cache.with_name("partial-" + cache.name)
    np.savez(tmp, ids=np.array(ids), vectors=vectors)
    os.replace(tmp, cache)
    return vectors


def guess(clip, vectors, categories):
    """[(label, confidence)] for every row of vectors."""
    texts, labels_of = clip_local.descriptions_from(categories)
    labels, share_rows = clip_local.shares(vectors, clip.embed_texts(texts), labels_of)
    return clip_local.best_labels(share_rows, labels)


def tally(rows):
    """[(group, [rows])], largest group first."""
    groups = {}
    for row in rows:
        groups.setdefault(int(row["group"]), []).append(row)
    return sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))


def write_tally_page(eval_data, rows, sample):
    parts = ["<!doctype html><meta charset='utf-8'><title>What is in the sample</title><style>"
             "body{font:14px system-ui;margin:24px}img{height:150px;margin:2px;border-radius:3px}"
             "h2{margin-top:32px}small{color:#666;font-weight:400}</style>"
             "<h1>What is in the sample</h1><p>Groups of similar-looking files, largest first, "
             "with the starting labels the local model would give them. Hover over a picture for "
             "its guess. A group that is clearly one kind of thing, and is not on the list, is a "
             "label to consider.</p>"]
    print("%5s  %s" % ("files", "starting labels the model gave"))
    for number, (group, members) in enumerate(tally(rows), 1):
        labels = {}
        for row in members:
            labels[row["label"]] = labels.get(row["label"], 0) + 1
        given = ", ".join("%s %d" % item for item in sorted(labels.items(), key=lambda i: -i[1]))
        print("%5d  group %d: %s" % (len(members), number, given))
        parts.append("<h2>Group %d <small>%d files: %s</small></h2>"
                     % (number, len(members), html.escape(given)))
        for row in sorted(members, key=lambda r: r["label"]):
            if common.make_thumbnail(eval_data, sample[row["id"]]):
                parts.append("<img loading='lazy' src='../thumbs/%s.jpg' title='%s %s'>"
                             % (row["id"], html.escape(row["label"], quote=True), row["confidence"]))
    page = common.inside(eval_data, "labels", "local_pass1_tally.html")
    page.write_text("".join(parts), encoding="utf-8")
    return page


def run_pass1(args):
    eval_data = args.eval_data
    rows = common.load_sample(eval_data)
    clip = clip_local.Clip(eval_data)
    vectors = image_vectors(eval_data, clip, rows)
    guesses = guess(clip, vectors, starting_categories())
    seed = json.loads(common.inside(eval_data, "sample_info.json").read_text(encoding="utf-8"))["seed"]
    groups = clip_local.group_similar(vectors, args.groups, seed=seed)
    out = [{"id": r["id"], "group": g, "label": label, "confidence": "%.3f" % confidence}
           for r, g, (label, confidence) in zip(rows, groups, guesses)]
    common.write_csv(common.inside(eval_data, "labels", "local_pass1.csv"), PASS1_COLUMNS, out)
    page = write_tally_page(eval_data, out, {r["id"]: r for r in rows})
    categories = common.inside(eval_data, "labels", "categories.json")
    if not categories.exists():
        categories.write_text(json.dumps(starting_categories(), indent=2), encoding="utf-8")
    print("Thumbnail grids: %s" % page)
    print('Settle the list of labels in %s and set "settled": true, then run --pass 2.' % categories)


def run_pass2(args):
    eval_data = args.eval_data
    categories = label_first_guess.load_categories(eval_data, 2)
    rows = common.load_sample(eval_data)
    clip = clip_local.Clip(eval_data)
    guesses = guess(clip, image_vectors(eval_data, clip, rows), categories)
    answers = {r["id"]: {"label": label, "error": ""} for r, (label, _c) in zip(rows, guesses)}
    common.inside(eval_data, "labels", "first_guess.json").write_text(json.dumps({
        "first_guess_by": clip_local.ClipZeroShot.name,
        "note": "A local candidate made the first guesses, so its own score reads a little high.",
    }, indent=2), encoding="utf-8")
    label_first_guess.write_labels(eval_data, answers)
    counts = {}
    for label, _c in guesses:
        counts[label] = counts.get(label, 0) + 1
    for label, count in sorted(counts.items(), key=lambda item: -item[1]):
        print("  %5d guessed as %s" % (count, label))


def main(argv=None):
    p = argparse.ArgumentParser(description="First-guess labels from a model on this computer. Uploads nothing.")
    p.add_argument("--pass", dest="pass_number", type=int, choices=(1, 2), required=True,
                   help="1: group similar files to settle the list. 2: label against the settled list.")
    p.add_argument("--groups", type=int, default=30,
                   help="Pass 1: how many groups of similar files to make.")
    p.add_argument("--eval-data", default=str(common.DEFAULT_EVAL_DATA))
    args = p.parse_args(argv)
    if not common.load_sample(args.eval_data):
        sys.exit("No sample yet. Run sample.py first.")
    (run_pass1 if args.pass_number == 1 else run_pass2)(args)


if __name__ == "__main__":
    main()
