#!/usr/bin/env python3
"""
organize_photos.py — Organize a large photo library directly on your computer.

Reads every photo under --source (e.g. an external drive), then builds a clean,
organized COPY under --output. Your originals are never modified, moved, or
deleted. No uploads, no recompression.

What it does:
  1. Scans all subfolders for photos (JPG, PNG, HEIC, WEBP, TIFF, BMP).
  2. Finds duplicates (exact visual duplicates) and lists them instead of
     copying them twice.
  3. Sorts everything by the date the photo was taken (EXIF data; falls back
     to the file's modification date for screenshots, which usually have no
     EXIF data) into YYYY/MM folders with clean filenames.
  4. Optionally pulls out every photo that looks like an example image you
     provide (--example), e.g. all your music-app screenshots, into its own
     folder.
  5. Writes a manifest.csv describing where everything went.

Requires: Python 3.9+, plus:  pip install pillow imagehash
Optional (for iPhone HEIC photos):  pip install pillow-heif

Usage:
  python organize_photos.py --source "E:\\" --output "E:\\Organized"
  python organize_photos.py --source /Volumes/MyDrive --output ~/Organized \\
      --example ~/screenshot_example.png --dry-run
"""

import argparse
import csv
import hashlib
import os
import shutil
import sys
from collections import defaultdict
from datetime import datetime

try:
    from PIL import Image, ExifTags
except ImportError:
    sys.exit("Pillow is required: pip install pillow")

try:
    import imagehash
except ImportError:
    sys.exit("imagehash is required: pip install imagehash")

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC_OK = True
except ImportError:
    HEIC_OK = False

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
if HEIC_OK:
    IMAGE_EXTS |= {".heic", ".heif"}

EXIF_DATETIME_ORIGINAL = 36867
EXIF_DATETIME = 306


def parse_args():
    p = argparse.ArgumentParser(description="Organize a photo library in place.")
    p.add_argument("--source", required=True,
                   help="Folder to scan (e.g. your external drive).")
    p.add_argument("--output", required=True,
                   help="Folder where the organized copy will be built.")
    p.add_argument("--example", default=None,
                   help="Example image: photos visually similar to this are "
                        "pulled into their own folder.")
    p.add_argument("--similar-name", default="matched_example",
                   help="Folder name for photos matching --example.")
    p.add_argument("--similar-threshold", type=int, default=10,
                   help="Max perceptual-hash distance (0-64) to count as "
                        "similar to --example. Lower = stricter. Default 10.")
    p.add_argument("--example-chrome", action="store_true",
                   help="Match on the app's UI chrome only (top and bottom "
                        "bands), ignoring the variable middle area. Best for "
                        "screenshots of a music app where the artwork changes "
                        "with every song.")
    p.add_argument("--dup-threshold", type=int, default=0,
                   help="Max perceptual-hash distance to count as a duplicate. "
                        "0 = exact duplicates only (fastest). Default 0.")
    p.add_argument("--keep-dupes", action="store_true",
                   help="Also copy duplicates into _duplicates/ for review.")
    p.add_argument("--dry-run", action="store_true",
                   help="Scan and report only; copy nothing.")
    return p.parse_args()


def iter_images(root):
    """Yield absolute paths of image files under root."""
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext in IMAGE_EXTS:
                yield os.path.join(dirpath, name)


def date_taken(path):
    """Return (datetime, source) using EXIF, else file modification time."""
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            for tag in (EXIF_DATETIME_ORIGINAL, EXIF_DATETIME):
                val = exif.get(tag)
                if val:
                    try:
                        return datetime.strptime(val, "%Y:%m:%d %H:%M:%S"), "exif"
                    except (ValueError, TypeError):
                        pass
    except Exception:
        pass
    ts = os.path.getmtime(path)
    return datetime.fromtimestamp(ts), "file-date"


def phash_of(path):
    """Perceptual hash of an image; None if unreadable."""
    try:
        with Image.open(path) as img:
            return imagehash.phash(img)
    except Exception:
        return None


def chrome_hash(img):
    """Perceptual hash of only the top and bottom bands of an image.

    For screenshots of music apps, the middle (album art) changes with
    every song while the UI chrome stays the same. Hashing just the chrome
    matches all such screenshots regardless of content in the middle.
    """
    W, H = img.size
    top = img.crop((0, 0, W, int(H * 0.16)))
    bottom = img.crop((0, int(H * 0.56), W, H))
    comp = Image.new("RGB", (W, top.height + bottom.height), "white")
    comp.paste(top, (0, 0))
    comp.paste(bottom, (0, top.height))
    return imagehash.phash(comp)


def hashes_of(path, need_chrome):
    """Return (perceptual_hash, chrome_hash or None); (None, None) if unreadable."""
    try:
        with Image.open(path) as img:
            h = imagehash.phash(img)
            ch = chrome_hash(img) if need_chrome else None
            return h, ch
    except Exception:
        return None, None


def hamming(a, b):
    return int(a - b)


def unique_dest(folder, stem, ext, make_dirs=True):
    """Destination path that never overwrites: adds _2, _3, ... as needed."""
    if make_dirs:
        os.makedirs(folder, exist_ok=True)
    candidate = os.path.join(folder, stem + ext)
    n = 2
    while os.path.exists(candidate):
        candidate = os.path.join(folder, "%s_%d%s" % (stem, n, ext))
        n += 1
    return candidate


def main():
    args = parse_args()
    source = os.path.abspath(args.source)
    output = os.path.abspath(args.output)
    if not os.path.isdir(source):
        sys.exit("Source folder not found: %s" % source)
    if output == source or output.startswith(source + os.sep):
        sys.exit("Output must not be inside the source folder.")

    example_hash = None
    example_chrome = None
    example_abs = os.path.abspath(args.example) if args.example else None
    if example_abs:
        if not os.path.isfile(example_abs):
            sys.exit("Example image not found: %s" % example_abs)
        example_hash, example_chrome = hashes_of(example_abs,
                                                 args.example_chrome)
        if example_hash is None:
            sys.exit("Could not read example image: %s" % example_abs)
        print("Example image loaded; similarity threshold = %d%s"
              % (args.similar_threshold,
                 " (UI-chrome matching)" if args.example_chrome else ""))

    print("Scanning %s ..." % source)
    paths = [p for p in iter_images(source)
             if os.path.abspath(p) != example_abs]
    print("Found %d image files." % len(paths))

    rows = []            # manifest rows
    kept_hashes = []     # (hash, dest) of copied images, for near-dupe checks
    seen_exact = {}      # str(hash) -> first source path
    stats = defaultdict(int)

    for i, path in enumerate(paths, 1):
        if i % 500 == 0 or i == len(paths):
            print("  hashed %d/%d ..." % (i, len(paths)))
        h, ch = hashes_of(path, args.example_chrome)
        if h is None:
            rows.append([path, "", "", "", "", "", "error-unreadable"])
            stats["errors"] += 1
            continue

        # Duplicate check
        is_dupe, dupe_of = False, ""
        key = str(h)
        if key in seen_exact:
            is_dupe, dupe_of = True, seen_exact[key]
        elif args.dup_threshold > 0:
            for kh, kdest in kept_hashes:
                if hamming(h, kh) <= args.dup_threshold:
                    is_dupe, dupe_of = True, kdest
                    break
        if is_dupe:
            stats["duplicates"] += 1
            dest = ""
            if args.keep_dupes and not args.dry_run:
                d = unique_dest(os.path.join(output, "_duplicates"),
                                os.path.splitext(os.path.basename(path))[0],
                                os.path.splitext(path)[1].lower(),
                                make_dirs=True)
                shutil.copy2(path, d)
                dest = d
            rows.append([path, dest, "", str(h), "", dupe_of,
                         "duplicate"])
            continue
        seen_exact[key] = path

        # Date + similarity (similarity uses the chrome hash when requested)
        dt, dsrc = date_taken(path)
        sim_hash = ch if args.example_chrome else h
        ex_hash = example_chrome if args.example_chrome else example_hash
        similar = (ex_hash is not None
                   and hamming(sim_hash, ex_hash) <= args.similar_threshold)

        ext = os.path.splitext(path)[1].lower()
        stem = dt.strftime("%Y%m%d_%H%M%S")
        try:
            with Image.open(path) as img:
                w, hd = img.size
            dims = "%dx%d" % (w, hd)
        except Exception:
            dims = ""

        if similar:
            folder = os.path.join(output, args.similar_name,
                                  dt.strftime("%Y"), dt.strftime("%m"))
            status = "matched-example"
            stats["matched"] += 1
        else:
            folder = os.path.join(output, dt.strftime("%Y"), dt.strftime("%m"))
            status = "copied"
            stats["copied"] += 1

        dest = unique_dest(folder, stem, ext, make_dirs=not args.dry_run)
        if not args.dry_run:
            shutil.copy2(path, dest)  # copy; original untouched
            kept_hashes.append((h, dest))
        rows.append([path, dest, dt.strftime("%Y-%m-%d %H:%M:%S") + " (%s)" % dsrc,
                     str(h), dims, "", status])

    manifest = os.path.join(output, "manifest.csv")
    if not args.dry_run:
        os.makedirs(output, exist_ok=True)
        with open(manifest, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(
                ["source_path", "destination_path", "date_taken",
                 "perceptual_hash", "dimensions", "duplicate_of", "status"])
            csv.writer(f).writerows(rows)

    print("\nDone%s." % (" (dry run — nothing copied)" if args.dry_run else ""))
    print("  copied:            %d" % stats["copied"])
    print("  matched example:   %d" % stats["matched"])
    print("  duplicates skipped:%d" % stats["duplicates"])
    print("  unreadable:        %d" % stats["errors"])
    if not args.dry_run:
        print("Organized copy: %s" % output)
        print("Manifest: %s" % manifest)
        print("Your originals were not modified.")


if __name__ == "__main__":
    main()
