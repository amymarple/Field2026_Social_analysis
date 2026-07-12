# ⚠️ Do animals actively maintain a preferred inter-individual distance (social spacing)?

**Direction:** `wiser_policy` · **id:** `approach_avoid`  

## 1. Verdict

⚠️ **candidate.** Distance-dependent social spacing: real-time APPROACH to far conspecifics (>3.8m, 8/8 nights, p=0.008) and AVOIDANCE of near ones (1-3.8m, p<=0.016) — active maintenance of a preferred distance; the first robustly night-validated social signal.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [wiser_policy_approach_avoid_2026a.md](../../results/2026a/wiser_policy/reports/wiser_policy_approach_avoid_2026a.md) | [wiser_policy_approach_avoid_07-05_2026a.md](../../archive/2026a/wiser_policy/reports/wiser_policy_approach_avoid_07-05_2026a.md) |

**Evidence:** 8 nights, 3,936 bout-partner pairs; night-level binomial sign test (survived pseudoreplication correction).

## 3. Canonical driver

`wiser/scripts/build_approach_avoid.py`

## 4. Canonical report

- [wiser_policy_approach_avoid_2026a.md](../../results/2026a/wiser_policy/reports/wiser_policy_approach_avoid_2026a.md)

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- coarse net proximity >=1m, heading-free (no fine steering)
- association NOT motivation (not 'attraction')
- group-level
- frame unverified

## 7. Superseded claims

a per-pair z test (pseudoreplicated -> corrected to a night-block test)

Change log: [`change_log/2026-07-12-approach-avoid.md`](../../change_log/2026-07-12-approach-avoid.md)

## 8. Exact rerun command

```bash
python wiser/scripts/build_approach_avoid.py --cohort 2026a
```

---
*Status source: Approach/avoid social spacing (Module 7) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
