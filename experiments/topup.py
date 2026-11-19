#!/usr/bin/env python3
"""
topup.py: find more examples of a rare label and add them to the sample.

Step 1, point 4 of docs/categorization-plan.md. An evenly spread sample
shows that a rare kind of file exists but holds too few of them to measure
(fewer than 40). This script looks for more in the part of a source that
was NOT sampled. It works in three stages, and a person or another
labeller decides between the second and the third:

  fetch   Copy every file of one source that is not in the sample into
          eval_data/topup/pool/. The source is only read, exactly as
          sample.py reads it; its location is taken from the sample's own
          record, so it is not typed again.
  pick    Choose which files of the pool are worth looking at for the
          wanted labels, and list them in eval_data/topup/picks.csv. A
          file is picked when the local model (clip_local.py) gives the
          wanted labels at least a small share, or when a fact about the
          file matches (--also type=png). The facts are a second net: a
          top-up found by the model alone holds only the examples that
          model finds easy, and would flatter it when it is measured.
  add     Read the labels someone gave the picked files
          (eval_data/topup/answers.csv: id, made, shows) and add the files
          that really have a wanted label to the sample, shared equally
          between the tuning half and the final-check half. They join each
          field's labels.csv as first guesses, to be reviewed like any
          other file.

Added files are marked `top-up` in the sample's `drawn` column. They make
a label look more common than it is, so evaluate.py counts them at a
reduced weight when it works out precision.

Usage:
  python experiments/topup.py fetch --source undated
  python experiments/topup.py pick --field shows --label receipt --label text-messages --also type=png
  python experiments/topup.py add --field shows --label receipt --label text-messages
"""
import argparse
import json
import os
import random
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import facts as facts_module  # noqa: E402
import sample  # noqa: E402
from common import organize_photos  # noqa: E402

POOL_COLUMNS = ["id", "source", "rel_path"]
PICK_COLUMNS = ["id", "why", "model_label", "share"]
ANSWER_COLUMNS = ["id", "made", "shows"]
MIN_SHARE = 0.10        # picked when the wanted labels together reach this share


def pool_file(eval_data, row):
    """Where the copy of one not-yet-sampled file waits inside eval_data."""
    return common.inside(eval_data, "topup", "pool", row["source"], *row["rel_path"].split("/"))


def load_pool(eval_data):
    return common.read_csv(common.inside(eval_data, "topup", "pool.csv"))


def not_sampled(listing, drawn):
    """The photo files of a source that the sampler did not draw, in a
    fixed order."""
    drawn = set(drawn)
    return sorted(p for p in listing if sample.wanted(p) and p not in drawn)


def fetch(eval_data, source):
    """Copy the rest of one source into the pool. Returns the pool rows of
    that source. Running it again copies only what is still missing."""
    info = json.loads(common.inside(eval_data, "sample_info.json").read_text(encoding="utf-8"))
    if source not in info["sources"]:
        sys.exit("The sample has no source named %r. It has: %s"
                 % (source, ", ".join(info["sources"])))
    location = info["sources"][source]["location"]
    drawn = [r["rel_path"] for r in common.read_csv(common.inside(eval_data, "draw.csv"))
             if r["source"] == source]
    pool = [r for r in load_pool(eval_data) if r["source"] != source]
    mine = [r for r in load_pool(eval_data) if r["source"] == source]
    if not mine:
        remote = sample.REMOTE.match(location)
        listing = sample.list_remote(*remote.groups()) if remote else sample.list_local(location)
        mine = [{"source": source, "rel_path": rel} for rel in not_sampled(listing, drawn)]
        for i, row in enumerate(mine, len(pool) + 1):
            row["id"] = "p%05d" % i
        common.write_csv(common.inside(eval_data, "topup", "pool.csv"), POOL_COLUMNS, pool + mine)

    todo = [r["rel_path"] for r in mine if not pool_file(eval_data, r).exists()]
    if todo:
        def dest_for(rel):
            return common.inside(eval_data, "topup", "pool", source, *rel.split("/"))
        remote = sample.REMOTE.match(location)
        if remote:
            sample.copy_remote(remote.group(1), remote.group(2), todo, dest_for)
        else:
            sample.copy_local(location, todo, dest_for)
    return mine


def parse_also(texts):
    """['type=png'] -> [('type', 'png')]."""
    out = []
    for text in texts or []:
        fact, sep, value = text.partition("=")
        if not sep or fact not in facts_module.FACT_COLUMNS:
            sys.exit("--also must look like FACT=VALUE with a fact from facts.py: %r" % text)
        out.append((fact, value))
    return out


def choose(pool_rows, labels, share_rows, wanted, fact_rows, also, min_share=MIN_SHARE):
    """Which pool files to look at, and why.

    share_rows[i][j] is the share the model gives pool file i for
    labels[j]; fact_rows[i] is that file's facts as text. A file is picked
    for 'model' when the wanted labels together reach min_share, and for
    'facts' when any FACT=VALUE of `also` matches. Returns PICK_COLUMNS
    rows, the model's most likely ones first."""
    columns = [labels.index(w) for w in wanted]
    picks = []
    for row, shares, facts in zip(pool_rows, share_rows, fact_rows):
        share = float(sum(shares[c] for c in columns))
        why = []
        if share >= min_share:
            why.append("model")
        if any(str(facts.get(fact)) == value for fact, value in also):
            why.append("facts")
        if why:
            best = max(range(len(labels)), key=lambda j: shares[j])
            picks.append({"id": row["id"], "why": "+".join(why), "model_label": labels[best],
                          "share": "%.3f" % share})
    return sorted(picks, key=lambda p: (-float(p["share"]), p["id"]))


def pick(eval_data, field, wanted, also, min_share=MIN_SHARE):
    """Run the local model and the facts over the pool and write picks.csv."""
    import clip_local
    pool, readable, fact_rows = load_pool(eval_data), [], []
    for row in pool:
        try:
            fact_rows.append(facts_module.as_text(facts_module.compute(
                pool_file(eval_data, row), os.path.dirname(row["rel_path"]))))
            readable.append(row)
        except Exception:
            continue            # not there, or not an image that can be opened
    categories = json.loads(common.field_file(eval_data, field, "categories.json")
                            .read_text(encoding="utf-8"))
    unknown = [w for w in wanted if w not in [e["label"] for e in categories["labels"]]]
    if unknown:
        sys.exit("Not a label of the '%s' question: %s" % (field, ", ".join(unknown)))
    clip = clip_local.Clip(eval_data)
    texts, labels_of = clip_local.descriptions_from(categories)
    vectors = clip.embed_images([str(pool_file(eval_data, r)) for r in readable])
    labels, share_rows = clip_local.shares(vectors, clip.embed_texts(texts), labels_of)
    picks = choose(readable, labels, share_rows, wanted, fact_rows, also, min_share)
    common.write_csv(common.inside(eval_data, "topup", "picks.csv"), PICK_COLUMNS, picks)
    return picks, len(readable)


def add(eval_data, field, wanted, seed=None):
    """Add the picked files whose answer for `field` is a wanted label to
    the sample. Returns {label: how many were added}."""
    sample_rows = common.load_sample(eval_data)
    for row in sample_rows:
        row["drawn"] = row.get("drawn") or "evenly"
    already = {(r["source"], r["rel_path"]) for r in sample_rows}
    pool = {r["id"]: r for r in load_pool(eval_data)}
    answers = [a for a in common.read_csv(common.inside(eval_data, "topup", "answers.csv"))
               if a.get(field) in wanted and a["id"] in pool
               and (pool[a["id"]]["source"], pool[a["id"]]["rel_path"]) not in already]
    if seed is None:
        seed = json.loads(common.inside(eval_data, "sample_info.json")
                          .read_text(encoding="utf-8")).get("seed", 0)
    rng = random.Random(seed)
    next_id = max([int(r["id"][1:]) for r in sample_rows] or [0]) + 1
    added, new_rows = {}, []
    for label in wanted:
        mine = sorted((a for a in answers if a[field] == label), key=lambda a: a["id"])
        rng.shuffle(mine)
        for i, answer in enumerate(mine):
            source_row = pool[answer["id"]]
            row = {"id": "s%04d" % next_id, "source": source_row["source"],
                   "rel_path": source_row["rel_path"],
                   "folder": os.path.dirname(source_row["rel_path"]),
                   "half": "tuning" if i % 2 == 0 else "final", "drawn": "top-up"}
            dest = common.sample_file(eval_data, row)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(pool_file(eval_data, source_row), dest)
            details = organize_photos.inspect_image(str(dest))
            if details is None:
                dest.unlink()
                continue
            row.update({"camera_dated": "yes" if details["camera_dated"] else "no",
                        "date_source": details["date_source"], "bytes": dest.stat().st_size,
                        "answers": answer})
            new_rows.append(row)
            added[label] = added.get(label, 0) + 1
            next_id += 1
    if not new_rows:
        return added
    for one_field in common.FIELDS:
        path = common.field_file(eval_data, one_field, "labels.csv")
        rows = common.read_csv(path)
        rows += [{"id": r["id"], "rel_path": r["rel_path"],
                  "guessed_label": r["answers"].get(one_field) or common.FIELD_DEFAULT[one_field],
                  "confirmed_label": "", "reviewed": ""} for r in new_rows]
        common.write_csv(path, common.LABEL_COLUMNS, rows)
    # The sample is written last: a crash before this leaves it as it was.
    common.write_csv(common.inside(eval_data, "sample.csv"), common.SAMPLE_COLUMNS,
                     sample_rows + new_rows)
    return added


def main(argv=None):
    p = argparse.ArgumentParser(description="Find more examples of a rare label in the files that were not sampled.")
    p.add_argument("stage", choices=("fetch", "pick", "add"))
    p.add_argument("--source", help="fetch: the sample's name for the source to look in.")
    p.add_argument("--field", choices=common.FIELDS,
                   help="pick, add: the question the wanted labels belong to.")
    p.add_argument("--label", action="append", default=[],
                   help="pick, add: a label to find more of. Give the option once per label.")
    p.add_argument("--also", action="append", default=[], metavar="FACT=VALUE",
                   help="pick: also pick every file with this fact, whatever the model says.")
    p.add_argument("--min-share", type=float, default=MIN_SHARE,
                   help="pick: the share the model must give the wanted labels together.")
    p.add_argument("--eval-data", default=str(common.DEFAULT_EVAL_DATA))
    args = p.parse_args(argv)
    if not common.load_sample(args.eval_data):
        sys.exit("No sample yet. Run sample.py first.")
    if args.stage == "fetch":
        if not args.source:
            p.error("fetch needs --source")
        rows = fetch(args.eval_data, args.source)
        there = sum(1 for r in rows if pool_file(args.eval_data, r).exists())
        print("%d files of '%s' were not sampled; %d are now in the pool."
              % (len(rows), args.source, there))
        return
    if not args.field or not args.label:
        p.error("%s needs --field and at least one --label" % args.stage)
    if args.stage == "pick":
        picks, looked_at = pick(args.eval_data, args.field, args.label,
                                parse_also(args.also), args.min_share)
        print("%d of the %d files in the pool are worth a look:" % (len(picks), looked_at))
        for why in sorted({p_["why"] for p_ in picks}):
            print("  %5d picked by %s" % (sum(1 for p_ in picks if p_["why"] == why), why))
        print("List: %s" % common.inside(args.eval_data, "topup", "picks.csv"))
    else:
        added = add(args.eval_data, args.field, args.label)
        for label in args.label:
            print("  %5d added as %s" % (added.get(label, 0), label))
        print("They are first guesses. Review them with review.py like any other file.")


if __name__ == "__main__":
    main()
