# Delta-wave detection: the lab detector ported and validated; the first cohort-3 channel scan (SF07, SF11)

**Date:** 2026-10-08. **Plan:** [implementation_plan/2026-10-08-delta-wave-detection.md](../implementation_plan/2026-10-08-delta-wave-detection.md).
**Status:** port validated. The cohort-3 channel choice waits for the user; nothing has run on the server.

## What was built

- **`ephys/delta_detect.py`** — an exact Python port of `neurocode/lfp/FindDeltaWaves.m` + `detect_delta_waves.m`.
  `--selftest` runs 12 checks.
  - The building blocks follow the MATLAB code: FilterLFP / Filter (cheby2 + filtfilt on a 1250-Hz grid interpolated
    across gaps), ZeroCrossings, CleanLFP, FindInterval / ConsolidateIntervals / Restrict, the EMG immobility gate.
  - **Wrapper versions:**
    - `2024-06` (a60fc16 … f560cfe): events intersecting `ignore_intervals` are dropped after detection.
    - `2025-09` (61e7b5b, current): those samples are cut out before detection.
  - Also covered: the user's older script `R_Project/PPP/codebook/pre_Ephys_pipline.m` (whole session, CleanLFP
    [6 Inf], peak−trough > 4.5), and the 2017 FindDeltaWaves for the record.
  - `replay` re-runs a lab session from its own files and compares event for event.
  - `scan` is the cohort-3 session scan. For every channel it runs NREM detection (final `imu_remclean` states, no EMG
    gate) and reports:
    - the lab channel rule (NREM 1–6 Hz power share);
    - a DOWN-state check (250–450 Hz LFP power at the delta peak, common-average referenced; also as recorded);
    - the delta-triggered LFP of all sites;
    - a per-shank proposal and two figures.
- **`ephys/delta_mua_check.py`** — a raw multi-unit check, with no sorting.
  - Method: threshold crossings on the raw 20-kHz `amplifier.dat` (common median reference, 600–6000 Hz, 4.5 MAD,
    1 ms refractory), firing rate at the delta peak against the −1…−0.6 s baseline.
  - It reproduces the scratch prototype: same 1032 events, rates within 2 spikes (chunk edges).

- **`ephys/delta_review_gui.py`** — a review page for the user ("做一个 GUI 我看看，至少波形像不像").
  - Each set shows 30 events drawn from the four amplitude quartiles.
  - Per event: the reference shank's LFP ±1.5 s (start / peak / end marked, optional 0–30 Hz display filter), the raw
    MUA raster of the same sites (fixed −4.5 MAD thresholds from 60 s of NREM), and the summed MUA of all live sites.
  - An overview tab shows the delta-triggered average LFP and the MUA PETH.
  - Keys 1 / 2 / 3, autosave in the browser, CSV + JSON export.
  - First page: `D:/Field2026_analysis_out/2026c/delta_review_20261008_1946/index.html` (SF11 09-02 shank 3 col 11;
    SF07 09-02 shank 1 col 55). It runs headless without errors.

## Validation (lab sessions, local read-only copies in `D:/Field2026_analysis_out/swr_reference/`)

| Session | Detector | Threshold | Lab events | Port | Recall ±10 ms | Precision ±10 ms | Exact sample | max Δz |
|---|---|---|---|---|---|---|---|---|
| HP17 d36 | detect_delta_waves (opto `ignore_intervals`) | 3 | 4503 | 4503 | 1.000 | 1.000 | 0.997 | 0.003 |
| HP18 d49 | detect_delta_waves | 4 (`detectionparms`) | 3341 | 3341 | 1.000 | 1.000 | 0.992 | 0.003 |
| HP17 d2 | detect_delta_waves + verify | 3.003 | 2313 | 2315 | 1.000 | 0.999 | 0.995 | 0.002 |
| HP18 d17 | detect_delta_waves + verify | 4.63 | 2250 | 2251 | 1.000 | 1.000 | 0.994 | 0.006 |
| HP18 d52 | detect_delta_waves + verify | 4.52 | 2891 | 2892 | 1.000 | 1.000 | 0.997 | 0.003 |
| RM10 d5 | detect_delta_waves + verify | 3.0007 | 4703 | 4704 | 1.000 | 1.000 | 0.995 | 0.002 |
| PPP20 d4 | detect_delta_waves | 3 | 2238 | 2239 | 1.000 | 1.000 | 0.992 | 0.008 |
| PPP4 d11 | the user's script | 4.5 | 3555 | 3558 | 1.000 | 0.999 | — | — |
| PPP7 d7 | the user's script | 4.5 | 4563 | 4565 | 1.000 | 1.000 | — | — |

What the replays established:
- HP18 d49 ran with threshold 4. Its `detectorinfo.threshold` is empty because verify_firing failed.
- HP17 d36 shows the `ignore_intervals` semantics. Without them the port has 231 extras, all overlapping an opto
  window. Cutting the samples instead (the current wrapper) does not reproduce the file.
- The user's script used neurocode's CleanLFP padding (±0.5 s, from 2022-10-13), not the codebook copy's ±2 s. Only
  ±0.5 s reproduces the stored `badIntervals` (364 / 519.8 s and 167 / 201.6 s) and the events.
- The 2017 FindDeltaWaves (no internal filter) finds nothing on unfiltered LFP. So the user's MATLAB path had the
  ≥ 2022-10 version, which behaves like the current one.
- Detector behaviour to remember: the rule is "a peak, then a deep trough". An inverted wave with a positive side lobe
  also passes, so polarity is a property of the channel, not something the detector enforces.

## Cohort 3, first scan (local LFPs = storage by MD5; final sleep read from storage)

Outputs are in `D:/Field2026_analysis_out/2026c/delta_scan_20261008/`: per session `*_delta_scan.{csv,npz,json,png}`,
`*_delta_profile.png`, the MUA npz files and `mua_delta_SF11_vs_SF07_20260902.png`. The first run without the
common-average reference is in `v1_noCAR/`.

**Delta waves are detected on every site of both animals.**
- Rate: 27–35 per NREM minute (lab rat HP17 d36: 27/min). Median duration about 320 ms.
- They are largely the same events across the probe: on SF11 09-06 the top sites share 84–96 %, and the tips share
  0.6–0.75 with the tops.

**SF11** (09-02, 09-05, 09-06) — the DOWN state is confirmed at the top sites.
- LFP 250–450 Hz drops −1.0 to −1.7 z at the peak, consistently across days on the shank-3 top sites:
  - col 11: −1.48 / −1.37 / −1.47;
  - col 8: −1.25 / −1.60 / −1.67.
- Shank 4's top sites are steady at about −1. Shank 2 loses the drop on 09-06.
- Raw MUA on 09-02: the top sites fall to 10–35 % of baseline at the peak. Below about site 6–10 the ratio exceeds 1
  (more firing around the delta peak), which fits cortex above hippocampus.

**SF07** (09-02, 09-08, 09-09) — no DOWN-state check is possible.
- The 250–450 Hz drop at the top sites is about −0.1 z, with or without the common-average reference.
- SF07's HF band is strongly common mode: signal r 0.39–0.47 between sites; the envelope r falls from 0.24–0.28 to
  0.03–0.06 after CAR.
- Raw MUA on 09-02: 52 of 64 sites at noise level (0.1–0.7 crossings/s). Only shank 1 sites 7–16 fire (1–18 Hz), with a
  mild drop at the peak (ratio 0.5–1.0).
- So the SF07 top sites carry no units, and their delta waves cannot be checked locally.
- SF07 `9_20260901_192912.215` has 10 s of NREM in `imu_remclean` and was skipped.

## 2026-10-09: the user's review and a per-event DOWN-state check

**The user's verdicts** (`ephys/configs/delta_review_2026c/`; the user: "老实说我不是很会看，只能做参考" — reference only).

| Set | Looks like it | Does not | Unsure |
|---|---|---|---|
| SF11 09-02 | 21 | 0 | 9 |
| SF07 09-02 | 8 | 13 | 9 |

- Against raw MUA at the peak, the events the user accepted are silent: firing ratio 0.22 (SF11) and 0.23 (SF07, shank-1
  spiking sites).
- The SF07 events the user rejected have ratio 0.60 and are shorter (193 vs 267 ms).
- Amplitude does not separate them (4.29 vs 4.26 z). So the lab's verify_firing, which raises the amplitude threshold,
  would not help on SF07.
- The first page's CSV export did not quote the set name (which contains a comma). It is fixed; the JSON was always
  correct.

**New code.**
- `ephys/mua_nrem.py`: NREM threshold crossings of all 64 channels per session, a reusable intermediate in
  `D:/Field2026_analysis_out/2026c/mua_nrem/<SFxx>/` (2–11 min per session).
- `delta_detect.py verify`:
  - per event, the summed spikes within ±50 ms of the peak vs −1…−0.4 s;
  - over the live sites with ≥ 1 Hz whose firing does not rise at the delta peaks (this keeps out hippocampal sites,
    which fire more);
  - verified = ratio ≤ 0.5, set before looking at the result;
  - Poisson p reported; untestable if fewer than 10 pre-window spikes;
  - self-test: 14 checks.

**Fraction of events verified at ratio ≤ 0.5:**

| Animal | 09-02 | 09-05 | 09-06 | 09-08 | 09-09 |
|---|---|---|---|---|---|
| SF11 | 70 % | 89 % | 93 % | — | — |
| SF07 | 35 % | — | — | 47 % | 62 % |

**Agreement with the user's labels.**
- SF11: 17 of the 21 accepted events are kept.
- SF07: 5 / 8 accepted and 6 / 13 rejected are kept (AUC 0.77).
- The per-event test is noisy by construction. About 6 spikes are expected in the window: with no true change, about
  15 % of events still reach ≤ 0.5.

**Kept vs rejected** (LFP average, independent of the selection; `delta_verify_kept_vs_rejected.png`).
- Kept events are longer and larger in every session.
- Examples: SF11 09-06, 307 vs 228 ms and 4.7 vs 3.8 z; SF07 09-08, 295 vs 261 ms and 4.7 vs 4.4 z.

## Open (for the user)

- SF11: choose the delta channel. Shank-3 top sites (col 11 or 8) are consistent across all three blocks; shank 4
  (20/27/18/22) is the alternative.
- SF07: detect from a top site without verification, as the user's own older script did? Or another check?
- Then: the remaining local sessions, the server run (`run_then_store.sh`, new part `delta`), and the other animals.
