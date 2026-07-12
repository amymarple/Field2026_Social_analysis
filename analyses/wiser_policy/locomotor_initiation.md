# ⚠️ What predicts the START of a locomotor bout (the entry side of the loop)?

**Direction:** `wiser_policy` · **id:** `locomotor_initiation`  

## 1. Verdict

⚠️ **candidate.** Bout-initiation hazard is 3.3x higher from open low-speed (0.85%) than settled shelter-rest (0.25%); initiation != ROI departure (26x); weather ~0, group-social NO-GO for initiation (asymmetry with leaving).

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [wiser_policy_locomotor_initiation_2026a.md](../../results/2026a/wiser_policy/reports/wiser_policy_locomotor_initiation_2026a.md) | — |

**Evidence:** 8 nights; 1,016 onsets / 198,735 at-risk epochs; state skill 6.2%.

## 3. Canonical driver

`wiser/scripts/analyze_locomotor_initiation.py`

## 4. Canonical report

- [wiser_policy_locomotor_initiation_2026a.md](../../results/2026a/wiser_policy/reports/wiser_policy_locomotor_initiation_2026a.md)

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- onset = speed-onset above ~7 in jitter (a lower bound; in-nest stirring invisible)
- not 'wake'
- frame unverified

## 7. Superseded claims

a first per-bin-rest decision unit that over-fragmented rest and violated D1

Change log: [`change_log/2026-07-11-locomotor-bout-initiation.md`](../../change_log/2026-07-11-locomotor-bout-initiation.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_locomotor_initiation.py --cohort 2026a
```

---
*Status source: Locomotor-bout initiation (Module 3) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
