#!/usr/bin/env python3
"""
review.py: confirm or correct the first-guess labels.

Step 1 of docs/categorization-plan.md. The first guesses are not the answer
key; a person confirms them. This opens a page in your browser, served from
this computer only, showing one guessed label at a time as a grid of
thumbnails. Click a picture that is wrong and pick its right label; then
"Confirm this grid" records the picked labels for the ones you clicked and
the guessed label for all the rest, and the next grid appears.

Every grid is saved as soon as it is confirmed, so the job can be stopped
and picked up later. Nothing is uploaded; the page only talks to this
script.

In the final-check half every file is looked at. The tuning half may be
reviewed more loosely: look at all of the small labels, spot-check the big
`photo` pile with --spot-check, then accept the rest of that pile unseen
with --accept-rest. Files accepted unseen are marked as such.

--stats prints how often a guess was changed, per label.

Usage:
  python experiments/review.py --half tuning
  python experiments/review.py --half tuning --spot-check 60
  python experiments/review.py --half tuning --accept-rest photo
  python experiments/review.py --stats
"""
import argparse
import html
import io
import json
import os
import random
import re
import secrets
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

GRID_SIZE = 48
LABEL_COLUMNS = common.LABEL_COLUMNS
STATS_COLUMNS = ["guessed_label", "half", "guessed", "looked_at", "changed", "changed_share",
                 "accepted_unseen", "not_reviewed"]


def labels_file(eval_data):
    return common.inside(eval_data, "labels", "labels.csv")


def load_labels(eval_data):
    rows = common.read_csv(labels_file(eval_data))
    for row in rows:
        row.setdefault("reviewed", "")
    return rows


def waiting(label_rows, half_of, half, label, spot_check=None, seed=0):
    """Rows guessed as `label` in this half that nobody has confirmed yet.
    With spot_check, only that many of them, picked at random but the same
    ones every time, so a stopped spot check resumes where it left off."""
    mine = [r for r in label_rows if r["guessed_label"] == label and half_of.get(r["id"]) == half]
    if spot_check is not None:
        mine = sorted(mine, key=lambda r: r["id"])
        random.Random(seed).shuffle(mine)
        mine = mine[:spot_check]
    return [r for r in mine if not r["confirmed_label"]]


def apply_grid(label_rows, shown_ids, corrections, allowed):
    """Record one confirmed grid: the corrected label for each clicked
    file, the guessed label for every other file that was shown."""
    shown = set(shown_ids)
    for file_id, label in corrections.items():
        if file_id not in shown or label not in allowed:
            raise ValueError("bad correction for %s" % file_id)
    for row in label_rows:
        if row["id"] in shown:
            row["confirmed_label"] = corrections.get(row["id"], row["guessed_label"])
            row["reviewed"] = "yes"


def accept_rest(label_rows, half_of, half, label):
    """Confirm, unseen, every still-unconfirmed file guessed as `label` in
    this half. Returns how many. Refused for the final-check half, where
    every file must be looked at."""
    if half != "tuning":
        raise ValueError("only the tuning half may be accepted unseen")
    count = 0
    for row in waiting(label_rows, half_of, half, label):
        row["confirmed_label"] = row["guessed_label"]
        row["reviewed"] = "no"
        count += 1
    return count


def stats(label_rows, half_of):
    """How often the reviewer changed a guess, per guessed label and half.
    Only files a person actually looked at count toward `changed`."""
    table = {}
    for row in label_rows:
        key = (row["guessed_label"], half_of.get(row["id"], ""))
        line = table.setdefault(key, {"guessed_label": key[0], "half": key[1], "guessed": 0,
                                      "looked_at": 0, "changed": 0, "accepted_unseen": 0,
                                      "not_reviewed": 0})
        line["guessed"] += 1
        if not row["confirmed_label"]:
            line["not_reviewed"] += 1
        elif row["reviewed"] == "no":
            line["accepted_unseen"] += 1
        else:
            line["looked_at"] += 1
            line["changed"] += row["confirmed_label"] != row["guessed_label"]
    for line in table.values():
        line["changed_share"] = ("%.3f" % (line["changed"] / line["looked_at"])
                                 if line["looked_at"] else "")
    return [table[key] for key in sorted(table)]


PAGE_STYLE = """
body{font:15px system-ui;margin:20px;background:#f6f6f4}
.grid{display:flex;flex-wrap:wrap;gap:8px}
.cell{width:190px;background:#fff;border:3px solid #fff;border-radius:6px;padding:4px;cursor:pointer}
.cell img{width:100%;height:170px;object-fit:contain;display:block}
.cell.wrong{border-color:#d9480f;background:#fff4e6}
.cell select{width:100%;margin-top:4px;display:none}.cell.wrong select{display:block}
.cell a{font-size:12px;color:#666}
button{font:16px system-ui;padding:10px 22px;margin:16px 0;cursor:pointer}
table td,table th{padding:4px 14px;text-align:left}
"""

GRID_SCRIPT = """
document.querySelectorAll('.cell').forEach(function (cell) {
  cell.addEventListener('click', function (event) {
    if (event.target.tagName === 'SELECT' || event.target.tagName === 'OPTION'
        || event.target.tagName === 'A') return;
    cell.classList.toggle('wrong');
  });
});
document.getElementById('confirm').addEventListener('click', function () {
  var corrections = {}, shown = [];
  document.querySelectorAll('.cell').forEach(function (cell) {
    shown.push(cell.dataset.id);
    if (cell.classList.contains('wrong')) corrections[cell.dataset.id] = cell.querySelector('select').value;
  });
  fetch('/confirm', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({token: TOKEN, shown: shown, corrections: corrections})})
    .then(function (r) { if (r.ok) location.reload(); else alert('Not saved: ' + r.status); });
});
"""


class Review:
    """What the server needs to remember between requests."""

    def __init__(self, eval_data, half, labels, spot_check, seed):
        self.eval_data = eval_data
        self.half = half
        self.labels = labels
        self.spot_check = spot_check
        self.seed = seed
        self.token = secrets.token_urlsafe(16)
        self.sample = {r["id"]: r for r in common.load_sample(eval_data)}
        self.half_of = {i: r["half"] for i, r in self.sample.items()}

    def spot_for(self, label):
        return self.spot_check if label == "photo" else None

    def waiting(self, rows, label):
        return waiting(rows, self.half_of, self.half, label, self.spot_for(label), self.seed)

    def index_page(self):
        rows = load_labels(self.eval_data)
        guessed = sorted({r["guessed_label"] for r in rows})
        lines = []
        for label in guessed:
            left = len(self.waiting(rows, label))
            total = sum(1 for r in rows if r["guessed_label"] == label
                        and self.half_of.get(r["id"]) == self.half)
            lines.append("<tr><td><a href='/grid?label=%s'>%s</a></td><td>%d</td><td>%d</td></tr>"
                         % (html.escape(label, quote=True), html.escape(label), total, left))
        return ("<h1>Review: %s half</h1><table><tr><th>Guessed label</th><th>Files</th>"
                "<th>Still to confirm</th></tr>%s</table><p>Start with the small labels.</p>"
                % (self.half, "".join(lines)))

    def grid_page(self, label):
        rows = load_labels(self.eval_data)
        left = self.waiting(rows, label)
        if not left:
            return "<h1>%s: all confirmed</h1><p><a href='/'>Back to the list</a></p>" % html.escape(label)
        options = "".join("<option%s>%s</option>" % (" selected" if name == "photo" and label != "photo" else "",
                                                     html.escape(name)) for name in self.labels if name != label)
        cells = []
        for row in left[:GRID_SIZE]:
            common.make_thumbnail(self.eval_data, self.sample[row["id"]])
            cells.append("<div class='cell' data-id='%s'><img src='/thumb/%s'>"
                         "<a href='/big/%s' target='_blank'>larger</a><select>%s</select></div>"
                         % (row["id"], row["id"], row["id"], options))
        return ("<p><a href='/'>Back to the list</a></p><h1>Guessed: %s</h1>"
                "<p>%d still to confirm. Click every picture that is NOT %s and pick its label. "
                "Then confirm: the rest are recorded as %s.</p><div class='grid'>%s</div>"
                "<button id='confirm'>Confirm this grid</button>"
                "<script>var TOKEN=%s;%s</script>"
                % (html.escape(label), len(left), html.escape(label), html.escape(label),
                   "".join(cells), json.dumps(self.token), GRID_SCRIPT))

    def confirm(self, body):
        if not secrets.compare_digest(str(body.get("token", "")), self.token):
            raise ValueError("wrong token")
        rows = load_labels(self.eval_data)
        apply_grid(rows, body["shown"], body["corrections"], self.labels)
        common.write_csv(labels_file(self.eval_data), LABEL_COLUMNS, rows)


def make_handler(review):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass                        # keep file ids out of the terminal

        def send(self, status, body, kind="text/html; charset=utf-8"):
            if isinstance(body, str):
                body = ("<!doctype html><meta charset='utf-8'><title>Review</title><style>%s</style>%s"
                        % (PAGE_STYLE, body)).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def local_only(self):
            """Refuse requests made under another site's name, so no web
            page open in the same browser can reach this server."""
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("127.0.0.1", "localhost")

        def do_GET(self):
            if not self.local_only():
                return self.send(403, "refused")
            url = urlparse(self.path)
            picture = re.fullmatch(r"/(thumb|big)/(s\d{4,})", url.path)
            if url.path == "/":
                self.send(200, review.index_page())
            elif url.path == "/grid":
                label = parse_qs(url.query).get("label", [""])[0]
                self.send(200, review.grid_page(label))
            elif picture and picture.group(2) in review.sample:
                row = review.sample[picture.group(2)]
                if picture.group(1) == "thumb":
                    path = common.make_thumbnail(review.eval_data, row)
                    data = path.read_bytes() if path else b""
                else:
                    buffer = io.BytesIO()
                    common.shrink(common.open_upright(common.sample_file(review.eval_data, row)),
                                  1600).save(buffer, "JPEG", quality=88)
                    data = buffer.getvalue()
                self.send(200, data, "image/jpeg")
            else:
                self.send(404, "not found")

        def do_POST(self):
            if not self.local_only() or self.path != "/confirm":
                return self.send(403, "refused")
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                review.confirm(body)
            except (ValueError, KeyError, TypeError):
                return self.send(400, "not saved")
            self.send(200, "saved")
    return Handler


def settled_labels(eval_data):
    path = common.inside(eval_data, "labels", "categories.json")
    if path.exists():
        return [c["label"] for c in json.loads(path.read_text(encoding="utf-8"))["labels"]]
    return [label for label, _ in common.STARTING_CATEGORIES]


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Confirm or correct the first-guess labels in a browser.")
    p.add_argument("--half", choices=("tuning", "final"), default="tuning")
    p.add_argument("--spot-check", type=int, default=None, metavar="N",
                   help="Tuning half only: offer just N of the files guessed as photo.")
    p.add_argument("--accept-rest", metavar="LABEL",
                   help="Tuning half only: confirm unseen every remaining file guessed as LABEL.")
    p.add_argument("--stats", action="store_true",
                   help="Print how often a guess was changed, per label, and stop.")
    p.add_argument("--port", type=int, default=0, help="Port to serve on. Default: any free one.")
    p.add_argument("--no-browser", action="store_true", help="Do not open the browser.")
    p.add_argument("--eval-data", default=str(common.DEFAULT_EVAL_DATA))
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    rows = load_labels(args.eval_data)
    if not rows:
        sys.exit("No first guesses yet. Run label_first_guess.py --pass 2 first.")
    half_of = {r["id"]: r["half"] for r in common.load_sample(args.eval_data)}

    if args.stats:
        table = stats(rows, half_of)
        common.write_csv(common.inside(args.eval_data, "labels", "review_stats.csv"),
                         STATS_COLUMNS, table)
        print("%-18s %-7s %7s %9s %8s %8s %12s" % ("guessed label", "half", "guessed",
                                                    "looked at", "changed", "unseen", "not reviewed"))
        for line in table:
            print("%-18s %-7s %7d %9d %8d %8d %12d"
                  % (line["guessed_label"], line["half"], line["guessed"], line["looked_at"],
                     line["changed"], line["accepted_unseen"], line["not_reviewed"]))
        return

    if args.spot_check is not None and args.half != "tuning":
        sys.exit("--spot-check is for the tuning half. Every final-check file is looked at.")
    if args.accept_rest:
        try:
            count = accept_rest(rows, half_of, args.half, args.accept_rest)
        except ValueError as error:
            sys.exit(str(error))
        common.write_csv(labels_file(args.eval_data), LABEL_COLUMNS, rows)
        print("Accepted %d files guessed as %s without looking." % (count, args.accept_rest))
        return

    info = common.inside(args.eval_data, "sample_info.json")
    seed = json.loads(info.read_text(encoding="utf-8")).get("seed", 0) if info.exists() else 0
    review = Review(args.eval_data, args.half, settled_labels(args.eval_data), args.spot_check, seed)
    server = HTTPServer(("127.0.0.1", args.port), make_handler(review))
    address = "http://127.0.0.1:%d/" % server.server_address[1]
    print("Reviewing the %s half at %s  (Ctrl-C to stop; everything confirmed is saved)"
          % (args.half, address))
    if not args.no_browser:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
