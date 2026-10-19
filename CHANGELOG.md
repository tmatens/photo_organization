# What changed and why

Plain-language notes on every change to the tool, newest first. Each entry
describes the tool **as it was at that point**, so an older entry can
describe behaviour that a newer entry above it has since changed. For what
the tool does today, read `README.md`.

## Double-click to sort one app's screenshots

`Sort Screenshots.bat`, in the zip next to `Organize Photos.bat`, runs
`sort_screenshots.py` without typing commands. It creates and opens an
`examples` folder if there are no examples yet, asks for the new drive's
letter (checking that `Organized\_review\screenshots` is there) and a
name for the app's folder, runs the preview, and moves the matches only
after a `Y`. Running it again checks only what is left. Nothing in the
tools changed.

## Double-click to run on Windows, and a plainer walkthrough

A friend got stuck at "the Python command prompt": the old walkthrough
said to install Python, and it was easy to open Python itself and type the
commands into its `>>>` prompt, where none of them work. Two changes:

- `Organize Photos.bat`, in the zip, does the whole job from a
  double-click. It finds Python (or installs it with winget when it is
  missing, so the "Add python.exe to PATH" box no longer matters), installs
  what the tool needs, asks for the drive letters, runs the 500-file test,
  opens its spreadsheet, and copies for real only after a `Y`. Drive
  letters are put in capitals, so answering `e` one day and `E` the next
  still resumes an interrupted run instead of scanning everything again.
- The Windows walkthrough is rewritten for someone who has never used a
  command line: one step per heading, a check after each, a warning about
  the `>>>` window at the top, `python -m pip` instead of `pip`, and a
  "Stuck?" list matching the messages people actually see.

Nothing in the tools changed.

## README corrections

The walkthrough's download step named an old version as its example and
left two shipped files out of the "check the folder" list; the manifest
description still mentioned a "match" status that no longer exists; the
Mac setup section had lost its heading; a sentence was repeated; and the
section explaining why image matching was removed did not account for
the screenshot sorter added in 1.5.0. All corrected. Nothing in the tools
changed.

## A second script pulls one app's screenshots into their own folder

`sort_screenshots.py` runs after the organizer and looks only inside
`_review/screenshots/`. Given a folder with one or more example
screenshots of an app, it moves every screenshot that shares the app's
frame, the header at the top and the controls at the bottom, into
`_review/<name>/`, by month. The picture in the middle, which changes
with every song, is ignored, and the phone's screen size does not
matter. The manifest is updated to the new locations and a log says what
matched what. It is safe to run again after adding another example; only
what is still in the screenshots folder is checked.

This brings back, in a simpler form, what the original script's example
matching was for: fifteen years of screenshots of songs to listen to
later, from several phones, in one place. It needs no extra library
(Pillow only), no threshold tuning for the common case, and it can be
run as many times as needed rather than deciding everything in one pass.
The matching rule was calibrated on a real screenshot of the app.

## A quick sample before the long wait

`--sample 500` processes 500 files spread evenly from the first file on
the first drive to the last file on the last, instead of everything. With
`--dry-run` that gives a representative preview of three drives in a few
minutes: a mix of old and new folders, camera photos and screenshots,
every drive. The walkthrough now has this as the step before the full
preview. The same spacing is used every time, so two samples give the
same answer. A sample can also be run for real; the full run afterwards
skips whatever the sample already copied.

## Only a camera's own date puts a file in the main library

Before, a timestamp in a filename, or an EXIF save time, was enough to
file a photo into the main `YYYY/MM` tree. Those can be written by
software long after the picture was taken: a Telegram save named
`photo_2022-03-14_10-00-00.jpg` is dated when it was sent, not shot, and
a save time is when an app last wrote the file. Now only camera evidence
counts: the EXIF capture or digitized date in a photo, or the creation
time inside a MOV/MP4 video. Everything else goes to `_review/`, still
sorted by month using the best date available, so the review pile stays
browsable.

For videos the bar is higher still, because the creation time inside a
MOV/MP4 file is written by whatever program last encoded it: a clip
re-sent through WhatsApp or exported from an editor has a good header
dated when that happened. A video counts as camera-dated only with both
a header time and a camera-style filename (`VID_20220314_100000.mp4`,
`IMG_1234.MOV`, and the usual Samsung, Pixel, Canon, Nikon, DJI and GoPro
patterns). Messaging apps, screen recorders and downloads never use those
names.

The review folder now has a sub-folder per reason, so each can be gone
through on its own: `_review/screenshots/` (skim and delete),
`_review/photos/` (needs a proper look; social-media and messaging saves
land here), `_review/videos/` (large; a separate sitting). Each is sorted
by month inside.

What moves: filename-dated app saves, software-only save times, and
re-encoded videos leave the main timeline for `_review/`. Camera photos
and camera videos with their original names are unaffected.
`--mix-undated` now means "file everything into the main tree by its
best-guess date". The README has a new "How dates are decided" table and
says how to run the drives one at a time.

## The reasons for the two removals, in one place

The README now has a short section, "Why there is no example matching or
look-alike grouping", with the case for removing both in 1.2.0 and the
risks that come with it. Nothing in the tool changed. *(Since renamed
"Why the organizer itself does no image matching", because the screenshot
sorter added in 1.5.0 does match screenshots, as a separate step.)*

## The download step is spelled out

Step 2 of the Windows walkthrough now says exactly where to click on the
GitHub releases page, which file to download (and which two links to
ignore), how to use Windows' "Extract All..." and where to point it, and
how to check the result. The release zip is now flat, with the files at
the top level, so extracting into `C:\photo_organizer` puts the script
directly there as the later steps assume. Nothing in the tool changed.

## Look-alike grouping is gone; the review folder needs a real look

The optional `--dup-threshold` grouping of photos that merely looked the
same has been removed, and with it the second library the tool depended
on. The install is now a single package, Pillow. "Duplicate" means
byte-for-byte identical, which is what was asked for; a thumbnail or a
re-saved copy is a different file and is copied too. In practice those
copies have no date information and land in `_review/` rather than next
to the original. The manifest no longer has a `perceptual_hash` column,
and `_duplicates/` is only created by `--keep-dupes`.

The README now says plainly that the review folder is not only junk.
Photos saved from social media or messaging apps arrive with their dates
stripped, so a real photo of yours that a friend posted and you saved back
is, to the tool, undated, and goes to `_review/` with the screenshots and
memes. That folder needs a look, not just a delete.

## The example-image matching is gone

The option to pull out every photo that looked like one example image has
been removed, along with its three companion options. With every
screenshot now going to `_review/` regardless, there was nothing left for
it to do that a quick look through that folder does not do better, and
fewer options means fewer ways to get a surprising result. The manifest
no longer has a `matched-example` status. Nothing else changed.

## Every screenshot goes to the review folder

Screenshots used to be treated like photos when they carried a date, which
Android screenshots always do in their filename, so they landed in the
main timeline between real photos. Now any PNG file, and any file named
`Screenshot...` (Samsung saves screenshots as JPEG with that name), goes
to `_review/`, sorted by month inside it. Cameras and phones never save a
photo as PNG, so a PNG is a screenshot, a meme or a graphic, not a photo.
The rule can be switched off with `--png-is-photo`.

With this, the review folder holds everything that is not a dated camera
photo or video: screenshots, memes, messaging-app images and downloads.
The example-image matching still works for anyone who wants one app's
screenshots in a folder of their own, but the Windows walkthrough no
longer depends on it. *(Superseded: the example matching was removed in
the next change; `sort_screenshots.py`, above, is its replacement.)* The
option that names the folder is now `--review-folder`.

## A start-to-finish Windows walkthrough

The README now opens with the whole job as ten numbered steps: install
Python, download the release, plug in the drives, preview, run, pull out
the screenshots, look through the result, and only then wipe the old
drives. Nothing in the tool changed. *(The walkthrough has since grown to
eleven steps and no longer uses the example matching.)*

## Videos are organized too

Phone and camera videos (MOV, MP4, M4V, 3GP, AVI, MKV, WMV, MTS) are now
copied into the same year/month folders as photos. The date comes from the
filename when it carries one, otherwise from the creation time stored
inside MOV and MP4 files, otherwise the video goes to `_review/` like an
undated photo. The manifest marks header dates `(video-metadata)`.

Identical videos are copied once, the same as photos. Two things apply to
photos only, because they need to look at the picture: the look-alike
grouping and the example-screenshot matching. *(Both since removed.)*
Videos are never mistaken for a screenshot.

One caveat: the creation time inside a video file is recorded in universal
time, and the script converts it to this computer's local time. A video
shot near midnight, or while travelling, can land on the neighbouring day.

## Several drives into one library, and Windows path rules

`--source` can now be given more than once, so three old external drives
can be combined into one new one in a single run. Duplicates are found
across all of them: a photo that lives on two drives is copied once, and
the manifest says which drive the kept copy came from.

Two Windows-specific problems are fixed. A whole drive given as `E:\` was
not recognised as containing `E:\Organized`, because the check doubled
the backslash; the comparison is now done the way Windows itself does it,
case-insensitively and per drive. And files inside folder trees deeper
than 260 characters, which old backups produce easily, were reported as
missing; every file operation now uses the form of the path that Windows
accepts without that limit. The manifest still shows paths the normal way.

## Dates are read from filenames when the photo itself has none

Phones and many apps put the capture time in the filename:
`IMG_20220314_100000.jpg`, `PXL_20220314_100000123.jpg`,
`Screenshot_20220314-100000.png`, `2022-03-14 10.00.00.jpg`. Android
screenshots in particular have no EXIF date but always have this. The
script now uses a filename timestamp when there is no EXIF capture date,
ranking it above the EXIF save date (which is only when the file was last
written) and above the file's modification time (which is often just when
it was copied). The manifest marks these `(filename)`. In practice this
moves most Android screenshots out of `_review/` and into the right month.
*(Superseded twice: since "Every screenshot goes to the review folder",
screenshots always go to `_review/`; and since "Only a camera's own date
puts a file in the main library", a filename date only decides the month
inside `_review/`, never a place in the main library.)*

## Photos with no real date get their own folder, and the scan skips junk

**Undated photos.** A screenshot, a picture received through a messaging
app, or a download has no EXIF date. The script used to file those by the
file's modification time, which is usually the day it was copied or
downloaded, into the same `YYYY/MM` folders as real camera photos. The
guesses were indistinguishable from the facts. They now go into
`_review/YYYY/MM/` instead, so the main library is only photos with a
known date, and the undated ones are together in one place to look over.
`--mix-undated` restores the old behaviour; `--undated-folder` renames the
folder. *(The option is now `--review-folder`, and the folder has
sub-folders `screenshots/`, `photos/` and `videos/`.)*

**What the scan ignores.** Hidden files (anything starting with `.`,
including the `._photo.jpg` sidecar files macOS leaves on external drives)
and system folders such as the Recycle Bin, Synology `@eaDir` thumbnail
caches, and Spotlight indexes are skipped. Before, the sidecars were
counted as unreadable photos and the thumbnail caches were copied as if
they were photos.

**What it tells you it left behind.** Videos are not copied, and the
summary now says how many were found. *(Superseded: since "Videos are
organized too", above, videos are copied and organized like photos.)*
iPhone HEIC photos need an optional
package; without it they were silently skipped, and the summary now says
how many and how to include them.

**Output location.** The output folder can now be inside the source
folder, as the README always claimed. The script skips its own output
when scanning, so re-running does not pick up the organized copies.

## "Duplicate" now means identical, and the best copy is the one kept

Before this change, two photos counted as duplicates when a visual
fingerprint matched. That fingerprint is the same for a full-size photo and
its 320-pixel thumbnail, or for a crisp original and a heavily compressed
copy from a messaging app. The script kept whichever one it happened to
meet first and skipped the other, so a library with thumbnails or app
exports could end up holding the small version while the original was
silently left out of the organized copy. Nothing in the manifest showed it.

Now:

- **Duplicate means byte-for-byte identical.** Those are listed in the
  manifest and copied once, exactly as before. A new `content_hash` column
  in the manifest shows the fingerprint used.
- **Look-alikes are a separate, opt-in step.** `--dup-threshold` groups
  photos that look the same. The one with the most pixels goes into the
  main library and the rest go to `_duplicates/` for review. They are
  never dropped, because "looks the same" is a judgement you may want to
  check yourself. Without the flag, look-alikes are all copied as ordinary
  photos.
- **The result no longer depends on folder order.** The script reads every
  photo first and decides afterwards, and it walks folders in alphabetical
  order, so the same library organizes the same way on every run and every
  computer.

## The preview shows real results, and re-running is now safe

Three related problems, one cause: the script only wrote its manifest at
the very end, and never read it back.

- **A dry run showed nothing.** It printed four counts and no manifest, so
  there was nothing to preview. It now writes `manifest_dryrun.csv` with the
  exact destination of every photo, including the `_2`, `_3` numbering that
  photos taken in the same second get.
- **Re-running doubled the library.** The script did not know what it had
  already copied, so a second run copied every photo again with `_2` on the
  name. It now reads `manifest.csv` at startup, skips everything listed, and
  still recognises a duplicate of a photo copied in an earlier run.
- **An interrupted run lost its record.** A crash, a full disk, or closing
  the terminal two hours in threw away the entire manifest. Each line is now
  written the moment it is decided.

Alongside that: a photo that fails to copy is recorded as `error-copy` and
the run continues instead of stopping dead; copies go through a temporary
name so an interruption never leaves a half-written photo under a real
name; and each image is now opened once instead of three times, which
makes the run noticeably faster, especially on iPhone HEIC files.

## Photos are now filed by the date they were taken

Before this change, the script was filing every photo by the date the file
was last saved, not the date the picture was taken. The two are the same for
a photo straight off the camera, but any photo that was edited, exported, or
passed through a photo app got sorted under the edit date. The manifest
labelled these "(exif)" as if the capture date had been used, so there was
no way to spot it.

The cause: the capture date lives in a sub-section of the EXIF data that the
Pillow library does not return by default. The script asked for it in the
wrong place, never found it, and fell through to the save date.

Now the script looks in the right place, and prefers the capture date, then
the digitized date (for scans), then the save date, then the file's own
modification time. The manifest's `date_taken` column says which one it used:
`exif-original`, `exif-digitized`, `exif-modified`, or `file-date`. Anything
marked `file-date` had no usable EXIF date and is worth a second look.

## Tests and automatic checks

The script now has a test suite that builds tiny synthetic photo libraries
and runs the script against them. The tests capture the promises the README
makes: originals are never touched, photos land in year/month folders,
identical files are copied once, dry run copies nothing, and the example
screenshot matching works *(since removed)*. Every future change will add a test that fails
before the fix and passes after it, so a bug fixed once stays fixed.

GitHub runs these tests automatically on Windows, macOS and Linux for every
proposed change. The package versions the script needs are now written down
in `requirements.txt`, so "install the required packages" installs the
exact versions that were tested.

One correction: the README said Python 3.9 or newer. The current Pillow
library needs 3.10, so the README now says 3.10.

## Starting point

The script and README as originally shared, with the example app name in the
documentation made generic. No behaviour was changed, so every later entry
can be compared against this version.
