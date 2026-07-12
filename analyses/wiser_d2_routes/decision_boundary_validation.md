# ⛔ Can decision-to-decision legs (a 'reorientation-punctuated' structure) be resolved from WISER?

**Direction:** `wiser_d2_routes` · **id:** `decision_boundary_validation`  

## 1. Verdict

⛔ **blocked (needs more data / another modality).** NO reliable boundary class at WISER resolution: pause heading-change is not separable from jitter (matched +18 deg vs jitter-null +20 deg); decision legs are NOT validatable without CV pose/keypoints.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [wiser_d2_routes_decision_boundary_validation_2026a.md](../../results/2026a/wiser_d2_routes/reports/wiser_d2_routes_decision_boundary_validation_2026a.md) | — |

**Evidence:** changepoint detector 30-77% false-positive, 4-24% sensitivity.

## 3. Canonical driver

`wiser/decision_boundary_validation/`

## 4. Canonical report

- [wiser_d2_routes_decision_boundary_validation_2026a.md](../../results/2026a/wiser_d2_routes/reports/wiser_d2_routes_decision_boundary_validation_2026a.md)

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- needs CV pose/keypoints (WISER cannot validate decision boundaries)

## 7. Superseded claims

the 'reorientation-punctuated' / discrete-legs reading

Change log: [`change_log/2026-07-11-decision-boundary-validation.md`](../../change_log/2026-07-11-decision-boundary-validation.md)

## 8. Exact rerun command

```bash
see wiser/decision_boundary_validation/ (validation subproject)
```

---
*Status source: Decision-boundary validation (Stage 1) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
