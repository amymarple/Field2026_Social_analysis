# decision_boundary_validation

Falsification test of the "pauses/kinematic changepoints are control-update boundaries, and
decision-to-decision legs beat the 3 s-filtered bouts" idea that followed the bout-segmentation
result. **Stage 1 only** (verdict-critical core) — **stopped at the interim boundary verdict per the
staging gate, because the boundary interpretation failed.**

**Verdict: no reliable boundary class exists at WISER resolution.** Reorientation-at-pauses is not
separable from localization jitter (jitter-only null +20.4° ≥ real +17.9°; effect reverses to −3.1°
when headings are well-resolved; heading-changepoint detector 30–77 % false-positive, 4–24 %
sensitivity; pause "predictability" is a speed confound). See `validation_report.md` and
`audit/inherited_claim_corrections.md`.

## Pipeline (analysis PC, `cv` env; pure numpy)
```
CACHE=<scratch>/bsv_cache                 # reuses the bout-segmentation cache (native ~4.4 Hz positions)
python src/extract_candidate_boundaries.py $CACHE   # A1 -> tables/candidate_boundaries.csv (131,566 events)
python src/matched_controls.py                      # A3 matched CEM turn test (+ sensitivity)
python src/predictability_break.py $CACHE           # A4 pre-event extrapolation error
python src/noise_simulation.py $CACHE               # A7 jitter null (DECISIVE) + well-resolved test
```
`src/dbv_common.py` = shared kinematics + robust heading foundation. `src/bout_seg.py` (reused from
`bout_segmentation_validation`) = the validated re-extraction engine + cache loader.

## Staging status
- **Stage 1 (done):** Stage 0 audit, candidate extraction, robust heading, matched controls,
  predictability break, noise null + well-resolved restriction → interim verdict.
- **Stage 2 (legs) & Stage 3 (vocabulary/policy): NOT built** — gated off because Stage 1 found no
  defensible boundary class. `segmentation_models.py`, `leg_extraction.py`, `vocabulary_comparison.py`
  and their tables/plots are intentionally absent (deferred, not skipped silently).

## Does not overwrite prior work
`bout_segmentation_validation/` and `outputs/route_motifs_*` are untouched; a transparent correction
note was added to the prior report pointing at the Stage 0 audit.
