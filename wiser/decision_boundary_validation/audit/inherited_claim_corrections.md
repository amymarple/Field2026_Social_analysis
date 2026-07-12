# Stage 0 — Audit of inherited bout-segmentation claims

Reconciles the internal inconsistencies in `bout_segmentation_validation/validation_report.md` before
building on it. **The main verdict (D: the ~4 s / ~100 in scale is a segmentation artifact) is
UNCHANGED and survives every correction below** — the corrections tighten hazard/distribution wording
and trip terminology, not the artifact conclusion. Nothing in the prior directory was edited; this log
records the corrections and the downstream analysis uses the corrected values.

| issue | source statement | code path | resolved value / interpretation | correction made |
|---|---|---|---|---|
| Two "untruncated medians" | "un-truncated median run is 0.54 s" (§decisive #2) vs A11 table "untrunc_dur_med 1.21" | `02_hazard_dist.py` uses `segment(min_bout=0, **min_disp=0**)` → **0.538 s**; `01/03` use `min_bout=0` but **`min_disp=15`** → **1.209 s** | Both are min_bout=0 (no duration truncation); they differ only by the displacement floor. Verified: min_disp 0 → 0.538 s (n=73 913); min_disp 7 (jitter floor) → 0.672 s (n=55 379); min_disp 15 → 1.209 s (n=27 689). | Report the primitive run median **at the jitter floor: ~0.5–0.7 s** (sub-second), and always state the displacement floor. Neither is 4 s → verdict D intact. |
| "near-memoryless termination" vs "lognormal best fit" | §decisive #3 says both | `02_hazard_dist.py` model comparison | **Incompatible.** Memoryless = exponential = **constant** hazard, which is the **WORST** fit (AIC **103 201**, verified). Lognormal wins (AIC 92 300) → hazard is **non-monotone** (rises then falls), not constant. | **Retract "memoryless."** Corrected: durations are a smooth **lognormal** continuum with **no characteristic-duration breakpoint**; the only hazard inflection is ~1.3 s ≈ the 1 s speed-smoothing window; the 4 s is truncation. |
| Weibull k≈1.1 provenance | "Weibull shape k=1.10 ≈ 1 (flat hazard)" cited as evidence | `hazard_model_comparison` | Weibull was a **secondary (non-winning) candidate** (AIC 102 469 > lognormal 92 300). k≈1.1 indicates only *weakly increasing* hazard, and is superseded by the better lognormal (non-monotone). | Do **not** cite k≈1.1 as the hazard verdict. Use it only as a descriptive note; the hazard conclusion rests on "no 4 s breakpoint + lognormal + 1.3 s inflection." |
| "99 % merged into trips" | §decisive #4 | `04_trips.py`: `frac_multi_bout_trips = (b["n_pause"]>=1).mean()` | = fraction of merged **units** that contain ≥1 bridged pause, at pause-merge 5 s. Merging **IS transitive** (`_segment_group` chains consecutive runs while each pause < threshold), so a unit can bridge many pauses. | State it as "**98.9 % of production bouts fall inside a transitively pause-merged episode** (≥1 bridged pause at a 5 s tolerance)," not "trips." |
| "trip" terminology | "trips reach the full paddock diagonal" | `04_trips.py`, report | No destination/objective validation was done; merges are pure pause-bridging with transitive chaining. | **Rename "trip" → "merged locomotor episode"** everywhere downstream. A destination-coherent "trip" is NOT claimed. (Operating principle: a transitive chain of fragments is not a coherent trip without destination evidence.) |
| Smoothing/threshold/grid provenance of each number | implicit | `bout_seg.add_speed_param` (smooth 7, speed window 1.0 s), `_segment_group` (moving_thr 12.63, max_gap 2.0), sampling median dt 0.228 s | All un-truncated numbers use smooth=7, thr=12.63, 4.4 Hz native grid (not 1 s gridded). The 1.29 s hazard inflection = the 1.0 s speed window (the true lower timescale limit). | Downstream uses the **native ~4.4 Hz grid** and reports smoothing/threshold with every statistic; no 1 s gridding. |

## Net effect on the prior verdict

- **Unchanged:** D (segmentation-defined scale). The load-bearing results — scale tracks min_bout ~1:1
  (slope 0.95; disp slope = median speed 25 in/s), un-truncated median ≪ 4 s, "3.8 s" = conditional
  median|≥3 s — are all correct and independent of the corrections above.
- **Corrected wording carried forward:** (a) primitive run median is **sub-second at the jitter floor**;
  (b) the hazard is **non-monotone lognormal with no 4 s breakpoint** (NOT memoryless); (c) pause-merged
  units are **"merged locomotor episodes," transitively chained**, not destination-validated trips.
- A pointer to this audit is added to the prior report (no silent edit of its body).
