#!/usr/bin/env python3
"""
sort_screenshots.py — Pull one app's screenshots out of the review folder.

Run AFTER organize_photos.py. It looks only inside <output>/_review/screenshots
and moves every screenshot that looks like one of your example screenshots
into <output>/_review/<name>/YYYY/MM. Nothing outside the review folder is
touched, and your original drives are never read.

Give it a folder of examples: one screenshot of the app, or one per look if
the app has changed over the years. Run it, look at what is still in
_review/screenshots, copy one of any that were missed into the examples
folder, and run it again. Only the leftovers are checked each time.

How matching works: an app's "now playing" screen keeps the same header at
the top and the same controls at the bottom while the picture in the middle
changes with every song. Each screenshot's top and bottom bands are shrunk
to a small grid and compared with the same bands of every example; a close
match on both bands means the same app layout, whatever the screen size.

Requires: Python 3.10+ and Pillow (same as organize_photos.py).

Usage:
  python sort_screenshots.py --output D:\\Organized --examples C:\\photo_organizer\\pandora --name pandora --dry-run
  python sort_screenshots.py --output D:\\Organized --examples C:\\photo_organizer\\pandora --name pandora
"""

import argparse
import csv
import os
import sys

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is required: pip install pillow")

# organize_photos.py lives next to this file; make sure it is found even
# when this script is run from another folder or with python -I.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from organize_photos import iter_images, longpath  # noqa: E402

# The bands of a phone screen that hold an app's own interface. Measured on
# a real now-playing screenshot: the top band is the status bar and header,
# the bottom band is title, controls and progress bar; the middle is the
# artwork, which changes with every song and is ignored.
TOP_BAND = (0.0, 0.16)
BOTTOM_BAND = (0.56, 1.0)
GRID = (12, 12)      # each band is shrunk to this many cells before comparing


def parse_args():
    p = argparse.ArgumentParser(
        description="Move one app's screenshots out of _review/screenshots "
                    "into their own folder, by comparing with example screenshots.")
    p.add_argument("--output", required=True,
                   help="The organized folder (the --output you gave organize_photos.py).")
    p.add_argument("--examples", required=True,
                   help="Folder holding one or more example screenshots of the app.")
    p.add_argument("--name", default="app",
                   help="Folder name under _review for the matches (default app).")
    p.add_argument("--review-folder", default="_review", metavar="NAME",
                   help="Name of the review folder (default _review).")
    p.add_argument("--threshold", type=int, default=12, metavar="N",
                   help="How different the bands may be and still match, 0-255 "
                        "(default 12). Raise it if screenshots are missed, lower "
                        "it if other apps are caught.")
    p.add_argument("--dry-run", action="store_true",
                   help="Report what would move; move nothing.")
    return p.parse_args()


def flat(img):
    """All pixel values of a small image (Pillow renamed this in 12.x)."""
    return getattr(img, "get_flattened_data", img.getdata)()


def band_signature(img):
    """[top grid, top mean colour, bottom grid, bottom mean colour] for an
    image, independent of its pixel size."""
    W, H = img.size
    sig = []
    for y0, y1 in (TOP_BAND, BOTTOM_BAND):
        band = img.crop((0, int(H * y0), W, int(H * y1))).convert("RGB")
        small = band.resize(GRID, Image.BOX)
        sig.append(list(flat(small.convert("L"))))
        pixels = list(flat(small))
        sig.append(tuple(sum(p[i] for p in pixels) // len(pixels) for i in range(3)))
    return sig


def band_distance(a, b):
    """Largest of: mean grey difference per band, mean colour difference per
    band. 0 = identical layout; small = same app; large = different."""
    worst = 0
    for i in (0, 2):
        grey = sum(abs(x - y) for x, y in zip(a[i], b[i])) / len(a[i])
        colour = sum(abs(x - y) for x, y in zip(a[i + 1], b[i + 1])) / 3
        worst = max(worst, grey, colour)
    return worst


def signature_of(path):
    try:
        with Image.open(longpath(path)) as img:
            return band_signature(img)
    except Exception:
        return None


def main():
    args = parse_args()
    output = os.path.abspath(args.output)
    review = os.path.join(output, args.review_folder)
    screenshots = os.path.join(review, "screenshots")
    target = os.path.join(review, args.name)
    manifest = os.path.join(output, "manifest.csv")
    if not os.path.isdir(screenshots):
        sys.exit("No screenshots folder found at %s. Run organize_photos.py first." % screenshots)
    if not os.path.isdir(args.examples):
        sys.exit("Examples folder not found: %s" % args.examples)
    if not 0 <= args.threshold <= 255:
        sys.exit("--threshold must be between 0 and 255.")

    examples = []
    for path in iter_images(os.path.abspath(args.examples), skipped={}):
        sig = signature_of(path)
        if sig is not None:
            examples.append((os.path.basename(path), sig))
    if not examples:
        sys.exit("No readable images in the examples folder.")
    print("Loaded %d example screenshot(s)." % len(examples))

    candidates = list(iter_images(screenshots, skipped={}))
    print("Checking %d screenshot(s) in %s ..." % (len(candidates), screenshots))

    moves = []   # (from, to, example, distance)
    for i, path in enumerate(candidates, 1):
        if i % 500 == 0 or i == len(candidates):
            print("  checked %d/%d ..." % (i, len(candidates)))
        sig = signature_of(path)
        if sig is None:
            continue
        best = min((band_distance(sig, ex), name) for name, ex in examples)
        if best[0] <= args.threshold:
            rel = os.path.relpath(path, screenshots)          # YYYY/MM/name.png
            moves.append((path, os.path.join(target, rel), best[1], best[0]))

    os.makedirs(longpath(review), exist_ok=True)
    log = os.path.join(review, "%s_sort%s.csv" % (args.name, "_dryrun" if args.dry_run else ""))
    with open(log, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["from", "to", "matched_example", "distance"])
        for src, dest, ex, dist in moves:
            w.writerow([src, dest, ex, "%.1f" % dist])

    if not args.dry_run and moves:
        moved = {}
        for src, dest, _ex, _d in moves:
            os.makedirs(longpath(os.path.dirname(dest)), exist_ok=True)
            os.replace(longpath(src), longpath(dest))
            moved[src] = dest
        # Keep manifest.csv true: its destination_path column must point at
        # where each file now is.
        if os.path.isfile(manifest):
            with open(manifest, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                columns = reader.fieldnames
                rows = list(reader)
            for row in rows:
                if row.get("destination_path") in moved:
                    row["destination_path"] = moved[row["destination_path"]]
            tmp = manifest + ".part"
            with open(tmp, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=columns)
                w.writeheader()
                w.writerows(rows)
            os.replace(tmp, manifest)
        # Drop month folders left empty by the moves.
        for dirpath, dirnames, filenames in os.walk(screenshots, topdown=False):
            if dirpath != screenshots and not dirnames and not filenames:
                os.rmdir(dirpath)

    print("\nDone%s." % (" (dry run: nothing moved)" if args.dry_run else ""))
    print("  matched:   %d of %d" % (len(moves), len(candidates)))
    print("  %s %s" % ("would move to:" if args.dry_run else "moved to:", target))
    print("  log: %s" % log)
    if len(moves) < len(candidates):
        print("Look through what is left in %s. If any are the app you are after,\n"
              "copy one of each different look into %s and run again."
              % (screenshots, os.path.abspath(args.examples)))


if __name__ == "__main__":
    main()
