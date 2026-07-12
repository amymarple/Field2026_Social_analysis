# ⚠️ Do the animals reuse spatial corridors, and are the corridors shared or individual?

**Direction:** `wiser_d2_routes` · **id:** `route_corridor_structure`  

## 1. Verdict

⚠️ **candidate.** Corridors are robust to QC and shared/environment-driven: cross-rat edge similarity 0.90 >> within-rat 0.35.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | — | — |

**Evidence:** 11 nights; night-to-night IoU only ~27%.

## 3. Canonical driver

`wiser/scripts/analyze_route_structure.py`

## 4. Canonical report

- _(off-repo run; see change log below)_

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- inch frame unverified (no physical-road claim)
- roadway-vs-camera audit undone (needs georeference)

## 7. Superseded claims

_None._

Change log: [`change_log/2026-06-29-route-structure-analysis.md`](../../change_log/2026-06-29-route-structure-analysis.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_route_structure.py --cohort 2026a
```

---
*Status source: Route structure — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
