# Pitch deck: ALAMKansya (BPI DataWave 2026)

For the 13 Nov submission: pitch deck plus a recorded presentation of 10–15 minutes.

- `Evidence-Brief-Pitch-Deck.pdf`: the deck, 19 slides at 1920×1080. The box at the top right of
  each slide names the required section it covers (A customer problem, B proposed solution,
  C role of AI, D expected benefits and impact, E feasibility and implementation).
- `Evidence-Brief-Pitch-Script.pdf`: what to say on each slide with running times (about 14½
  minutes, slides only), with notes for recording. Source:
  `script.md` (rendered through `script.html`).
- `slides.html`: the deck source, in the Bantay-Baha layout (Bebas Neue, Barlow, Space Mono) on a
  light background in BPI red and gold. `img/` holds prototype screenshots (synthetic data).
- `previous/`: the earlier deck organised by the judging score sheet.

To re-export the deck after editing: open `slides.html` in Edge or Chrome, Print, "Save as PDF",
margins None, "Background graphics" on. To re-export
the script, edit `script.md`, regenerate `script.html` and print it the same way (A4).

Figures come from `docs/HANDOFF.md` and the `backend/eval` runs. Token use and cost were measured
on 6 Bedrock briefs (Claude Sonnet 5.5, medium effort, 16 Nov 2026). Pilot targets and hosting
costs are proposals and estimates.

## Live demo

`ALAMKansya-Demo-Script.pdf` (source `demo-script.md`): a separate script for a live walkthrough of the app.
A 6-minute core demo in three acts (Ben asks, Ana reviews and approves, Ben is told), four optional extras
(permissions and access, ask an analyst, before you commission, Taglish), a pre-demo checklist and what to do if
something goes wrong.

`ALAMKansya-Demo.mp4`: a silent 5½-minute screen recording of acts 1–3 of the demo script, recorded from the
live app on synthetic data, with a visible cursor and a short caption per step, for the team to voice over.

`ALAMKansya-Demo-Edited.mp4`: the same recording with effects (hook card, act cards, zooms, callouts, spotlight,
end card), identical timing. `ALAMKansya-Demo-Voiceover.pdf` (source `demo-voiceover.md`): the voice-over cued to
the video's timestamps, each line sized to fit its slot.
