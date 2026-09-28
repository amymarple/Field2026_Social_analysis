# Thermal traces — detect persistent warm anomalies rats leave behind (108)

**Date:** 2026-07-13
**Status:** Phase 0 (feasibility) = DONE → **GO on 108, NO-GO on 109**. Phase 1 detector built, 108-scoped;
candidate-only, weakly validated. Not yet a canonical `results/` direction.
**New files:** `thermal/trace_feasibility.py`, `thermal/detect_traces.py` (extend the `thermal/` subsystem;
see [[thermal-cameras-108-109]]).
**Direction (if promoted):** `thermal_traces`. Until then outputs go to a caller `--out`, not `results/`.

## Motivation

The user's goal is not rat position/count but the **traces rats leave behind** in thermal — a resting-spot
"heat ghost" (warmed ground) or a urine/scent deposit: a localized WARM anomaly at a fixed spot that appears,
PERSISTS after the rat leaves, and DECAYS. This suits thermal's strength (persistence over time), unlike
rat-counting which hit a ~0.5-recall ceiling ([change_log/2026-07-13-thermal-warm-blob-detector.md]).
User choices: any persistent WARM anomaly (cast wide); deliverables = event list + nightly hotspot heatmap.

## Phase 0 — feasibility (gate), DONE

`thermal/trace_feasibility.py`: auto-anchored probe. Derives "rat rested then left" events from the rat
detector's blobs (no georeference / hand-picked pixels needed), then at each fixed spot measures
**annulus-referenced contrast over time** (median warm disk − surrounding annulus, on the AGC-undone
`robust_norm` frame, excluding OSD + the roaming red spot-meter per frame — the annulus cancels AGC
whole-frame flicker) and fits post-departure `c(t)=c0·exp(−(t−t0)/tau)+b`.

**Result (2026-07-01, 21:00):**
- **108 = GO** — 5/19 rest-departures left a clearly decaying warm ghost. Textbook case at pixel (731,113):
  rat leaves → contrast drops 130→55 → **decays 55→15 over ~2 min** (tau≈84 s); crops show a faint warm
  patch where the rat rested. Cleaner/faster cases too (tau 30–60 s, R²≥0.7).
- **109 = NO-GO** — 0/9; the best candidate returns to baseline within ~8 s of departure. Measurement is
  identical and clean, so the absence is real. **Traces are viewpoint/substrate-dependent:** 108 images
  warmable bare ground/berms that hold body heat; 109 images vegetation/wires that do not.

Calibration handed to Phase 1: baseline window ~176 s, median persistence ~36 s, median tau ~59 s.

## Phase 1 — detector (108-scoped), BUILT

`thermal/detect_traces.py`, **rat-anchored** (the Phase-0-validated, high-precision path; reuses
`trace_feasibility` primitives `derive_events`/`_ring_indices`/`contrast_at`/`classify`/`_fit_decay` and
`detect_blobs` `robust_norm`/masks/`iter_frames`/`WarmBlobDetector`):
1. Rat detector (or a prior `detections.csv`) → **rest-then-depart events** (rat dwelled ≥ dwell_min then the
   spot went rat-free ≥ gap — the moment a ghost is planted).
2. Per event, measure annulus contrast(t); a ghost must (i) step UP on arrival, (ii) stay above the
   pre-baseline band AFTER departure for ≥ min_persist, (iii) fit an exponential DECAY (finite tau, R²≥0.3).
   **Flat post-departure (tau→∞) = a constant structure the rat sat by → REJECTED** (the pole/berm/rock
   discriminator, done by decay physics). A moving rat (translates) never produces a stationary event.
2b. **Still-present-rat gates** (the rat detector's ~0.5 recall makes "departure" unreliable, so post-
   departure warmth can just be the rat): (1) **re-detection** — truncate persistence at the first rat
   re-detection at the site; clean persistence < min_persist → `rat_present`; (2) **post-departure MOTION**
   — a cooling ghost is thermally static, a lingering rat twitches; `post_motion_frac > 0.15 → rat_present`.
   The two catch different cases (a still-but-re-detected rat vs an undetected-but-moving rat).
3. Outputs: **`traces.csv`** (per event: `arrival_frame, depart_frame, persist_s, cx, cy, peak_contrast,
   onset_amp, tau_s, decay_r2, verdict, osd_clock_note`; coords are THERMAL PIXELS), a nightly
   **`trace_heatmap.png`** (confirmed-ghost splats weighted by persistence, over a representative frame),
   `summary.json` (params + caveats + git), and per-trace contrast plots + crops.

## Outputs are CANDIDATE-only — non-claims

RELATIVE brightness NOT temperature (AGC, not radiometric; tau is a relative relaxation time); traces are
candidate resting heat-ghosts, NOT confirmed marks/deposits and NOT identity; times = frame idx + filename
wallclock (OSD ~1 h behind); NOT georeferenced (pixel coords; WISER cross-ref by-eye only); **108-scoped**;
biased to larger/longer resting ghosts → small fast urine deposits systematically MISSED; rat-anchored on a
~0.5-recall detector so some ghosts missed; unsupervised/unvalidated.

## Verification

- `python thermal/detect_traces.py --selftest` → PASS (decaying MOTIONLESS ghost ACCEPTED; static warm bar +
  a jittering lingering-rat REJECTED via the motion gate).
- 108 2026-07-01 21:00 run → **3 confirmed traces of 19 events** (was 5 before the still-present-rat gates;
  2 were the rat still present — re-detected at +1 and +3 frames). Heatmap + traces.csv render sensibly.

## Deferred / not done

Full-frame scan variant (approach B: long frozen-holdout rolling-median baseline + `_local_z`, catches ghosts
the rat detector missed); `output_paths`/`measurement_context`/`cohort` promotion to a canonical
`thermal_traces` direction; a urine/deposit-specific micro-probe near the eyewitness "behind the shelter"
(`FIELD_OBSERVATIONS.md:153`); more nights/hours to quantify ghost yield; by-eye heatmap cross-ref vs WISER
dwell hierarchy (`results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_site_hierarchy_2026a.md`); ambient-temp
(AWN) annotation; a second 109 hour to confirm the NO-GO is permanent.

## Non-goals

No radiometric temperature (the MP4s can't support it); no identity; no georeference; no behavioral/latrine
claim; no change to `detect_blobs.py`, `cv/`, `wiser/`.
