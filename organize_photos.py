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
  5. Writes a manifest.csv describing where everything went, one line at a
     time as it works, so an interrupted run still leaves a complete record.
     A dry run writes manifest_dryrun.csv instead, with the destinations a
     real run would use. Re-running after an interruption picks up where the
     manifest left off instead of copying everything again.

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

# EXIF date tags, in order of preference. The first two live in the Exif
# sub-IFD, which Pillow's getexif() does NOT include: it has to be opened with
# get_ifd(). DateTime (306) is in the top-level IFD0 and is the time the file
# was last saved, not the time the photo was taken, so it is the last resort.
EXIF_IFD_POINTER = 34665
EXIF_DATETIME_ORIGINAL = 36867   # when the shutter fired
EXIF_DATETIME_DIGITIZED = 36868  # when it was scanned or imported
EXIF_DATETIME = 306              # when the file was last saved


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


def parse_exif_datetime(val):
    """Parse an EXIF 'YYYY:MM:DD HH:MM:SS' string; None if absent or junk.

    Some cameras pad the string with NUL bytes, and some write all zeros as a
    placeholder; both must fall through to the next tag rather than crash.
    """
    if isinstance(val, bytes):
        val = val.decode("ascii", "ignore")
    if not isinstance(val, str):
        return None
    val = val.strip("\x00 \t\r\n")
    try:
        return datetime.strptime(val, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def date_taken(path):
    """Return (datetime, source) for when the photo was taken.

    source is one of: exif-original (capture time), exif-digitized (scan or
    import time), exif-modified (last save; weakest), file-date (no EXIF at
    all; the file's modification time, which may just be when it was copied).
    """
    try:
        with Image.open(path) as img:
            dt, dsrc = exif_date(img)
            if dt is not None:
                return dt, dsrc
    except Exception:
        pass
    ts = os.path.getmtime(path)
    return datetime.fromtimestamp(ts), "file-date"


def exif_date(img):
    """(datetime, source) from an already-open image's EXIF; (None, None) if
    it has no usable date. See date_taken() for the meaning of source."""
    try:
        exif = img.getexif()
        sub = exif.get_ifd(EXIF_IFD_POINTER)
        candidates = (
            (sub, EXIF_DATETIME_ORIGINAL, "exif-original"),
            (sub, EXIF_DATETIME_DIGITIZED, "exif-digitized"),
            (exif, EXIF_DATETIME, "exif-modified"),
        )
        for table, tag, label in candidates:
            dt = parse_exif_datetime(table.get(tag))
            if dt is not None:
                return dt, label
    except Exception:
        pass
    return None, None


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


def inspect_image(path, need_chrome):
    """Everything the script needs to know about one image, read in a single
    open: perceptual hash, chrome hash (if asked), dimensions and date.
    Returns None if the file cannot be read as an image."""
    try:
        with Image.open(path) as img:
            h = imagehash.phash(img)
            ch = chrome_hash(img) if need_chrome else None
            dims = "%dx%d" % img.size
            dt, dsrc = exif_date(img)
    except Exception:
        return None
    if dt is None:
        dt, dsrc = datetime.fromtimestamp(os.path.getmtime(path)), "file-date"
    return {"hash": h, "chrome": ch, "dims": dims, "date": dt,
            "date_source": dsrc}


def hamming(a, b):
    return int(a - b)


def unique_dest(folder, stem, ext, taken):
    """Destination path that never overwrites: adds _2, _3, ... as needed.

    `taken` is the set of destinations already planned in this run. Checking
    it as well as the disk means a dry run numbers collisions exactly as the
    real run would, instead of showing every clash as the same name.
    """
    candidate = os.path.join(folder, stem + ext)
    n = 2
    while candidate in taken or os.path.exists(candidate):
        candidate = os.path.join(folder, "%s_%d%s" % (stem, n, ext))
        n += 1
    taken.add(candidate)
    return candidate


def load_manifest(path):
    """Rows of an existing manifest keyed by source path, for resuming."""
    done = {}
    if not os.path.isfile(path):
        return done
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            done[row["source_path"]] = row
    return done


def copy_atomic(src, dest):
    """Copy through a temporary name so an interrupted copy never leaves a
    half-written file under the final name."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    shutil.copy2(src, tmp)
    os.replace(tmp, dest)


MANIFEST_COLUMNS = ["source_path", "destination_path", "date_taken",
                    "perceptual_hash", "dimensions", "duplicate_of", "status"]


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
        info = inspect_image(example_abs, args.example_chrome)
        if info is None:
            sys.exit("Could not read example image: %s" % example_abs)
        example_hash, example_chrome = info["hash"], info["chrome"]
        print("Example image loaded; similarity threshold = %d%s"
              % (args.similar_threshold,
                 " (UI-chrome matching)" if args.example_chrome else ""))

    # The manifest is the record of what has been done. A real run appends
    # to it and skips anything already listed, which is what makes re-running
    # after an interruption safe. A dry run writes its own file and never
    # reads it back, so a preview can be repeated freely.
    manifest = os.path.join(
        output, "manifest_dryrun.csv" if args.dry_run else "manifest.csv")
    done = {} if args.dry_run else load_manifest(manifest)

    print("Scanning %s ..." % source)
    paths = [p for p in iter_images(source)
             if os.path.abspath(p) != example_abs]
    print("Found %d image files." % len(paths))
    todo = [p for p in paths if p not in done]
    if done:
        print("Resuming: %d already in manifest, %d still to do."
              % (len(paths) - len(todo), len(todo)))

    kept_hashes = []     # (hash, dest) of copied images, for near-dupe checks
    seen_exact = {}      # str(hash) -> first source path
    taken = set()        # destination paths planned or already used
    stats = defaultdict(int)

    # Seed from the previous run so a duplicate of a photo copied last time
    # is still recognised as a duplicate this time.
    for src_path, row in done.items():
        if row["status"] in ("copied", "matched-example") and row["perceptual_hash"]:
            seen_exact.setdefault(row["perceptual_hash"], src_path)
            if args.dup_threshold > 0:
                kept_hashes.append((imagehash.hex_to_hash(row["perceptual_hash"]),
                                    row["destination_path"]))
        if row["destination_path"]:
            taken.add(row["destination_path"])

    os.makedirs(output, exist_ok=True)
    fresh = args.dry_run or not done
    with open(manifest, "w" if fresh else "a", newline="",
              encoding="utf-8") as mf:
        writer = csv.writer(mf)
        if fresh:
            writer.writerow(MANIFEST_COLUMNS)

        def record(row):
            writer.writerow(row)
            mf.flush()   # each line lands on disk as soon as it is decided

        for i, path in enumerate(todo, 1):
            if i % 500 == 0 or i == len(todo):
                print("  processed %d/%d ..." % (i, len(todo)))
            info = inspect_image(path, args.example_chrome)
            if info is None:
                record([path, "", "", "", "", "", "error-unreadable"])
                stats["errors"] += 1
                continue
            h, ch = info["hash"], info["chrome"]
            key = str(h)
            ext = os.path.splitext(path)[1].lower()

            # Duplicate check
            is_dupe, dupe_of = False, ""
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
                if args.keep_dupes:
                    dest = unique_dest(os.path.join(output, "_duplicates"),
                                       os.path.splitext(os.path.basename(path))[0],
                                       ext, taken)
                    if not args.dry_run:
                        try:
                            copy_atomic(path, dest)
                        except OSError as e:
                            print("  could not copy %s: %s" % (path, e),
                                  file=sys.stderr)
                            stats["copy_errors"] += 1
                            record([path, dest, "", key, info["dims"], dupe_of,
                                    "error-copy"])
                            continue
                record([path, dest, "", key, info["dims"], dupe_of, "duplicate"])
                continue
            seen_exact[key] = path

            # Date + similarity (similarity uses the chrome hash when requested)
            dt, dsrc = info["date"], info["date_source"]
            sim_hash = ch if args.example_chrome else h
            ex_hash = example_chrome if args.example_chrome else example_hash
            similar = (ex_hash is not None
                       and hamming(sim_hash, ex_hash) <= args.similar_threshold)

            stem = dt.strftime("%Y%m%d_%H%M%S")
            if similar:
                folder = os.path.join(output, args.similar_name,
                                      dt.strftime("%Y"), dt.strftime("%m"))
                status = "matched-example"
            else:
                folder = os.path.join(output, dt.strftime("%Y"), dt.strftime("%m"))
                status = "copied"

            dest = unique_dest(folder, stem, ext, taken)
            date_str = dt.strftime("%Y-%m-%d %H:%M:%S") + " (%s)" % dsrc
            if not args.dry_run:
                try:
                    copy_atomic(path, dest)  # copy; original untouched
                except OSError as e:
                    print("  could not copy %s: %s" % (path, e), file=sys.stderr)
                    stats["copy_errors"] += 1
                    record([path, dest, date_str, key, info["dims"], "",
                            "error-copy"])
                    continue
            kept_hashes.append((h, dest))
            stats["matched" if similar else "copied"] += 1
            record([path, dest, date_str, key, info["dims"], "", status])

    print("\nDone%s." % (" (dry run: nothing copied)" if args.dry_run else ""))
    if done:
        print("  done in a previous run: %d" % (len(paths) - len(todo)))
    print("  copied:            %d" % stats["copied"])
    print("  matched example:   %d" % stats["matched"])
    print("  duplicates skipped:%d" % stats["duplicates"])
    print("  unreadable:        %d" % stats["errors"])
    if stats["copy_errors"]:
        print("  COPY FAILURES:     %d (see error-copy rows in the manifest)"
              % stats["copy_errors"])
    if args.dry_run:
        print("Preview of where everything would go: %s" % manifest)
    else:
        print("Organized copy: %s" % output)
        print("Manifest: %s" % manifest)
        print("Your originals were not modified.")
    if stats["copy_errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
