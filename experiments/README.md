# Categorization experiment

Scripts for the measurement described in
[docs/categorization-plan.md](../docs/categorization-plan.md). They are for
developers. None of this is in the release zip, and the tool does not use it.

Everything these scripts write goes into `eval_data/` at the top of the
checkout, which `.gitignore` excludes. That folder holds real photos, their
names and per-file results. It is never committed. Only totals are copied
from it into the plan's results table, by hand.

## Install

    pip install -r requirements-dev.txt -r experiments/requirements.txt

The harness, the fact table, the rules and the review page need Pillow
alone. `anthropic` is needed only to send files for first-guess labels;
`onnxruntime` and `tokenizers` only for the local model. `onnxruntime` needs
Python 3.11 or newer, so this file does not install on Python 3.10.

## Two questions per file

Every file gets two labels, each answering one question, called a field:

- `made`: how the file was made (a camera photo, a screen capture, a saved
  image, a copy of something on paper);
- `shows`: what it shows (a receipt, a text thread, a document, a drawing,
  a meme or graphic, a thing, some other screen, or a photo).

The lists and the guide for close calls are in `common.py`. From pass 2
onwards every command takes `--field made` or `--field shows`, and each
field keeps its own files in `eval_data/labels/<field>/` and
`eval_data/results/<field>/`.

## The steps, in order

| Step | Command | What it does |
|---|---|---|
| Sample | `python experiments/sample.py --source undated=FOLDER --source camera=FOLDER` | Copies about 1,200 files, spread evenly, into `eval_data/` and splits them once into a tuning half and a final-check half. Sources are only read. `host:/folder` reads over ssh. |
| First guess, pass 1 | `python experiments/label_first_guess.py --pass 1` | **Sends the sampled files to the Anthropic API.** Free description plus a first label. Try `--dry-run` first: it prints what would be sent and sends nothing. |
| Tally | `python experiments/label_first_guess.py --tally --merge` | Counts the descriptions and writes thumbnail grids per group, and puts a starting list of labels for each field in `eval_data/labels/<field>/categories.json`, to be settled by a person. |
| First guess, pass 2 | `python experiments/label_first_guess.py --pass 2 --field made`, then `--field shows` | Labels every file against the settled list of one field. |
| First guess, locally | `python experiments/label_local.py --pass 1`, settle the lists, then `--pass 2 --field made` and `--field shows` | The same two steps with a small CLIP model on this computer instead. **Uploads nothing.** Pass 1 groups similar-looking files into thumbnail grids. The model files (about 600 MB) are downloaded once into `eval_data/models/` and checked against pinned hashes. |
| Top up | `python experiments/topup.py fetch --source undated`, then `pick --field shows --label receipt --also type=png`, label the picks, then `add --field shows --label receipt` | For a label with fewer than 40 examples. Copies the files of a source that were not sampled into `eval_data/topup/pool/` (the source is only read), lists the ones worth a look, and adds those someone labelled as wanted to both halves, marked `top-up`. They count for less in precision, because they make the label look more common than it is. |
| Review | `python experiments/review.py --field made --half tuning`, then `--field shows` | A local page: click the wrong ones, relabel them, confirm the rest of the grid. `--stats` shows how often a guess was changed. If `eval_data/labels/<field>/second_opinion.csv` holds a second labeller's answers, each label is split into a disagree pile (do it first) and an agree pile (spot-check it, then `--accept-rest all` in the tuning half). |
| Facts | `python experiments/facts.py --half tuning` | The table of facts that need no model. |
| Fact review | `python experiments/fact_review.py --field made` | Charts every fact against every label and says which separate it. |
| Rules | edit `experiments/rules.py`, then `python experiments/rules.py --field made` | Each rule of one field measured alone. |
| Measure | `python experiments/evaluate.py --candidate rules --field made --half tuning` | Precision, recall, confusion table, speed and install size for one candidate. |

## Ground rules

- **Uploads.** `label_first_guess.py` is the only script that sends anything
  anywhere, and only the sampled files, as small re-saved copies without
  EXIF data, file names or folders. It needs the library owner's say-so.
  The API key is read from the `ANTHROPIC_API_KEY` environment variable.
- **Which first guess.** Use the hosted model or the local one, not both.
  If the local model made the guesses, `eval_data/labels/<field>/first_guess.json`
  says so, and that model's own score will read a little high.
- **Two halves.** Rules, wording and thresholds are tuned on the tuning half
  only. `evaluate.py --half final` runs once per candidate and refuses a
  second run.
- **A new candidate** is a module in this folder with an object named
  `MADE` or `SHOWS` (or both), each with a `name`, a `field` saying which
  question it answers, and a `predict(paths)` method returning one
  `(label, confidence)` pair per path. See the top of `evaluate.py`.
- **Tests** are in `tests/test_experiment_*.py`. They use synthetic images
  and need no real photos, model or network.
