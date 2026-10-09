# What are the short NREM bouts that end in REM? Part A: REM-like by label-free LFP; Part B (blind reading) built (2026-10-09)

Plan (before computing): [implementation_plan/2026-10-09-short-rem-bouts.md](../implementation_plan/2026-10-09-short-rem-bouts.md).

This is the top next step of the research-logic map (`n.rip_short_bouts`, round r7); the user said "可以试试" (let's try it).

Claim #55 found that 40 % of REM entries come from NREM bouts ≤ 60 s, which are ripple-poor and often come directly after
REM. The question: are they REM interruptions or intermediate sleep that the scorer labels NREM, or genuine short NREM?

## What changed

- **New `ephys/short_rem_bouts.py`**, with commands:
  - `features`: Part A;
  - `review`: Part B page;
  - `report`;
  - `--selftest`, 3 checks: segment sets, epochs inside the segment, band powers.
- **Report:** `results/2026c/ephys_spikes/reports/ephys_spikes_short_rem_bouts_2026c.md`, plus `_summary_2026c.csv`, the figure
  `ephys_spikes_short_rem_bouts_2026c.png` and the pointer `run_manifest_short_rem_bouts_2026c.json`.
- **Run:** `$OUT_ROOT/2026c/short_rem_bouts_20261009_1534/` (`segments`, `epochs`, `lda_fits`, `summary_by_animal`).
- **Blind reading page:** `review/index.html`, 110 panels.
  - The key is `review_key_SEALED.csv`, outside the page folder.
  - Answers go to `ephys/configs/short_bout_review_2026c/`.

**Online version of Part B** (the user asked another person to read, 2026-10-09): a private artifact,
https://claude.ai/artifact/YFG89wkHR29dyzjbSXMbtE.
- It holds the same 110 panels, with no labels and no key.
- Each reader's answers go to `db` document `reads/<their id>`: readable by the owner only, never by other readers.
- Readers need Contributor access (Editor when invited from outside the organisation). Below that, the page keeps answers
  in the reader's browser and offers a file to send back.
- Read the answers back with `ArtifactData list reads`; the key stays in `review_key_SEALED.csv`.

## Definitions (headline)

- **Sets** (records and coverage as in the REM ripple model):
  - R60 / W60 = NREM bouts ≤ 60 s followed by REM / WAKE, split by the state before them;
  - references per animal × block (≤ 60 each): N_ref = mid-NREM of bouts ≥ 5 min; R_ref = REM bouts ≥ 40 s without 10-s
    ends; T_ref = the last 30 s of long NREM bouts before REM.
- **Epochs:** each second whose 2-s window lies inside the segment.
- **Features:** CA1 radiatum θ and θ/δ; cortical δ and σ (10–16 Hz); all detected SWRs; fast LFP-EMG. Each is z-scored on
  the N_ref + R_ref epochs per animal × block.
- **pREM** = the LDA posterior of REM (N_ref vs R_ref, equal priors; reference accuracy 0.95–0.98), averaged over a
  segment.

## Results (Part A, description)

- **Pre-registered reading: REM-like on both scorings (6/6).**
  - FINAL R60-after-REM pREM 0.58–0.90 (animal medians), against R_ref 0.95–0.99, N_ref 0.02–0.03 and T_ref 0.16–0.43.
  - The intermediate criterion is also met (4/6 FINAL, 6/6 pass2med).
- **What makes a short bout REM-like is the state before it:**
  - after REM: REM-like even when it ends in WAKE (0.42–0.83);
  - after WAKE: 0.29–0.73 when it ends in REM, 0.21–0.30 when it ends in WAKE.
- **Ripples:** 0–32 / min in R60 after REM, about REM's 0–7 / min, against 48–89 / min in N_ref.
- SF11 has 3 such bouts; without it the rule passes 5/5.

## Reading

- The short NREM bouts between REM bouts look REM-like by label-free LFP measures, but not fully: they sit between REM
  and NREM.
- This supports reading #55 as REM interruptions or intermediate sleep cut out of REM episodes, rather than genuine
  ripple-poor NREM.
- **Not independent of the scorer** (same LFP, a related theta measure). The human blind reading (Part B) decides; it
  awaits the user.

## Verification

- `python ephys/short_rem_bouts.py --selftest` → PASS.
- The panels show no scorer label.
- The agent did not judge them: only one panel's layout was checked.
