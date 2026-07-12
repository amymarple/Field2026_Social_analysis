# ⚠️ How accurate is the shelter detector, stratified by view quality?

**Direction:** `cv_shelter` · **id:** `detector_validation`  

## 1. Verdict

⚠️ **candidate.** Ground-truth validation on random closed-footage samples reports accuracy stratified by view_quality and asserts the safety check that degraded/unusable bins never score occupied_high_motion.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [cv_shelter_cv_audit_2026a.md](../../results/2026a/cv_shelter/reports/cv_shelter_cv_audit_2026a.md) | — |

**Evidence:** validate_shelter rescored with rat_feasibility-6; see cv_audit.

## 3. Canonical driver

`cv/validate_shelter.py`

## 4. Canonical report

- [cv_shelter_cv_audit_2026a.md](../../results/2026a/cv_shelter/reports/cv_shelter_cv_audit_2026a.md)

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- accuracy is view-quality-dependent
- small labeled ground-truth set

## 7. Superseded claims

cv_audit 07-02/07-03 (-> 07-04, archived)

Change log: [`change_log/2026-07-01-glass-degradation-zones.md`](../../change_log/2026-07-01-glass-degradation-zones.md)

## 8. Exact rerun command

```bash
.\cv\run_validate.ps1 --date 2026-06-30 --n 60
```

---
*Status source: Detector validation (validate_shelter) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
