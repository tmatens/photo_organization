# What changed and why

Plain-language notes on every change to the script, newest first. Each entry
links to the pull request, which holds the exact code change and a longer
explanation.

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
