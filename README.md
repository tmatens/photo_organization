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

## Easiest way on Windows: double-click

1. **Download the tool** and extract it, as in step 2 of the walkthrough
   below. Any folder on this computer works (not one of the old drives).
2. **Plug in** the old drives and the new one, if your photos are on
   drives.
3. In the extracted folder, **double-click `Organize Photos.bat`**. If a
   blue box says "Windows protected your PC", click **More info**, then
   **Run anyway**.
4. **Answer its questions.** For each, either type a drive letter (like
   `E`) or drag a folder from File Explorer onto the window, then press
   Enter. Open File Explorer and click **This PC** to see drive letters.
   - **Old photos:** it asks one at a time, so you can add several drives
     and folders. Press Enter on an empty line when that's all. A letter
     means the whole drive; for photos on this computer's own `C:` drive,
     drag the folder they are in (such as Pictures) rather than typing `C`.
   - **Copy to:** a drive letter or a folder. The copy goes into a new
     folder called `Organized` inside it, for example `D:\Organized`.

It installs Python by itself if it is missing, runs a quick test that
copies nothing, opens a spreadsheet of what it would do, and copies for
real only after you type `Y`. If it is interrupted, double-click it again
with the same answers and it carries on where it stopped. Step 9 below
explains the folders it makes.

**Screenshots of one app mixed in?** Afterwards, double-click
`Sort Screenshots.bat` to pull them into their own folder, for example
years of screenshots of songs in a music app. It opens an `examples`
folder for you to copy one of those screenshots into, asks where
`Organized` is (a drive letter, or drag the `Organized` folder onto the
window) and a name for the app's folder, shows a preview, and moves them
only after you type `Y`. It only moves the copies inside `Organized`;
your original photos are never touched. Run it again for another app, or
after adding an example of a look it missed.

If the double-click way does not work, the walkthrough below does the
same thing one command at a time.

## Step by step on Windows: three old drives onto one new SSD

No programming knowledge needed. You will copy and paste a few lines of
text into a window and press Enter. Go one step at a time, and do the
check at the end of each step before moving on.

> **The most important thing to know:** every command below goes into a
> **PowerShell** window that you open in step 4. You do **not** open
> "Python" from the Start menu and type into it. If you ever see a window
> whose line starts with `>>>`, that is the wrong place: type `exit()`,
> press Enter, close it, and go to step 4.

### Step 1. Install Python (once)

Python is the free program that runs this tool. You install it once and
then never open it yourself.

1. Go to https://www.python.org/downloads/ and click the big yellow
   **Download Python** button.
2. Open the file it downloads (it is in your **Downloads** folder).
3. If you see a window with a box that says **"Add python.exe to PATH"**,
   **tick that box first**, then click **Install Now**. This box is the
   step people most often miss.
4. If instead a black window opens and asks questions, type `y` and press
   Enter for each one.
5. When it says it has finished, close the installer. Do not open Python.

### Step 2. Download this tool

1. Open https://github.com/tmatens/photo_organization/releases/latest
2. Scroll down to **Assets** and click the file named
   `photo_organizer-<version>.zip` (for example
   `photo_organizer-1.5.1.zip`). Ignore the two "Source code" links.
3. Open your **Downloads** folder, right-click that zip file, and choose
   **Extract All...**
4. In the box that appears, delete what is written there, type
   `C:\photo_organizer`, and click **Extract**.

**Check:** open `C:\photo_organizer` in File Explorer. You should see files
called `organize_photos.py` and `requirements.txt` right there. If you see
just one folder instead, open it: *that* is the folder to use in step 4.

### Step 3. Plug in the drives

Plug in all the old drives and the new one. Open File Explorer and click
**This PC**. Each drive has a letter, like `E:`. Write down which letter
is which.

The examples below use `E:`, `F:` and `G:` for the three old drives and
`D:` for the new drive. **Change the letters in every command to match
yours.**

**Photos in a folder rather than filling a whole drive?** Wherever a
command says `--source E:\`, you can give a folder instead, in quotes:
`--source "C:\Users\Joel\Pictures"`. The same goes for `--output`.

### Step 4. Open PowerShell in the tool's folder

1. In File Explorer, open `C:\photo_organizer`.
2. Click once in the **address bar** at the top (where it says
   `C:\photo_organizer`) so the text turns blue.
3. Type `powershell` and press Enter.

A blue or black window opens. Its last line ends in
`C:\photo_organizer>` with a blinking cursor. This is where every command
goes. To paste a command: copy it from this page, **right-click** inside
the window (Ctrl+V also works), then press **Enter**.

**Check:** paste this and press Enter:
```
python --version
```
It should answer with something like `Python 3.13.1`. If it does not,
see "Stuck?" below before going on.

### Step 5. Install what the tool needs (once)

Paste each line, press Enter, and wait for it to finish:
```
python -m pip install -r requirements.txt
python -m pip install -r requirements-optional.txt
```
Lots of text will scroll past. That is normal. The first line should end
with `Successfully installed` (or `Requirement already satisfied`). The
second line adds support for iPhone (HEIC) photos; if it shows red errors,
skip it. The tool still works and tells you at the end how many iPhone
photos it had to leave out.

### Step 6. Quick test (a few minutes, copies nothing)

```
python organize_photos.py --source E:\ --source F:\ --source G:\ --output D:\Organized --dry-run --sample 500
```
This looks at 500 files spread across the drives and writes a
spreadsheet of what it *would* do. When the cursor comes back, open
`D:\Organized\manifest_dryrun.csv` in Excel. If camera photos are going
into year and month folders, and screenshots and odds and ends into
`_review`, carry on. If not, stop here and ask.

### Step 7. Full preview (copies nothing)

```
python organize_photos.py --source E:\ --source F:\ --source G:\ --output D:\Organized --dry-run
```
This can take a long time on big drives. Leave the window open. When it
is done, open `D:\Organized\manifest_dryrun.csv` in Excel again and look
at a few rows: `destination_path` is where each file will go, `status`
says whether it will be copied or is a duplicate, and `date_taken` says
where the date came from.

### Step 8. Do it for real

The same command without `--dry-run`:
```
python organize_photos.py --source E:\ --source F:\ --source G:\ --output D:\Organized
```
This can take hours. Leave the window open and the computer awake. If it
gets interrupted (closed window, restart, unplugged drive), open
PowerShell again (step 4) and run the same command: it picks up where it
stopped.

**Only one old drive plugged in at a time?** Run it with just that drive,
then later with the next one, always to the same `--output`:
```
python organize_photos.py --source E:\ --output D:\Organized
python organize_photos.py --source F:\ --output D:\Organized
```
The tool remembers what it already copied, so a photo that is on both
drives is copied only once.

### Step 9. Look through the result

Open `D:\Organized` in File Explorer:
- `2019\`, `2020\`, ... — photos and videos with a camera date, by year
  and month.
- `_review\` — everything else, in three folders, each sorted by month:
  - `_review\screenshots\` — screenshots. Mostly junk; skim and delete.
  - `_review\photos\` — photos with no camera date: memes and downloads,
    but also **real photos saved from Facebook, WhatsApp, texts and so
    on**, because those apps remove the date. Worth a proper look.
  - `_review\videos\` — videos that are not camera originals: re-sent
    clips, screen recordings, downloads.
- `manifest.csv` — a spreadsheet listing every file from the old drives
  and where it went.

### Step 10 (optional). Pull one app's screenshots into their own folder

If `_review\screenshots\` is full of screenshots of one app, for example
songs you captured to remember later. The easy way: double-click
`Sort Screenshots.bat` in `C:\photo_organizer` and answer its questions.
By hand:
1. Make a folder `C:\photo_organizer\examples` and copy one of those
   screenshots into it. If the app's look changed over the years, add one
   of each look.
2. In PowerShell (step 4), preview, then run:
   ```
   python sort_screenshots.py --output D:\Organized --examples C:\photo_organizer\examples --name music --dry-run
   python sort_screenshots.py --output D:\Organized --examples C:\photo_organizer\examples --name music
   ```
3. The matches move to `D:\Organized\_review\music\`. If some were missed,
   copy one of the missed ones into the examples folder and run again.

### Step 11. Wipe the old drives, only when you are happy

The tool never deletes anything. Once you have checked the new drive,
clearing the old ones is up to you.

### Stuck?

- **The line starts with `>>>`, or you see `SyntaxError` or
  `invalid syntax`.** You are typing into Python itself, not PowerShell.
  Type `exit()`, press Enter, close that window, and open PowerShell the
  way step 4 describes. You never need the `>>>` window.
- **"python is not recognized", or typing `python` opens the Microsoft
  Store.** Python is not installed, or the "Add python.exe to PATH" box
  was not ticked. First try typing `py` instead of `python` in every
  command (for example `py --version`, then
  `py -m pip install -r requirements.txt`). If that does not work either,
  close PowerShell, run the Python installer from step 1 again, choose
  **Modify**, click Next, tick **Add Python to environment variables**,
  click Install, and then open PowerShell again (step 4).
- **"pip is not recognized".** Type the commands exactly as written
  above, starting with `python -m pip`, not just `pip`.
- **"Pillow is required".** Step 5 was skipped or did not finish. Do
  step 5 again.
- **"can't open file" or "No such file or directory".** PowerShell is not
  in the tool's folder. The line before the cursor must end in
  `C:\photo_organizer>`. Open PowerShell from that folder as in step 4.
- **"Source folder not found".** A drive letter in the command is wrong
  or the drive is unplugged. Check the letters under This PC (step 3).
- **Nothing seems to happen.** On big drives it can work for a long time
  before printing much. If the window looks frozen, press Enter once:
  clicking inside a PowerShell window can pause it.
- **Still stuck?** Take a photo or screenshot of the whole PowerShell
  window and send it to whoever gave you this tool.

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
