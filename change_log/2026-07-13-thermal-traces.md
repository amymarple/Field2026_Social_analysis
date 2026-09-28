# Thermal traces — rat heat-ghost detector (feasibility-gated, 108-scoped)

**Date:** 2026-07-13
**Plan:** [implementation_plan/2026-07-13-thermal-traces.md](../implementation_plan/2026-07-13-thermal-traces.md)
**Status:** Phase 0 DONE (GO/108, NO-GO/109); Phase 1 detector built, 108-scoped, candidate-only. No canonical
`results/` output, no direction promoted. Triggered by the user reframing the goal from "where/how many rats"
to "detect the **traces** rats leave behind (e.g. urine that looks a bit hot)".

## What shipped

- `thermal/trace_feasibility.py` — Phase 0 auto-anchored feasibility probe (GO/NO-GO gate).
- `thermal/detect_traces.py` — Phase 1 rat-anchored heat-ghost detector + `--selftest`.

## Method

A trace is the OPPOSITE regime to the rat detector: the rat is GONE and faint stationary warmth remains and
FADES. Rat-anchored pipeline (reuses `detect_blobs.robust_norm`/masks/`iter_frames`/`WarmBlobDetector` and
`trace_feasibility` primitives): rat detector → **rest-then-depart events** → per-event **annulus-referenced
contrast(t)** (AGC-undone, OSD + roaming red-crosshair excluded; annulus cancels AGC flicker) → accept a ghost
only if it steps up on arrival, stays elevated AFTER departure ≥ min_persist, and fits an exponential DECAY
(finite tau, R²≥0.3). **Flat-forever = a structure the rat sat by → rejected** (decay-physics discriminator).

**Still-present-rat gates (added after review):** because the rat detector's ~0.5 recall makes "departure"
(= detector stops firing) unreliable, warmth after "departure" can just be the rat still there. Two gates
separate a real ghost from a still-present/returning rat: (1) **re-detection** — truncate persistence at the
first rat re-detection at the site (if the clean pre-return persistence < min_persist → `rat_present`);
(2) **post-departure MOTION** — a cooling ground ghost is thermally static (small smooth frame-to-frame
change) while a lingering rat twitches; `post_motion_frac > 0.15 → rat_present`. The two catch different cases
(a fairly-still but re-detected rat vs an undetected but moving rat). A rat that sits perfectly still stays
indistinguishable from a ghost by thermal alone — an honest limit.

Outputs: `traces.csv` event list (now incl. `clean_persist`, `rat_return_f`, `post_motion_frac`), nightly
`trace_heatmap.png` (persistence-weighted splats over a frame), `summary.json`, per-trace contrast plots +
crops. Everything RELATIVE brightness, candidate-only.

## Key result — traces are substrate-dependent

Phase 0 on 2026-07-01 21:00, verified by eye (contrast curves + before/after crops):
- **108 = GO.** 5/19 rest-departures left a decaying warm ghost. Textbook case (731,113): rat leaves →
  130→55 → **decays 55→15 over ~2 min** (tau≈84 s); other cases tau 30–60 s, R²≥0.7. The "after" crop shows a
  faint warm patch where the rat rested; a detector-dropout would stay flat — it didn't.
- **109 = NO-GO.** 0/9; best candidate back to baseline within ~8 s. Same clean measurement → the absence is
  real. 108 images warmable ground (holds body heat); 109 images vegetation/wires (does not). So heat-ghost
  detectability depends on **what the camera sees**, not just rat presence — a finding in itself, and the
  reason the detector is 108-scoped.

## Verification

- **Self-test PASS** — synthetic AGC drift + static warm bar (reject: flat) + a rat that leaves a decaying,
  MOTIONLESS ghost (accept) + a rat the detector LOSES that stays and JITTERS (reject via the motion gate):
  `verdicts={'ghost':'ghost','bar':'no_ghost','linger':'rat_present'}`, motion `{ghost 0.01, linger 0.65}`.
- **Real run** (108, 2026-07-01 21:00): 19 events → **3 confirmed traces** (was 5 before the gates). Review
  flagged that some "traces" were the rat still present; the gates correctly downgraded 2 to `rat_present`
  — (731,113) rat re-detected at +1 frame (motion was low 0.03, so the RE-DETECTION gate caught it, not
  motion), (947,187) rat back at +3. Survivors (437,50)/(403,42) are rat-free + thermally static (motion
  0.02–0.05); (666,425) kept but weak (τ=453, rat returned only at +56). Honest yield is low and every trace
  stays candidate-only. `traces.csv` + `trace_heatmap.png` render sensibly.

## Not done / deferred

Full-frame-scan variant (long frozen-holdout rolling-median baseline + `_local_z`, to catch ghosts the rat
detector missed); `output_paths`/`measurement_context`/cohort promotion to a canonical `thermal_traces`
direction; a urine/deposit-specific micro-probe near the eyewitness "behind the shelter"; more nights/hours to
quantify yield; by-eye heatmap cross-ref vs the WISER dwell hierarchy; ambient-temp (AWN) annotation; a second
109 hour to confirm the NO-GO. Not radiometric temperature, not identity, not a behavioral/latrine claim.
