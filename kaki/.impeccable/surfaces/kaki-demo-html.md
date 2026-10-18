---
version: 1
slug: "kaki-demo-html"
primary_target: "kaki-demo.html"
related_targets: []
---

# Kaki live demo (kaki-demo.html)

Mode: Operate. The presenter completes three demo flows in front of judges; the phone screens are an emulated iOS device.

Audience and job: Datathon judges watching live on a projector or laptop. The presenter must start any flow, switch language, and score a typed message without hunting for controls. Judges must read the phone as a real iPhone.

Constraints: single HTML file; keep every flow, string, scorer, voice and metric behavior; demo-only disclaimer stays.

## Direction contract

THESIS: The brief pins the world: a real iPhone 16 Pro in Natural Titanium, running genuine iOS screens. The page refuses the Figma-export phone of absolutely positioned boxes, coordinate tap zones and floating blob avatars.

OWN-WORLD: iOS system vocabulary (SF/Inter type ramp, grouped inset lists, system tints, materials, Dynamic Island, sheets, alerts, banners). The stage is a warm-graphite product-staging backdrop. Kaki contributes teal #0E8F7E, yellow #FFC21A for guidance, and its expressive line face (see the companion update below).

STORY: Judges see Kaki point and speak during a safe booking, then watch it stop a WhatsApp prize scam and a fake-police call. They come away believing it fits on their parents' phones.

FIRST VIEWPORT: On the left, the titanium iPhone at full stage height under a soft stage light, showing the home screen. On the right, the console: language segmented control and three flow rows (each with a run state) at the top, then the scorer with a live risk meter, then metrics and the alert log.

FORM: Pinned by the brief (an iOS device emulation), so no roll was run. The signature move is that Kaki lives in the Dynamic Island: it rests as a compact live activity and expands into a caption that speaks to the senior. seed: none (unavailable)

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Companion update — 2026-10-18

Scope: the user confirmed redesigning the companion character, inspired by HeyClicky. This update covers that component and its caption integration only. The existing dark demo and simulated iPhone retain their incumbent design. Earlier whole-page direction above remains historical context; this update does not reconcile unrelated drift.

THESIS: A minimal expressive line face inspired by HeyClicky, retaining Kaki's teal identity.

OWN-WORLD: The existing dark demo and iPhone remain the component's surroundings. Rounded teal strokes use white backing for separation; warnings use dark-teal strokes with yellow backing.

STORY: A happy guide accompanies safe tasks; a concerned expression supports scam warnings.

FIRST VIEWPORT: A standalone face rests on the home screen. Guidance uses one foreground face and a clear caption above the dock. Resting duplicates hide during guidance; background captions and resting faces hide during alert overlays.

FORM: Code-led 64×64 inline SVG geometry, with ten instances: eight resting appearances, one guidance face and one warning face. Eyes blink; mouth motion follows the actual speech lifecycle; reduced-motion disables these animations. seed: none (user-pinned component reference).

FINISH: Scoped finish review is ship-ready with no requested corrections. Companion tokens and usage are recorded in root DESIGN.md and .impeccable/design.json. Reference: .impeccable/review/heyclicky-character-reference.png, sourced from https://www.heyclicky.com/icon-light.svg. Captures: desktop.png, mobile.png, companion-preview.png, companion-alert.png, companion-home.png and companion-detail.png under .impeccable/review/. Behavioral evidence: companion-checks.json; visual verdict: companion-finish-review.md.

Validation: zero JavaScript errors; all four language captions fit; all eight resting faces fit the phone; speech start, end, stale callbacks and reset pass; concerned expression swaps correctly; reduced-motion reports no animation. The existing fixed-width phone's broader mobile behavior remains outside this component update.
