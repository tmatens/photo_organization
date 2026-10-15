# What changed and why

Plain-language notes on every change to the script, newest first. Each entry
links to the pull request, which holds the exact code change and a longer
explanation.

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
