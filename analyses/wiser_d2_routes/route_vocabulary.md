# ❌ Is there a discrete, shared route 'vocabulary' the animals draw from?

**Direction:** `wiser_d2_routes` · **id:** `route_vocabulary`  

## 1. Verdict

❌ **retracted / falsified.** FALSIFIED (conditional on 3s-bout segmentation): verdict C = continuous route manifold, NOT a discrete vocabulary; endpoints dominate and the shared structure is the endpoint GRAPH, not a path vocabulary.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [wiser_d2_routes_route_vocabulary_SCIENTIFIC_SUMMARY_2026a.md](../../results/2026a/wiser_d2_routes/reports/wiser_d2_routes_route_vocabulary_SCIENTIFIC_SUMMARY_2026a.md) | — |

**Evidence:** 1692 units, 13 nights; endpoint chord 7.88 in ~ jitter beats the K=176 route dict 15.72; robust to bouts<->pause-merged episodes.

## 3. Canonical driver

`wiser/scripts/analyze_route_vocabulary.py`

## 4. Canonical report

- [wiser_d2_routes_route_vocabulary_SCIENTIFIC_SUMMARY_2026a.md](../../results/2026a/wiser_d2_routes/reports/wiser_d2_routes_route_vocabulary_SCIENTIFIC_SUMMARY_2026a.md)

## 5. Figures

- [cumulative_novel_motifs.png](../../results/2026a/wiser_d2_routes/figures/route_vocabulary/cumulative_novel_motifs.png)
- [dictionary_size_vs_test_error.png](../../results/2026a/wiser_d2_routes/figures/route_vocabulary/dictionary_size_vs_test_error.png)
- [endpoint_vs_route_model.png](../../results/2026a/wiser_d2_routes/figures/route_vocabulary/endpoint_vs_route_model.png)
- [first_night_acquisition.png](../../results/2026a/wiser_d2_routes/figures/route_vocabulary/first_night_acquisition.png)
- [mdl_vs_dictionary_size.png](../../results/2026a/wiser_d2_routes/figures/route_vocabulary/mdl_vs_dictionary_size.png)
- [real_vs_geometry_null.png](../../results/2026a/wiser_d2_routes/figures/route_vocabulary/real_vs_geometry_null.png)
- [temporal_holdout_coverage.png](../../results/2026a/wiser_d2_routes/figures/route_vocabulary/temporal_holdout_coverage.png)

## 6. Blockers

- PROVISIONAL: settled only by re-running on validated decision-to-decision legs, which WISER cannot resolve (needs CV)
- reusable-shape reduction is sub-jitter-floor

## 7. Superseded claims

the 'discrete shared route vocabulary' reading; also corrected a Phase-B 'z>2' individual-residual claim (z was 1.84)

Change log: [`change_log/2026-07-11-route-vocabulary-validation.md`](../../change_log/2026-07-11-route-vocabulary-validation.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_route_vocabulary.py --cohort 2026a
```

---
*Status source: Route-vocabulary validation (PROVISIONAL) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
