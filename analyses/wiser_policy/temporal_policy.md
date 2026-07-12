# ⚠️ Does the leaving rule change over the night, or is it time-invariant?

**Direction:** `wiser_policy` · **id:** `temporal_policy`  

## 1. Verdict

⚠️ **candidate.** The conditional leaving RULE is time-invariant (held-out hour-varying Delta-bits -0.0004; night-slope z 0.51); hour/night differences are state occupancy under ONE shared rule; crowding suppresses leaving, constant across the night.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [wiser_policy_temporal_SUMMARY_2026a.md](../../results/2026a/wiser_policy/reports/wiser_policy_temporal_SUMMARY_2026a.md) | — |

**Evidence:** hour-label null z 0.73.

## 3. Canonical driver

`wiser/scripts/analyze_temporal_policy.py`

## 4. Canonical report

- [wiser_policy_temporal_SUMMARY_2026a.md](../../results/2026a/wiser_policy/reports/wiser_policy_temporal_SUMMARY_2026a.md)

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- inch frame unverified

## 7. Superseded claims

_None._

Change log: [`change_log/2026-07-11-temporal-policy.md`](../../change_log/2026-07-11-temporal-policy.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_temporal_policy.py --cohort 2026a
```

---
*Status source: Temporal policy (time-invariance) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
