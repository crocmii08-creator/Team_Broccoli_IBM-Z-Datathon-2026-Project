"""
Kaki Backend API — serves the models produced by ../train.py.
Designed for IBM LinuxONE (s390x) behind nginx; runs anywhere Python does.

Endpoints:
  POST /api/scan-message   classify a text message as safe / suspicious / scam
  POST /score              same as scan-message; the contract kaki-demo.html calls
  POST /api/scan-transfer  classify a PayNow / bank transfer
  GET  /api/stats          SIMULATED scam-wave radar (static demo data)
  GET  /api/health         health check

Configuration (environment):
  KAKI_MODEL_DIR        directory holding scam_model.pkl, txn_model.pkl, manifest.json
  KAKI_ALLOWED_ORIGINS  comma-separated CORS origins (default: http://localhost:8080)
  KAKI_RATE_LIMIT       requests per minute per client, per worker (default 60; 0 = off)
  KAKI_TRUST_PROXY      "1" when behind exactly one reverse proxy (uses X-Forwarded-For)
"""

import hashlib
import json
import logging
import math
import os
import pickle
import platform
import sys
import threading
import time
from collections import defaultdict, deque

import sklearn
from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

BASE = os.path.dirname(os.path.abspath(__file__))
# kaki_ml.py lives at the project root locally and next to app.py in the image.
for _p in (BASE, os.path.dirname(BASE)):
    if os.path.exists(os.path.join(_p, "kaki_ml.py")) and _p not in sys.path:
        sys.path.insert(0, _p)
import kaki_ml  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kaki")

MAX_TEXT_CHARS = 2000
MAX_AMOUNT = 10_000_000


# ── Model loading ──────────────────────────────────────────────────────────────
class ModelError(RuntimeError):
    pass


def default_model_dir():
    env = os.environ.get("KAKI_MODEL_DIR")
    if env:
        return env
    for d in (os.path.join(BASE, "models"), os.path.join(os.path.dirname(BASE), "models")):
        if os.path.exists(os.path.join(d, "manifest.json")):
            return d
    return os.path.join(BASE, "models")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_models(model_dir):
    """Load the pickles named in manifest.json after checking their SHA-256.
    The hash check catches swapped or corrupted files; it is not a substitute
    for keeping the model directory read-only (the Docker image does)."""
    manifest_path = os.path.join(model_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        raise ModelError(f"No manifest.json in {model_dir}. Run `python train.py` first.")
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    if manifest.get("schema_version") != kaki_ml.SCHEMA_VERSION:
        raise ModelError(f"Model schema {manifest.get('schema_version')} != {kaki_ml.SCHEMA_VERSION}; retrain.")
    if manifest.get("sklearn_version") != sklearn.__version__:
        raise ModelError(f"Models were pickled with scikit-learn {manifest.get('sklearn_version')} but "
                         f"{sklearn.__version__} is installed; retrain or pin the same version.")
    loaded = {}
    for name in ("scam_model.pkl", "txn_model.pkl"):
        path = os.path.join(model_dir, name)
        expected = manifest.get("files", {}).get(name)
        if not expected or not os.path.exists(path) or _sha256(path) != expected:
            raise ModelError(f"{path} is missing or does not match manifest.json")
        with open(path, "rb") as f:
            loaded[name] = pickle.load(f)
    return loaded["scam_model.pkl"]["pipeline"], loaded["txn_model.pkl"]["model"], manifest


# ── Warnings (4 languages; translations need native-speaker review) ────────────
WARNINGS = {
    "en": {
        "scam":       "Kaki thinks this looks like a scam. Real police, banks and MAS never ask you to transfer money. Stop and call your family first.",
        "suspicious": "Kaki is not sure about this. Do you know this person in real life? Take your time and ask family if unsure.",
        "safe":       "Kaki did not spot scam signs. If anyone asks for money, passwords or OTPs, check with family first.",
    },
    "zh": {
        "scam":       "Kaki 觉得这像是骗局。真正的警察、银行和金管局绝不会叫你转账。请先停下来，打电话给家人。",
        "suspicious": "Kaki 不太确定。你在现实中认识这个人吗？不要急，不确定就问家人。",
        "safe":       "Kaki 没有发现诈骗迹象。如果有人向你要钱、密码或一次性密码，请先问家人。",
    },
    "ms": {
        "scam":       "Kaki rasa ini mungkin penipuan. Polis, bank dan MAS yang sebenar tidak akan meminta anda memindahkan wang. Berhenti dan hubungi keluarga dahulu.",
        "suspicious": "Kaki tidak pasti tentang ini. Adakah anda kenal orang ini? Jangan tergesa-gesa, tanya keluarga jika ragu.",
        "safe":       "Kaki tidak nampak tanda penipuan. Jika ada yang minta wang, kata laluan atau OTP, tanya keluarga dahulu.",
    },
    "ta": {
        "scam":       "இது மோசடி போல் தெரிகிறது என்று Kaki நினைக்கிறது. உண்மையான காவல்துறை, வங்கிகள், MAS ஒருபோதும் பணம் அனுப்பச் சொல்லாது. நிறுத்தி, முதலில் குடும்பத்தினரை அழையுங்கள்.",
        "suspicious": "Kaki-க்கு இதில் உறுதியில்லை. இந்த நபரை உங்களுக்கு நேரில் தெரியுமா? அவசரப்பட வேண்டாம், சந்தேகம் இருந்தால் குடும்பத்தினரிடம் கேளுங்கள்.",
        "safe":       "Kaki மோசடி அறிகுறிகளைக் காணவில்லை. யாராவது பணம், கடவுச்சொல் அல்லது OTP கேட்டால், முதலில் குடும்பத்தினரிடம் கேளுங்கள்.",
    },
}


def resolve_lang(lang):
    lang = str(lang or "en").lower()
    lang = kaki_ml.LANG_ALIASES.get(lang, lang)
    return lang if lang in WARNINGS else "en"


def verdict(label, lang):
    return {
        "label":   label,
        "lang":    lang,
        "message": WARNINGS[lang][label],
        "action":  {"scam": "freeze_screen", "suspicious": "slow_down"}.get(label, "continue"),
        # A suggestion for the client UI; this API does not contact anyone.
        "suggest_family_call": label == "scam",
        "pause_seconds": 10 if label == "scam" else 0,
    }


# ── Scoring helpers (shared by every endpoint) ─────────────────────────────────
def score_message(scam_pipe, text):
    prob = float(scam_pipe.predict_proba([text])[0, 1])
    hits = kaki_ml.rule_hits(text)
    vec, clf = scam_pipe.named_steps["vec"], scam_pipe.named_steps["clf"]
    coef = clf.coef_[0]
    present = [(f, coef[vec.vocabulary_[f]]) for f in kaki_ml.features(text) if f in vec.vocabulary_]
    top = [f for f, w in sorted(present, key=lambda x: -x[1]) if w > 0][:5]
    return prob, hits, top


def score_transfer(txn_model, amount, balance_before, balance_after, txn_type, hour, recipient_known):
    feats = kaki_ml.txn_features(amount, balance_before, balance_after, txn_type, hour)
    model_prob = float(txn_model.predict_proba([feats])[0, 1])
    heuristic = kaki_ml.transfer_heuristic(amount, balance_before, recipient_known)
    return model_prob, heuristic


# ── Input validation ───────────────────────────────────────────────────────────
class BadInput(ValueError):
    pass


def json_body():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise BadInput("request body must be a JSON object")
    return body


def num(body, key, default=None, lo=0.0, hi=MAX_AMOUNT):
    v = body.get(key, default)
    if v is None:
        raise BadInput(f"{key} is required")
    if isinstance(v, bool):
        raise BadInput(f"{key} must be a number")
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise BadInput(f"{key} must be a number")
    if not math.isfinite(v) or not lo <= v <= hi:
        raise BadInput(f"{key} must be between {lo:g} and {hi:g}")
    return v


def text_field(body, key, required=True):
    v = body.get(key, "")
    if not isinstance(v, str):
        raise BadInput(f"{key} must be a string")
    v = v.strip()
    if required and not v:
        raise BadInput(f"{key} is required")
    if len(v) > MAX_TEXT_CHARS:
        raise BadInput(f"{key} must be at most {MAX_TEXT_CHARS} characters")
    return v


# ── Rate limiting (in-process, per worker) ─────────────────────────────────────
class RateLimiter:
    def __init__(self, per_minute):
        self.per_minute = per_minute
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key):
        if self.per_minute <= 0:
            return True
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.per_minute:
                return False
            q.append(now)
            if len(self.hits) > 10_000:          # bound memory
                for k in [k for k, v in self.hits.items() if not v][:5_000]:
                    del self.hits[k]
            return True


# ── App factory ────────────────────────────────────────────────────────────────
def create_app(model_dir=None, scam_pipe=None, txn_model=None):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
    if os.environ.get("KAKI_TRUST_PROXY") == "1":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
    origins = [o.strip() for o in os.environ.get("KAKI_ALLOWED_ORIGINS", "http://localhost:8080").split(",") if o.strip()]
    CORS(app, origins=origins)
    limiter = RateLimiter(int(os.environ.get("KAKI_RATE_LIMIT", "60")))

    if scam_pipe is None or txn_model is None:
        scam_pipe, txn_model, manifest = load_models(model_dir or default_model_dir())
    else:
        manifest = {"trained_at": None, "data_sources": "injected"}
    logger.info("Models loaded (trained_at=%s)", manifest.get("trained_at"))

    @app.before_request
    def _limit():
        if request.method == "POST" and not limiter.allow(request.remote_addr or "?"):
            return jsonify({"error": "rate limit exceeded"}), 429

    @app.errorhandler(BadInput)
    def _bad(e):
        return jsonify({"error": str(e)}), 400

    @app.errorhandler(413)
    def _too_big(e):
        return jsonify({"error": "request body too large"}), 413

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok", "arch": platform.machine(),
                        "model_trained_at": manifest.get("trained_at"),
                        "data_sources": manifest.get("data_sources")})

    def _scan_message():
        body = json_body()
        text = text_field(body, "text")
        lang = resolve_lang(body.get("lang"))
        prob, hits, top = score_message(scam_pipe, text)
        result = verdict(kaki_ml.decide(prob, hits), lang)
        result.update({
            "score":            round(prob, 4),
            "scam_probability": round(prob, 4),
            "rule_hits":        hits,
            "matchedWords":     hits + [w for w in top if w not in hits],
        })
        return jsonify(result)

    app.add_url_rule("/api/scan-message", "scan_message", _scan_message, methods=["POST"])
    app.add_url_rule("/score", "score", _scan_message, methods=["POST"])

    @app.route("/api/scan-transfer", methods=["POST"])
    def scan_transfer():
        body = json_body()
        lang = resolve_lang(body.get("lang"))
        amount = num(body, "amount")
        balance_before = num(body, "balance_before")
        balance_after = num(body, "balance_after", default=max(0.0, balance_before - amount))
        hour = int(num(body, "hour_of_day", default=12, hi=23))
        txn_type = str(body.get("type", "TRANSFER")).upper()
        if txn_type not in kaki_ml.TYPE_MAP:
            raise BadInput(f"type must be one of {sorted(kaki_ml.TYPE_MAP)}")
        recipient_known = body.get("recipient_known", True)
        if not isinstance(recipient_known, bool):
            raise BadInput("recipient_known must be true or false")
        context = text_field(body, "message_context", required=False)

        model_prob, heuristic = score_transfer(txn_model, amount, balance_before, balance_after,
                                               txn_type, hour, recipient_known)
        risk = max(model_prob, heuristic)
        msg_label = None
        if context:
            m_prob, m_hits, _ = score_message(scam_pipe, context)
            msg_label = kaki_ml.decide(m_prob, m_hits)
            if msg_label == "scam":
                risk = min(1.0, risk + 0.30)

        if risk >= kaki_ml.THRESHOLDS["scam"]:
            label = "scam"
        elif risk >= kaki_ml.THRESHOLDS["suspicious"]:
            label = "suspicious"
        else:
            label = "safe"
        result = verdict(label, lang)
        result.update({
            "fraud_probability": round(risk, 4),
            "model_probability": round(model_prob, 4),
            "heuristic_floor":   heuristic,
            "message_label":     msg_label,
            "amount":            amount,
            "recipient_known":   recipient_known,
        })
        return jsonify(result)

    @app.route("/api/stats")
    def stats():
        return jsonify({
            "simulated": True,
            "note": "Static demo data, not real reports. Production would aggregate anonymised signals from opted-in devices.",
            "active_wave": True,
            "wave_type": "government_impersonation",
            "intensity": "HIGH",
            "top_patterns": ["police impersonation", "MAS safe-account", "CPF investment scam"],
        })

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=False)
