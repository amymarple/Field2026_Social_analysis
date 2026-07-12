# ⚠️ Is there a ranked hierarchy of preferred rest landmarks?

**Direction:** `wiser_d3_sleep` · **id:** `sleep_site_hierarchy`  

## 1. Verdict

⚠️ **candidate.** Landmark rest sites rank into a hierarchy (H1-H4) by occupancy.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [wiser_d3_sleep_site_hierarchy_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_site_hierarchy_2026a.md) | — |

**Evidence:** 11 days.

## 3. Canonical driver

`wiser/scripts/analyze_sleep_site_hierarchy.py`

## 4. Canonical report

- [wiser_d3_sleep_site_hierarchy_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_site_hierarchy_2026a.md)

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- 'sleep' = low-speed proxy
- frame unverified

## 7. Superseded claims

_None._

Change log: [`change_log/2026-07-11-sleep-site-hierarchy.md`](../../change_log/2026-07-11-sleep-site-hierarchy.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_sleep_site_hierarchy.py --cohort 2026a
```

---
*Status source: Sleep-site hierarchy (Direction 3) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
