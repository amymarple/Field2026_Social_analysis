# Nightly 9pm–12am behavior & social, 6/28–6/30

## Date

2026-07-01. Uncommitted at writing.

## Plan

[`implementation_plan/2026-06-30-nightly-behavior.md`](../implementation_plan/2026-06-30-nightly-behavior.md).
Companion to [`2026-06-30-nightly-progression.md`](2026-06-30-nightly-progression.md) (raw movement).

## What changed

- `src/wiser_analysis_utils.py` — new "Nightly behavior & social" helpers: `nightly_roi_use`
  (home/resource/tunnel/open time + home↔open transition rate), `nightly_movement_by_cat` (open-only
  rate + active fraction), `nightly_social` (pairwise distance / ≤0.5-1-2 m proximity + reliability /
  clustering / leave-one-out occupancy similarity), `nightly_graph_structure` (per-night ROI
  transition network + night-to-night edge cosine/Jaccard), `nightly_geometry` (coverage,
  concentration, dispersion, corridor/skeleton cells); plots `plot_nightly_paired`,
  `plot_nightly_timebudget`, `plot_nightly_lines`.
- `scripts/analyze_nightly_behavior.py` — driver on the 5-rat paired core (Sova removed), nights
  6/28–6/30; writes 6 CSVs + B1–B9 figures + conclusion + manifest to
  `D:\Field2026_analysis_out\nightly_behavior_*`.

## Why

To answer whether the rats settle (more home/shelter, more resource use, less outside movement),
whether social structure (shared space vs move-together) changes, and whether the exploration network
and space-use geometry stabilize/simplify across the first nights.

## Source data used for verification

Read **read-only**: `D:\Wiser\data\1stcohort_2026.sqlite` (live), `…\tag_reports.sqlite` (baseline),
`configs/wiser_rois.json` (confirmed ROIs). Home = ROI type `refuge` (2 houses + 4 refuges); tunnel_1
present 6/28 only.

## Verification performed

conda `cv`; `py_compile` + end-to-end run. Coherent candidate story (n=5 paired, exploratory):
- **Settling:** home/shelter 0.07→0.13, food/water 0.01→0.03 (both up); **outside movement
  246→142 m/valid-hr (down)**; outside active fraction 0.16→0.08.
- **Exploration graph:** distinct edges 37→33→28 (**simplifies**); night-to-night edge cosine
  **0.50 → 0.97** (**stabilizes** after night 1); out-hub `open` → `house_1` on the wet night.
- **Social:** shared-space occupancy similarity **0.84→0.65→0.72** (individualize, then wet-night
  reconverge); ≤1 m proximity 0.14→0.13 (reliable; 7 in floor ≪ 1 m); mean pairwise distance
  190→171→184 in.
- **Geometry:** coverage 0.59→0.54, corridor cells 2481→2131 (space use narrows).
- 5 rats × 3 nights; B1–B9 render; read-only; no writes under `D:\Wiser`.

## QC output

`nightly_roi_use.csv`, `nightly_movement_by_cat.csv`, `nightly_social.csv`,
`nightly_graph_structure.csv`, `nightly_graph_similarity.csv`, `nightly_geometry.csv`,
`nightly_behavior_conclusion.txt`, `run_manifest.json`, `figures/B1…B9`.

## Known limitations

Exploratory: 3 nights, n=5 paired. **6/30 wet-ground confounded with habituation** (cannot separate);
tunnel present 6/28 only (home trend reported without it); finer-than-1 m proximity unreliable vs the
7 in jitter floor; distances jitter-inflated (paired/relative only); WISER frame unverified; Sova
removed.
