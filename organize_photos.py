#!/usr/bin/env python3
"""
organize_photos.py — Organize a large photo library directly on your computer.

Reads every photo under --source (e.g. an external drive), then builds a clean,
organized COPY under --output. Your originals are never modified, moved, or
deleted. No uploads, no recompression.

What it does:
  1. Scans all subfolders for photos (JPG, PNG, HEIC, WEBP, TIFF, BMP).
  2. Finds duplicates. A file that is byte-for-byte identical to one already
     seen is listed in the manifest instead of being copied twice. With
     --dup-threshold, photos that merely LOOK the same (a thumbnail, a
     re-saved copy, a burst frame) are grouped too: the largest version is
     kept in the main tree and the rest go to _duplicates/ for review.
  3. Sorts everything by the date the photo was taken (EXIF data) into
     YYYY/MM folders with clean filenames. Photos with no EXIF date at all
     (screenshots, images received through messaging apps, downloads) are
     dated from their filename when it carries one (IMG_20220314_100000,
     Screenshot_20220314-100000, 2022-03-14 10.00.00); otherwise they go
     into their own _review/YYYY/MM tree, dated by the file's modification
     time, so guessed dates never mix with real ones.
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
import re
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
HEIC_EXTS = {".heic", ".heif"}
if HEIC_OK:
    IMAGE_EXTS |= HEIC_EXTS
VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".avi", ".3gp", ".mkv", ".wmv", ".mts"}

# Folders that never hold a person's photos: OS trash and index folders,
# Synology thumbnail caches, and the junk a Mac zip adds.
SKIP_DIRS = {"@eaDir", ".Trashes", ".Spotlight-V100", ".fseventsd",
             ".TemporaryItems", "$RECYCLE.BIN", "System Volume Information",
             "__MACOSX"}

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
    p.add_argument("--dup-threshold", type=int, default=None, metavar="N",
                   help="Also group photos that LOOK the same: perceptual-hash "
                        "distance 0-64. 2-4 catches thumbnails and re-saved "
                        "copies; 6-10 also catches burst frames and small "
                        "edits. The largest version of each group is kept; "
                        "the others are copied to _duplicates/. Off by "
                        "default: only byte-identical files are duplicates.")
    p.add_argument("--undated-folder", default="_review", metavar="NAME",
                   help="Folder for photos that have no EXIF date (default "
                        "_review). They are sorted by file date inside it.")
    p.add_argument("--mix-undated", action="store_true",
                   help="File undated photos into the main YYYY/MM tree by "
                        "file date instead of keeping them separate.")
    p.add_argument("--keep-dupes", action="store_true",
                   help="Also copy byte-identical duplicates into _duplicates/ "
                        "instead of just listing them.")
    p.add_argument("--dry-run", action="store_true",
                   help="Scan and report only; copy nothing.")
    return p.parse_args()


def iter_images(root, skipped, exclude=None):
    """Yield image paths under root, in a stable order.

    Skips hidden files and system folders, and the `exclude` folder (the
    output, when it lives inside the source). Counts what it leaves behind
    in `skipped` so the summary can say so.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in SKIP_DIRS and not d.startswith(".")
            and os.path.join(dirpath, d) != exclude)
        for name in sorted(filenames):
            if name.startswith("."):
                # ._photo.jpg sidecars that macOS leaves on external drives,
                # .DS_Store, and other hidden files.
                skipped["hidden"] += 1
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext in IMAGE_EXTS:
                yield os.path.join(dirpath, name)
            elif ext in HEIC_EXTS:
                skipped["heic"] += 1     # only reached when pillow-heif is absent
            elif ext in VIDEO_EXTS:
                skipped["video"] += 1
            else:
                skipped["other"] += 1


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


# Filenames that carry a timestamp. Phones and photo apps write these, and
# the timestamp is the moment of capture, which makes it more trustworthy
# than an EXIF save time and far better than the file's modification time.
#   IMG_20220314_100000.jpg, PXL_20220314_100000123.jpg, 20220314_100000.jpg
#   Screenshot_20220314-100000.png, Screenshot_20220314-100000_Music.jpg
#   2022-03-14 10.00.00.jpg, 2022-03-14_10-00-00.jpg, 2022-03-14T10:00:00.jpg
FILENAME_DATE_PATTERNS = [
    re.compile(r"(?<!\d)((?:19|20)\d{2})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2})(?!\d{3}\d)"),
    re.compile(r"(?<!\d)((?:19|20)\d{2})-(\d{2})-(\d{2})[ _T](\d{2})[.:\-](\d{2})[.:\-](\d{2})"),
]


def date_from_filename(name):
    """A datetime embedded in a filename, or None. Digits that do not form a
    real calendar date (month 13, hour 25) do not count."""
    for pat in FILENAME_DATE_PATTERNS:
        for m in pat.finditer(name):
            try:
                return datetime(*(int(g) for g in m.groups()))
            except ValueError:
                continue
    return None


def best_date(path, img):
    """(datetime, source) for when the photo was taken, best evidence first.

    source is one of: exif-original (capture time), exif-digitized (scan or
    import time), filename (a timestamp in the file's name), exif-modified
    (last save; weak), file-date (nothing better; the file's modification
    time, which may just be when it was copied).
    """
    dt, dsrc = exif_date(img)
    if dsrc in ("exif-original", "exif-digitized"):
        return dt, dsrc
    from_name = date_from_filename(os.path.basename(path))
    if from_name is not None:
        return from_name, "filename"
    if dt is not None:
        return dt, dsrc
    return datetime.fromtimestamp(os.path.getmtime(path)), "file-date"


def date_taken(path):
    """(datetime, source) for a path; see best_date() for the sources."""
    try:
        with Image.open(path) as img:
            return best_date(path, img)
    except Exception:
        from_name = date_from_filename(os.path.basename(path))
        if from_name is not None:
            return from_name, "filename"
    return datetime.fromtimestamp(os.path.getmtime(path)), "file-date"


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


def content_hash(path):
    """SHA-256 of the file's bytes: two files with the same value are
    identical copies, whatever their names or dates."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def inspect_image(path, need_chrome):
    """Everything the script needs to know about one image, read in a single
    open: content hash, perceptual hash, chrome hash (if asked), dimensions
    and date. Returns None if the file cannot be read as an image."""
    try:
        sha = content_hash(path)
        with Image.open(path) as img:
            h = imagehash.phash(img)
            ch = chrome_hash(img) if need_chrome else None
            w, hgt = img.size
            dt, dsrc = best_date(path, img)
    except Exception:
        return None
    return {"sha": sha, "hash": h, "chrome": ch, "dims": "%dx%d" % (w, hgt),
            "pixels": w * hgt, "date": dt, "date_source": dsrc}


def hamming(a, b):
    return int(a - b)


def hash_int(h):
    """An imagehash as a plain int, so distances are a cheap XOR + popcount."""
    return int(str(h), 16)


def int_hamming(a, b):
    return (a ^ b).bit_count()


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
                    "perceptual_hash", "content_hash", "dimensions",
                    "duplicate_of", "status"]


def scan(todo, need_chrome):
    """Read every image once. Returns one entry per path, in path order."""
    entries = []
    for i, path in enumerate(todo, 1):
        if i % 500 == 0 or i == len(todo):
            print("  scanned %d/%d ..." % (i, len(todo)))
        info = inspect_image(path, need_chrome)
        entry = {"path": path, "ext": os.path.splitext(path)[1].lower(),
                 "status": None, "dest": "", "dupe_of": ""}
        if info is None:
            entry["status"] = "error-unreadable"
        else:
            entry.update(info)
        entries.append(entry)
    return entries


def find_duplicates(entries, args, seen_sha, kept_phash):
    """Decide which entries are duplicates of which.

    Exact duplicates (same bytes) always count. Visual duplicates only count
    when --dup-threshold is given; within each visual group the entry with
    the most pixels is kept and the rest become near-duplicates of it. A
    photo copied by an EARLIER run (seen_sha / kept_phash) is always the
    keeper: it is already on disk and is not moved.
    """
    readable = [e for e in entries if e["status"] is None]

    # 1. Exact duplicates: first occurrence in path order wins.
    for e in readable:
        if e["sha"] in seen_sha:
            e["status"], e["dupe_of"] = "duplicate", seen_sha[e["sha"]]
        else:
            seen_sha[e["sha"]] = e["path"]

    if args.dup_threshold is None:
        return

    # 2. Visual duplicates among what is left. Each group is a list of
    # entries; a group may also be anchored to a photo from an earlier run.
    groups = []   # [int hash of representative, anchor path or None, [entries]]
    for ph, src_path in kept_phash:
        groups.append([ph, src_path, []])
    for e in readable:
        if e["status"] is not None:
            continue
        hi = hash_int(e["hash"])
        for g in groups:
            if int_hamming(hi, g[0]) <= args.dup_threshold:
                g[2].append(e)
                break
        else:
            groups.append([hi, None, [e]])

    for _rep, anchor, members in groups:
        if not members:
            continue
        if anchor is not None:
            keeper_path, losers = anchor, members
        else:
            # Most pixels wins; path order breaks ties, so the result is the
            # same on every run.
            keeper = max(members, key=lambda e: (e["pixels"], -members.index(e)))
            keeper_path = keeper["path"]
            losers = [e for e in members if e is not keeper]
        for e in losers:
            e["status"], e["dupe_of"] = "near-duplicate", keeper_path


def main():
    args = parse_args()
    source = os.path.abspath(args.source)
    output = os.path.abspath(args.output)
    if not os.path.isdir(source):
        sys.exit("Source folder not found: %s" % source)
    if output == source:
        sys.exit("Output must be a different folder from the source.")
    if source.startswith(output + os.sep):
        sys.exit("Output must not contain the source folder.")
    if args.dup_threshold is not None and not 0 <= args.dup_threshold <= 64:
        sys.exit("--dup-threshold must be between 0 and 64.")

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
    skipped = defaultdict(int)
    paths = [p for p in iter_images(source, skipped, exclude=output)
             if os.path.abspath(p) != example_abs]
    print("Found %d image files." % len(paths))
    todo = [p for p in paths if p not in done]
    if done:
        print("Resuming: %d already in manifest, %d still to do."
              % (len(paths) - len(todo), len(todo)))

    # Seed from the previous run so a duplicate of a photo copied last time
    # is still recognised as a duplicate this time.
    seen_sha = {}      # content hash -> source path of the copy that was kept
    kept_phash = []    # (int perceptual hash, source path) of kept copies
    taken = set()      # destination paths planned or already used
    for src_path, row in done.items():
        if row["status"] in ("copied", "matched-example"):
            if row.get("content_hash"):
                seen_sha.setdefault(row["content_hash"], src_path)
            if row.get("perceptual_hash"):
                kept_phash.append((int(row["perceptual_hash"], 16), src_path))
        if row["destination_path"]:
            taken.add(row["destination_path"])

    # Step 1: read every photo. Step 2: decide duplicates with the whole
    # picture in hand, so the best copy of each photo can be chosen rather
    # than whichever one happened to be seen first.
    entries = scan(todo, args.example_chrome)
    find_duplicates(entries, args, seen_sha, kept_phash)

    # Step 3: copy and record, one line at a time.
    stats = defaultdict(int)
    os.makedirs(output, exist_ok=True)
    fresh = args.dry_run or not done
    with open(manifest, "w" if fresh else "a", newline="",
              encoding="utf-8") as mf:
        writer = csv.writer(mf)
        if fresh:
            writer.writerow(MANIFEST_COLUMNS)

        def record(e, date_str=""):
            writer.writerow([e["path"], e["dest"], date_str,
                             str(e.get("hash", "")), e.get("sha", ""),
                             e.get("dims", ""), e["dupe_of"], e["status"]])
            mf.flush()   # each line lands on disk as soon as it is decided

        def copy(e):
            """Copy e to e['dest']; on failure mark it and return False."""
            if args.dry_run:
                return True
            try:
                copy_atomic(e["path"], e["dest"])
                return True
            except OSError as err:
                print("  could not copy %s: %s" % (e["path"], err),
                      file=sys.stderr)
                stats["copy_errors"] += 1
                e["status"] = "error-copy"
                return False

        for i, e in enumerate(entries, 1):
            if i % 500 == 0 or i == len(entries):
                print("  copied %d/%d ..." % (i, len(entries)))
            if e["status"] == "error-unreadable":
                stats["errors"] += 1
                record(e)
                continue

            if e["status"] in ("duplicate", "near-duplicate"):
                stats[e["status"]] += 1
                # Exact duplicates are only listed unless --keep-dupes; near
                # duplicates are always kept for review, because "looks the
                # same" is a judgement the owner may want to check.
                if e["status"] == "near-duplicate" or args.keep_dupes:
                    e["dest"] = unique_dest(
                        os.path.join(output, "_duplicates"),
                        os.path.splitext(os.path.basename(e["path"]))[0],
                        e["ext"], taken)
                    copy(e)
                record(e)
                continue

            # Date + similarity (similarity uses the chrome hash when requested)
            dt, dsrc = e["date"], e["date_source"]
            sim_hash = e["chrome"] if args.example_chrome else e["hash"]
            ex_hash = example_chrome if args.example_chrome else example_hash
            similar = (ex_hash is not None
                       and hamming(sim_hash, ex_hash) <= args.similar_threshold)

            stem = dt.strftime("%Y%m%d_%H%M%S")
            undated = dsrc == "file-date" and not args.mix_undated
            if similar:
                folder = os.path.join(output, args.similar_name,
                                      dt.strftime("%Y"), dt.strftime("%m"))
                e["status"] = "matched-example"
            elif undated:
                # No real date: keep these out of the main timeline so a
                # download date never masquerades as the day a photo was taken.
                folder = os.path.join(output, args.undated_folder,
                                      dt.strftime("%Y"), dt.strftime("%m"))
                e["status"] = "copied"
            else:
                folder = os.path.join(output, dt.strftime("%Y"), dt.strftime("%m"))
                e["status"] = "copied"
            e["dest"] = unique_dest(folder, stem, e["ext"], taken)
            date_str = dt.strftime("%Y-%m-%d %H:%M:%S") + " (%s)" % dsrc
            if copy(e):
                stats["matched" if similar else ("undated" if undated else "copied")] += 1
            record(e, date_str)

    print("\nDone%s." % (" (dry run: nothing copied)" if args.dry_run else ""))
    if done:
        print("  done in a previous run: %d" % (len(paths) - len(todo)))
    print("  copied:            %d" % stats["copied"])
    if not args.mix_undated:
        print("  copied, no EXIF date: %d (in %s/, sorted by file date)"
              % (stats["undated"], args.undated_folder))
    print("  matched example:   %d" % stats["matched"])
    print("  duplicates skipped:%d" % stats["duplicate"])
    if args.dup_threshold is not None:
        print("  near-duplicates:   %d (in _duplicates/)" % stats["near-duplicate"])
    print("  unreadable:        %d" % stats["errors"])
    if stats["copy_errors"]:
        print("  COPY FAILURES:     %d (see error-copy rows in the manifest)"
              % stats["copy_errors"])
    if skipped["heic"]:
        print("  NOT INCLUDED: %d HEIC/HEIF photos. Install the optional "
              "package (pip install -r requirements-optional.txt) and run "
              "again to add them." % skipped["heic"])
    if skipped["video"]:
        print("  NOT INCLUDED: %d video files. This tool organizes photos "
              "only; videos stay where they are." % skipped["video"])
    if skipped["hidden"]:
        print("  ignored %d hidden/system files (names starting with '.')"
              % skipped["hidden"])
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
