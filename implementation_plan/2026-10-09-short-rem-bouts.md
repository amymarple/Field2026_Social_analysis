# What are the short NREM bouts that end in REM? (cohort 2026c) — plan, before computing

2026-10-09. The top next step of the research-logic map (`n.rip_short_bouts`, round r7). The user's go: "可以试试" (let's
try it).

## Why

Claim #55: 40 % of REM entries come from NREM bouts ≤ 60 s.
- 42 % of those bouts come directly after REM.
- They are ripple-poor: about 22 / min, against about 50 / min in short bouts ending in WAKE.
- They carry the ripple counter's small held-out gain.

The question is what these bouts are:
- **(a) REM interruptions or intermediate sleep that the scorer labels NREM.** This is the classic transition state:
  cortical spindles with hippocampal theta.
- **(b) Genuine short NREM that happens to be ripple-poor.**

The scorer and the ripple detector read the same LFP, so the claim audit could not separate the two. This step
describes the bouts with measures that do not use the scorer's labels. The human blind reading (Part B) is the decisive
measure.

## Data

- Scorings: FINAL 1-s states (primary) and pass2med (check).
- Records, steps and coverage exactly as in `ephys/rem_ripple_model.py`:
  - SWR tier validated / good;
  - before `use_until`;
  - outside the settle windows;
  - before 09-11 19:40.
- LFP: storage `analysis/lfp/` (1250 Hz, read-only).
- Fast LFP-EMG: storage `analysis/emg_from_lfp/` (50 Hz; `corr` = cross-channel 300–450 Hz correlation, the pipeline's
  EMG proxy).
- Channels per animal × probe block from `ephys/configs/swr_channels_2026c.yaml`:
  - cortex = `noise_col` (the top, ripple-free cortical site);
  - CA1 radiatum = `sharpwave_col`;
  - CA1 pyramidal = `ripple_col`.

## Bout sets (from the scoring modelled)

- **R60:** NREM bouts ≤ 60 s followed directly by REM, split by the state before them (REM / WAKE / unknown).
- **W60:** NREM bouts ≤ 60 s followed directly by WAKE, split the same way.
- **References**, per animal × probe block, up to 60 each:
  - **N_ref:** the middle 30 s of NREM bouts ≥ 5 min (≥ 120 s from both ends);
  - **R_ref:** the middle of REM bouts ≥ 40 s (the first and last 10 s dropped);
  - **T_ref:** the last 30 s of NREM bouts ≥ 5 min that end in REM (the pre-REM transition of long bouts).

## Features per 1-s step (2-s Hann windows, 1-s step; no state label used)

- `theta` = log power 6–10 Hz on the radiatum site; `td` = log(P 6–10 / P 1–4 Hz) on the same site.
- `delta_ctx` = log power 1–4 Hz on the cortical site; `sigma_ctx` = log power 10–16 Hz (spindle band) on the same site.
- `rip` = ripple events per s: every detected SWR event (flags and state labels ignored).
- `emg` = mean fast LFP-EMG `corr` over the second.
- **Normalisation:** each feature is z-scored per animal × block with the pooled N_ref + R_ref epochs.

## Automated reading (Part A, description)

- **Per animal × block:** a linear discriminant (LDA, equal priors) NREM vs REM, fitted on N_ref vs R_ref epochs.
  - **Primary version:** the four spectral features (theta, td, delta_ctx, sigma_ctx).
  - **Sensitivity:** cortex only (delta_ctx, sigma_ctx), the part furthest from the scorer's own theta channel.
- **Per bout:**
  - `pREM` = the mean posterior P(REM-like) over its seconds;
  - `frac_REM` = the share of seconds with P > 0.5;
  - `inter` = the share of seconds that are "intermediate": sigma_ctx ≥ the N_ref median AND td ≥ the midpoint of the N_ref
    and R_ref medians.
  - Also its ripple and EMG rates.
- **Pre-registered reading.** Per animal, the median over its R60-after-REM bouts. "≥ 5/6" means animals with such
  bouts; if fewer than 6 animals have them, n − 1 of n.
  - **REM-like:** median pREM > 0.5 in ≥ 5/6 animals → the scorer cut them out of REM episodes (supports a).
  - **Genuine NREM:** median pREM < 0.5 in ≥ 5/6 animals, with delta_ctx and sigma_ctx at N_ref levels (within ±0.5 SD of
    the N_ref median) → genuine NREM, ripple-poor (supports b).
  - **Intermediate:** median `inter` ≥ 0.3 in ≥ 5/6 animals, or pREM between 0.3 and 0.7 → intermediate sleep (a
    transition state; supports a, as a third state rather than REM).
  - **Otherwise:** mixed, and the human reading decides.
- **Comparisons, all description:**
  - R60 vs W60 (do the bouts that end in REM differ from those that end in WAKE?);
  - R60 vs T_ref (are they like the last 30 s of a long bout before REM?).
- **The automated part is not independent of the scorer** (same LFP, a related theta measure). It is read only together
  with Part B.

## Human blind reading (Part B, decisive)

- **A page for the user,** one panel per item, shuffled, with IDs that do not reveal the set:
  - 40 R60 bouts (stratified: 25 after REM, 15 after WAKE), 40 W60, 15 N_ref, 15 R_ref;
  - balanced over animals where possible.
- **Each panel:**
  - the 2 minutes around the segment: CA1 radiatum and cortical spectrograms (0–20 Hz), the td and sigma traces, LFP-EMG;
  - the segment marked, but no scorer labels anywhere, before or after;
  - a 10-s raw LFP trace (cortex, radiatum, pyramidal) centred on the segment.
- **Choices:** NREM / REM / intermediate (spindles + theta) / wake / cannot tell.
- **Export:** JSON + CSV → `ephys/configs/short_bout_review_2026c/`.
- **Reading after the user's answers:**
  - agreement with the scorer (κ) on the references;
  - the share of R60 bouts read as REM / intermediate vs NREM;
  - the agreement with Part A.

## Rules

- No state label enters the features.
- The agent does not judge the panels.
- Nothing is written into the raw or storage folders.
- Bulk output → `$OUT_ROOT/2026c/short_rem_bouts_<ts>/`; report → `results/2026c/ephys_spikes/reports/ephys_spikes_short_rem_bouts_2026c.md`.

## Output

- `ephys/short_rem_bouts.py`:
  - `features`: Part A;
  - `review`: the page;
  - `merge`: after the user's answers;
  - `--selftest`.
- Report and change log `change_log/2026-10-09-short-rem-bouts.md`.
