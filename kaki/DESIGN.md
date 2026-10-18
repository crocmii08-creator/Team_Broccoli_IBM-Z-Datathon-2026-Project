---
name: Kaki companion
description: Implemented companion component within the existing Kaki live demo
colors:
  companion-teal: "#0E8F7E"
  companion-concern: "#173E39"
  companion-backing: "#FFFFFF"
  guidance-yellow: "#FFC21A"
  caption-ink: "#17212A"
typography:
  body:
    fontFamily: "Inter, sans-serif"
    fontSize: "17px"
    fontWeight: 600
    lineHeight: 1.4
rounded:
  caption: "16px"
spacing:
  companion-gap: "8px"
  rest-padding: "8px"
components:
  companion:
    width: "64px"
    height: "64px"
    textColor: "{colors.companion-teal}"
  companion-rest:
    width: "80px"
    height: "80px"
    padding: "{spacing.rest-padding}"
  companion-warning:
    width: "64px"
    height: "64px"
    textColor: "{colors.companion-concern}"
  companion-caption:
    backgroundColor: "{colors.companion-backing}"
    textColor: "{colors.caption-ink}"
    typography: "{typography.body}"
    rounded: "{rounded.caption}"
    padding: "12px 14px"
---

# Design System: Kaki companion

## Overview

**Creative North Star: "The expressive line companion"**

This records the user-approved companion redesign in `kaki-demo.html`, using the pinned HeyClicky character as its reference. A sparse, angular happy face feels friendly through expression and rounded strokes. Kaki retains its teal identity and switches to concern for warnings.

This is a component system, not a new whole-page identity. The surrounding demo, phone, controls and app screens remain incumbent context; their observed colors below are descriptive rather than new system commitments.

**Key Characteristics:**

- Minimal inline SVG line geometry.
- Happy guidance and concerned warning expressions.
- Readable captions and one foreground companion.
- Speech-linked motion with reduced-motion support.

## Colors

### Primary

- **Companion Teal:** happy face strokes and caption outline; retains Kaki's identity.
- **Concerned Deep Teal:** warning face strokes.

### Secondary

- **Guidance Yellow:** warning stroke backing; also the incumbent tap-highlight color.

### Neutral

- **White Backing:** thick under-stroke separating the happy face from app content; caption background.
- **Caption Ink:** guidance caption text.

Observed surroundings: body `#0F1923`, header `#0A1017`, panels `#131F2C`, borders `#1E2B38`, body text `#E8EDF2`, secondary text `#8899AA`, blue accents `#64B5F6`, and warning red `#C8283A`. These existing page values are context only; this component pass does not authorize or prescribe a surrounding redesign.

## Typography

Guidance captions use the frontmatter body role. The warning caption also uses the observed 17px size and 1.4 line-height; its incumbent weight is not changed by this update. Text wraps within the available caption width, including long multilingual strings.

**The Caption Rule.** Every spoken line retains a visible caption; update the existing text span rather than adding duplicate text.

## Layout

The base face occupies a square defined in frontmatter. Resting faces have a larger outer box with padding, retaining the same drawable face size. The guidance row aligns the face and caption at their bottom edges with the companion gap. It sits 178px above the phone viewport bottom, with 10px left and right insets, above the dock.

Eight resting placements belong to their existing app screens. The shared guidance and warning faces bring the shipped total to ten inline SVG instances. The phone viewport remains the incumbent 393×852px canvas; its fixed width is an observed constraint, not a responsive rule to propagate to new pages.

## Elevation & Depth

The face has a subtle ambient drop shadow (`0 2px 2px rgba(0,50,43,.14)`); concern uses a red-tinted shadow (`0 2px 2px rgba(60,0,0,.15)`). White or yellow backing provides the primary separation from app content. The caption retains its inset teal outline (2px stroke, −2px outline offset).

## Shapes

The SVG viewBox is `0 0 64 64`. Foreground paths use a 4.5-unit stroke and an 8.5-unit backing stroke, both unfilled with round caps and joins. Happy eyes are open chevrons and the smile is a shallow curved path. Concern substitutes slanted brows and an inverted mouth curve. Preserve the sparse face without adding a head disk or dotted halo.

## Components

### Companion

The face communicates through geometry and state. Its outer element has `role="img"` and an expression-specific accessible label; the internal SVG is hidden from assistive technology and cannot receive focus. Faces use `pointer-events:none` so the guidance layer does not consume taps.

Eyes blink on a 6s cycle. Happy-mouth motion uses a 0.48s alternate cycle only while a real speech utterance is active. Speech start and completion handlers are guarded against stale callbacks; replacement, error and reset clear the speaking state. Concerned paths remain static. With `prefers-reduced-motion:reduce`, eye and mouth animations are disabled.

**The One Foreground Face Rule.** Hide resting duplicates while a guidance caption is shown; hide background guidance captions and resting faces while alert overlays are visible.

### Caption

The guidance caption uses the frontmatter caption tokens and grows within the row. Assign caption content through `textContent`; preserve the existing voice-note element and remove obsolete text nodes. Warning text uses its existing alert presentation with the larger caption size recorded above.

## Do's and Don'ts

### Do:

- **Do** retain teal happy strokes, white backing and yellow-backed concern.
- **Do** keep captions readable in English, Mandarin, Malay and Tamil.
- **Do** bind mouth motion to speech events and honor reduced-motion.
- **Do** show one foreground companion during guidance and warnings.

### Don't:

- **Don't** restore the old dotted-halo mascot in this component.
- **Don't** animate a speaking mouth merely because a caption is visible.
- **Don't** treat this component guide as authorization to redesign the surrounding demo.
