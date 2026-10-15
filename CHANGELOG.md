# What changed and why

Plain-language notes on every change to the script, newest first. Each entry
links to the pull request, which holds the exact code change and a longer
explanation.

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

## Photos with no real date get their own folder, and the scan skips junk

**Undated photos.** A screenshot, a picture received through a messaging
app, or a download has no EXIF date. The script used to file those by the
file's modification time, which is usually the day it was copied or
downloaded, into the same `YYYY/MM` folders as real camera photos. The
guesses were indistinguishable from the facts. They now go into
`_review/YYYY/MM/` instead, so the main library is only photos with a
known date, and the undated ones are together in one place to look over.
`--mix-undated` restores the old behaviour; `--undated-folder` renames the
folder.

**What the scan ignores.** Hidden files (anything starting with `.`,
including the `._photo.jpg` sidecar files macOS leaves on external drives)
and system folders such as the Recycle Bin, Synology `@eaDir` thumbnail
caches, and Spotlight indexes are skipped. Before, the sidecars were
counted as unreadable photos and the thumbnail caches were copied as if
they were photos.

**What it tells you it left behind.** Videos are not copied, and the
summary now says how many were found. iPhone HEIC photos need an optional
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
screenshot matching works. Every future change will add a test that fails
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
