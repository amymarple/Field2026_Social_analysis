# 2026-10-10 — Awake ripples across the paddock at night: validity, EMG removal, maps (cohort 2026c)

Plan: [implementation_plan/2026-10-10-awake-ripple-map.md](../implementation_plan/2026-10-10-awake-ripple-map.md),
Amendments 1–6, all written before the step they govern. Report:
[results/2026c/ephys_spikes/reports/ephys_spikes_awake_ripple_map_2026c.md](../results/2026c/ephys_spikes/reports/ephys_spikes_awake_ripple_map_2026c.md).

## What was done

- **Phase 0 (counts).** Per-second night tables per animal: state, head IMU, V3 position, house membership, probe
  block, handling and BLE masks, detectability, events.
  - The pre-registered qSWR left almost no field time: 93 % of night wake is in theta.
  - So the primary definition became the production's kept rule in non-locomotor detectable wake (aSWR, Amendment 2).
- **Phase 1 (validity), four readings.**
  - **Readers:** reader HC (the user) on four pages; the user's mentor scoring the raw page.
  - **Raw page:** field 0.80, house 0.95 precision. "Unsure" was EMG; "not" was theta.
  - **Denoising, two methods:**
    - single-site regression: looked the same to the user;
    - **EMG removal by ICA** (`ephys/emg_ica.py`), a port of Weiwei Chen's Sirota-lab EMG_removing toolbox (thesis
      ch. 5, `Ref/Chen_Weiwei.pdf`). Two fixes after the Codex review:
      - numOfIC = n;
      - acceptance on ≥ 2 of 3 seeds.
    - The port matches the MATLAB original in R2021b: removed loading |cos| 1.000, removed signal r 0.99–1.00.
    - Forced removal cut 37 % of the NREM ripple band, so it is never shown.
    - 111 / 140 items cleaned; SF09 cannot be (unverified order).
  - **Cleaned page:** unsure 13 → 0. But random moments were called "ripple" 18 / 25 times, without a spike burst.
  - **Strict re-read** (Amendment 5): 141 panels, new ids, 30 fresh controls, ± 50 ms rule.
    - NREM s 0.88, random α 0.18 → the reading discriminates.
    - π̂ field 0.94 [0.69, 1.00], house 1.00 [0.83, 1.00] → **gate PASS**.
    - Strict calls agree with raw MUA: field "ripple" 3.2× burst vs "unsure" 0.4×.
- **Phase 2 (maps)**, Amendment 6, fixed before any map: `ephys/awake_ripple_phase2.py` (`awake_ripple_map.py phase2`,
  `--selftest`).
  - 48-in field bins, houses as their own places, distance rings.
  - Bout-swap null (1000).
  - T1 spatial information, T2 / T2b stability, T3 house / field Mantel–Haenszel rate ratio, 1-D ring O / E and slope,
    Holm, a bout-level Poisson GLM, five sensitivities.
  - Every animal carries its note: SF09 not validated, SF08 4 / 8, SF11 houses only, SF07 descriptive.

## Results (Phase 2)

- **In inference:** SF08, SF09, SF10. The others are descriptive.
- **Place dependence of the field map: weak.**
  - SF10: spatial information 0.038 vs null 0.028 bits / event, Holm p 0.018, robust in 5 / 5 sensitivities.
  - SF09: 0.045 vs 0.036, Holm p 0.015, 4 / 5; it fails without the rain nights.
  - SF08: none.
  - Not stable across nights or trial halves where it can be estimated (SF09 r −0.47 / −0.52). Elsewhere it cannot be
    estimated: too little field time per night.
- **House vs field.** Awake ripples per non-locomotor minute are not higher at home.
  - Lower in the houses in SF08 (rate ratio 0.80, null 0.85, Holm p 0.006, 5 / 5) and SF09 (0.85, null 0.88, p 0.006,
    4 / 5).
  - Not different in SF10 (0.94, p 0.65).
  - The bout GLM gives house IRR 0.82–0.91 (SF08, SF09, SF10, SF12).
  - Most of the raw difference follows bout duration and time of night (the null medians 0.85–0.93).
  - Food was in the houses, so "house" = home + food site + huddle.
- **No distance gradient in the field** (slopes −0.06 to 0.04, Holm p ≥ 0.74). SF12, descriptive: +0.35 on 6 bins.

## Definitions (headline)

- **aSWR:** a kept production SWR in a non-locomotor detectable wake second: WAKE, head IMU ok and still / active,
  outside handling, SWR-covered, theta-detectable (EMG-detectable on ripple-only blocks), with a position.
- **Spatial information:** $I = \sum_i p_i \frac{\lambda_i}{\bar\lambda}\log_2\frac{\lambda_i}{\bar\lambda}$, over field
  bins with ≥ 60 s. In bits / event; 0 = uniform.
- **Rate ratio:** $RR_{MH} = \frac{\sum_b c_{h,b} o_{f,b} / o_b}{\sum_b c_{f,b} o_{h,b} / o_b}$, where $c$ = events,
  $o$ = seconds, $h$ / $f$ = house / field, $b$ = probe block.
- **Bout-swap null:** within night × block × duration class (ratio 1.25) × clock hour, the bouts' event sequences are
  permuted, with offsets rescaled. It keeps place, duration, time and the event-count distribution, and breaks the
  event–place link.
- **Strict-reading share:** $\hat\pi = (p - \alpha)/(s - \alpha)$, where $s$ = the call rate on NREM SWRs and $\alpha$ =
  the call rate on random quiet moments.

## Files

- New: `ephys/emg_ica.py`, `ephys/awake_ripple_phase2.py`.
- Changed: `ephys/awake_ripple_map.py` — `emgica`, `rerender --denoise [regress|ica] --key --mark-ms`, `phase2`.
- Reader exports: `ephys/configs/awake_ripple_review_2026c/` (HC raw, cleaned, strict).
- Reports `results/2026c/ephys_spikes/reports/ephys_spikes_awake_ripple_map_{phase0_,}2026c.md` + `_stats`, `_rings`,
  `_glm`, `_sensitivity` CSVs; figures `…awake_ripple_map_{SFxx,summary,rings}_2026c.png`.
- Bulk: `D:/Field2026_analysis_out/2026c/awake_ripple_map_20261010_1452/` — `emg_ica_v2/`, `strict/`, `matlab_check/`
  (incl. the Codex reply), `phase2/`.

## Open

- The mentor's raw-page reading (κ cross-check).
- The theta-quiet aSWR sensitivity (± 2 s theta / delta series per session).
- Phase 3 (relations between animals).
- SF09 needs a verified within-shank order before it can be cleaned.
