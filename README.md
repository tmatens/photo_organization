# Photo Organizer

Organizes a large photo and video library **directly on your computer** — no
uploads, no compression, and your originals are never modified, moved, or
deleted. It builds an organized *copy* and tells you exactly where everything
went.

## What it does

1. **Scans** every subfolder of your external drives for photos
   (JPG, PNG, HEIC, WEBP, TIFF, BMP) and videos (MOV, MP4, M4V, 3GP, AVI,
   MKV, WMV, MTS).
2. **Finds duplicates** — a file that is identical to one already seen is
   listed in the manifest instead of being copied twice.
3. **Sorts by date taken** into `YYYY/MM` folders with clean filenames like
   `20220314_100000.jpg`. Only a date the camera wrote counts: the EXIF
   capture date inside a photo, or the creation time inside a MOV/MP4
   video. See "How dates are decided" below.
4. **Keeps everything else out of the timeline.** Screenshots (any PNG, or
   a file named `Screenshot...`) and anything without a camera date go into
   a separate `_review/` tree with a sub-folder per reason (`screenshots/`,
   `photos/`, `videos/`), each sorted by month using the best date
   available, for you to look through. **Photos saved from social media,
   messaging apps or the web end up here**, because those services strip
   the camera's date on the way out: a real photo of yours that a friend
   posted and you saved back is, to the tool, not camera-dated. The review
   folder is not only junk; it needs a look.
5. **Writes `manifest.csv`** — a spreadsheet listing every photo and video,
   where it went, which date was used, and whether it was a duplicate.
6. **Optionally pulls one app's screenshots out** of the review folder into
   their own folder, given an example screenshot. A separate script; see
   step 10 of the walkthrough.

## Quick start on Windows: three old drives onto one new SSD

This is the whole job, start to finish. Each step is one command.

1. **Install Python** from https://www.python.org/downloads/ . On the first
   screen of the installer tick **"Add python.exe to PATH"**, then Install.
2. **Download this tool.**
   1. In a browser, open
      https://github.com/tmatens/photo_organization/releases/latest
   2. Scroll down to the **Assets** heading and click the file named
      `photo_organizer-<version>.zip` (the version number changes; take
      whichever is there).
      Ignore the two "Source code" links; those are for programmers.
   3. The browser saves it to your **Downloads** folder. Open Downloads in
      File Explorer, right-click the zip file, and choose **Extract All...**
   4. In the dialog that opens, delete the suggested location and type
      `C:\photo_organizer` instead, then click **Extract**.
   5. Check: `C:\photo_organizer` should now contain `organize_photos.py`,
      `sort_screenshots.py`, `README.md`, `CHANGELOG.md`, `requirements.txt`
      and `requirements-optional.txt` directly, not inside another folder. If you see a folder instead,
      open it and use *that* folder's path wherever the steps below say
      `C:\photo_organizer`.
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
6. **Quick sample first** (a few minutes). Nothing is copied. This looks
   at 500 files spread evenly across all three drives and writes a
   spreadsheet of what it would do with them:
   ```
   python organize_photos.py --source E:\ --source F:\ --source G:\ --output D:\Organized --dry-run --sample 500
   ```
   Open `D:\Organized\manifest_dryrun.csv` in Excel. If the pattern looks
   right (camera photos under years and months, screenshots and odds and
   ends under `_review`), continue. If not, this is the moment to ask.
7. **Full preview.** Same, for every file:
   ```
   python organize_photos.py --source E:\ --source F:\ --source G:\ --output D:\Organized --dry-run
   ```
   This takes a while on big drives. When it finishes, open
   `D:\Organized\manifest_dryrun.csv` in Excel and look at a few rows: the
   `destination_path` column is where each file would go, `status` says
   whether it would be copied or is a duplicate of something else, and
   `date_taken` says where the date came from.
8. **Run for real.** Same command without `--dry-run`:
   ```
   python organize_photos.py --source E:\ --source F:\ --source G:\ --output D:\Organized
   ```
   If it is interrupted, run the same command again; it continues where it
   stopped.

   **Only one drive plugged in at a time?** Run it with just that drive, then
   again later with the next one, always to the same `--output`:
   ```
   python organize_photos.py --source E:\ --output D:\Organized
   python organize_photos.py --source F:\ --output D:\Organized
   ```
   The tool remembers what it has already copied, so a photo on F: that was
   already copied from E: is recognised and not copied twice.
9. **Look through `D:\Organized`:**
   - `2019\`, `2020\`, ... — photos and videos with a known date.
   - `_review\` — everything that is not a camera-dated photo or video, in
     three sub-folders so each can be gone through on its own:
     - `_review\screenshots\` — anything that is a PNG or named
       `Screenshot...`. Mostly junk; skim and delete by month.
     - `_review\photos\` — photos with no camera date: memes, downloads,
       and also **real photos saved from social media or messaging apps**,
       which arrive with the camera's date stripped. Needs a proper look.
     - `_review\videos\` — videos that are not camera originals: re-sent
       copies, screen recordings, downloads. Large files; worth a separate
       sitting.
     All three are sorted by month inside.
   - `manifest.csv` — one line per file on the old drives saying what
     happened to it.
10. **Pull one app's screenshots into their own folder** (optional). If
    years of screenshots of one app are mixed into `_review\screenshots\`,
    for example songs you captured to remember later:
    1. Make a folder `C:\photo_organizer\examples` and copy one of those
       screenshots into it. One is usually enough; if the app's look has
       changed over the years, add one of each look.
    2. Preview, then run:
       ```
       python sort_screenshots.py --output D:\Organized --examples C:\photo_organizer\examples --name music --dry-run
       python sort_screenshots.py --output D:\Organized --examples C:\photo_organizer\examples --name music
       ```
    3. The matches move to `D:\Organized\_review\music\`, by month. Look at
       what is left in `_review\screenshots\`; if any of the app's
       screenshots were missed, copy one into the examples folder and run
       again. Only the leftovers are checked each time.
11. **Only when you are happy with the new drive**, wipe the old ones. The
    tool never deletes anything; that last step is yours.

## Setup on a Mac, or by hand

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

## Pulling one app's screenshots out: `sort_screenshots.py`

Runs after the organizer and looks only inside `_review/screenshots/`. It
compares each screenshot's top band (status bar and header) and bottom
band (title, controls, progress bar) with the same bands of your example
screenshots, shrunk to a small grid so the phone's screen size does not
matter. The middle of the screen, where artwork changes with every song,
is ignored. Matches move to `_review/<name>/YYYY/MM/`, `manifest.csv` is
updated to the new locations, and a log in `_review/` says which example
each file matched and how closely.

| Option | What it does |
|---|---|
| `--output FOLDER` | The organized folder (the `--output` you gave the organizer) |
| `--examples FOLDER` | Folder of example screenshots, one per look |
| `--name NAME` | Folder under `_review` for the matches (default `app`) |
| `--threshold N` | How different the bands may be and still match, 0 to 255 (default 12). Raise if screenshots are missed, lower if other apps are caught |
| `--dry-run` | Report and log what would move; move nothing |

Measured on a real music-app screenshot: the same app on four different
phone sizes and with different songs scores under 2; other apps score
above 38; a blank screen in the app's colour scores 20. The default of 12
sits in the gap.

## Useful options

| Option | What it does |
|---|---|
| `--dry-run` | Scan and report only; copy nothing |
| `--sample N` | Process only N files, spread evenly across every drive and folder, to see results in minutes. A later full run skips whatever a sample already copied |
| `--keep-dupes` | Also copy identical duplicates into `_duplicates/` instead of only listing them |
| `--review-folder NAME` | Folder for screenshots and anything without a camera date (default `_review`) |
| `--png-is-photo` | Treat PNG and `Screenshot...` files like any other file instead of sending them straight to the review folder |
| `--mix-undated` | File everything into the main `YYYY/MM` tree by its best-guess date; no review folder for dates |

## How dates are decided

Each file is checked against a short list of evidence, best first. The
manifest's `date_taken` column says which one was used.

| Source | What it is | Proves a camera? |
|---|---|---|
| `exif-original` | EXIF capture time, written when the shutter fired | yes |
| `exif-digitized` | EXIF digitized time, written by scanners and import tools | yes |
| `video-metadata` | creation time inside a MOV/MP4 file | only with a camera-style filename |
| `filename` | a timestamp in the name, e.g. `IMG_20220314_100000.jpg` | no |
| `exif-modified` | EXIF save time: when the file was last written, not taken | no |
| `file-date` | the file's modification time, usually when it was copied | no |

Only the first three put a file in the main `YYYY/MM` library. The others
only decide which month a file sits under inside `_review/`. The reason: a
timestamp in a filename, a save time, or a file date can all be written by
software long after the picture was taken. A Telegram save named
`photo_2022-03-14_10-00-00.jpg` is dated when it was sent, not shot.

Videos are the weak case. The creation time inside a MOV/MP4 file is
written by whatever program last encoded it, so a clip re-sent through
WhatsApp or exported from an editor has a perfectly good header dated
when that happened. To count as camera-dated a video needs **both** a
header time and a camera-style filename: `VID_20220314_100000.mp4`
(Android), `PXL_...` (Pixel), `20220314_100000.mp4` (Samsung), `IMG_1234.MOV`
(iPhone), or the `MVI_`, `DSC_`, `DJI_` and GoPro patterns from real
cameras. Messaging apps, screen recorders and downloads never use those
names. When both exist, the filename supplies the date itself, because it
is in local time and the header time is not. A camera video that was
renamed on its way to the drive goes to `_review/videos/` under the right
month.

## Notes

- The `--output` folder can be anywhere, including on the same external
  drive or inside a source folder; the script never scans its own output.
- **Windows paths:** write a whole drive as `E:\` with no quotes. A folder
  with spaces needs quotes and no trailing backslash: `"D:\My Photos"`.
  Folder trees deeper than Windows' usual 260-character limit are handled;
  nothing on the drive needs renaming first.
- Videos are organized alongside photos. Identical videos are copied once.
- Hidden files (names starting with `.`) and system folders such as the
  Recycle Bin are ignored.
- The months inside `_review/` come from whatever date was available, often
  just the day a file was copied or downloaded. Treat that tree as "needs a
  look", not as a timeline.
- Large libraries take hours. The script prints progress as it goes. If it is interrupted, run the same
  command again: it reads `manifest.csv`, skips everything already done, and
  continues. To start over from scratch, delete the output folder first.
- "Duplicate" means byte-for-byte identical. Two photos that look the same
  but differ in size or quality (a thumbnail, a copy re-saved by a messaging
  app) are both real files, so both are copied. The smaller copy has no
  camera date and so lands in `_review/`.
- `manifest.csv` in the output folder records every decision, so you can
  audit or undo anything. It is written one line at a time as the script
  works, so even an interrupted run leaves a complete record of what it did.
- If a photo cannot be copied (disk full, permission problem), the script
  records it as `error-copy` in the manifest, carries on with the rest, and
  reports the count at the end.

## Why the organizer itself does no image matching

Earlier versions of the organizer could pull out every photo that looked
like one example image, and could group photos that merely looked the
same, all during the copy. Both were removed in 1.2.0. Matching one app's
screenshots came back in 1.5.0 as a separate script that runs afterwards
over the review folder. Overall better, with known risks.

Why better:

- Every screenshot already goes to `_review/screenshots/`, so the organizer
  has nothing to match during the copy; the sorter works on that folder.
- Thumbnails and app re-saves carry no camera date, so they already land in
  `_review/` too; look-alike grouping would only have sorted the review pile.
- A similarity decision made during the copy could not be checked or
  undone; the sorter previews, logs which example matched, and can be run
  again after adding an example.
- Three packages gone; the install is Pillow alone.
- Fewer options: the walkthrough uses three for the organizer.

Risks:

- Two files with identical pixels but different metadata (an export from a
  photo app, a copy with location stripped) are both kept, side by side in
  a month folder.
- Burst frames and near-identical shots are all kept.
- Real photos saved back from social media or messaging apps have no camera
  date and land in `_review/photos/` with the memes. That folder needs a
  look, not a delete.
- The sorter matches an app's frame, not its name. A different app with a
  very similar layout would be pulled too; the dry-run log shows it before
  anything moves.

## For developers

A plain-language log of every change is in `CHANGELOG.md`. To run the tests:
```
pip install -r requirements-dev.txt
pytest
```
The tests build small synthetic photo libraries, so they need no real photos.
