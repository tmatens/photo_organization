"""Shared helpers for the test suite.

Every test builds its own tiny photo library from synthetic images, so the
suite needs no real photos and runs the same on Mac, Windows and Linux.
"""
import csv
import hashlib
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import ExifTags, Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "organize_photos.py"


def make_image(seed, size=(640, 480)):
    """A deterministic, photo-like image. Different seeds look very different
    to a perceptual hash; the same seed is pixel-identical every time."""
    rng = random.Random(seed)
    img = Image.new("RGB", size, tuple(rng.randint(0, 255) for _ in range(3)))
    draw = ImageDraw.Draw(img)
    w, h = size
    for _ in range(12):
        x0, y0 = rng.randint(0, w), rng.randint(0, h)
        x1, y1 = x0 + rng.randint(w // 8, w // 2), y0 + rng.randint(h // 8, h // 2)
        draw.rectangle([x0, y0, x1, y1], fill=tuple(rng.randint(0, 255) for _ in range(3)))
    return img


def write_photo(path, seed, size=(640, 480), date_original=None, date_modified=None, quality=92):
    """Save a synthetic JPEG. `date_original` goes into DateTimeOriginal (the
    capture time, in the Exif sub-IFD); `date_modified` into DateTime (IFD0)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img = make_image(seed, size)
    exif = Image.Exif()
    if date_modified:
        exif[ExifTags.Base.DateTime] = date_modified
    if date_original:
        exif.get_ifd(ExifTags.IFD.Exif)[ExifTags.Base.DateTimeOriginal] = date_original
    kwargs = {"exif": exif} if (date_original or date_modified) else {}
    img.save(path, "JPEG", quality=quality, **kwargs)
    return path


def write_screenshot(path, chrome_seed, middle_seed, size=(400, 800)):
    """A fake music-app screenshot: a fixed top and bottom band (the app's UI)
    around a middle area that changes with every song."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    w, h = size
    img = make_image(chrome_seed, size)
    middle = make_image(middle_seed, (w, int(h * 0.40)))
    img.paste(middle, (0, int(h * 0.16)))
    img.save(path, "PNG")
    return path


def sha256_tree(root):
    """{relative path: sha256} for every file under root. Used to prove the
    source library is untouched."""
    out = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def run_script(*args, check=True):
    """Run organize_photos.py as a user would, from the command line."""
    cmd = [sys.executable, "-I", str(SCRIPT)] + [str(a) for a in args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise AssertionError("script failed (%d)\nstdout:\n%s\nstderr:\n%s"
                             % (proc.returncode, proc.stdout, proc.stderr))
    return proc


def read_manifest(output):
    with open(Path(output) / "manifest.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture
def library(tmp_path):
    """An empty source and output folder pair, side by side (never nested)."""
    src = tmp_path / "source"
    out = tmp_path / "output"
    src.mkdir()
    return src, out
