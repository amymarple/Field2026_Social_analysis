# ❌ Is the ~4 s / ~100 in 'bout capacity' a real behavioral unit?

**Direction:** `wiser_d2_routes` · **id:** `bout_segmentation_validation`  

## 1. Verdict

❌ **retracted / falsified.** RETRACTED: the '~4 s bout capacity' is a SEGMENTATION ARTIFACT (scale moves 1:1 with the 3 s min-bout filter); the un-truncated median run is sub-second at the jitter floor; hazard is non-monotone lognormal with no 4 s breakpoint ('memoryless' retracted).

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [wiser_d2_routes_bout_segmentation_validation_2026a.md](../../results/2026a/wiser_d2_routes/reports/wiser_d2_routes_bout_segmentation_validation_2026a.md) | — |

**Evidence:** 0.54 s no-filter median; 99% of bouts sit inside longer pause-merged episodes.

## 3. Canonical driver

`wiser/bout_segmentation_validation/`

## 4. Canonical report

- [wiser_d2_routes_bout_segmentation_validation_2026a.md](../../results/2026a/wiser_d2_routes/reports/wiser_d2_routes_bout_segmentation_validation_2026a.md)

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- needs CV pose/keypoints to define validated legs

## 7. Superseded claims

the '~4 s / ~100 in bout capacity' and 'memoryless' claims

Change log: [`change_log/2026-07-11-bout-segmentation-validation.md`](../../change_log/2026-07-11-bout-segmentation-validation.md)

## 8. Exact rerun command

```bash
see wiser/bout_segmentation_validation/ (validation subproject)
```

---
*Status source: Bout-segmentation validation — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
