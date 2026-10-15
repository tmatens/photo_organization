#!/usr/bin/env python3
"""
organize_photos.py — Organize a large photo and video library on your computer.

Reads every photo under --source (e.g. an external drive; repeat the option
to combine several drives), then builds a clean, organized COPY under
--output. Your originals are never modified, moved, or deleted. No uploads,
no recompression.

What it does:
  1. Scans all subfolders for photos (JPG, PNG, HEIC, WEBP, TIFF, BMP) and
     videos (MOV, MP4, M4V, 3GP, AVI, MKV, WMV, MTS).
  2. Finds duplicates. A file that is byte-for-byte identical to one already
     seen is listed in the manifest instead of being copied twice. With
     --dup-threshold, photos that merely LOOK the same (a thumbnail, a
     re-saved copy, a burst frame) are grouped too: the largest version is
     kept in the main tree and the rest go to _duplicates/ for review.
  3. Sorts everything by the date the photo was taken (EXIF data) into
     YYYY/MM folders with clean filenames. Photos with no EXIF date at all
     (images received through messaging apps, downloads) are dated from
     their filename when it carries one (IMG_20220314_100000,
     2022-03-14 10.00.00); otherwise they go into a _review/YYYY/MM tree,
     dated by the file's modification time, so guessed dates never mix
     with real ones. Screenshots (any PNG, or a file named Screenshot...)
     always go to _review, whatever date they carry: cameras never write
     PNG, so a PNG is a screenshot, a meme or a graphic, not a photo.
  4. Writes a manifest.csv describing where everything went, one line at a
     time as it works, so an interrupted run still leaves a complete record.
     A dry run writes manifest_dryrun.csv instead, with the destinations a
     real run would use. Re-running after an interruption picks up where the
     manifest left off instead of copying everything again.

Requires: Python 3.9+, plus:  pip install pillow imagehash
Optional (for iPhone HEIC photos):  pip install pillow-heif

Usage:
  python organize_photos.py --source E:\\ --source F:\\ --output D:\\Organized
  python organize_photos.py --source /Volumes/MyDrive --output ~/Organized --dry-run
"""

import argparse
import csv
import hashlib
import os
import re
import shutil
import struct
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

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
# Formats built from QuickTime/MP4 "boxes", which carry a creation time.
QUICKTIME_EXTS = {".mov", ".mp4", ".m4v", ".3gp"}

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
    p = argparse.ArgumentParser(description="Build an organized, deduplicated COPY of a photo and video library. Originals are never changed.")
    p.add_argument("--source", required=True, action="append", metavar="FOLDER",
                   help="Folder to scan (e.g. an external drive). Repeat the "
                        "option to combine several drives into one library; "
                        "duplicates are found across all of them.")
    p.add_argument("--output", required=True,
                   help="Folder where the organized copy will be built.")
    p.add_argument("--dup-threshold", type=int, default=None, metavar="N",
                   help="Also group photos that LOOK the same: perceptual-hash "
                        "distance 0-64. 2-4 catches thumbnails and re-saved "
                        "copies; 6-10 also catches burst frames and small "
                        "edits. The largest version of each group is kept; "
                        "the others are copied to _duplicates/. Off by "
                        "default: only byte-identical files are duplicates.")
    p.add_argument("--review-folder", default="_review", metavar="NAME",
                   help="Folder for screenshots and for photos with no date "
                        "(default _review). Sorted by date inside it.")
    p.add_argument("--mix-undated", action="store_true",
                   help="File undated photos into the main YYYY/MM tree by "
                        "file date instead of keeping them separate.")
    p.add_argument("--png-is-photo", action="store_true",
                   help="Treat PNG files and files named Screenshot... like "
                        "any other photo instead of sending them to the "
                        "review folder.")
    p.add_argument("--keep-dupes", action="store_true",
                   help="Also copy byte-identical duplicates into _duplicates/ "
                        "instead of just listing them.")
    p.add_argument("--dry-run", action="store_true",
                   help="Scan and report only; copy nothing.")
    return p.parse_args()


def longpath(path):
    """The path in the form Windows file APIs accept beyond 260 characters.

    Deep folder trees on backup drives routinely exceed that limit, and
    without this prefix Windows reports the file as missing. Other platforms
    return the path unchanged.
    """
    if os.name != "nt" or path.startswith("\\\\?\\"):
        return path
    if path.startswith("\\\\"):          # \\server\share -> \\?\UNC\server\share
        return "\\\\?\\UNC\\" + path[2:]
    return "\\\\?\\" + path


def plainpath(path):
    """Undo longpath() for anything a person will read."""
    if path.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path[8:]
    if path.startswith("\\\\?\\"):
        return path[4:]
    return path


def is_inside(path, folder, pathmod=os.path):
    """True if path is folder itself or anything under it. Works for drive
    roots like E:\\ (naive string checks double the backslash and fail) and
    for paths on different drives (never inside each other)."""
    try:
        common = pathmod.commonpath([path, folder])
    except ValueError:
        return False
    return pathmod.normcase(common) == pathmod.normcase(folder)


def iter_images(root, skipped, exclude=None):
    """Yield image paths under root, in a stable order.

    Skips hidden files and system folders, and the `exclude` folder (the
    output, when it lives inside the source). Counts what it leaves behind
    in `skipped` so the summary can say so.
    """
    for dirpath, dirnames, filenames in os.walk(longpath(root)):
        dirpath = plainpath(dirpath)
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
            if ext in IMAGE_EXTS or ext in VIDEO_EXTS:
                yield os.path.join(dirpath, name)
            elif ext in HEIC_EXTS:
                skipped["heic"] += 1     # only reached when pillow-heif is absent
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


def is_screenshot(path):
    """Screenshots are never camera photos: cameras and phones write JPEG or
    HEIC, so a PNG is a screenshot, a meme or a graphic. Samsung phones save
    screenshots as JPEG but name them Screenshot_... ."""
    name = os.path.basename(path).lower()
    return (name.endswith(".png")
            or name.startswith("screenshot") or name.startswith("screen shot"))


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
    return datetime.fromtimestamp(os.path.getmtime(longpath(path))), "file-date"


def date_taken(path):
    """(datetime, source) for a path; see best_date() for the sources."""
    try:
        with Image.open(longpath(path)) as img:
            return best_date(path, img)
    except Exception:
        from_name = date_from_filename(os.path.basename(path))
        if from_name is not None:
            return from_name, "filename"
    return datetime.fromtimestamp(os.path.getmtime(longpath(path))), "file-date"


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


def content_hash(path):
    """SHA-256 of the file's bytes: two files with the same value are
    identical copies, whatever their names or dates."""
    h = hashlib.sha256()
    with open(longpath(path), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def quicktime_creation_time(path):
    """Creation time stored in a MOV/MP4 file's 'mvhd' box, as local time;
    None if the file has none or is not a QuickTime/MP4 container.

    The file is a sequence of boxes (size, type, payload). The movie header
    lives inside 'moov', which iPhones usually write at the END of the file,
    so the top level is walked by seeking over each box rather than reading
    the video data. The time is seconds since 1904-01-01 UTC.
    """
    try:
        with open(longpath(path), "rb") as f:
            f.seek(0, 2)
            total = f.tell()

            def boxes(start, end):
                pos = start
                while pos + 8 <= end:
                    f.seek(pos)
                    hdr = f.read(8)
                    if len(hdr) < 8:
                        return
                    size, kind = struct.unpack(">I4s", hdr)
                    hdr_len = 8
                    if size == 1:                      # 64-bit size follows
                        size = struct.unpack(">Q", f.read(8))[0]
                        hdr_len = 16
                    elif size == 0:                    # box runs to end of file
                        size = end - pos
                    if size < hdr_len:
                        return
                    yield kind, pos + hdr_len, pos + size
                    pos += size

            for kind, start, end in boxes(0, total):
                if kind != b"moov":
                    continue
                for kind2, start2, _end2 in boxes(start, end):
                    if kind2 != b"mvhd":
                        continue
                    f.seek(start2)
                    version = f.read(1)[0]
                    f.seek(start2 + 4)
                    if version == 1:
                        secs = struct.unpack(">Q", f.read(8))[0]
                    else:
                        secs = struct.unpack(">I", f.read(4))[0]
                    if secs == 0:
                        return None
                    epoch = datetime(1904, 1, 1, tzinfo=timezone.utc)
                    return (epoch + timedelta(seconds=secs)).astimezone().replace(tzinfo=None)
    except (OSError, struct.error, OverflowError, ValueError):
        pass
    return None


def inspect_video(path):
    """What the script needs to know about a video: content hash and date.
    Videos have no perceptual hash, so they are deduplicated by content only."""
    try:
        sha = content_hash(path)
    except OSError:
        return None
    dt = date_from_filename(os.path.basename(path))
    dsrc = "filename"
    if dt is None and os.path.splitext(path)[1].lower() in QUICKTIME_EXTS:
        dt = quicktime_creation_time(path)
        dsrc = "video-metadata"
    if dt is None:
        dt, dsrc = datetime.fromtimestamp(os.path.getmtime(longpath(path))), "file-date"
    return {"kind": "video", "sha": sha, "hash": None,
            "dims": "", "pixels": 0, "date": dt, "date_source": dsrc}


def inspect_file(path):
    """inspect_image() or inspect_video() depending on the extension."""
    if os.path.splitext(path)[1].lower() in VIDEO_EXTS:
        return inspect_video(path)
    return inspect_image(path)


def inspect_image(path):
    """Everything the script needs to know about one image, read in a single
    open: content hash, perceptual hash, dimensions and date. Returns None
    if the file cannot be read as an image."""
    try:
        sha = content_hash(path)
        with Image.open(longpath(path)) as img:
            h = imagehash.phash(img)
            w, hgt = img.size
            dt, dsrc = best_date(path, img)
    except Exception:
        return None
    return {"kind": "image", "sha": sha, "hash": h,
            "dims": "%dx%d" % (w, hgt), "pixels": w * hgt, "date": dt,
            "date_source": dsrc}


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
    while candidate in taken or os.path.exists(longpath(candidate)):
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
    os.makedirs(longpath(os.path.dirname(dest)), exist_ok=True)
    tmp = dest + ".part"
    shutil.copy2(longpath(src), longpath(tmp))
    os.replace(longpath(tmp), longpath(dest))


MANIFEST_COLUMNS = ["source_path", "destination_path", "date_taken",
                    "perceptual_hash", "content_hash", "dimensions",
                    "duplicate_of", "status"]


def scan(todo):
    """Read every file once. Returns one entry per path, in path order."""
    entries = []
    for i, path in enumerate(todo, 1):
        if i % 500 == 0 or i == len(todo):
            print("  scanned %d/%d ..." % (i, len(todo)))
        info = inspect_file(path)
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
        if e["status"] is not None or e["hash"] is None:   # videos: no visual hash
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
    sources = [os.path.abspath(s) for s in args.source]
    output = os.path.abspath(args.output)
    for source in sources:
        if not os.path.isdir(source):
            sys.exit("Source folder not found: %s" % source)
        if os.path.normcase(output) == os.path.normcase(source):
            sys.exit("Output must be a different folder from the source.")
        if is_inside(source, output):
            sys.exit("Output must not contain a source folder: %s" % source)
    if args.dup_threshold is not None and not 0 <= args.dup_threshold <= 64:
        sys.exit("--dup-threshold must be between 0 and 64.")

    # The manifest is the record of what has been done. A real run appends
    # to it and skips anything already listed, which is what makes re-running
    # after an interruption safe. A dry run writes its own file and never
    # reads it back, so a preview can be repeated freely.
    manifest = os.path.join(
        output, "manifest_dryrun.csv" if args.dry_run else "manifest.csv")
    done = {} if args.dry_run else load_manifest(manifest)

    skipped = defaultdict(int)
    paths = []
    for source in sources:
        print("Scanning %s ..." % source)
        paths.extend(iter_images(source, skipped, exclude=output))
    print("Found %d photo and video files." % len(paths))
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
        if row["status"] == "copied":
            if row.get("content_hash"):
                seen_sha.setdefault(row["content_hash"], src_path)
            if row.get("perceptual_hash"):
                kept_phash.append((int(row["perceptual_hash"], 16), src_path))
        if row["destination_path"]:
            taken.add(row["destination_path"])

    # Step 1: read every photo. Step 2: decide duplicates with the whole
    # picture in hand, so the best copy of each photo can be chosen rather
    # than whichever one happened to be seen first.
    entries = scan(todo)
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
            phash = e.get("hash")
            writer.writerow([e["path"], e["dest"], date_str,
                             "" if phash is None else str(phash), e.get("sha", ""),
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

            # Where does it go?
            dt, dsrc = e["date"], e["date_source"]
            stem = dt.strftime("%Y%m%d_%H%M%S")
            undated = dsrc == "file-date" and not args.mix_undated
            screenshot = (e["kind"] == "image" and not args.png_is_photo
                          and is_screenshot(e["path"]))
            if screenshot or undated:
                # Not a camera photo, or no real date: keep these out of the
                # main timeline, but still sorted by month for browsing.
                folder = os.path.join(output, args.review_folder,
                                      dt.strftime("%Y"), dt.strftime("%m"))
                e["status"] = "copied"
                bucket = "screenshots" if screenshot else "undated"
            else:
                folder = os.path.join(output, dt.strftime("%Y"), dt.strftime("%m"))
                e["status"] = "copied"
                bucket = "copied"
            e["dest"] = unique_dest(folder, stem, e["ext"], taken)
            date_str = dt.strftime("%Y-%m-%d %H:%M:%S") + " (%s)" % dsrc
            if copy(e):
                stats[bucket] += 1
                if e["kind"] == "video":
                    stats["videos"] += 1
            record(e, date_str)

    print("\nDone%s." % (" (dry run: nothing copied)" if args.dry_run else ""))
    if done:
        print("  done in a previous run: %d" % (len(paths) - len(todo)))
    print("  copied:            %d" % stats["copied"])
    print("  to %s/: %d screenshots, %d with no date"
          % (args.review_folder, stats["screenshots"], stats["undated"]))
    print("  (videos among the above: %d)" % stats["videos"])
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
