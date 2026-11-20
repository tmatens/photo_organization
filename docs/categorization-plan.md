# Plan: categorizing photos that need review

Status: **plan only. Nothing here is built or measured yet.** This file is
for developers; it is not part of the release zip.

## The question

After a run, `_review/` holds everything without a camera date, and the
main `YYYY/MM` tree holds everything with one. Both contain files a person
would rather deal with as a group: receipts, documents, memes, screenshots
saved as JPEG, and photos of printed photos. Can a script label these well
enough to sort them, on the user's own computer, without making the tool
hard to install?

This plan answers that by measurement before any feature is built. It ends
in one of three decisions: ship a model-based categorizer, ship a
rules-only one, or ship nothing.

## Constraints that do not move

- **No uploads.** The tool never sends a photo anywhere. Any model it
  uses runs locally; a one-time model download is acceptable.
  One exception, in this experiment only and never in the tool: the
  sampled files of the labelled set may be sent to a hosted model to get
  first-guess labels (step 1), if the owner of that library agrees.
- **The organizer stays as it is.** Categorizing is a separate script run
  afterwards, like `sort_screenshots.py`, with a dry run, a log, and an
  updated `manifest.csv`. The base install stays Pillow alone; anything a
  model needs is optional, the way HEIC support is.
- **Originals are never touched.** The script reads and moves only the
  copies under the organized folder.
- **Real photos never enter this repo.** The labelled set, per-file results
  and anything naming a file stay on the machine that holds the photos.
  Only totals (counts, precision, recall, speed) are written here.

## Categories

A starting list. It is expected to change after the first round of
labelling shows what is actually in a library.

| Label | What counts |
|---|---|
| `screenshot` | A capture of a phone or computer screen, whatever its file type or name |
| `receipt` | A till receipt, invoice or ticket, photographed or scanned |
| `document` | Any other page of text: a letter, a form, a whiteboard, a slide |
| `photo-of-photo` | A camera picture of a printed photo, an album page or a framed picture |
| `meme-or-graphic` | An image made on a computer: a meme, a poster, a logo, a chart |
| `photo` | An ordinary photo. The default, and by far the largest group |

The list is settled from what is actually in the library, not guessed. In
the first labelling pass (step 1) the hosted model also writes a few words
describing each file in its own terms, and may answer `other`. Those
descriptions are grouped and counted, and a person looks through each
sizeable group and decides: a new label, part of an existing one, or just
`photo`. A group becomes a label only if it is common enough to matter and
is something a person would deal with as a group. The model then labels
every file again against the settled list, and that second pass is what
gets reviewed. A sample this size shows that a rare kind of file exists;
it does not hold enough of them to measure, so a new label is topped up to
40 examples like any other.

### Two questions per file, not one label

The first round of labelling showed that one label per file does not fit.
A screen capture of a receipt is a screenshot and a receipt at once, and
whichever rule picks the winner moves a large share of the screen captures
from one label to another. The single list above mixed two questions: how
the file was made, and what it shows. So each file is now labelled twice,
with exactly one answer to each question.

**How the file was made** (`made`):

| Label | What counts |
|---|---|
| `screen-capture` | A capture of a phone or computer screen, whatever its file type or name, cropped or not |
| `saved-image` | An image made on a computer and saved as it is: a meme, a graphic, a logo, a product picture |
| `paper-copy` | A scan or a camera picture of something on paper: a page, a card, a drawing, a printed photo |
| `camera-photo` | Taken with a camera or a phone camera. The default, and by far the largest group |

**What the file shows** (`shows`):

| Label | What counts |
|---|---|
| `text-thread` | A back-and-forth of written messages between people: a text or chat conversation, a comment thread under a social media post, a forum or email thread |
| `receipt` | Proof of a purchase or payment: a till receipt, an invoice, a bill, an order confirmation or a transaction, on paper or on a screen |
| `ticket` | A ticket, a boarding pass, a booking or a travel itinerary, on paper or on a screen, whether or not it shows a price |
| `cart` | A shopping cart or basket: items chosen in a shop's site or app but not yet paid for |
| `document` | A letter, form, flyer, schedule, map, card or page of a PDF: something that is, or would be, a sheet of paper. An ordinary web page or email is not this |
| `drawing` | A drawing, painting or handwriting made by hand, where the artwork fills the picture |
| `product` | A product picture or a shop page saved from the web, with nothing bought: one item, or several put together in a collage |
| `interior` | The inside of a building with no person or pet as the subject: a room, a hallway, a piece of decor in place, whether your own picture or a saved decorating idea |
| `car` | A car or other vehicle is the main subject of the picture: one for sale, your own, damage to one, its interior or dashboard. A picture of people or pets with a car in it, or a street where cars happen to be, is not this |
| `meme-or-graphic` | A meme, a quote card, an infographic, a logo, an advert or another made image |
| `thing` | Your own picture that records or shows a thing, with no person as the subject: an item for sale, damage or a repair, something you own, a sign |
| `screen-other` | A screen, web page or app page that shows nothing listed here: a form, a calendar, a search result, a video frame, a post that is mostly text |
| `photo` | A real picture of people, pets, places, events or food, however it reached you: taken with a camera, saved from the web, or shown on a captured screen where the picture is the point. The default, and by far the largest group |

The old labels map onto these. A `screenshot` is a `screen-capture` that
shows whatever it shows. A `photo-of-photo` is a `paper-copy` that shows a
`photo`. The old `photo` is a `camera-photo` that shows a `photo`.

What this changes in the rest of the plan:

- **No rule about which label wins.** Within one question a file still
  gets exactly one answer, and the guide for that question says what to do
  when two seem to fit. That guide is written down before labelling
  starts, not during it. It is in `experiments/common.py`.
- **Where a file is sorted to is a separate choice.** A sorter that puts
  each file in one place needs an order of preference between the two
  answers. That order belongs to the sorting step and can change without
  anything being labelled again.
- **Every step below runs once per question.** Wherever a later step says
  "label", read it as a label of one of the two questions. The two halves,
  the 40-example floor, the candidates and the bars of step 5 apply to each
  question separately, and the results table gets a row per label of each.
- **The two questions are expected to differ in how they can be answered.**
  How a file was made is the kind of thing facts about the file may
  decide. What it shows is where a model, or text that can be read, is
  likelier to be needed. Measuring them apart shows that split directly.

## Step 1. Build a labelled set

Nothing can be compared without a set of files whose right answers are
known. The repo's test libraries are synthetic and are no use for this.

1. Run the organizer on a real library.
2. Draw a sample from the organized folder, spread evenly across folders
   the way `--sample` does: about 600 files from `_review/` and about 600
   from the main tree. The main tree matters because a receipt or a photo
   of a photo taken with the phone's camera has a camera date and never
   reaches `_review/`.
3. Let a strong model make the first guess, then correct it. Send each
   sampled file, shrunk to a small copy, to a large hosted model (Claude,
   through the Anthropic API) with the label definitions above, and write
   its guesses to `labels.csv` (path, guessed label, confirmed label).
   This model only helps build the answer key; it is not a candidate and
   never ships. A small review script then shows the files one guessed
   label at a time, as a grid of thumbnails. The reviewer clicks the ones
   that are wrong and gives each its right label; the rest of the grid is
   confirmed in one go. The job can be stopped and resumed. Three rules:
   - **This is the one place photos leave the computer**, and only the
     sampled files, only with the say-so of the person whose library it
     is. See "Constraints". Without that say-so, a local candidate from
     step 3 makes the first guesses instead; note which one, because
     reviewers tend to accept suggestions and that candidate's score
     will then read a little high.
   - **The guesses are not the answer key.** A person confirms them. In
     the final-check half every file is looked at, including the large
     pile guessed as `photo`: a receipt filed under `photo` is found only
     if someone looks there, and skipping that makes recall read higher
     than it is. The tuning half may be reviewed more loosely: all of the
     small categories, and a spot check of `photo`.
   - **Record how often the reviewer changed a guess**, per label. It
     shows how far the hosted model can be trusted if the set is ever
     extended, and it is the ceiling to compare the local candidates
     with.
4. Top up the rare categories. If a label has fewer than 40 examples,
   find more until it does; below that, its numbers mean little.
   `experiments/topup.py` looks for them in the files of a source that
   were not sampled. Three rules:
   - **Cast two nets.** A local model suggests files, and so does a plain
     fact about the file (for instance "is a PNG"). A top-up found by a
     model alone holds only the examples that model finds easy, and it
     would flatter that model when it is measured.
   - **Mark what was added, and how many.** A top-up makes the label look
     more common than it is. Recall is not affected. Precision is: with
     more true examples in the set, the right answers outnumber the wrong
     ones by more than they would in the library. So the harness counts
     the files of a topped-up label at a reduced weight, such that
     together they count as many as the evenly drawn ones did.
   - **Added files are first guesses** and are reviewed like any other,
     shared equally between the two halves.
5. Split the set in two, once, at random: half for **tuning** and half for
   **the final check**. Wording, thresholds and model choices are tuned on
   the first half only. The second half is used once per candidate, at the
   end. Without this, the numbers flatter whichever candidate was fiddled
   with most.

The set lives in a folder named `eval_data/`, which `.gitignore` excludes.

Better still is a second labelled set from a different person's library,
used only for the final check. One library reflects one person's phones
and apps.

## Step 2. Build the harness

One script, `experiments/evaluate.py`, kept out of the release zip. Every
candidate plugs into it through the same small interface: given a list of
image paths, return a label and a confidence between 0 and 1 for each.

For each candidate it reports:

- **Per category:** precision (of the files it gave this label, how many
  were right) and recall (of the files that truly have this label, how
  many it found), at several confidence thresholds.
- **A confusion table:** which labels get mistaken for which.
- **Speed:** images per second on a CPU, with no graphics card, including
  the time to open and shrink each image.
- **Cost to the user:** installed size of the extra packages, size of the
  model download, and whether it installs cleanly with `pip` on Windows,
  macOS and Linux for the Python versions CI covers.

It writes two files into `eval_data/`: totals, and a per-file list of
mistakes for a person to look through. Only the totals are copied into the
results table at the end of this file.

The harness itself is tested with synthetic images, in the existing
`tests/` style, so CI covers its arithmetic without needing real photos
or a model.

## Step 2b. Look for mechanical signals first

Before any model is tried, find out how much can be decided from facts
that need no model. Once the labelled set exists, compute a table with one
row per file in the tuning half and one column per fact, using Pillow
alone:

- **About the file:** type; pixel size and whether it matches a known
  phone or computer screen; shape (width to height); which EXIF fields
  are present (camera make and model, lens, flash, software); the name
  pattern; the folder it originally came from, as recorded in
  `manifest.csv` (a folder named for a messaging app, downloads or
  screenshots says a lot); bytes per pixel.
- **About the pixels:** share that are near-white or near-black; how many
  distinct colours; how colourful; share of the image that is perfectly
  flat colour (screens and graphics have it, camera sensors never do);
  whether edges fall in rows the way lines of text do; a uniform band
  across the top or bottom, like a status bar.

Then, per label:

1. Chart each fact for that label against all the others and write down
   which ones separate it cleanly, which partly, and which not at all.
2. Turn the clean ones into rules a person can read in one sentence each
   ("screen-sized, no camera make, over a third flat colour: screenshot").
   A rule may also say only what a file is *not*.
3. Measure each rule with the harness: how many files it decides, and how
   often it is right.

The result is a table of labels against "share decided by rules at the
step 5 precision". It settles what the models are for:

- A label the rules cover needs no model. If that is every label that
  matters, stop here and ship rules.
- For a label the rules partly cover, the model is measured only on what
  the rules leave undecided, and rules run first when both ship: fewer
  files reach the model, so it is faster and has fewer chances to be
  wrong.
- A label with no usable signal is the model's job alone. Expect
  `photo-of-photo` here: it is an ordinary camera file of an ordinary
  scene, and little about the file gives it away.

The rules are found on the tuning half and checked once on the final-check
half, like everything else. The table of facts names files, so it stays in
`eval_data/`; the rules and their totals go in this file.

## Step 3. Candidates, cheapest first

Each one is measured before the next is tried. A later candidate has to
beat the earlier ones by enough to justify what it adds.

1. **Rules only, no model.** The rules found in step 2b. Needs nothing
   beyond Pillow. This is the baseline every model must beat, and for
   each label the models are judged on what these rules leave undecided.
2. **A small CLIP model, zero-shot.** The model scores each image against
   a short description of each label ("a photo of a till receipt"), with
   no training. Run through ONNX Runtime rather than PyTorch, to keep the
   install small. Start with the smallest widely used variant (ViT-B/32).
3. **Other models of the same kind.** A larger CLIP, a SigLIP model, and
   a model built for phones and laptops such as MobileCLIP. Same harness,
   same descriptions. This shows whether a bigger download buys accuracy
   on the hard category, photos of photos.
4. **Learning from examples.** Keep the model from 2 or 3, but instead of
   descriptions, compare each image with a handful of labelled examples.
   This is the `sort_screenshots.py` idea with a model behind it: the user
   drops a few receipts in a folder and the script finds the rest. Measure
   with 5, 20 and 50 examples per label, drawn from the tuning half.
5. **Rules and model together.** Rules decide the cases they are sure of;
   the model decides the rest. This is the expected shape of anything
   that ships with a model, so every model candidate is also measured
   this way.

Out of scope: any hosted service, and large vision-language models that
need a graphics card or several gigabytes of memory.

## Step 4. Iterate

For each model candidate, on the tuning half only:

1. Run it with the plainest descriptions and record the result.
2. Read the mistakes file. Group the errors by cause: wrong description,
   an unclear label definition, a category that should be split or merged,
   or a real limit of the model.
3. Change one thing: the wording, the set of descriptions per label, the
   image size, the threshold. Run again and record it, better or worse.
4. Stop when two changes in a row move nothing, or after ten rounds.

Then run the candidate once on the final-check half and write that row in
the results table. If the labels themselves changed along the way, relabel
both halves before any final check.

## Step 5. Decide

A candidate is good enough to ship for a label when, on the final-check
half, at one fixed confidence threshold:

- **Precision is at least 95%.** A file moved into `receipts/` that is not
  a receipt is a photo hidden from the person looking for it. Wrong moves
  cost more than missed ones.
- **Recall is at least 60%.** Below that, the folder it leaves behind is
  barely smaller and the feature is not worth an install.
- **It handles at least 5 images a second** on an ordinary laptop CPU, so
  20,000 files finish in about an hour.
- **The extra install is under 500 MB** in total and needs no compiler.

These numbers are a starting position, to be confirmed or changed before
step 3 begins, not after the results are in.

Labels are judged one at a time. Shipping `receipt` and `document` while
leaving `photo-of-photo` out is a fine outcome. A label that fails is
dropped, not shipped with a warning.

If rules alone pass for the labels that matter, ship rules alone.

## Step 6. If something ships

A separate `categorize.py`, shaped like `sort_screenshots.py`:

- `--dry-run` first; a CSV log with the label and confidence for every
  file it would move.
- Inside `_review/`, confident matches move to `_review/<label>/YYYY/MM/`
  and `manifest.csv` is updated.
- In the main `YYYY/MM` tree it only reports by default. Taking a
  camera-dated photo out of the timeline on a model's say-so needs an
  explicit option.
- Model packages go in their own optional requirements file, pinned. The
  model file is pinned by version and checked against a recorded hash
  after download. Both get an update path (Renovate) in the same change
  that adds them.
- A double-click `.bat`, a README section and a CHANGELOG entry, as for
  the sorter.

## Open questions

- Whose library, and how many, for the labelled set?
- Is the category list right, or is something common missing (documents
  of identity, children's drawings, product photos for selling)?
- Should the thresholds in step 5 be stricter for the main tree than for
  `_review/`?
- Where does the model file come from, and is that source acceptable as a
  download the double-click script makes on a friend's computer?

## Results

Filled in as candidates are measured. Final-check half only; totals only.

| Candidate | Label | Precision | Recall | Threshold | Images/s (CPU) | Extra install |
|---|---|---|---|---|---|---|
| | | | | | | |
