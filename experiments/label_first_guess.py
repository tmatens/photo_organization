#!/usr/bin/env python3
"""
label_first_guess.py: first-guess labels from a hosted model.

Step 1 of docs/categorization-plan.md. THIS IS THE ONE SCRIPT THAT SENDS
PHOTOS OFF THIS COMPUTER. It sends only the sampled files in eval_data/,
each as a small re-saved copy (no EXIF, no file name, no folder), to the
Anthropic API, and only with the say-so of the person whose photos they
are. It helps build the answer key; it is not a candidate and never ships.

It runs in two passes:

  --pass 1   For each file: a few words of free description, a two- or
             three-word "kind", and the best fit from the starting list of
             labels, or "other".
  --tally    Counts the kinds, largest group first, and writes a page with
             a grid of thumbnails per group, so a person can settle the
             list of labels. Add --merge to have the model fold near-
             identical kinds together first (this sends the kinds as text,
             no photos).
  --pass 2   Labels every file against the settled list in
             eval_data/labels/categories.json. This pass is what gets
             reviewed.

--dry-run prints how many files would be sent and from where, and sends
nothing. Requests go through the Message Batches API, which costs half as
much and takes up to an hour. A run can be stopped at any point; running the
same command again picks up the batches already sent and sends only what is
still missing.

The API key is read from the ANTHROPIC_API_KEY environment variable by the
anthropic package. This script never prints it or writes it anywhere.

Usage:
  python experiments/label_first_guess.py --pass 1 --dry-run
  python experiments/label_first_guess.py --pass 1
  python experiments/label_first_guess.py --tally --merge
  python experiments/label_first_guess.py --pass 2
"""
import argparse
import base64
import html
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

DEFAULT_MODEL = "claude-opus-5-5"
# The model sees an image as 28-pixel squares, so a 768-pixel copy costs at
# most 28 x 28 = 784 image tokens: small text is still readable, and 1,200
# files stay cheap.
DEFAULT_MAX_EDGE = 768
PATCH = 28
MAX_BATCH_BYTES = 100 * 1000 * 1000    # well under the API's 256 MB per batch
MAX_BATCH_REQUESTS = 500

PASS1_COLUMNS = ["id", "description", "kind", "label", "error"]
PASS2_COLUMNS = ["id", "label", "error"]

# A draft of the rule for files that fit two labels. The plan requires this
# to be written down before labelling starts; it is settled together with
# the list of labels, in categories.json.
DRAFT_TIE_RULE = ("When two labels fit, what the file IS wins over what it shows: a screen "
                  "capture of a receipt is a screenshot, and a camera picture of a printed photo "
                  "of a receipt is a photo-of-photo. Between receipt and document, a receipt wins.")


def starting_categories():
    return {"settled": False,
            "labels": [{"label": label, "what_counts": what}
                       for label, what in common.STARTING_CATEGORIES],
            "when_two_apply": DRAFT_TIE_RULE}


def label_guide(categories):
    lines = ["- %s: %s" % (c["label"], c["what_counts"]) for c in categories["labels"]]
    return "\n".join(lines) + "\n\n" + categories["when_two_apply"]


def prompt_and_schema(pass_number, categories):
    """The instruction text and the shape of the answer for one pass."""
    names = [c["label"] for c in categories["labels"]]
    if pass_number == 1:
        text = ("This image is one file from a personal photo library. Three things:\n"
                "1. description: a few plain words saying what it is.\n"
                "2. kind: two or three lowercase words naming the kind of image, general "
                "enough that similar files would get the same words (for example "
                "'till receipt', 'chat screenshot', 'family photo', 'child's drawing').\n"
                "3. label: the best fit from this list, or 'other' if none fits well.\n\n"
                + label_guide(categories))
        properties = {"description": {"type": "string"}, "kind": {"type": "string"},
                      "label": {"type": "string", "enum": names + ["other"]}}
    else:
        text = ("This image is one file from a personal photo library. Give it exactly one "
                "label from this list.\n\n" + label_guide(categories))
        properties = {"label": {"type": "string", "enum": names}}
    schema = {"type": "object", "properties": properties,
              "required": list(properties), "additionalProperties": False}
    return text, schema


def encode_image(path, max_edge):
    """A small JPEG of the file, as base64 text. Re-saving it drops the
    EXIF data, so no date, camera or location travels with the picture."""
    img = common.shrink(common.open_upright(path), max_edge)
    buffer = io.BytesIO()
    img.save(buffer, "JPEG", quality=85)
    return base64.standard_b64encode(buffer.getvalue()).decode("ascii"), img.size


def image_tokens(size):
    """Roughly what one image costs: the API counts 28-pixel squares."""
    w, h = size
    return -(-w // PATCH) * -(-h // PATCH)


def build_request(file_id, image_b64, pass_number, categories, model):
    """One entry of a batch. The only things that identify the file are the
    sample id (s0001...) and the picture itself."""
    text, schema = prompt_and_schema(pass_number, categories)
    return {
        "custom_id": file_id,
        "params": {
            "model": model,
            # Thinking counts toward this limit, so leave room for it.
            "max_tokens": 2048,
            "output_config": {"effort": "low",
                              "format": {"type": "json_schema", "schema": schema}},
            "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                             "data": image_b64}},
                {"type": "text", "text": text},
            ]}],
        },
    }


def split_into_batches(requests):
    """Group requests so no batch is too large to send."""
    batches, current, size = [], [], 0
    for request in requests:
        weight = len(request["params"]["messages"][0]["content"][0]["source"]["data"])
        if current and (size + weight > MAX_BATCH_BYTES or len(current) >= MAX_BATCH_REQUESTS):
            batches.append(current)
            current, size = [], 0
        current.append(request)
        size += weight
    if current:
        batches.append(current)
    return batches


def read_answer(result, columns):
    """Turn one batch result into a row for the pass's CSV file. Anything
    other than a clean answer becomes a row with `error` set, so the file
    is tried again on the next run."""
    row = {c: "" for c in columns}
    row["id"] = result.custom_id
    if result.result.type != "succeeded":
        row["error"] = result.result.type
        return row
    message = result.result.message
    if message.stop_reason != "end_turn":
        row["error"] = message.stop_reason or "no answer"
        return row
    try:
        answer = json.loads(next(b.text for b in message.content if b.type == "text"))
    except (StopIteration, ValueError):
        row["error"] = "unreadable answer"
        return row
    for column in columns:
        if column in answer:
            row[column] = " ".join(str(answer[column]).split())
    return row


def still_to_do(eval_data, pass_number, limit=None):
    """Sample rows with no answer yet for this pass."""
    done = {r["id"] for r in common.read_csv(pass_file(eval_data, pass_number)) if not r["error"]}
    rows = [r for r in common.load_sample(eval_data) if r["id"] not in done]
    return rows[:limit] if limit else rows


def pass_file(eval_data, pass_number):
    return common.inside(eval_data, "labels", "pass%d.csv" % pass_number)


def state_file(eval_data, pass_number):
    return common.inside(eval_data, "labels", "pass%d_batches.json" % pass_number)


def load_state(eval_data, pass_number):
    path = state_file(eval_data, pass_number)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"batches": []}


def save_state(eval_data, pass_number, state):
    path = state_file(eval_data, pass_number)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_categories(eval_data, pass_number):
    path = common.inside(eval_data, "labels", "categories.json")
    if pass_number == 1:
        return starting_categories()
    if not path.exists():
        sys.exit("No settled list of labels yet. Run --tally, then edit %s." % path)
    categories = json.loads(path.read_text(encoding="utf-8"))
    if not categories.get("settled"):
        sys.exit('The list in %s is not marked as settled. Edit it and set "settled": true.' % path)
    return categories


def describe_run(rows, pass_number, model, max_edge, eval_data):
    """What a run would send. Printed by --dry-run and before a real run."""
    print("Pass %d would send %d files to the Anthropic API (model %s)."
          % (pass_number, len(rows), model))
    groups = {}
    for row in rows:
        key = (row["source"], row["half"])
        groups[key] = groups.get(key, 0) + 1
    for (source, half), count in sorted(groups.items()):
        print("  %5d from source '%s', %s half" % (count, source, half))
    print("  Each file is sent as a re-saved JPEG at most %d pixels long, without EXIF,"
          % max_edge)
    print("  file name or folder. All of them come from %s."
          % common.inside(eval_data, "files"))
    per_image = image_tokens((max_edge, max_edge))
    print("  At most about %d image tokens per file, %.1f million in all."
          % (per_image, per_image * len(rows) / 1e6))


def run_pass(args):
    eval_data, pass_number = args.eval_data, args.pass_number
    categories = load_categories(eval_data, pass_number)
    state = load_state(eval_data, pass_number)
    waiting = {i for b in state["batches"] if not b["collected"] for i in b["ids"]}
    rows = [r for r in still_to_do(eval_data, pass_number, args.limit) if r["id"] not in waiting]

    describe_run(rows, pass_number, args.model, args.max_edge, eval_data)
    if waiting:
        print("  %d more files are in batches already sent and waiting for answers." % len(waiting))
    if args.dry_run:
        print("Dry run: nothing was sent.")
        return

    import anthropic                    # only needed when something is really sent
    client = anthropic.Anthropic()      # reads the key from the environment

    requests = []
    for row in rows:
        try:
            data, _size = encode_image(common.sample_file(eval_data, row), args.max_edge)
        except Exception:
            print("  could not open %s, skipped" % row["id"])
            continue
        requests.append(build_request(row["id"], data, pass_number, categories, args.model))
    for chunk in split_into_batches(requests):
        batch = client.messages.batches.create(requests=chunk)
        state["batches"].append({"batch_id": batch.id, "collected": False,
                                 "ids": [r["custom_id"] for r in chunk]})
        save_state(eval_data, pass_number, state)       # saved before the next one is sent
        print("  sent a batch of %d files" % len(chunk))

    columns = PASS1_COLUMNS if pass_number == 1 else PASS2_COLUMNS
    answers = {r["id"]: r for r in common.read_csv(pass_file(eval_data, pass_number))}
    for entry in state["batches"]:
        if entry["collected"]:
            continue
        while client.messages.batches.retrieve(entry["batch_id"]).processing_status != "ended":
            print("  waiting for a batch of %d files (Ctrl-C is safe; run again to resume)"
                  % len(entry["ids"]))
            time.sleep(30)
        for result in client.messages.batches.results(entry["batch_id"]):
            answers[result.custom_id] = read_answer(result, columns)
        common.write_csv(pass_file(eval_data, pass_number), columns,
                         sorted(answers.values(), key=lambda r: r["id"]))
        entry["collected"] = True
        save_state(eval_data, pass_number, state)

    failed = sum(1 for r in answers.values() if r["error"])
    print("Pass %d: %d files answered, %d failed%s."
          % (pass_number, len(answers) - failed, failed,
             " (run again to retry them)" if failed else ""))
    if pass_number == 2:
        write_labels(eval_data, answers)


def write_labels(eval_data, answers):
    """labels.csv: path, guessed label, confirmed label. Confirmed labels a
    person has already given are kept."""
    path = common.inside(eval_data, "labels", "labels.csv")
    before = {r["id"]: r for r in common.read_csv(path)}
    rows = [{"id": r["id"], "rel_path": r["rel_path"],
             "guessed_label": answers[r["id"]]["label"],
             "confirmed_label": before.get(r["id"], {}).get("confirmed_label", ""),
             "reviewed": before.get(r["id"], {}).get("reviewed", "")}
            for r in common.load_sample(eval_data)
            if r["id"] in answers and not answers[r["id"]]["error"]]
    common.write_csv(path, common.LABEL_COLUMNS, rows)
    print("First guesses for %d files are in %s. Next: review.py" % (len(rows), path))


def merge_kinds(counts, model, dry_run):
    """Ask the model to fold near-identical kinds into groups. Sends the
    kinds as text; no photos. Returns {kind: group}."""
    print("Merging would send %d short descriptions as text, and no photos, to the "
          "Anthropic API (model %s)." % (len(counts), model))
    if dry_run:
        print("Dry run: nothing was sent.")
        return {}
    import anthropic
    listing = "\n".join("%s (%d)" % (kind, n) for kind, n in sorted(counts.items()))
    schema = {"type": "object", "additionalProperties": False, "required": ["groups"],
              "properties": {"groups": {"type": "array", "items": {
                  "type": "object", "additionalProperties": False, "required": ["name", "kinds"],
                  "properties": {"name": {"type": "string"},
                                 "kinds": {"type": "array", "items": {"type": "string"}}}}}}}
    with anthropic.Anthropic().messages.stream(
            model=model, max_tokens=32000,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content":
                       "Each line is a short name for a kind of image in a personal photo "
                       "library, with how many files got it. Many lines mean the same thing "
                       "in different words. Put every line into a group of lines that a person "
                       "sorting the library would treat as one kind. Aim for 15 to 40 groups, "
                       "keep clearly different kinds apart, and copy each kind exactly, "
                       "without its count.\n\n" + listing}]) as stream:
        message = stream.get_final_message()
    if message.stop_reason != "end_turn":
        sys.exit("The model did not finish grouping (%s)." % message.stop_reason)
    answer = json.loads(next(b.text for b in message.content if b.type == "text"))
    return {kind: group["name"] for group in answer["groups"] for kind in group["kinds"]}


def tally_groups(pass1_rows, merged=None):
    """[(group, [rows])], largest group first. Without a merge, files are
    grouped by their kind, ignoring case and spacing."""
    groups = {}
    for row in pass1_rows:
        if row["error"]:
            continue
        kind = " ".join(row["kind"].lower().split())
        groups.setdefault((merged or {}).get(kind, kind), []).append(row)
    return sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))


def run_tally(args):
    eval_data = args.eval_data
    pass1 = common.read_csv(pass_file(eval_data, 1))
    if not pass1:
        sys.exit("Pass 1 has not been run yet.")
    merged = None
    if args.merge:
        counts = {}
        for group, rows in tally_groups(pass1):
            counts[group] = len(rows)
        merged = merge_kinds(counts, args.model, args.dry_run)
        if args.dry_run:
            return
    groups = tally_groups(pass1, merged)
    sample = {r["id"]: r for r in common.load_sample(eval_data)}

    parts = ["<!doctype html><meta charset='utf-8'><title>What is in the sample</title><style>"
             "body{font:14px system-ui;margin:24px}img{height:150px;margin:2px;border-radius:3px}"
             "h2{margin-top:32px}small{color:#666;font-weight:400}</style>"
             "<h1>What is in the sample</h1><p>Groups of similar files, largest first, with the "
             "labels the model gave them. Hover over a picture for its description.</p>"]
    print("%5s  %s" % ("files", "group (labels given)"))
    for group, rows in groups:
        labels = {}
        for row in rows:
            labels[row["label"]] = labels.get(row["label"], 0) + 1
        given = ", ".join("%s %d" % item for item in sorted(labels.items(), key=lambda i: -i[1]))
        print("%5d  %s (%s)" % (len(rows), group, given))
        parts.append("<h2>%s <small>%d files: %s</small></h2>"
                     % (html.escape(group), len(rows), html.escape(given)))
        for row in rows:
            if common.make_thumbnail(eval_data, sample[row["id"]]):
                parts.append("<img loading='lazy' src='../thumbs/%s.jpg' title='%s'>"
                             % (row["id"], html.escape("%s [%s]" % (row["description"], row["label"]),
                                                       quote=True)))
    page = common.inside(eval_data, "labels", "pass1_tally.html")
    page.write_text("".join(parts), encoding="utf-8")
    categories = common.inside(eval_data, "labels", "categories.json")
    if not categories.exists():
        categories.write_text(json.dumps(starting_categories(), indent=2), encoding="utf-8")
    print("Thumbnail grids: %s" % page)
    print('Settle the list of labels in %s and set "settled": true, then run --pass 2.' % categories)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="First-guess labels for the sampled files from a hosted model.")
    p.add_argument("--pass", dest="pass_number", type=int, choices=(1, 2),
                   help="1: free description and a first label. 2: label against the settled list.")
    p.add_argument("--tally", action="store_true",
                   help="Count pass 1's descriptions and write the thumbnail grids.")
    p.add_argument("--merge", action="store_true",
                   help="With --tally: have the model fold similar kinds together (text only).")
    p.add_argument("--dry-run", action="store_true",
                   help="Print how many files would be sent and from where. Sends nothing.")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--max-edge", type=int, default=DEFAULT_MAX_EDGE,
                   help="Longest side, in pixels, of the copy that is sent.")
    p.add_argument("--limit", type=int, default=None,
                   help="Send at most this many files, for a small trial.")
    p.add_argument("--eval-data", default=str(common.DEFAULT_EVAL_DATA))
    args = p.parse_args(argv)
    if bool(args.pass_number) == args.tally:
        p.error("give exactly one of --pass 1, --pass 2 or --tally")
    return args


def main(argv=None):
    args = parse_args(argv)
    if args.tally:
        run_tally(args)
    else:
        run_pass(args)


if __name__ == "__main__":
    main()
