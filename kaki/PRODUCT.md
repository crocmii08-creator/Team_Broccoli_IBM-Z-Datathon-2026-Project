# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

The demo is a single web page. Inside it, a simulated iPhone 16 Pro (Natural Titanium) runs the Kaki experience, and every phone screen follows iOS conventions faithfully.

## Users

- **Primary audience for this page:** IBM Z Datathon 2026 judges. They watch a live presentation on a laptop or projector while the presenter clicks through the demo flows.
- **Who the product serves:** Singapore seniors (65+), addressed as "Ah Ma" / 阿嬤 / Nenek / பாட்டி. They use everyday apps (WhatsApp, HealthHub, phone calls) and are targeted by scams.
- **Human in the loop:** a family member (the son) who receives Kaki's alerts.

## Product Purpose

Kaki is a voice-first scam-detection and guided-navigation assistant for seniors. It speaks aloud, highlights the next button to tap one step at a time, and warns in English, Mandarin, Malay or Tamil as soon as it sees or hears scam wording. Success on this page means judges can see, within one live run, both Kaki guiding a safe task and Kaki stopping a scam, and they believe it could run on a real iPhone.

## Positioning

Kaki pairs live guidance with scam interception in all four of Singapore's official languages, and scores messages with a classifier trained and served on IBM LinuxONE (s390x). It is a companion that speaks and points, not a blocklist.

## Operating Context

- The demo is presented live. The presenter drives the side console (language, three demo flows, a message scorer, model metrics, an alert log) while the phone shows what the senior sees.
- Flow 1, safe: book a HealthHub appointment with Kaki highlighting each tap.
- Flow 2, scam: a WhatsApp "prize" message is scored and Kaki intervenes.
- Flow 3, scam call: during a call from a fake police officer, the transcript is scored live and Kaki tells the senior to hang up.
- Speech uses the browser's speech synthesis, and recognition falls back to demo transcripts. Scoring runs in the browser from `kaki_model.json`, with an embedded keyword fallback.

## Capabilities and Constraints

- A single self-contained file, `kaki-demo.html`, served over a local HTTP server so `kaki_model.json` can load.
- All four languages switch instantly for speech, captions and warnings. The non-English strings still need native-speaker review.
- Simulated apps only. No real banking, calls or messages are accessed, and the page must keep saying so.
- Scoring picks its mode automatically. It uses the LinuxONE `/score` API when `/api/health` answers (add `?api=0` to force local), otherwise the in-browser model from `kaki_model.json` (schema v2), and a keyword fallback only if the model fails to load. The page shows which mode is active.
- The in-browser `kaki-shared` block is a line-for-line port of `kaki_ml.py`, and `tests/test_parity.py` checks it. It must stay byte-identical between its marker comments.

## Brand Commitments

- Name: Kaki. Mascot: a minimal teal (#0E8F7E) line face with happy chevron eyes and a curved smile, inspired by the user-pinned HeyClicky reference. Rounded strokes have a white backing; warnings use a concerned dark-teal face with yellow (#FFC21A) backing. Yellow also marks Kaki's guidance highlight.
- Voice: warm, short and respectful. Kaki addresses the senior directly ("Ah Ma, tap…") and praises success.
- The IBM LinuxONE · Z Datathon 2026 · SSF2026 attribution stays visible.

## Evidence on Hand

- Out-of-fold model metrics in `kaki_model.json` (`meta.metrics.model_a`): overall AUC, catch rate, false alarms and precision at scam, plus per-language Singapore figures with sample counts and low-confidence flags. The page reads every number from the file and hard-codes none. The model metadata records the training architecture (currently AMD64), so the page must not claim it was trained on s390x unless the file says so.
- Pitch statistics already in the demo: S$661M lost to scams in Singapore in 2023, 37,000+ cases reported, 89% of seniors own smartphones.
- `scam_sg.csv` (51 labelled messages in four languages) and `kaki-pitch-deck.pptx`.
- No testimonials, users, or deployments exist. Do not invent them.

## Product Principles

1. The senior's screen comes first. Every phone screen must read as a real iPhone the senior already knows.
2. Show, don't claim. Judges should watch Kaki guide and intercept in real time.
3. Act before harm. A warning appears before the risky tap, not after.
4. Family stays in the loop. Alerts reach a trusted person rather than shaming the senior.

## Accessibility & Inclusion

The product serves seniors, so on-phone text uses large sizes (17pt body or larger for Kaki's captions), touch targets are at least 44pt, and contrast is high. Every spoken line is also shown as a caption, and the page honors reduced-motion preferences.
