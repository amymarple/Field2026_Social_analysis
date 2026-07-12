# ⚠️ Do CV shelter occupancy (CH05/CH06) and WISER near-shelter occupancy agree?

**Direction:** `crossmodal` · **id:** `cv_wiser_sleep_reconciliation`  

## 1. Verdict

⚠️ **candidate.** Asymmetric measurement reconciliation (NOT symmetric cross-val): CV visible-through-glass is a LOWER bound on WISER near-shelter occupancy; headline is per-shelter CV precision ~1.0 + recall gap ~0.49-0.64, never a pooled agreement number.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [crossmodal_cv_wiser_alignment_diagnosis_2026a.md](../../results/2026a/crossmodal/reports/crossmodal_cv_wiser_alignment_diagnosis_2026a.md), [crossmodal_cv_wiser_geometry_diagnosis_2026a.md](../../results/2026a/crossmodal/reports/crossmodal_cv_wiser_geometry_diagnosis_2026a.md) | — |

**Evidence:** 07-02 rerun: 960 bins / 42 episodes; low joint kappa~0.20 is the kappa paradox + definition mismatch, NOT misalignment (+/-1 h lag sweep flat) and NOT optical failure (recall gap on clear glass = wall-edge blind zone).

## 3. Canonical driver

`wiser/scripts/analyze_sleep_site_cv_crossval.py`

## 4. Canonical report

- [crossmodal_cv_wiser_alignment_diagnosis_2026a.md](../../results/2026a/crossmodal/reports/crossmodal_cv_wiser_alignment_diagnosis_2026a.md)
- [crossmodal_cv_wiser_geometry_diagnosis_2026a.md](../../results/2026a/crossmodal/reports/crossmodal_cv_wiser_geometry_diagnosis_2026a.md)

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- kappa is a base-rate-warned diagnostic only, never the headline
- recall gap = coverage/definition limit (wall-edge blind zone)
- CV a lower bound (huddle overlap + blind zone)

## 7. Superseded claims

older 6/29-6/30 kappa (0.66/0.68-0.82) predate the [ns] pandas binning fix

Change log: [`change_log/2026-07-06-cv-wiser-reconciliation-reframe.md`](../../change_log/2026-07-06-cv-wiser-reconciliation-reframe.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_sleep_site_cv_crossval.py --cohort 2026a
```

---
*Status source: Sleep-site WISER<->CV cross-val (Direction 3) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
