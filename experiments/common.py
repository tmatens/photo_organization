"""Shared helpers for the categorization experiment.

Everything the experiment writes goes into one folder, eval_data/, which
.gitignore excludes. That folder holds real photos and their names, so
nothing in it is ever committed. The helpers here keep that promise in one
place: every script builds its output paths with inside(), which refuses a
path that would land anywhere else.
"""
import csv
import os
import sys
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("Pillow is required: pip install pillow")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EVAL_DATA = REPO_ROOT / "eval_data"

# organize_photos.py lives one folder up. Importing it also switches on HEIC
# support when pillow-heif is installed, exactly as the organizer does.
sys.path.insert(0, str(REPO_ROOT))
import organize_photos  # noqa: E402

PHOTO_EXTS = organize_photos.IMAGE_EXTS | organize_photos.HEIC_EXTS

# The starting list from docs/categorization-plan.md. The first labelling
# pass may also answer "other"; the settled list replaces this one.
STARTING_CATEGORIES = [
    ("screenshot", "A capture of a phone or computer screen, whatever its file type or name"),
    ("receipt", "A till receipt, invoice or ticket, photographed or scanned"),
    ("document", "Any other page of text: a letter, a form, a whiteboard, a slide"),
    ("photo-of-photo", "A camera picture of a printed photo, an album page or a framed picture"),
    ("meme-or-graphic", "An image made on a computer: a meme, a poster, a logo, a chart"),
    ("photo", "An ordinary photo. The default, and by far the largest group"),
]

SAMPLE_COLUMNS = ["id", "source", "rel_path", "folder", "half", "camera_dated",
                  "date_source", "bytes"]
# reviewed: "yes" when a person looked at the file, "no" when its guess was
# accepted unseen (tuning half only), empty while it is still unconfirmed.
LABEL_COLUMNS = ["id", "rel_path", "guessed_label", "confirmed_label", "reviewed"]


def inside(eval_data, *parts):
    """The path eval_data/parts..., refused if it would fall outside
    eval_data. Every write in the experiment goes through here."""
    root = Path(eval_data).resolve()
    path = root.joinpath(*[str(p) for p in parts]).resolve()
    if path != root and root not in path.parents:
        raise ValueError("refusing to write outside the eval data folder: %s" % path)
    return path


def read_csv(path):
    """Rows of a CSV file as dicts; an empty list if the file is not there."""
    path = Path(path)
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, columns, rows):
    """Write rows to a CSV file in one step: a temporary file next to the
    target is written first and then renamed over it, so a crash or Ctrl-C
    never leaves a half-written file behind."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, path)


def load_sample(eval_data):
    """The sampler's list of files, one dict per file."""
    return read_csv(inside(eval_data, "sample.csv"))


def sample_file(eval_data, row):
    """Where the copy of one sampled file lives inside eval_data."""
    return inside(eval_data, "files", row["source"], *row["rel_path"].split("/"))


def open_upright(path):
    """Open an image the way a person would see it: turned according to its
    EXIF orientation and converted to plain RGB."""
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        return img.convert("RGB")


def shrink(img, max_edge):
    """A copy of img whose longer side is at most max_edge pixels. Images
    already that small are returned unchanged, never enlarged."""
    w, h = img.size
    longest = max(w, h)
    if longest <= max_edge:
        return img
    scale = max_edge / longest
    return img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)


def thumbnail_path(eval_data, file_id):
    return inside(eval_data, "thumbs", file_id + ".jpg")


def make_thumbnail(eval_data, row, max_edge=256):
    """Create (once) and return a small JPEG of one sampled file, for the
    tally and review pages. Returns None if the file cannot be opened."""
    dest = thumbnail_path(eval_data, row["id"])
    if dest.exists():
        return dest
    try:
        img = shrink(open_upright(sample_file(eval_data, row)), max_edge)
    except Exception:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    img.save(tmp, "JPEG", quality=80)
    os.replace(tmp, dest)
    return dest
