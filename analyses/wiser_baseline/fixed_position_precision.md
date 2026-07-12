# ✅ What is WISER's static position precision (the jitter floor that bounds every spatial claim)?

**Direction:** `wiser_baseline` · **id:** `fixed_position_precision`  

## 1. Verdict

✅ **confirmed.** Stationary jitter floor is ~7 in (18 cm) median, p95 ~15 in, at ~3.7-3.9 Hz — a precision floor, not accuracy.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [wiser_baseline_fixed_position_summary_2026a.csv](../../results/2026a/wiser_baseline/reports/wiser_baseline_fixed_position_summary_2026a.csv) | — |

**Evidence:** Fixed-position test vs surveyed ground truth; RMS jitter median ~7 in.

## 3. Canonical driver

`wiser/scripts/analyze_fixed_position_test.py`

## 4. Canonical report

- [wiser_baseline_fixed_position_summary_2026a.csv](../../results/2026a/wiser_baseline/reports/wiser_baseline_fixed_position_summary_2026a.csv)

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- precision only, not absolute accuracy
- inch frame is an unverified offset origin

## 7. Superseded claims

_None._

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_fixed_position_test.py --data D:\Wiser\data --trim-minutes 5
```

---
*Status source: Fixed-position precision — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
