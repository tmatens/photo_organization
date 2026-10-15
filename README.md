# Photo Organizer

Organizes a large photo and video library **directly on your computer** — no
uploads, no compression, and your originals are never modified, moved, or
deleted. It builds an organized *copy* and tells you exactly where everything
went.

## What it does

1. **Scans** every subfolder of your external drive for photos
   (JPG, PNG, HEIC, WEBP, TIFF, BMP) and videos (MOV, MP4, M4V, 3GP, AVI,
   MKV, WMV, MTS).
2. **Finds duplicates** — a file that is identical to one already seen is
   listed in the manifest instead of being copied twice.
3. **Sorts by date taken** into `YYYY/MM` folders with clean filenames like
   `20220314_100000.jpg`, using the photo's EXIF data. If there is no EXIF
   capture date but the filename carries a timestamp (phones and apps write
   names like `IMG_20220314_100000.jpg` or `Screenshot_20220314-100000.png`),
   that is used instead. Videos use the filename timestamp or the date
   stored inside MOV/MP4 files.
4. **Keeps non-photos out of the timeline.** Screenshots (any PNG, or a
   file named `Screenshot...`) and anything with no date at all go into a
   separate `_review/YYYY/MM` tree, sorted by month, for you to look
   through. Cameras and phones never save a photo as PNG, so a PNG is a
   screenshot, a meme or a graphic. **Photos saved from social media,
   messaging apps or the web also end up here**, because those services
   strip the date information on the way out: a real photo of yours that a
   friend posted and you saved back is, to the tool, undated. The review
   folder is not only junk; it needs a look.
5. **Writes `manifest.csv`** — a spreadsheet listing every photo, where it
   went, its date, and whether it was a duplicate or a match.

## Quick start on Windows: three old drives onto one new SSD

This is the whole job, start to finish. Each step is one command.

1. **Install Python** from https://www.python.org/downloads/ . On the first
   screen of the installer tick **"Add python.exe to PATH"**, then Install.
2. **Download this tool** from the Releases page on GitHub (the `.zip`), and
   unzip it somewhere simple, such as `C:\photo_organizer`.
3. **Plug in the drives.** All three old drives and the new SSD. Note the
   drive letters Windows gives them (open File Explorer and look under
   "This PC"). The examples below use `E:`, `F:`, `G:` for the old drives and
   `D:` for the new SSD; use yours.
4. **Open PowerShell in the tool's folder:** in File Explorer, open
   `C:\photo_organizer`, click in the address bar, type `powershell`, press
   Enter.
5. **Install what the tool needs** (once):
   ```
   pip install -r requirements.txt
   pip install -r requirements-optional.txt
   ```
   The second line adds iPhone HEIC support. If it fails, skip it; the tool
   will tell you at the end how many HEIC photos it could not include.
6. **Preview.** Nothing is copied; this only reads the drives and writes a
   spreadsheet of what it would do:
   ```
   python organize_photos.py --source E:\ --source F:\ --source G:\ --output D:\Organized --dry-run
   ```
   This takes a while on big drives. When it finishes, open
   `D:\Organized\manifest_dryrun.csv` in Excel and look at a few rows: the
   `destination_path` column is where each file would go, `status` says
   whether it would be copied or is a duplicate of something else, and
   `date_taken` says where the date came from.
7. **Run for real.** Same command without `--dry-run`:
   ```
   python organize_photos.py --source E:\ --source F:\ --source G:\ --output D:\Organized
   ```
   If it is interrupted, run the same command again; it continues where it
   stopped.
8. **Look through `D:\Organized`:**
   - `2019\`, `2020\`, ... — photos and videos with a known date.
   - `_review\` — everything that is not a dated camera photo: screenshots,
     memes, downloads, and also **real photos saved from social media or
     messaging apps**, which arrive with their dates stripped. Sorted by
     month inside. This folder needs a look, not just a delete.
   - `manifest.csv` — one line per file on the old drives saying what
     happened to it.
9. **Only when you are happy with the new drive**, wipe the old ones. The
   tool never deletes anything; that last step is yours.


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

## Useful options

| Option | What it does |
|---|---|
| `--dry-run` | Scan and report only; copy nothing |
| `--keep-dupes` | Also copy identical duplicates into `_duplicates/` instead of only listing them |
| `--review-folder NAME` | Folder for screenshots and undated photos (default `_review`) |
| `--png-is-photo` | Treat PNG and `Screenshot...` files like any other photo instead of sending them to the review folder |
| `--mix-undated` | File undated photos into the main `YYYY/MM` tree by file date instead |

## Notes

- The `--output` folder can be anywhere, including on the same external
  drive or inside a source folder; the script never scans its own output.
- **Windows paths:** write a whole drive as `E:\` with no quotes. A folder
  with spaces needs quotes and no trailing backslash: `"D:\My Photos"`.
  Folder trees deeper than Windows' usual 260-character limit are handled;
  nothing on the drive needs renaming first.
- Videos are organized alongside photos. Identical videos are copied once. Hidden files (names starting with `.`) and system folders
  such as the Recycle Bin are ignored.
- The file date used for `_review/` photos is often just the day they were
  copied or downloaded, not the day they were taken. Treat that tree as
  "needs a look", not as a timeline.
- Large libraries take a while (roughly 1–2 hours per 50,000 photos). The
  script prints progress as it goes. If it is interrupted, run the same
  command again: it reads `manifest.csv`, skips everything already done, and
  continues. To start over from scratch, delete the output folder first.
- "Duplicate" means byte-for-byte identical. Two photos that look the same
  but differ in size or quality (a thumbnail, a copy re-saved by a messaging
  app) are both real files, so both are copied. The smaller copy usually has
  no date information and so lands in `_review/`.
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
