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
alone. `anthropic` is needed only to send files for first-guess labels.

## The steps, in order

| Step | Command | What it does |
|---|---|---|
| Sample | `python experiments/sample.py --source undated=FOLDER --source camera=FOLDER` | Copies about 1,200 files, spread evenly, into `eval_data/` and splits them once into a tuning half and a final-check half. Sources are only read. `host:/folder` reads over ssh. |
| First guess, pass 1 | `python experiments/label_first_guess.py --pass 1` | **Sends the sampled files to the Anthropic API.** Free description plus a first label. Try `--dry-run` first: it prints what would be sent and sends nothing. |
| Tally | `python experiments/label_first_guess.py --tally --merge` | Counts the descriptions and writes thumbnail grids per group, to settle the list of labels in `eval_data/labels/categories.json`. |
| First guess, pass 2 | `python experiments/label_first_guess.py --pass 2` | Labels every file against the settled list. |
| Review | `python experiments/review.py --half tuning` | A local page: click the wrong ones, relabel them, confirm the rest of the grid. `--stats` shows how often a guess was changed. |
| Facts | `python experiments/facts.py --half tuning` | The table of facts that need no model. |
| Fact review | `python experiments/fact_review.py` | Charts every fact against every label and says which separate it. |
| Rules | edit `experiments/rules.py`, then `python experiments/rules.py` | Each rule measured alone. |
| Measure | `python experiments/evaluate.py --candidate rules --half tuning` | Precision, recall, confusion table, speed and install size for one candidate. |

## Ground rules

- **Uploads.** `label_first_guess.py` is the only script that sends anything
  anywhere, and only the sampled files, as small re-saved copies without
  EXIF data, file names or folders. It needs the library owner's say-so.
  The API key is read from the `ANTHROPIC_API_KEY` environment variable.
- **Two halves.** Rules, wording and thresholds are tuned on the tuning half
  only. `evaluate.py --half final` runs once per candidate and refuses a
  second run.
- **A new candidate** is a module in this folder with a `CANDIDATE` object
  that has a `name` and a `predict(paths)` method returning one
  `(label, confidence)` pair per path. See the top of `evaluate.py`.
- **Tests** are in `tests/test_experiment_*.py`. They use synthetic images
  and need no real photos, model or network.
