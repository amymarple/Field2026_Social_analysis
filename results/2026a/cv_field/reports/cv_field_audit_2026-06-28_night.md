# cv_field milestone audit — 2026a (metadata)

**Verdict:** metadata-only: selection coverage + provenance recorded; no error metric invented

- channels: CH03, CH04  ·  total frames selected: 40
- day/night split (all rounds): {'night': 40}

## Per-round selection

- **round 0** — 40 frames, methods {'medoid': 3, 'fps': 37}, distinct clusters 3, day/night {'night': 40}

## Per-camera calibration RMSE (cm)

- CH03: 19.694
- CH04: 11.278

## Whole-field regime caveats

- scope is night-IR only (21:00–04:20); CH01/CH02 daytime color is corrupt and excluded.
- counts are a LOWER BOUND (visible_count): wall-edge blind band + huddle occlude animals.
- NO cross-camera identity (animal_id=<camera>:<track_id>) — no whole-field per-animal / cross-camera-headcount claims.
- day/night split is approximate (recording-start wallclock hour); expect ~all night in-scope.
- clusters are a labeling heuristic, not evidence of behavioral discreteness.
