# Photo Organizer

Organizes a large photo library **directly on your computer** — no uploads, no
compression, and your originals are never modified, moved, or deleted. It
builds an organized *copy* and tells you exactly where everything went.

## What it does

1. **Scans** every subfolder of your external drive for photos
   (JPG, PNG, HEIC, WEBP, TIFF, BMP).
2. **Finds duplicates** — a file that is identical to one already seen is
   listed in the manifest instead of being copied twice. Optionally it also
   groups photos that merely *look* the same (a thumbnail, a re-saved copy,
   a burst frame), keeps the largest version, and puts the rest in a review
   folder.
3. **Sorts by date taken** into `YYYY/MM` folders with clean filenames like
   `20220314_100000.jpg`, using the photo's EXIF data. If there is no EXIF
   capture date but the filename carries a timestamp (phones and apps write
   names like `IMG_20220314_100000.jpg` or `Screenshot_20220314-100000.png`),
   that is used instead. Anything with no date at all goes into a separate
   `_review/YYYY/MM` tree sorted by file date, so a guessed date never
   mixes with a real one.
4. **Pulls out lookalikes** — give it an example image (e.g. one of your
   music-app screenshots) and it copies every visually similar photo into its
   own folder.
5. **Writes `manifest.csv`** — a spreadsheet listing every photo, where it
   went, its date, and whether it was a duplicate or a match.

## Setup

You need Python 3.10 or newer.

**Mac:** Python usually comes preinstalled. Open Terminal and check:
```
python3 --version
```

**Windows:** Install Python from python.org (tick "Add python.exe to PATH"
during setup). Then open PowerShell.

Install the required packages (same command on Mac and Windows, run from the
folder containing the script):
```
pip install -r requirements.txt
```
iPhone HEIC photos only: also run `pip install -r requirements-optional.txt`.

## How to run

**1. Preview first (dry run — copies nothing):**
```
# Windows: three old drives (E:, F:, G:) into a new drive D:
python organize_photos.py --source E:\ --source F:\ --source G:\ --output D:\Organized --dry-run
# Mac
python3 organize_photos.py --source /Volumes/MyDrive --output ~/Organized --dry-run
```
Repeat `--source` for each drive or folder you want combined. Duplicates are
found across all of them, so a photo that lives on two drives is copied once.

The preview writes `manifest_dryrun.csv` in the output folder: one line per
photo showing exactly where the real run would put it. Open it in a
spreadsheet and check a few rows before continuing.

**2. Full run:**
```
# Windows
python organize_photos.py --source E:\ --source F:\ --source G:\ --output D:\Organized
# Mac
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
| `--dup-threshold N` | Also group photos that look the same, 0–64 (off by default; 2–4 catches thumbnails and re-saved copies; 6–10 also catches burst frames and small edits). The largest version is kept; the rest go to `_duplicates/` |
| `--keep-dupes` | Also copy identical duplicates into `_duplicates/` instead of only listing them |
| `--undated-folder NAME` | Folder for photos with no EXIF date (default `_review`) |
| `--mix-undated` | File undated photos into the main `YYYY/MM` tree by file date instead |

## Notes

- The `--output` folder can be anywhere, including on the same external
  drive or inside a source folder; the script never scans its own output.
- **Windows paths:** write a whole drive as `E:\` with no quotes. A folder
  with spaces needs quotes and no trailing backslash: `"D:\My Photos"`.
  Folder trees deeper than Windows' usual 260-character limit are handled;
  nothing on the drive needs renaming first.
- Videos are not copied. The script organizes photos only and tells you at
  the end how many video files it left behind. Hidden files (names starting
  with `.`) and system folders such as the Recycle Bin are ignored.
- The file date used for `_review/` photos is often just the day they were
  copied or downloaded, not the day they were taken. Treat that tree as
  "needs a look", not as a timeline.
- Large libraries take a while (roughly 1–2 hours per 50,000 photos). The
  script prints progress as it goes. If it is interrupted, run the same
  command again: it reads `manifest.csv`, skips everything already done, and
  continues. To start over from scratch, delete the output folder first.
- "Duplicate" means byte-for-byte identical. Two photos that look the same
  but differ in size or quality are both real files, so by default both are
  copied. Use `--dup-threshold` to group them; the one with the most pixels
  stays in the main library and the others go to `_duplicates/`, where you
  can check them before deleting anything.
- `manifest.csv` in the output folder records every decision, so you can
  audit or undo anything. It is written one line at a time as the script
  works, so even an interrupted run leaves a complete record of what it did.
- If a photo cannot be copied (disk full, permission problem), the script
  records it as `error-copy` in the manifest, carries on with the rest, and
  reports the count at the end.

## For developers

A plain-language log of every change is in `CHANGELOG.md`. To run the tests:
```
pip install -r requirements-dev.txt
pytest
```
The tests build small synthetic photo libraries, so they need no real photos.
