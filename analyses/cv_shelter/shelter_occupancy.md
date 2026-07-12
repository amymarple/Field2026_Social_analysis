# ⚠️ How many animals are inside each shelter, and are they resting or active (through-glass CV)?

**Direction:** `cv_shelter` · **id:** `shelter_occupancy`  

## 1. Verdict

⚠️ **candidate.** CH05/CH06 through-glass occupancy + rest/active state, view-quality-gated: degraded inside-glass never becomes occupied_high_motion, unusable -> indeterminate; counts are a LOWER bound (wall-edge blind zone).

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [cv_shelter_measurement_context_audit_2026a.md](../../results/2026a/cv_shelter/reports/cv_shelter_measurement_context_audit_2026a.md) | — |

**Evidence:** 6 dates x 2 cameras; robust_inside_motion rejects rain speckle/glare/AE.

## 3. Canonical driver

`cv/shelter_sleep.py`

## 4. Canonical report

- [cv_shelter_measurement_context_audit_2026a.md](../../results/2026a/cv_shelter/reports/cv_shelter_measurement_context_audit_2026a.md)

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- glass fog/condensation/rain/film view-quality artifacts
- wall-edge blind zone -> counts are a lower bound
- no cross-camera identity

## 7. Superseded claims

_None._

Change log: [`change_log/2026-07-03-wiser-shelter-occupancy-state.md`](../../change_log/2026-07-03-wiser-shelter-occupancy-state.md)

## 8. Exact rerun command

```bash
python cv/shelter_sleep.py --channel CH05 --date 2026-06-30
```

---
*Status source: Shelter occupancy (docs/methods/shelter_cv_measurement.md) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
