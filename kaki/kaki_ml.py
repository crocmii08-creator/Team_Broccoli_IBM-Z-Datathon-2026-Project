"""
kaki_ml.py — the single source of truth for Kaki's text features, scam rules,
decision thresholds and transaction features.

Imported by train.py (training), backend/app.py (LinuxONE inference API) and
tests/. kaki-demo.html carries a line-for-line JavaScript port of
normalise() / features() / rule_hits() / decide() between the markers
`BEGIN kaki-shared` and `END kaki-shared`; tests/test_parity.py checks that
the two produce identical output, so change both together.

Model design: one logistic regression over *binary* features
(word unigrams + word bigrams for Latin/Tamil script, character unigrams +
bigrams for Han script). Because features are binary and un-normalised, the
model's logit is exactly `intercept + sum(weight of each feature present)`,
so the browser reproduces the server's probability exactly from
kaki_model.json — no approximation, no separate "browser model".
"""

import math
import re
import unicodedata

SCHEMA_VERSION = 2

# Score at or above "suspicious" → amber warning; at or above "scam" → freeze.
THRESHOLDS = {"suspicious": 0.35, "scam": 0.70}

LANGS = ("en", "zh", "ms", "ta")
LANG_ALIASES = {"mandarin": "zh", "chinese": "zh", "malay": "ms", "bm": "ms", "tamil": "ta", "english": "en"}

# ── Normalisation ──────────────────────────────────────────────────────────────
# Only [0-9] (never \d) and no \b, so the JS port behaves identically.
_URL_RE   = re.compile(r"(?:https?://|www\.)\S+")
_MONEY_RE = re.compile(r"(?:s\$|\$|sgd ?)[0-9][0-9,]*(?:\.[0-9]+)?|[0-9][0-9,]*(?:\.[0-9]+)? ?sgd")
_PHONE_RE = re.compile(r"\+?[0-9][0-9 -]{6,}[0-9]")
_HAN_RUN_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]+|[^㐀-䶿一-鿿豈-﫿]+")
_HAN_CHAR_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")


def _keep(ch: str) -> bool:
    # Letters, combining marks (Tamil vowel signs!) and numbers survive.
    return unicodedata.category(ch)[0] in "LMN"


def normalise(text: str) -> str:
    """Lower-case, mask URLs / money / phone numbers, drop punctuation."""
    text = unicodedata.normalize("NFC", str(text)).lower()
    text = _URL_RE.sub(" url ", text)
    text = _MONEY_RE.sub(" moneyfigure ", text)
    text = _PHONE_RE.sub(" phonenumber ", text)
    text = "".join(ch if _keep(ch) else " " for ch in text)
    return " ".join(t for t in text.split(" ") if t)


def features(text: str) -> list:
    """Binary feature strings for one message (sorted, de-duplicated)."""
    feats = set()
    words = []                       # non-Han words in order, for bigrams
    for token in normalise(text).split(" "):
        if not token:
            continue
        for run in _HAN_RUN_RE.findall(token):
            if _HAN_CHAR_RE.match(run):
                chars = list(run)
                feats.update(chars)
                feats.update(a + b for a, b in zip(chars, chars[1:]))
                words.append(None)   # Han run breaks the word-bigram chain
            elif len(run) >= 2:
                feats.add(run)
                words.append(run)
            else:
                words.append(None)
    for a, b in zip(words, words[1:]):
        if a and b:
            feats.add(a + " " + b)
    return sorted(feats)


def analyzer(text: str) -> list:
    """CountVectorizer analyzer (module-level so pickles stay importable)."""
    return features(text)


# ── Rule layer: specific, word-bounded scam phrases (all languages) ────────────
# Applied regardless of the selected UI language — a scammer may write in any.
# Phrases are written un-normalised and normalised once at import.
_RAW_SCAM_PHRASES = [
    # English
    "safe account", "safe custody account", "safety account", "money laundering",
    "arrest warrant", "warrant for your arrest", "do not tell anyone", "don't tell anyone",
    "do not inform your bank", "do not contact police", "transfer all funds",
    "guaranteed returns", "risk-free profit", "100% risk free", "you will be arrested",
    # "Hi Mum, new number" impersonation — one hit alone gives an amber check
    "new number", "changed number", "my phone broke", "换了号码", "新号码", "nombor baru", "புதிய எண்",
    # Mandarin
    "安全账户", "洗钱", "逮捕令", "被逮捕", "不要告诉任何人", "保证回报",
    # Malay
    "akaun selamat", "pengubahan wang haram", "pencucian wang", "waran tangkap",
    "jangan beritahu sesiapa", "akan ditangkap",
    # Tamil (agglutinative: list the inflected forms scammers actually use)
    "பாதுகாப்பான கணக்கு", "பாதுகாப்பான கணக்கில்", "பாதுகாப்பான கணக்குக்கு",
    "யாரிடமும் சொல்லாதே", "யாரிடமும் சொல்லாதீர்கள்", "கைது செய்யப்படுவீர்கள்",
]
SCAM_PHRASES = sorted({normalise(p) for p in _RAW_SCAM_PHRASES})


def rule_hits(text: str) -> list:
    """Scam phrases present in the message. Latin/Tamil phrases match on whole
    words only (so "mas" never matches "christmas"); Han phrases match as
    substrings because Chinese has no spaces."""
    norm = normalise(text)
    padded = " " + norm + " "
    hits = []
    for p in SCAM_PHRASES:
        if _HAN_CHAR_RE.search(p):
            if p in norm:
                hits.append(p)
        elif " " + p + " " in padded:
            hits.append(p)
    return hits


def decide(prob: float, hits: list) -> str:
    """Combine model probability and rule hits into safe / suspicious / scam.
    Two or more distinct scam phrases are treated as a scam on their own."""
    if prob >= THRESHOLDS["scam"] or len(hits) >= 2 or (hits and prob >= THRESHOLDS["suspicious"]):
        return "scam"
    if prob >= THRESHOLDS["suspicious"] or hits:
        return "suspicious"
    return "safe"


def sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z)) if z >= 0 else math.exp(z) / (1.0 + math.exp(z))


# ── Transaction features (PaySim schema) ───────────────────────────────────────
# PaySim has no "recipient known" signal and its amounts are simulated currency
# units, not SGD. Recipient familiarity is therefore handled by the explicit,
# hand-written TRANSFER_HEURISTIC below — never presented as learned.
TYPE_MAP = {"CASH_OUT": 0, "TRANSFER": 1, "PAYMENT": 2, "DEBIT": 3, "CASH_IN": 4}
TXN_FEATURES = ["amount", "old_balance", "new_balance", "amount_ratio", "type_enc", "hour"]


def txn_features(amount, old_balance, new_balance, txn_type, hour) -> list:
    return [
        float(amount),
        float(old_balance),
        float(new_balance),
        float(amount) / (float(old_balance) + 1.0),
        float(TYPE_MAP.get(str(txn_type).upper(), TYPE_MAP["TRANSFER"])),
        float(int(hour) % 24),
    ]


# Hand-written rules (not learned). Each returns a floor on the risk score.
TRANSFER_HEURISTIC = {
    "source": "hand-written heuristic; PaySim has no recipient-familiarity field",
    "rules": [
        {"if": "recipient unknown AND amount/balance > 0.85", "min_score": 0.90},
        {"if": "recipient unknown AND amount > 20000",        "min_score": 0.85},
        {"if": "recipient unknown AND amount/balance > 0.5",  "min_score": 0.60},
        {"if": "recipient unknown AND amount > 1000",         "min_score": 0.40},
        {"if": "amount/balance > 0.85",                       "min_score": 0.50},
    ],
}


def transfer_heuristic(amount: float, balance: float, recipient_known: bool) -> float:
    ratio = amount / (balance + 1.0)
    unknown = not recipient_known
    if unknown and ratio > 0.85:
        return 0.90
    if unknown and amount > 20000:
        return 0.85
    if unknown and ratio > 0.5:
        return 0.60
    if unknown and amount > 1000:
        return 0.40
    if ratio > 0.85:
        return 0.50
    return 0.0
