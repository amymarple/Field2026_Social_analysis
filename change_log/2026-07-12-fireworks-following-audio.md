# 2026-07-12 — July-4 fireworks → following: time-resolved + audio cross-modal test

**Status:** ⚠️ candidate. Tests the FIELD OBSERVATION (FIELD_OBSERVATIONS Day 7: "during the July 4th
fireworks (~21:00), increased group-level movement, more following") against the Phase-B2 following-episode
data, the AWN weather, and the CH01/CH02 camera-mic audio. Reuses existing following detection (NO rebuild).
Full definitions + figure in `outputs/following_incidents_2026-06-28_to_2026-07-08/FIREWORKS_FOLLOWING_REPORT.md`.

## The question and why the naive test fails

A whole-night average makes the fireworks night **n = 1** and only weakly elevated. Two refinements
(user-directed) fix that: (1) the fireworks are TIME-LOCALIZED, so bin the night and compare 07-04's
fireworks window to the same clock on the other nights (real n = 10 controls); (2) the camera mics recorded
the actual fireworks, so align acoustically.

## What was built

- `scripts/analyze_following_weather.py` — per-night following vs AWN rain + env-map flags (weather cross-check).
- `scripts/analyze_fireworks_timecourse.py` — 10-min between-night bin test around the fireworks time.
- `scripts/analyze_fireworks_audio_align.py` — CH01/CH02 audio level ↔ following, 5-min grid + cross-correlation.
- `scripts/make_fireworks_watchlist.py` — focused video watch-list for the burst windows.
- `scripts/plot_fireworks_psth.py` — the stimulus-aligned figure (`plots/fireworks_following_audio_psth.png`).
- Extracted `audio/outputs/audio_features_CH0{1,2}_2026-07-04.csv` (20:00–24:00, the `audio` env).

## Results

- **Weather cross-check first (de-confounds the night).** AWN in-window rain disagrees with the env-map's
  coarse `wet` flag: **07-04 (fireworks) had 0.00 mm rain in-window — it was DRY.** So "fireworks vs a
  normal dry night" is a valid comparison. Genuinely rainy nights (06-30 0.30 mm, 07-06 2.39 mm) show
  *less* following (wet 0.0094 < dry 0.0149) — **rain does NOT increase following** (and is confounded by
  rain→UWB dropout).
- **Time-resolved (real n).** 07-04 following bursts at **21:30 (z = +2.4)** and **22:20 (z = +5.2)** vs the
  same clock on the other 10 nights, separated by near-zero bins; the whole 21:00–22:00 window is only
  z = +0.5 (the bursts are washed out by averaging). The 22:20 burst survives multiple-comparison correction.
- **Audio cross-modal (two mics).** CH01 and CH02 independently place the fireworks at 21:25–22:55 (peak
  ~0 dBFS-rel at 21:35–21:45; quiet before 21:00 / after 23:00). Following vs audio-peak correlate
  **r ≈ 0.37 (CH01) / 0.34 (CH02) at lag 0**; CH02 best-lag −5 min (near zero). The following bursts fall on
  the loudest audio bins.
- **Mechanism NOT resolved.** Burst episodes are tight (4–18 in, cos 0.93–1.00, 1–19 s lag) — consistent
  with following OR startle co-flight. A 96-episode video watch-list (`fireworks_0704_video_watchlist.csv`)
  is staged; highest-confidence clips 21:35–21:38 (CH03/CH04) and 22:18 (CH03).

## Verdict

**Candidate, cross-modally time-locked.** The 07-04 following elevation is REAL, time-localized to the
acoustically-confirmed fireworks window, and not a rain artifact. It is NOT established as *social
following*: WISER cannot distinguish it from synchronized startle co-flight, and it is one night. The
progression whole-night (n=1, weak) → 10-min bins (two bursts) → audio (coincidence) → CH02 (confirmation)
is the evidence chain. Only video can resolve the construct.

## Caveats

n = 1 fireworks night; camera↔WISER clock sync UNVERIFIED (cross-corr lag mixes offset + response delay,
though lag-0 r > 0 implies rough alignment); audio is RELATIVE dBFS (not SPL), CH01/CH02 location-specific;
following = herd-level lagged co-movement, "leader" = temporal order, inch frame UNVERIFIED; 07-04 also a
burrow night; the following ramps before the acoustic peak (locked to the window, not to individual volleys).

## Provenance

Following data unchanged (Phase-B2 `strict_following_episodes.csv`). Only descriptive stratification +
cross-modal alignment added. Nothing in `analysis_exchange/published/` touched.
