# bout_segmentation_validation

Falsification test for the route-motif / bout-length result that rats move in short,
~constant-speed bouts with a **~4 s "capacity" and ~8 ft characteristic length**. It asks
whether that scale is biological or **imposed by the segmentation pipeline** (minimum bout
duration, pause handling, smoothing, speed window, displacement filter).

**Verdict: D (segmentation-defined scale)** for the reported 4 s / 100 in numbers; the real
structure is **B (ballistic reorientation-punctuated primitives, near-memoryless hazard) + C
(fragments of paddock-scale multi-stop trips)**. **A (a genuine characteristic run duration) is
falsified.** See `validation_report.md`.

## How it works
1. `src/00_cache_positions.py <cache>` — loads + cleans the WISER night positions ONCE (exact
   production path) and caches them, so every sweep re-extracts from **positions**, not the
   already-filtered `route_bouts.csv`. Also emits the sampling-rate audit facts.
2. `src/bout_seg.py` — the re-extraction engine. Every rule is a parameter; two gap concepts are
   separated (`max_gap_s` = dropout; `pause_merge_s` = pause bridging / trips). Validated to
   reproduce production bouts (n=1778 vs 1692+85-cap; medians match).
3. `src/01_audit_sensitivity.py` — Analyses 1 (audit), 2 (parameter surface), 5 (scale-vs-filter).
4. `src/02_hazard_dist.py` — Analyses 3 (left-truncation), 4 (hazard + model selection), 10 (dists).
5. `src/03_ballisticity_stability.py` — Analyses 8 (jitter null), 11 (cross-animal/night stability).
6. `src/04_trips.py` — Analysis 6 (trip merging) + light 7 (turn angle at pauses).

Run (analysis PC, `cv` env):
```
CACHE=<scratch>/bsv_cache
python src/00_cache_positions.py $CACHE
python src/01_audit_sensitivity.py $CACHE
python src/02_hazard_dist.py $CACHE
python src/03_ballisticity_stability.py $CACHE
python src/04_trips.py $CACHE
```
`tables/` and `plots/` hold the outputs. Pure numpy (scipy/statsmodels/sklearn are absent in `cv`).

## Coverage
Done: A1, A2, A3, A4, A5, A6, A8, A10, A11. Partial: A7 (turn-angle across pauses; full
landmark/social decision-point analysis deferred). Deferred: A9 (reuse length-matched — a secondary
refinement, not verdict-critical). See `run_manifest.json`.

## Does NOT overwrite the existing analysis
The original `outputs/route_motifs_2026-06-28_to_2026-07-10/` (incl. `bout_length_report.md`) is
untouched. This directory is a separate, additive validation that **corrects the interpretation** of
those numbers.
