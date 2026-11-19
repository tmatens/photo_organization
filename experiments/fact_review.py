#!/usr/bin/env python3
"""
fact_review.py: which facts separate each label from the rest.

Step 2b of docs/categorization-plan.md, the part done per label. It reads
the fact table of the tuning half and the confirmed labels of one field
(how the file was made, or what it shows) and, for every label and every
fact, charts that label against all the others and gives
a verdict:

  clean    one cut on this fact alone picks out most of the label and is
           almost never wrong
  partly   the fact leans the right way but needs help from another
  no       the fact says nothing about this label
  too few  the label has fewer than 40 files in this half, so any cut that
           looks perfect may be luck; top the label up before judging it

The verdicts and charts go to eval_data/facts/<field>/review.html and
separation.csv. A person reads them and writes the rules in rules.py; this
script suggests cuts but writes no rules itself.

Usage:
  python experiments/fact_review.py --field made
"""
import argparse
import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import evaluate  # noqa: E402
import facts as facts_module  # noqa: E402

MIN_EXAMPLES = 40      # the plan's floor: below this a label's numbers mean little
SEPARATION_COLUMNS = ["label", "fact", "verdict", "best_cut", "precision", "recall", "ranking"]
BINS = 24


def ranking_score(mine, others):
    """How well a number ranks this label's files apart from the rest: 0.5
    means not at all, 1.0 means every one of this label's files is higher
    than every other file, 0.0 means every one is lower."""
    if not mine or not others:
        return 0.5
    ordered = sorted([(v, 1) for v in mine] + [(v, 0) for v in others])
    rank_sum, i = 0.0, 0
    while i < len(ordered):
        j = i
        while j < len(ordered) and ordered[j][0] == ordered[i][0]:
            j += 1
        average_rank = (i + 1 + j) / 2          # ties share the middle rank
        rank_sum += average_rank * sum(flag for _v, flag in ordered[i:j])
        i = j
    return (rank_sum - len(mine) * (len(mine) + 1) / 2) / (len(mine) * len(others))


def best_number_cut(mine, others, min_precision=evaluate.MIN_PRECISION):
    """The single cut ('at least X' or 'at most X') that finds the most of
    this label while staying at min_precision. Returns (text, precision,
    recall), or (None, None, 0.0) when no cut is that precise."""
    best = (None, None, 0.0)
    for cut in sorted(set(mine)):
        for text, keep in (("at least %.4g" % cut, lambda v, c=cut: v >= c),
                           ("at most %.4g" % cut, lambda v, c=cut: v <= c)):
            hits = sum(1 for v in mine if keep(v))
            wrong = sum(1 for v in others if keep(v))
            precision = hits / (hits + wrong)
            recall = hits / len(mine)
            if precision >= min_precision and recall > best[2]:
                best = (text, precision, recall)
    return best


def best_value_cut(mine, others, min_precision=evaluate.MIN_PRECISION):
    """For a fact that is a word, not a number: the set of values that are
    each precise enough for this label, taken together."""
    good, hits, wrong = [], 0, 0
    for value in sorted(set(mine)):
        mine_n = sum(1 for v in mine if v == value)
        other_n = sum(1 for v in others if v == value)
        if mine_n / (mine_n + other_n) >= min_precision:
            good.append(value or "(empty)")
            hits += mine_n
            wrong += other_n
    if not good:
        return None, None, 0.0
    return "is " + " or ".join(good), hits / (hits + wrong), hits / len(mine)


def verdict(precision, recall, ranking, examples=MIN_EXAMPLES):
    """clean, partly, no or too few. See the top of this file."""
    if examples < MIN_EXAMPLES:
        return "too few"
    if precision is not None and recall >= evaluate.MIN_RECALL:
        return "clean"
    if (precision is not None and recall >= 0.15) or abs(ranking - 0.5) >= 0.3:
        return "partly"
    return "no"


def review(fact_rows, truth_by_id):
    """One dict per (label, fact) with the verdict and the best single cut."""
    rows = [r for r in fact_rows if r["id"] in truth_by_id]
    out = []
    for label in sorted(set(truth_by_id.values())):
        for fact in facts_module.FACT_COLUMNS[1:]:
            mine = [r[fact] for r in rows if truth_by_id[r["id"]] == label]
            others = [r[fact] for r in rows if truth_by_id[r["id"]] != label]
            if not mine or not others:
                continue
            if facts_module.is_number(fact):
                ranking = ranking_score(mine, others)
                cut, precision, recall = best_number_cut(mine, others)
            else:
                ranking = 0.5
                cut, precision, recall = best_value_cut(mine, others)
            out.append({"label": label, "fact": fact, "best_cut": cut or "",
                        "precision": precision, "recall": recall, "ranking": ranking,
                        "verdict": verdict(precision, recall, ranking, len(mine)),
                        "mine": mine, "others": others})
    return out


def chart(mine, others, numeric):
    """A small SVG: this label's files in one colour, the rest in another,
    each scaled to its own total so a rare label is still visible."""
    if numeric:
        low, high = min(mine + others), max(mine + others)
        span = (high - low) or 1.0

        def bucket(v):
            return min(BINS - 1, int((v - low) / span * BINS))
        names = None
        count = BINS
    else:
        names = sorted(set(mine + others))[:BINS]

        def bucket(v):
            return names.index(v) if v in names else None
        count = len(names)
    bars = []
    for values, colour, offset in ((others, "#9aa5b1", 0), (mine, "#d9480f", 5)):
        tally = [0] * count
        for v in values:
            b = bucket(v)
            if b is not None:
                tally[b] += 1
        for i, n in enumerate(tally):
            height = 40 * n / len(values)
            bars.append('<rect x="%d" y="%.1f" width="5" height="%.1f" fill="%s"/>'
                        % (i * 12 + offset, 42 - height, height, colour))
    caption = ""
    if names:
        caption = '<div class="names">%s</div>' % html.escape(" · ".join(n or "(empty)" for n in names))
    return '<svg width="%d" height="44">%s</svg>%s' % (count * 12, "".join(bars), caption)


def write_html(dest, results, counts):
    parts = ["<!doctype html><meta charset='utf-8'><title>Fact review</title><style>"
             "body{font:14px system-ui;margin:24px;max-width:1100px}"
             "td,th{padding:4px 10px;text-align:left;vertical-align:top;border-bottom:1px solid #ddd}"
             ".clean{color:#087f5b;font-weight:600}.partly{color:#b35c00}.no,.too{color:#999}"
             ".names{font-size:11px;color:#666;max-width:300px}</style>"
             "<h1>Which facts separate each label</h1>"
             "<p>Orange bars: this label. Grey bars: every other file. Each is scaled to its own total.</p>"]
    for label in sorted(counts):
        parts.append("<h2>%s <small>(%d files)</small></h2><table><tr><th>Fact</th><th>Verdict</th>"
                     "<th>Best single cut</th><th>Right</th><th>Finds</th><th>Chart</th></tr>"
                     % (html.escape(label), counts[label]))
        mine = sorted((r for r in results if r["label"] == label),
                      key=lambda r: ({"clean": 0, "partly": 1, "no": 2, "too few": 3}[r["verdict"]],
                                     -r["recall"]))
        for r in mine:
            parts.append("<tr><td>%s</td><td class='%s'>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                         % (r["fact"], r["verdict"], r["verdict"], html.escape(r["best_cut"]),
                            evaluate.percent(r["precision"]), evaluate.percent(r["recall"]),
                            chart(r["mine"], r["others"], facts_module.is_number(r["fact"]))))
        parts.append("</table>")
    dest.write_text("".join(parts), encoding="utf-8")


def main(argv=None):
    p = argparse.ArgumentParser(description="Chart every fact against every label on the tuning half.")
    p.add_argument("--field", choices=common.FIELDS, required=True,
                   help="Which question: how the file was made, or what it shows.")
    p.add_argument("--eval-data", default=str(common.DEFAULT_EVAL_DATA))
    args = p.parse_args(argv)
    rows, _unreviewed = evaluate.labelled_rows(args.eval_data, "tuning", args.field)
    truth = {r["id"]: r["true_label"] for r in rows}
    if not truth:
        sys.exit("No confirmed labels for the tuning half yet. Run review.py first.")
    results = review(facts_module.load(args.eval_data, "tuning"), truth)
    counts = {}
    for label in truth.values():
        counts[label] = counts.get(label, 0) + 1
    common.write_csv(common.inside(args.eval_data, "facts", args.field, "separation.csv"), SEPARATION_COLUMNS,
                     [dict(r, precision="" if r["precision"] is None else "%.3f" % r["precision"],
                           recall="%.3f" % r["recall"], ranking="%.3f" % r["ranking"])
                      for r in results])
    dest = common.inside(args.eval_data, "facts", args.field, "review.html")
    dest.parent.mkdir(parents=True, exist_ok=True)
    write_html(dest, results, counts)
    for label in sorted(counts):
        clean = [r["fact"] for r in results if r["label"] == label and r["verdict"] == "clean"]
        partly = [r["fact"] for r in results if r["label"] == label and r["verdict"] == "partly"]
        if counts[label] < MIN_EXAMPLES:
            print("%-18s %4d files  too few to judge (needs %d)" % (label, counts[label], MIN_EXAMPLES))
            continue
        print("%-18s %4d files  clean: %s  | partly: %s"
              % (label, counts[label], ", ".join(clean) or "none", ", ".join(partly) or "none"))
    print("Charts: %s" % dest)


if __name__ == "__main__":
    main()
