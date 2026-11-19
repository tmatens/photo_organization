"""
clip_local.py: a small CLIP model that runs on this computer.

CLIP turns a picture into a list of 512 numbers and a sentence into another
such list; a picture and a sentence that go together end up with similar
numbers. Scoring one picture against a short description of each label, and
taking the best match, gives a label with no training at all ("zero-shot").

The model is OpenAI's CLIP ViT-B/32, run through ONNX Runtime on the CPU.
Nothing is uploaded. The model files are downloaded once into
eval_data/models/ and checked against the hashes recorded below; a file
that does not match is refused.

Two uses, with the same code:
  - label_local.py uses it to make first-guess labels for the review, when
    the photos may not be sent to a hosted model.
  - CANDIDATE plugs it into evaluate.py as candidate 2 of the plan.

Needs the packages in experiments/requirements.txt. numpy comes with
onnxruntime.
"""
import hashlib
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

from PIL import Image  # noqa: E402

# The model, pinned to one revision of one public repository. The pin is
# changed by hand, never by a bot: a different export is a different
# candidate and every number measured with the old one stops applying.
MODEL = {
    "name": "clip-vit-b32",
    "base_url": "https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/"
                "6b7c523703ae26e39be4b03774966f8571c7f523/",
    "files": {
        "vision_model.onnx": ("onnx/vision_model.onnx",
                              "fd6e1402a588279d1723c7534d4bcba5bc0b14b47dfab0e46f8c47b8270d7d40"),
        "text_model.onnx": ("onnx/text_model.onnx",
                            "3f6571f5bad13a97c469c1622e1cfc4d9aef78b79fdbfcff804ca357bfada8cc"),
        "tokenizer.json": ("tokenizer.json",
                           "f7f3b7af117d467b58374797691a6438d3e6b9e9cef800dfd5dced7f697a90cd"),
    },
}

# How CLIP expects a picture: 224 pixels square, each colour shifted and
# scaled by these numbers from its training.
SIDE = 224
MEAN = (0.48145466, 0.4578275, 0.40821073)
STD = (0.26862954, 0.26130258, 0.27577711)
# CLIP multiplies similarities by 100 before turning them into shares.
SHARPNESS = 100.0

# Short descriptions to score a picture against, per label of the starting
# list. A settled list carries its own in categories.json.
STARTING_DESCRIPTIONS = {
    "screenshot": ["a screenshot of a phone screen", "a screenshot of a computer screen",
                   "a screenshot of an app"],
    "receipt": ["a photo of a till receipt", "a scanned invoice", "a photo of a ticket"],
    "document": ["a photo of a printed page of text", "a scanned letter or form",
                 "a photo of a whiteboard with writing", "a presentation slide"],
    "photo-of-photo": ["a photo of a printed photograph", "a photo of a photo album page",
                       "a photo of a framed picture on a wall"],
    "meme-or-graphic": ["a meme with a caption", "a poster or an advert", "a logo", "a chart",
                        "a digital illustration"],
    "photo": ["a photo of people", "a photo of a place outdoors", "a photo of a room indoors",
              "a photo of food", "a photo of an animal", "a photo of an object"],
}


# The same for the labels of the two fields in common.FIELD_LABELS.
FIELD_DESCRIPTIONS = {
    "screen-capture": ["a screenshot of a phone screen", "a screenshot of a computer screen",
                       "a screenshot of an app", "a screenshot of a web page"],
    "saved-image": ["a meme with a caption", "a digital graphic or illustration", "a logo",
                    "a product picture on a plain white background"],
    "paper-copy": ["a scanned page", "a photo of a sheet of paper", "a photo of a printed photograph",
                   "a photo of a drawing on paper"],
    "camera-photo": ["a photo of people", "a photo of a place outdoors", "a photo of a room indoors",
                     "a photo of food", "a photo of an animal", "a photo of an object"],
    "text-messages": ["a screenshot of a text message conversation",
                      "a screenshot of chat bubbles in a messaging app"],
    "receipt": ["a photo of a till receipt", "a scanned invoice or bill",
                "a screenshot of an order confirmation",
                "a screenshot of a purchase or transaction on a phone"],
    "document": ["a printed page of text", "a letter or a form", "a flyer or a schedule",
                 "a page of a PDF"],
    "drawing": ["a crayon or marker drawing on paper", "a hand-drawn picture",
                "a painting made by hand", "handwriting on paper"],
    "meme-or-graphic": ["a meme with a caption", "an infographic", "a logo", "an advertisement",
                        "a quote on a plain background"],
    "product": ["a product picture on a white background", "a screenshot of a shopping page",
                "a collage of products from a shop", "a catalogue picture of furniture"],
    "thing": ["a photo of something for sale", "a photo of damage or a repair",
              "a photo of an object on a table", "a photo of an empty room", "a photo of a sign"],
    "nothing-special": ["a photo of people", "a photo of a child", "a photo of a place outdoors",
                        "a photo of an event", "a photo of food", "a photo of a pet",
                        "a screenshot of an app", "a screenshot of a social media post"],
}


# Names for the groups of similar files that pass 1 of label_local.py finds.
# CLIP cannot make up words, so it picks from this list: the names whose
# numbers sit closest to a group. The list is deliberately much wider than
# the starting labels, so a kind of file nobody thought of can still show up
# by name. Each is read as "a <kind>".
KINDS = [
    # screens
    "screenshot of a text message conversation", "screenshot of a social media post",
    "screenshot of a web page", "screenshot of a map", "screenshot of a video game",
    "screenshot of a phone home screen", "screenshot of an email", "screenshot of a music player",
    "screenshot of a video call", "screenshot of an online shop", "screenshot of a spreadsheet",
    "screenshot of computer code", "screenshot of a calendar", "screenshot of a banking app",
    # paper
    "photo of a till receipt", "photo of an invoice or bill", "photo of an event ticket",
    "photo of a printed letter", "photo of a filled-in form", "photo of a handwritten note",
    "photo of a book page", "photo of a newspaper or magazine page", "photo of a whiteboard",
    "photo of a restaurant menu", "photo of a recipe", "photo of a business card",
    "photo of an identity card or passport", "photo of a medical document",
    "photo of a school worksheet", "photo of a child's drawing", "photo of a sign or notice",
    "photo of a product label or packaging", "photo of a price tag", "photo of a barcode or QR code",
    "photo of a computer screen", "photo of a television screen", "presentation slide",
    "scanned document",
    # pictures of pictures
    "photo of an old printed photograph", "photo of a photo album page",
    "photo of a framed picture on a wall", "scan of an old photograph",
    "black and white photograph", "school portrait", "photo of a painting or artwork",
    # made on a computer
    "meme with a caption", "cartoon or comic", "digital illustration", "poster or flyer",
    "advertisement", "logo", "chart or graph", "diagram", "floor plan", "map", "infographic",
    "greeting card", "invitation", "motivational quote on a background", "emoji or sticker",
    "collage of several photos", "photo with a filter and text added", "wallpaper image",
    "product photo on a white background", "stock photo",
    # ordinary photos
    "selfie", "portrait of one person", "group photo of people", "photo of a baby",
    "photo of children playing", "photo of a family at home", "photo of a wedding",
    "photo of a birthday party", "photo of a school event", "photo of a sports game",
    "photo of a concert or show", "photo of a holiday celebration", "photo of a dog",
    "photo of a cat", "photo of a wild animal", "photo of food on a plate", "photo of a drink",
    "photo of a landscape", "photo of a beach", "photo of mountains", "photo of a sunset",
    "photo of a city street", "photo of a building", "photo of a house", "photo of a garden",
    "photo of flowers", "photo of snow", "photo of a car", "photo of a room indoors",
    "photo of furniture", "photo of a toy", "photo of clothes", "photo of a tool or appliance",
    "photo of damage or a repair", "photo of something for sale", "photo of a museum exhibit",
    "photo taken from a plane or car window", "blurry or accidental photo", "very dark photo",
]


def name_groups(vectors, groups, kind_vectors, kinds=None, top=3):
    """{group number: [the `top` kinds closest to that group's average
    picture]}. A suggestion for a person to read, nothing more."""
    kinds = kinds or KINDS
    names = {}
    for group in sorted(set(groups)):
        members = vectors[[i for i, g in enumerate(groups) if g == group]]
        centre = unit(members.mean(axis=0, keepdims=True))[0]
        order = (kind_vectors @ centre).argsort()[::-1][:top]
        names[group] = [kinds[i] for i in order]
    return names


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def model_folder(eval_data, model=MODEL):
    return common.inside(eval_data, "models", model["name"])


def fetch_model(eval_data, model=MODEL, download=urllib.request.urlretrieve):
    """Make sure every model file is in eval_data/models/ and is exactly the
    file that was pinned. Downloads what is missing. A file whose hash does
    not match is deleted and reported, never used."""
    folder = model_folder(eval_data, model)
    folder.mkdir(parents=True, exist_ok=True)
    for name, (remote, expected) in model["files"].items():
        path = folder / name
        if not path.exists():
            print("Downloading %s (once)..." % name)
            tmp = path.with_name(name + ".part")
            download(model["base_url"] + remote, str(tmp))
            os.replace(tmp, path)
        if sha256_of(path) != expected:
            path.unlink()
            sys.exit("%s is not the pinned model file (its hash differs). It has been removed."
                     % name)
    return folder


def model_megabytes(eval_data, model=MODEL):
    """Size of the downloaded model files, for the harness's cost report."""
    folder = model_folder(eval_data, model)
    return sum((folder / name).stat().st_size for name in model["files"]) / 1e6


def prepare(img):
    """One picture as CLIP wants it: the shorter side shrunk to 224 pixels,
    the middle 224 x 224 cut out, colours scaled. Returns a numpy array of
    shape (3, 224, 224)."""
    import numpy as np
    w, h = img.size
    scale = SIDE / min(w, h)
    img = img.resize((max(SIDE, round(w * scale)), max(SIDE, round(h * scale))), Image.BICUBIC)
    w, h = img.size
    left, top = (w - SIDE) // 2, (h - SIDE) // 2
    pixels = np.asarray(img.crop((left, top, left + SIDE, top + SIDE)), dtype=np.float32) / 255.0
    pixels = (pixels - np.array(MEAN, dtype=np.float32)) / np.array(STD, dtype=np.float32)
    return pixels.transpose(2, 0, 1)


def unit(vectors):
    """Scale each row to length 1, so a dot product is a similarity."""
    import numpy as np
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def shares(image_vectors, description_vectors, labels_of):
    """For each picture, how strongly it matches each label, as shares that
    add up to 1.

    Every description competes with every other (a softmax of the
    similarities), and a label's share is the sum over its descriptions.
    labels_of[i] is the label description i belongs to. A catch-all label
    such as `photo` needs many different descriptions; adding them up lets
    any one of them win a picture, where averaging them into one vague
    description would lose to a single specific one.
    Returns (labels in first-seen order, array of shares)."""
    import numpy as np
    scores = SHARPNESS * image_vectors @ description_vectors.T
    scores = scores - scores.max(axis=1, keepdims=True)
    exp = np.exp(scores)
    each = exp / exp.sum(axis=1, keepdims=True)
    labels = list(dict.fromkeys(labels_of))
    columns = [each[:, [i for i, name in enumerate(labels_of) if name == label]].sum(axis=1)
               for label in labels]
    return labels, np.stack(columns, axis=1)


def best_labels(share_rows, labels):
    """[(label, confidence)] from shares(): the strongest label per picture
    and its share."""
    top = share_rows.argmax(axis=1)
    return [(labels[i], float(row[i])) for i, row in zip(top, share_rows)]


def group_similar(vectors, groups, seed=0, rounds=25):
    """Sort pictures into `groups` clusters of similar ones (k-means on the
    unit vectors). Returns a group number per picture. The same seed gives
    the same groups."""
    import numpy as np
    rng = np.random.default_rng(seed)
    groups = min(groups, len(vectors))
    centres = vectors[rng.choice(len(vectors), size=groups, replace=False)]
    assigned = np.zeros(len(vectors), dtype=int)
    for _ in range(rounds):
        assigned = (vectors @ centres.T).argmax(axis=1)
        for g in range(groups):
            members = vectors[assigned == g]
            if len(members):
                centres[g] = members.mean(axis=0)
        centres = unit(centres)
    return [int(g) for g in assigned]


class Clip:
    """The loaded model. Loading takes a second or two, so make one and
    reuse it."""

    def __init__(self, eval_data, model=MODEL):
        import onnxruntime
        from tokenizers import Tokenizer
        folder = fetch_model(eval_data, model)
        options = {"providers": ["CPUExecutionProvider"]}      # no graphics card, by design
        self.vision = onnxruntime.InferenceSession(str(folder / "vision_model.onnx"), **options)
        self.text = onnxruntime.InferenceSession(str(folder / "text_model.onnx"), **options)
        self.tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))

    def embed_images(self, paths, batch=16):
        """A unit vector per image path. A file that cannot be opened gets a
        row of zeros, which matches nothing."""
        import numpy as np
        out = np.zeros((len(paths), 512), dtype=np.float32)
        for start in range(0, len(paths), batch):
            good, pixels = [], []
            for i, path in enumerate(paths[start:start + batch], start):
                try:
                    pixels.append(prepare(common.open_upright(path)))
                    good.append(i)
                except Exception:
                    pass
            if good:
                vectors = self.vision.run(None, {"pixel_values": np.stack(pixels)})[0]
                out[good] = unit(vectors)
        return out

    def embed_texts(self, texts):
        """A unit vector per sentence. Sentences go in one at a time: this
        export of the model has no way to be told which tokens are padding."""
        import numpy as np
        rows = []
        for text in texts:
            ids = np.array([self.tokenizer.encode(text).ids], dtype=np.int64)
            rows.append(self.text.run(None, {"input_ids": ids})[0][0])
        return unit(np.stack(rows))


def descriptions_from(categories):
    """([description], [label of each description]) from a categories dict.
    A label without its own descriptions falls back to the starting ones."""
    texts, labels_of = [], []
    for entry in categories["labels"]:
        for text in (entry.get("descriptions") or FIELD_DESCRIPTIONS.get(entry["label"])
                     or STARTING_DESCRIPTIONS.get(entry["label"], [])):
            texts.append(text)
            labels_of.append(entry["label"])
    missing = [e["label"] for e in categories["labels"] if e["label"] not in labels_of]
    if missing:
        sys.exit("These labels have no descriptions to score pictures against: %s"
                 % ", ".join(missing))
    return texts, labels_of


class ClipZeroShot:
    """Candidate 2 of the plan, for evaluate.py. One per field: it scores
    pictures against the descriptions in that field's settled list."""

    name = MODEL["name"] + "-zero-shot"

    def __init__(self, field):
        self.field = field
        self.eval_data = common.DEFAULT_EVAL_DATA
        self.loaded = None

    def configure(self, eval_data):
        self.eval_data = eval_data

    def predict(self, paths):
        if self.loaded is None:
            clip = Clip(self.eval_data)
            path = common.field_file(self.eval_data, self.field, "categories.json")
            texts, labels_of = descriptions_from(json.loads(path.read_text(encoding="utf-8")))
            self.loaded = (clip, clip.embed_texts(texts), labels_of)
        clip, description_vectors, labels_of = self.loaded
        labels, share_rows = shares(clip.embed_images(list(paths)), description_vectors, labels_of)
        return best_labels(share_rows, labels)


MADE = ClipZeroShot("made")
SHOWS = ClipZeroShot("shows")
