#!/usr/bin/env python3
"""
sample.py: copy a sample of real photos into eval_data/ for labelling.

Step 1 of docs/categorization-plan.md. Give it one or two sources: a folder
of files without a camera date and a folder of camera-dated photos. It picks
files spread evenly through each source (every k-th file, first to last, the
way organize_photos.py --sample does), copies them into eval_data/files/ and
splits them once, at random, into a tuning half and a final-check half.

The sources are only ever read. A source can be a folder on this computer or
a folder on another machine reached over ssh, written host:/folder. Each
file keeps its folder path relative to the source, because the folder a file
came from is one of the facts the experiment looks at.

Running it again never draws a new sample: it finishes any copies that were
interrupted and leaves the split as it is.

Usage:
  python experiments/sample.py --source undated=/photos/unsorted --source camera=nas:/photos/sorted --count 1200
"""
import argparse
import json
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from common import organize_photos  # noqa: E402

# host:/folder means "over ssh". A single letter before the colon is a
# Windows drive (C:/photos), not a host.
REMOTE = re.compile(r"^([^/\\:]{2,}):(/.*)$")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Copy an evenly spread sample of photos into eval_data/ and split it in two.")
    p.add_argument("--source", action="append", required=True, metavar="NAME=FOLDER",
                   help="A source to sample from, with a short name for it. FOLDER is a local "
                        "folder or host:/folder for ssh. Give the option once per source.")
    p.add_argument("--count", type=int, default=1200,
                   help="How many files to sample in total, shared equally between the sources.")
    p.add_argument("--seed", type=int, default=None,
                   help="Seed for the random split. Chosen at random and recorded if not given.")
    p.add_argument("--eval-data", default=str(common.DEFAULT_EVAL_DATA),
                   help="Folder the sample is written to. Never committed.")
    return p.parse_args(argv)


def parse_source(text):
    """'name=folder' -> (name, folder)."""
    name, sep, location = text.partition("=")
    if not sep or not name or not location or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        sys.exit("--source must look like NAME=FOLDER, with a plain short name: %r" % text)
    return name, location


def wanted(rel_path):
    """True for a photo file that is not hidden and not in a system folder.
    Same exclusions as organize_photos.py; videos are left out."""
    parts = rel_path.split("/")
    if any(p in organize_photos.SKIP_DIRS or p.startswith(".") for p in parts):
        return False
    return os.path.splitext(parts[-1])[1].lower() in common.PHOTO_EXTS


def list_local(folder):
    """Every file under a local folder, as paths relative to it with / between parts."""
    root = Path(folder)
    if not root.is_dir():
        sys.exit("Source folder not found: %s" % folder)
    out = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            out.append(Path(dirpath, name).relative_to(root).as_posix())
    return out


def list_remote(host, folder):
    """Every file under a folder on another machine, listed with find over
    ssh. find only reads."""
    cmd = ["ssh", "-o", "BatchMode=yes", host,
           "cd %s && find . -type f -print0" % shlex.quote(folder)]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0 and not proc.stdout:
        sys.exit("Could not list the source over ssh:\n%s" % proc.stderr.decode("utf-8", "replace"))
    names = proc.stdout.decode("utf-8", "surrogateescape").split("\0")
    return [n[2:] if n.startswith("./") else n for n in names if n]


def pick_evenly(items, count):
    """count items spread from first to last: every k-th one, as
    organize_photos.py --sample does. Fewer than count items: all of them."""
    if count >= len(items):
        return list(items)
    step = len(items) / count
    return [items[int(i * step)] for i in range(count)]


def copy_local(folder, rel_paths, dest_for):
    for rel in rel_paths:
        dest = dest_for(rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(folder, *rel.split("/")), dest)


def copy_remote(host, folder, rel_paths, dest_for):
    """Copy the named files from another machine in one ssh connection.

    The remote side runs tar, which only reads, and streams the files back.
    Each file in the stream is written out by hand to its place in
    eval_data, and only if it is one that was asked for, so nothing in the
    stream can choose where it lands."""
    asked = set(rel_paths)
    cmd = ["ssh", "-o", "BatchMode=yes", host,
           "tar -C %s --null -T - -cf -" % shlex.quote(folder)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)
    names = "\0".join(rel_paths).encode("utf-8", "surrogateescape") + b"\0"
    # The list of names is far smaller than a pipe buffer problem would
    # need, but tar starts answering before it has read it all, so feed it
    # from a thread while the main thread reads the stream.
    import threading

    def feed():
        try:
            proc.stdin.write(names)
            proc.stdin.close()
        except OSError:
            pass
    feeder = threading.Thread(target=feed, daemon=True)
    feeder.start()
    try:
        with tarfile.open(fileobj=proc.stdout, mode="r|") as stream:
            for member in stream:
                name = member.name[2:] if member.name.startswith("./") else member.name
                if not member.isfile() or name not in asked:
                    continue
                dest = dest_for(name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_name(dest.name + ".tmp")
                with open(tmp, "wb") as out:
                    shutil.copyfileobj(stream.extractfile(member), out)
                os.replace(tmp, dest)
    except tarfile.ReadError:
        pass        # an empty or cut-off stream; the caller reports what is missing
    feeder.join()
    proc.wait()


def draw(sources, count, eval_data):
    """Decide which files make up the sample and record the decision, so an
    interrupted run picks up the same files instead of drawing again."""
    per_source = count // len(sources)
    rows = []
    info = {"sources": {}, "asked_for": count}
    for name, location in sources:
        remote = REMOTE.match(location)
        listing = list_remote(*remote.groups()) if remote else list_local(location)
        photos = sorted(p for p in listing if wanted(p))
        chosen = pick_evenly(photos, per_source)
        info["sources"][name] = {"location": location, "photo_files": len(photos),
                                 "drawn": len(chosen)}
        for rel in chosen:
            rows.append({"source": name, "rel_path": rel})
    for i, row in enumerate(rows, 1):
        row["id"] = "s%04d" % i
    common.write_csv(common.inside(eval_data, "draw.csv"), ["id", "source", "rel_path"], rows)
    with open(common.inside(eval_data, "sample_info.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)
    return rows, info


def copy_missing(rows, info, eval_data):
    """Copy every drawn file that is not in eval_data yet."""
    for name, details in info["sources"].items():
        todo = [r["rel_path"] for r in rows if r["source"] == name
                and not common.sample_file(eval_data, r).exists()]
        if not todo:
            continue

        def dest_for(rel, name=name):
            return common.inside(eval_data, "files", name, *rel.split("/"))
        remote = REMOTE.match(details["location"])
        if remote:
            copy_remote(remote.group(1), remote.group(2), todo, dest_for)
        else:
            copy_local(details["location"], todo, dest_for)


def split_halves(rows, seed):
    """Mark each row 'tuning' or 'final'. Shuffled within each source, so
    both halves hold the same share of each."""
    rng = random.Random(seed)
    for name in sorted({r["source"] for r in rows}):
        group = [r for r in rows if r["source"] == name]
        rng.shuffle(group)
        for i, row in enumerate(group):
            row["half"] = "tuning" if i < (len(group) + 1) // 2 else "final"


def main(argv=None):
    args = parse_args(argv)
    eval_data = args.eval_data
    sources = [parse_source(s) for s in args.source]
    if len({name for name, _ in sources}) != len(sources):
        sys.exit("Each --source needs its own name.")
    if common.load_sample(eval_data):
        sys.exit("A sample already exists in %s. The split is made once and is not redrawn."
                 % eval_data)

    draw_file = common.inside(eval_data, "draw.csv")
    info_file = common.inside(eval_data, "sample_info.json")
    if draw_file.exists() and info_file.exists():
        rows = common.read_csv(draw_file)
        info = json.loads(info_file.read_text(encoding="utf-8"))
        print("Continuing an interrupted run: %d files already drawn." % len(rows))
    else:
        rows, info = draw(sources, args.count, eval_data)

    copy_missing(rows, info, eval_data)

    kept, missing, unreadable = [], 0, 0
    for row in rows:
        path = common.sample_file(eval_data, row)
        if not path.exists():
            missing += 1        # the source would not let it be read
            continue
        details = organize_photos.inspect_image(str(path))
        if details is None:
            unreadable += 1     # copied, but not an image Pillow can open
            path.unlink()
            continue
        row["folder"] = os.path.dirname(row["rel_path"])
        row["camera_dated"] = "yes" if details["camera_dated"] else "no"
        row["date_source"] = details["date_source"]
        row["bytes"] = path.stat().st_size
        kept.append(row)

    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(10 ** 9)
    split_halves(kept, seed)
    info.update({"seed": seed, "kept": len(kept), "could_not_be_copied": missing,
                 "could_not_be_opened": unreadable})
    with open(info_file, "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)
    common.write_csv(common.inside(eval_data, "sample.csv"), common.SAMPLE_COLUMNS, kept)

    print("Sampled %d files into %s" % (len(kept), eval_data))
    for name, details in info["sources"].items():
        mine = [r for r in kept if r["source"] == name]
        print("  %-12s %5d of %d photo files (%d tuning, %d final check; %d with a camera date)"
              % (name, len(mine), details["photo_files"],
                 sum(r["half"] == "tuning" for r in mine),
                 sum(r["half"] == "final" for r in mine),
                 sum(r["camera_dated"] == "yes" for r in mine)))
    if missing or unreadable:
        print("  left out: %d could not be copied, %d could not be opened" % (missing, unreadable))
    print("  split seed: %d" % seed)


if __name__ == "__main__":
    main()
