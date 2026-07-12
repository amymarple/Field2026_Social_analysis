# Change log — Bout-segmentation validation: the "~4 s / ~100 in capacity" is a segmentation artifact

**Date:** 2026-07-11
**Status:** ⚠️ candidate (validation). Additive — does NOT overwrite the route-motif / bout-length
outputs. Re-extracts bouts from **positions** (5.97 M cleaned night fixes, 13 nights) with every
segmentation rule parameterized, to falsify the reported bout scale.
**Analysis dir:** `wiser/bout_segmentation_validation/` (README, validation_report,
src/, tables/, plots/, run_manifest.json).

## Motivation

`bout_length_report.md` concluded rats have a **fixed ~4 s locomotor "capacity" / ~8 ft characteristic
bout length**. But the production bout definition (min duration 3 s, any pause breaks a bout, 1 s speed
smoothing, 15 in displacement filter) makes `3 s × 25 in/s ≈ 75 in` — right at the displacement mode.
This run attempts to falsify the biological reading.

## Verdict: **D (segmentation-defined scale)**; true structure **B + C**; **A falsified**

- **A5 — the scale moves ~1:1 with the filter:** duration median = 0.89 + **0.95**·min_bout (R² 0.99);
  displacement median = 21.6 + **25.0**·min_bout (slope = the median speed). The "100 in" is
  min_bout × speed.
- **A3 — left-truncation:** un-truncated median run = **0.54 s**; `median | ≥3 s = 3.76 s` = the
  production "3.8 s". The tight CV (0.26) is manufactured (un-truncated CV 0.67).
- **A4/A10 — hazard near-memoryless:** best fit **lognormal**; Weibull **k = 1.10 ≈ 1**; only hazard
  breakpoint at **1.29 s ≈ the 1 s speed-smoothing window**, not 4 s → no characteristic run duration.
- **A6 — trips:** a 5 s pause tolerance merges **98.9 %** of bouts into multi-leg trips; 30 s merge
  reaches the **full paddock diagonal (524 in)**. Production bouts are trip *legs*.
- **A7 — pauses reorient:** ~**64°** heading change across a pause vs **16°** within a run.
- **A8 — short bouts not wiggly:** straightness 1.08 real vs 1.06 jitter-null (noise, not behaviour).
- **A11 — universal:** identical across every animal/night/epoch (artifact signature, not biology).

Engine validated: reproduces production bouts (n 1778 vs 1692 + 85-cap; medians match).

## Corrected statement

Rats move in **ballistic, ~straight, ~constant-speed (~25 in/s) primitives with a near-memoryless
termination hazard, separated by reorientation pauses, composing into longer paddock-scale multi-stop
trips.** There is **no intrinsic ~4 s run limit**; the reported scale is a property of the 3 s-minimum
contiguous-run segmentation.

## Coverage
Done: A1–A6, A8, A10, A11. Partial: A7 (turn-angle; landmark/social deferred). Deferred: A9
(reuse length-matched — secondary, not verdict-critical). Pure numpy (scipy absent) — MLE/hazard/model
comparison implemented directly; truncated-gamma normalization approximated.

## Follow-ups
- If a route/trip unit is wanted downstream, define it at the **trip** level (pause-merge ~5–10 s), not
  the contiguous-run level, and re-derive motifs/recurrence on trips.
- A9 (reuse-vs-length matched) + full A7 (pause decision-points vs landmarks/social) if the
  reorientation-pause finding is pursued.
