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

# Every file is labelled twice, on two separate questions ("fields"), with
# exactly one answer to each. Keeping them apart means a screen capture of a
# receipt needs no rule about which label wins: it is a screen-capture on
# the first question and a receipt on the second.
FIELDS = ("made", "shows")
FIELD_QUESTIONS = {"made": "How was the file made?", "shows": "What does the file show?"}
FIELD_LABELS = {
    "made": [
        ("screen-capture", "A capture of a phone or computer screen, whatever its file type or name, "
                           "cropped or not"),
        ("saved-image", "An image made on a computer and saved as it is: a meme, a graphic, a logo, "
                        "a product picture"),
        ("paper-copy", "A scan or a camera picture of something on paper: a page, a card, a drawing, "
                       "a printed photo"),
        ("camera-photo", "Taken with a camera or a phone camera. The default, and by far the largest "
                         "group"),
    ],
    "shows": [
        ("text-thread", "A back-and-forth of written messages between people: a text or chat "
                        "conversation, a comment thread under a social media post, a forum or "
                        "email thread"),
        ("receipt", "Proof of a purchase or payment: a till receipt, an invoice, a bill, an order "
                    "confirmation or a transaction, on paper or on a screen"),
        ("ticket", "A ticket, a boarding pass, a booking or a travel itinerary, on paper or on a "
                   "screen, whether or not it shows a price"),
        ("cart", "A shopping cart or basket: items chosen in a shop's site or app but not yet "
                 "paid for"),
        ("document", "A letter, form, flyer, schedule, map, card or page of a PDF: something that is, "
                     "or would be, a sheet of paper. An ordinary web page or email is not this"),
        ("drawing", "A drawing, painting or handwriting made by hand, where the artwork fills the "
                    "picture"),
        ("product", "A product picture or a shop page saved from the web, with nothing bought: one "
                    "item, or several put together in a collage"),
        ("interior", "The inside of a building with no person or pet as the subject: a room, a "
                     "hallway, a piece of decor in place, whether your own picture or a saved "
                     "decorating idea"),
        ("meme-or-graphic", "A meme, a quote card, an infographic, a logo, an advert or another made "
                            "image"),
        ("thing", "Your own picture that records or shows a thing, with no person as the subject: "
                  "an item for sale, damage or a repair, something you own, a sign"),
        ("screen-other", "A screen, web page or app page that shows nothing listed here: a form, a "
                         "calendar, a search result, a video frame, a post that is mostly text"),
        ("photo", "A real picture of people, pets, places, events or food, however it reached "
                  "you: taken with a camera, saved from the web, or shown on a captured screen "
                  "where the picture is the point. The default, and by far the largest group"),
    ],
}
# The label a field falls back to, and the one most files get.
FIELD_DEFAULT = {"made": "camera-photo", "shows": "photo"}
# What to do when two labels of one field seem to fit. Written down before
# labelling starts, as the plan requires.
FIELD_TIE_RULE = {
    "made": "Judge only how the file came to exist, never what is on it. A screen capture of a photo "
            "is a screen-capture. A camera picture of a printed photo or of a page is a paper-copy. "
            "A collage put together from camera photos is a camera-photo.",
    "shows": "Judge only what is on it, never how it was made. When two labels fit, the one that "
             "comes first in this order wins: text-thread, receipt, ticket, cart, document, "
             "drawing, "
             "product, interior, meme-or-graphic, thing, screen-other, "
             "photo.",
}

# The list for the first look at a new sample, before the two fields are
# settled. The first labelling pass may also answer "other".
STARTING_CATEGORIES = [
    ("screenshot", "A capture of a phone or computer screen, whatever its file type or name"),
    ("receipt", "A till receipt, invoice or ticket, photographed or scanned"),
    ("document", "Any other page of text: a letter, a form, a whiteboard, a slide"),
    ("photo-of-photo", "A camera picture of a printed photo, an album page or a framed picture"),
    ("meme-or-graphic", "An image made on a computer: a meme, a poster, a logo, a chart"),
    ("photo", "An ordinary photo. The default, and by far the largest group"),
]

# drawn: "evenly" for a file of the evenly spread sample, "top-up" for one
# added afterwards because its label was rare (topup.py). Empty in a sample
# made before top-ups existed, which means "evenly".
SAMPLE_COLUMNS = ["id", "source", "rel_path", "folder", "half", "camera_dated",
                  "date_source", "bytes", "drawn"]
# reviewed: "yes" when a person looked at the file, "no" when its guess was
# accepted unseen (tuning half only), empty while it is still unconfirmed.
LABEL_COLUMNS = ["id", "rel_path", "guessed_label", "confirmed_label", "reviewed"]


def field_file(eval_data, field, *parts):
    """The path eval_data/labels/<field>/parts...: where one field's list of
    labels, guesses, confirmed labels and second opinion are kept."""
    if field not in FIELDS:
        raise ValueError("field must be one of %s, not %r" % (", ".join(FIELDS), field))
    return inside(eval_data, "labels", field, *parts)


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
