# cv_field whole-field measurement checklist (CH01–CH04)

Carry these regimes on **every** whole-field number, before any behavioral claim. This is the whole-field
analogue of the shelter `regime-aware-cv-measurement` skill — but the through-glass fog/view-quality/glass
machinery does **not** apply here (CH01–CH04 are not shelter-glass cameras). `field_audit.py` checks the
computable items; the rest are interpretation rules.

## Scope (2026a): night-IR only

cv_field analyzes the **night-vision window 21:00 → 04:20 only** — every frame is **night-IR monochrome**, so
there is no day/night split to worry about and a night-only detector is correct (we never infer on day
frames). A "night" crosses midnight (hours 21–23 of date *D* + 00:00–04:20 of date *D+1*, two date folders).
**CH01/CH02 daytime COLOR is excluded** — a bitrate-overflow bug partially corrupts it; their night-IR stream
is fine. So the pool must be drawn from the night window; a stray daytime frame (esp. CH01/CH02 color) is
out-of-scope and possibly corrupt.

## Regimes that confound the numbers

- **Within-night IR variation.** IR illumination falloff, moths/insects near the emitters, and moon/ambient
  light still vary the look across a night — the round-0 farthest-point coverage is meant to span that range.
- **Weather.** Rain, wet ground, wind-moved vegetation, and glare create motion/appearance that inflates or
  splits boxes. Cross-reference `data_manifests/field_conditions.yaml` windows before trusting a count change.
- **Occlusion → counts are a LOWER BOUND.** The wall-edge blind band and rat-on-rat huddles hide animals from
  the detector. Report `visible_count`, never a definitive headcount; defer huddles (the `label_frames.py`
  `g`-huddle marker) rather than guessing a pile size.
- **NO cross-camera identity (the big one).** `merge_cameras.py` sets `animal_id = <camera>:<track_id>`, so a
  rat seen in the CH01/CH02 panorama overlap is counted twice and a track that crosses cameras gets two ids.
  **Forbidden until cross-camera dedup exists:** whole-field per-animal trajectories, cross-camera headcounts,
  "rat X went from A to B across cameras."

## Provenance / calibration to verify each run

- **Per-camera calibration RMSE** (`cv/configs/CH0x_calib.json` `reproj_rmse_cm`) — a large RMSE means the
  field-cm coordinates for that camera are unreliable; flag it rather than pooling silently.
- **Field-cm bounds** — points landing outside the surveyed field (609.6 × 1219.2 cm, origin pole A0) signal a
  calibration or ground-point error.
- **measurement_context sidecar** — every run carries `mc_run_id`, the detector fingerprint, and the
  **embedding fingerprint** + active-learning round/params, so numbers are auditable and stratifiable.

## Coordinate frame (unlike WISER)

The CV cm frame is the **surveyed physical frame** (origin pole A0) — metric and verified — so the "unverified
WISER inch frame" caveat does **not** apply to cv_field's own outputs. But **WISER × CV cross-modal alignment
stays unverified** until the pole-survey georeference passes QC.

## The active-learning claim itself must be falsified

"Few labels → strong detector" is only supported once a round's honest session-split held-out mAP **beats an
equal-budget random-selection control** (`select_frames.py --method random`). Until then, report the selection
as a labeling strategy, not a demonstrated win. Clusters are a labeling heuristic only — never reported as
behavioral types (`field_cluster.pca_competitor_report` is the guard).
