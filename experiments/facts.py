#!/usr/bin/env python3
"""
facts.py: the table of facts that need no model.

Step 2b of docs/categorization-plan.md. For every sampled file in one half
this works out a row of plain facts using Pillow alone: some about the file
(type, pixel size, EXIF fields, name pattern, folder, bytes per pixel) and
some about the pixels (how much is near-white, how many colours, how much
is perfectly flat, whether edges fall in rows like lines of text, whether
there is a uniform band at the top or bottom).

The table names real files, so it is written to eval_data/facts/ and never
leaves it. fact_review.py reads it to find which facts separate each label.

Usage:
  python experiments/facts.py --half tuning
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

from PIL import ExifTags, Image, ImageChops, ImageFilter, ImageOps, ImageStat  # noqa: E402

# Pixel sizes of common phone, tablet and computer screens, short side
# first. A file whose size matches one, either way up, was very likely
# captured from a screen: cameras do not produce these sizes.
SCREEN_SIZES = {
    # iPhone
    (640, 960), (640, 1136), (750, 1334), (1242, 2208), (1125, 2436), (828, 1792),
    (1242, 2688), (1080, 2340), (1170, 2532), (1284, 2778), (1179, 2556), (1290, 2796),
    (1206, 2622), (1320, 2868),
    # Android phones
    (720, 1280), (1080, 1920), (1080, 2160), (1080, 2220), (1080, 2280), (1080, 2400),
    (1080, 2408), (1080, 2412), (1080, 2424), (1008, 2244), (1344, 2992), (1440, 2560),
    (1440, 2960), (1440, 3040), (1440, 3088), (1440, 3120), (1440, 3200),
    # iPad
    (768, 1024), (1536, 2048), (1620, 2160), (1640, 2360), (1668, 2224), (1668, 2388),
    (2048, 2732),
    # Computers
    (720, 1280), (768, 1366), (800, 1280), (900, 1440), (864, 1536), (900, 1600),
    (1050, 1680), (1200, 1920), (1440, 2560), (1600, 2560), (1664, 2560), (1800, 2880),
    (1964, 3024), (2160, 3840), (2234, 3456),
}

# Words in a folder path that say where a file came from.
FOLDER_HINTS = (
    ("screenshots", ("screenshot", "screen shot", "screencapture", "captura")),
    ("messaging", ("whatsapp", "telegram", "signal", "messenger", "wechat", "viber", "mms", "sms")),
    ("downloads", ("download",)),
    ("social", ("instagram", "facebook", "snapchat", "tiktok", "twitter", "pinterest", "reddit")),
    ("camera", ("dcim", "camera")),
    ("scans", ("scan",)),
)

# What a file name looks like once its digits are hidden. Order matters:
# the first pattern that matches wins.
NAME_PATTERNS = (
    ("screenshot", re.compile(r"^screen ?shot", re.I)),
    ("messaging", re.compile(r"^(IMG|VID)-\d{8}-WA\d+|^signal-|^received_|^FB_IMG_", re.I)),
    ("camera", re.compile(r"^(IMG_\d{4}|IMG_E\d{4}|DSC_?\d{4}|DSCN\d{4}|PXL_\d{8}_\d+"
                          r"|\d{8}_\d{6}|IMG_\d{8}_\d{6}|P\d{7}|MVIMG_)", re.I)),
    ("uuid", re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-", re.I)),
    ("digits", re.compile(r"^\d+$")),
    ("web", re.compile(r"[?&=%]|^image\d*$|^download|^unnamed", re.I)),
)

FACT_COLUMNS = [
    "id", "type", "width", "height", "megapixels", "aspect", "screen_sized",
    "has_make", "has_model", "has_lens", "has_flash", "has_date_taken", "software",
    "name_pattern", "folder_hint", "folder_depth", "bytes_per_pixel",
    "near_white", "near_black", "distinct_colours", "colourfulness", "flat_share",
    "quiet_rows", "row_changes", "top_band_spread", "bottom_band_spread",
]

WORK_EDGE = 384     # pixel facts are measured on a copy this many pixels long


def name_pattern(file_name):
    """The kind of name a file has: camera, screenshot, messaging, uuid,
    digits, web or other."""
    stem = os.path.splitext(file_name)[0]
    for kind, pattern in NAME_PATTERNS:
        if pattern.search(stem):
            return kind
    return "other"


def folder_hint(folder):
    """What the original folder path suggests about where a file came from,
    or 'none'."""
    lowered = folder.lower()
    for hint, words in FOLDER_HINTS:
        if any(word in lowered for word in words):
            return hint
    return "none"


def exif_facts(img):
    """Which EXIF fields a camera would write are present, and the first
    word of the Software field (the app that last saved the file)."""
    facts = {"has_make": "no", "has_model": "no", "has_lens": "no", "has_flash": "no",
             "has_date_taken": "no", "software": ""}
    try:
        exif = img.getexif()
        sub = exif.get_ifd(ExifTags.IFD.Exif)
    except Exception:
        return facts
    if str(exif.get(ExifTags.Base.Make, "")).strip():
        facts["has_make"] = "yes"
    if str(exif.get(ExifTags.Base.Model, "")).strip():
        facts["has_model"] = "yes"
    if sub.get(ExifTags.Base.LensModel) or sub.get(ExifTags.Base.LensSpecification):
        facts["has_lens"] = "yes"
    if sub.get(ExifTags.Base.Flash) is not None:
        facts["has_flash"] = "yes"
    if sub.get(ExifTags.Base.DateTimeOriginal):
        facts["has_date_taken"] = "yes"
    software = str(exif.get(ExifTags.Base.Software, "")).strip().split(" ")[0]
    facts["software"] = re.sub(r"[^A-Za-z]", "", software).lower()[:20]
    return facts


def share(histogram, low, high, total):
    """Share of pixels whose value falls in low..high, from a 256-bin histogram."""
    return sum(histogram[low:high + 1]) / total if total else 0.0


def pixel_facts(img):
    """Facts about what the picture looks like, from a small copy.

    The copy is made by picking pixels, not blending them, so areas of
    perfectly flat colour stay perfectly flat and camera noise stays noisy."""
    w, h = img.size
    scale = WORK_EDGE / max(w, h)
    if scale < 1:
        img = img.resize((max(8, round(w * scale)), max(8, round(h * scale))), Image.NEAREST)
    w, h = img.size
    pixels = w * h
    grey = img.convert("L")

    # Near-white and near-black: the darkest channel is bright, or the
    # brightest channel is dark.
    r, g, b = img.split()
    darkest = ImageChops.darker(ImageChops.darker(r, g), b)
    brightest = ImageChops.lighter(ImageChops.lighter(r, g), b)
    near_white = share(darkest.histogram(), 240, 255, pixels)
    near_black = share(brightest.histogram(), 0, 15, pixels)

    colours = img.getcolors(maxcolors=pixels)
    distinct = len(colours) / pixels

    colourfulness = ImageStat.Stat(img.convert("HSV").split()[1]).mean[0] / 255

    # Perfectly flat: a pixel identical to its neighbour on the right and
    # the one below. Screens and graphics have large areas like this; a
    # camera sensor never does, outside a blown-out sky.
    right = ImageChops.difference(img.crop((0, 0, w - 1, h - 1)), img.crop((1, 0, w, h - 1)))
    below = ImageChops.difference(img.crop((0, 0, w - 1, h - 1)), img.crop((0, 1, w - 1, h)))
    # Take the largest difference of the three channels: a weighted grey
    # would round a tiny colour difference down to nothing.
    cr, cg, cb = ImageChops.lighter(right, below).split()
    change = ImageChops.lighter(ImageChops.lighter(cr, cg), cb)
    flat_share = change.histogram()[0] / ((w - 1) * (h - 1))

    # Lines of text: rows full of edges separated by rows with none. Squash
    # the edge picture to one column, giving the amount of edge per row,
    # then count how many rows are quiet and how often quiet and busy swap.
    edges = grey.filter(ImageFilter.FIND_EDGES).crop((1, 1, w - 1, h - 1))
    per_row = list(edges.resize((1, edges.height), Image.BOX).tobytes())
    peak = max(per_row) or 1
    quiet = [value < 0.15 * peak for value in per_row]
    quiet_rows = sum(quiet) / len(quiet)
    changes = sum(1 for a, b2 in zip(quiet, quiet[1:]) if a != b2)
    row_changes = 100 * changes / len(quiet)

    # A status bar or a navigation bar is a strip of nearly one colour.
    band = max(2, round(h * 0.04))
    top = ImageStat.Stat(grey.crop((0, 0, w, band))).stddev[0]
    bottom = ImageStat.Stat(grey.crop((0, h - band, w, h))).stddev[0]

    return {"near_white": near_white, "near_black": near_black, "distinct_colours": distinct,
            "colourfulness": colourfulness, "flat_share": flat_share, "quiet_rows": quiet_rows,
            "row_changes": row_changes, "top_band_spread": top, "bottom_band_spread": bottom}


def compute(path, folder=""):
    """Every fact about one file, as a dict. `folder` is the folder the file
    originally came from, relative to its source."""
    path = str(path)
    with Image.open(path) as img:
        facts = exif_facts(img)
        upright = ImageOps.exif_transpose(img).convert("RGB")
    w, h = upright.size
    facts.update({
        "type": os.path.splitext(path)[1].lower().lstrip("."),
        "width": w, "height": h,
        "megapixels": w * h / 1e6,
        "aspect": max(w, h) / min(w, h),
        "screen_sized": "yes" if (min(w, h), max(w, h)) in SCREEN_SIZES else "no",
        "name_pattern": name_pattern(os.path.basename(path)),
        "folder_hint": folder_hint(folder),
        "folder_depth": len([p for p in folder.split("/") if p]),
        "bytes_per_pixel": os.path.getsize(path) / (w * h),
    })
    facts.update(pixel_facts(upright))
    return facts


def as_text(facts):
    """Facts with numbers rounded for the CSV file."""
    return {k: ("%.4f" % v if isinstance(v, float) else v) for k, v in facts.items()}


def is_number(column):
    return column not in ("id", "type", "screen_sized", "has_make", "has_model", "has_lens",
                          "has_flash", "has_date_taken", "software", "name_pattern",
                          "folder_hint")


def load(eval_data, half):
    """The fact table of one half, with numeric columns as numbers."""
    rows = common.read_csv(common.inside(eval_data, "facts", "facts_%s.csv" % half))
    for row in rows:
        for column in FACT_COLUMNS:
            if is_number(column):
                row[column] = float(row[column])
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(description="Compute the table of facts for one half of the sample.")
    p.add_argument("--half", choices=("tuning", "final"), default="tuning")
    p.add_argument("--eval-data", default=str(common.DEFAULT_EVAL_DATA))
    args = p.parse_args(argv)

    rows, failed = [], 0
    for row in common.load_sample(args.eval_data):
        if row["half"] != args.half:
            continue
        try:
            facts = compute(common.sample_file(args.eval_data, row), row["folder"])
        except Exception:
            failed += 1
            continue
        rows.append(dict(as_text(facts), id=row["id"]))
    dest = common.inside(args.eval_data, "facts", "facts_%s.csv" % args.half)
    common.write_csv(dest, FACT_COLUMNS, rows)
    print("Facts for %d files written to %s" % (len(rows), dest))
    if failed:
        print("%d files could not be read and are left out." % failed)


if __name__ == "__main__":
    main()
