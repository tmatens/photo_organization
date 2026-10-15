# Photo Organizer

Organizes a large photo library **directly on your computer** — no uploads, no
compression, and your originals are never modified, moved, or deleted. It
builds an organized *copy* and tells you exactly where everything went.

## What it does

1. **Scans** every subfolder of your external drive for photos
   (JPG, PNG, HEIC, WEBP, TIFF, BMP).
2. **Finds duplicates** — exact visual duplicates are listed once in a report
   instead of being copied twice.
3. **Sorts by date taken** into `YYYY/MM` folders with clean filenames like
   `20220314_100000.jpg`. Uses the photo's EXIF data; screenshots (which have
   no EXIF data) fall back to the file date.
4. **Pulls out lookalikes** — give it an example image (e.g. one of your
   music-app screenshots) and it copies every visually similar photo into its
   own folder.
5. **Writes `manifest.csv`** — a spreadsheet listing every photo, where it
   went, its date, and whether it was a duplicate or a match.

## Setup

You need Python 3.9 or newer.

**Mac:** Python usually comes preinstalled. Open Terminal and check:
```
python3 --version
```

**Windows:** Install Python from python.org (tick "Add python.exe to PATH"
during setup). Then open PowerShell.

Install the two required packages (same command on Mac and Windows):
```
pip install pillow imagehash
```
iPhone HEIC photos only: also run `pip install pillow-heif`.

## How to run

**1. Preview first (dry run — changes nothing):**
```
# Mac
python3 organize_photos.py --source /Volumes/MyDrive --output ~/Organized --dry-run
# Windows
python organize_photos.py --source E:\ --output C:\Organized --dry-run
```

**2. Full run:**
```
python3 organize_photos.py --source /Volumes/MyDrive --output ~/Organized
```

**3. Also extract all music-app screenshots** (use any one of them as the example):
```
python3 organize_photos.py --source /Volumes/MyDrive --output ~/Organized \
    --example ~/screenshot_example.png --example-chrome
```
Matches go into `Organized/matched_example/`. The `--example-chrome` flag is
the key detail for app screenshots: it compares only the app's UI (top and bottom),
ignoring the album art that changes with every song — so screenshots from
different songs still match, while regular photos don't. If it's catching too
much or too little, tune with `--similar-threshold` (default 10; lower =
stricter, higher = looser).

## Useful options

| Option | What it does |
|---|---|
| `--dry-run` | Scan and report only; copy nothing |
| `--example FILE` | Pull visually similar photos into their own folder |
| `--similar-name NAME` | Folder name for matches (default `matched_example`) |
| `--similar-threshold N` | Strictness of matching, 0–64 (default 10) |
| `--dup-threshold N` | Also treat near-duplicates as dupes (default 0 = exact only) |
| `--keep-dupes` | Copy duplicates into `_duplicates/` for manual review |

## Notes

- The `--output` folder must not be inside `--source`. A different folder on
  the same external drive works fine if there's free space.
- Large libraries take a while (roughly 1–2 hours per 50,000 photos). The
  script prints progress as it goes and can be safely re-run.
- `manifest.csv` in the output folder records every decision, so you can
  audit or undo anything.
