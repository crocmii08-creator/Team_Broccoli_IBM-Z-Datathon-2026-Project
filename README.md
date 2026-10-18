# Kaki — AI Guardian for Singapore Seniors
### IBM Z Datathon 2026 · Event Code: SSF2026

Kaki is a voice-first scam-detection and guided-navigation assistant for seniors in Singapore. It speaks, circles the next button step by step, and warns in English, Mandarin, Malay or Tamil when it sees or hears scam wording.

*Demo only. No real banking, calls or messages are accessed, and no family member is actually contacted.*

---

## Files

| File | Purpose |
|------|---------|
| `kaki-demo.html` | Single-file web demo (open through a local server) |
| `kaki_model.json` | Model weights, thresholds, rule phrases and measured metrics, written by `train.py` |
| `kaki_ml.py` | Shared feature extraction, scam phrases, thresholds and transfer features, used by training, the API and the tests |
| `train.py` | The only training pipeline. Writes `kaki_model.json` and `models/` |
| `models/` | `scam_model.pkl`, `txn_model.pkl` and `manifest.json` (SHA-256 hashes), loaded by the API |
| `scam_sg.csv` | 54 Singapore-style labelled scam/legit messages (EN 19, ZH 12, MS 12, TA 11) |
| `backend/app.py` | Flask inference API (gunicorn), built to run on LinuxONE |
| `backend/Dockerfile`, `docker-compose.yml`, `deploy/nginx.conf` | Container deployment: demo plus API on one origin |
| `notebooks/` | Interactive walkthroughs that call `train.py` (so their numbers match) |
| `tests/` | pytest suite: browser/JS parity, export correctness, API contract |
| `frontend/index.html` | Original Figma export (reference screens only) |

---

## Run the demo

### Option 1: browser only (in-browser model)

```bash
cd kaki            # this folder
python3 -m http.server 8080
# open http://localhost:8080/kaki-demo.html
```

Open the page through a server, not `file://`, so `fetch('./kaki_model.json')` works. The browser computes exactly the same probability as the API, because the model is a logistic regression over binary features and `kaki_model.json` holds every weight.

If `kaki_model.json` cannot be loaded, the demo falls back to a small keyword list. The Model Metrics panel then shows **"⚠ Keyword fallback … Reduced protection"**, so you can always tell which mode is active.

### Option 2: full stack (LinuxONE API)

```bash
docker compose up --build
# open http://localhost:8080
```

nginx serves the demo and proxies `/score` and `/api/*` to the backend. The demo detects the API through `/api/health` and scores through it; the panel shows "Scoring: LinuxONE API". Add `?api=0` to the URL to force in-browser scoring.

### Demo flows

| Flow | What to do |
|------|-----------|
| Flow 1: HealthHub (safe) | Click the green button, then tap each highlighted element on the phone |
| Flow 2: Prize scam | Click the red button and watch Kaki detect the scam |
| Flow 3: Scam call | Click the orange button, accept the call, and watch the transcript score rise |

The language toggle (EN / 中文 / BM / தமிழ்) sits above the flow buttons. Translations still need review by native speakers.

---

## Train the models

Requires Python 3.11+. A Kaggle account is optional (public datasets download anonymously through `kagglehub`).

```bash
pip install -r requirements-train.txt
python train.py              # --no-plots on headless machines, --offline to skip Kaggle
```

`train.py` writes `kaki_model.json`, `models/scam_model.pkl`, `models/txn_model.pkl` and `models/manifest.json`. It records the CPU architecture it ran on (`meta.trained_on_arch`). To claim "trained on LinuxONE", run it there and commit the output.

Data sources:
- `uciml/sms-spam-collection-dataset` (English SMS spam)
- `ealaxi/paysim1` (synthetic mobile-money transactions). The whole file is scanned: every fraud row is kept and legitimate rows are sampled uniformly.
- `scam_sg.csv` (Singapore-specific scripts in four languages)

If a download fails, small embedded fallbacks are used, and the metrics are tagged `"data_source": "fallback"`. Do not report those numbers.

### How the models are evaluated

| Model | Protocol | Reported |
|-------|----------|----------|
| A: scam messages | 4-fold stratified out-of-fold predictions after removing duplicate messages | AUC; catch rate and false-alarm rate at the amber threshold; precision/recall at the scam threshold; each both model-only and with rule phrases |
| B: transfers | 80/20 stratified holdout on sampled PaySim | ROC-AUC, PR-AUC, precision/recall at 0.5, feature importances |

Current results are in `kaki_model.json → meta.metrics`, and the demo's metrics panel reads them from there.

Read them with these caveats:
- **Per-language SG numbers rest on 11–19 messages each** and are flagged `low_confidence`. The model alone flags 57–78% of SG scams, depending on the language.
- The rule phrases were written with the SG scripts in view, so the "with rules" SG figures are optimistic.
- PaySim balances leak the label, amounts are simulated units (not SGD), and PaySim has no "recipient known" field. Recipient familiarity is a **hand-written heuristic** (`kaki_ml.TRANSFER_HEURISTIC`), not a learned feature.
- The biggest improvement available is more real, native-speaker Mandarin, Malay and Tamil scam and legitimate messages.

### Decision rule (same in the API and the browser)

`kaki_ml.decide(prob, rule_hits)`:
- **scam** if any of these hold:
  - prob ≥ 0.70
  - two or more distinct scam phrases match
  - one phrase matches and prob ≥ 0.35
- **suspicious** if prob ≥ 0.35 or one phrase matches
- **safe** otherwise

Scam phrases match on whole words, so "mas" never matches "christmas".

---

## API (`backend/app.py`)

| Endpoint | Body | Returns |
|----------|------|---------|
| `POST /score` (also `/api/scan-message`) | `{"text": str ≤ 2000, "lang": "en"\|"zh"\|"ms"\|"ta"}` | `{score, label, matchedWords, rule_hits, message, action, suggest_family_call, pause_seconds, lang}` |
| `POST /api/scan-transfer` | `{amount, balance_before, balance_after?, type?, hour_of_day?, recipient_known: bool, message_context?, lang?}` | `{label, fraud_probability, model_probability, heuristic_floor, message_label, …}` |
| `GET /api/health` | | status, architecture, model training time and data sources |
| `GET /api/stats` | | **static simulated** radar data (`"simulated": true`) |

Input is validated (400 on bad JSON, wrong types, non-finite or negative amounts, oversize text). CORS is limited to `KAKI_ALLOWED_ORIGINS`. Requests are rate-limited per client (`KAKI_RATE_LIMIT`, per worker). The API checks model pickles against `manifest.json` and the installed scikit-learn version before loading them.

`suggest_family_call` is a hint for the client UI. The API does not contact anyone.

### Run the API without Docker

```bash
pip install -r requirements-train.txt
python train.py --no-plots
python backend/app.py        # http://localhost:5001
```

### Build for LinuxONE (s390x)

```bash
docker buildx build --platform linux/s390x -f backend/Dockerfile -t kaki-backend .
```

The build context is the project root. If `models/manifest.json` exists, those models are used. Otherwise the build runs `train.py`. The image ships the models read-only and runs as a non-root user.

---

## Tests

```bash
python -m pytest tests -q
```

The suite covers:
- The browser score equals the server score.
- Exported weights are signed.
- The JS port in `kaki-demo.html` matches `kaki_ml.py` (needs Node).
- API validation, language coverage, CORS, rate limiting and tampered-model rejection.

---

## Judging criteria mapping (IBM Z Datathon 2026)

| Criterion | Kaki approach |
|-----------|--------------|
| **AI / ML on Z** | Training script and inference container built for LinuxONE s390x; the architecture used is recorded in the model file |
| **Social impact** | Targets scams against Singapore seniors (65+) |
| **Multilingual** | Warnings and rule phrases in EN, 中文, BM and தமிழ் (native-speaker review pending) |
| **Responsible AI** | One model in browser and API; matched words returned; low-confidence metrics flagged; "safe" verdicts never tell users to relax their guard; family-call suggestion keeps a human in the loop (simulated in the demo) |
| **Technical depth** | Binary n-gram LR exported exactly to the browser; PaySim RandomForest plus an explicit heuristic; out-of-fold evaluation; Python/JS parity tests |
