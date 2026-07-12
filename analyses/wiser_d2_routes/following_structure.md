# ⚠️ Are there stable leader-follower dyads, or is following a promiscuous herd effect?

**Direction:** `wiser_d2_routes` · **id:** `following_structure`  

## 1. Verdict

⚠️ **candidate.** Following is HERD/promiscuous, not stable dyads: 7-10/10 pairs beat the circular-shift null nightly but the top pair reshuffles (Spearman 0.11); Sen is the dominant leader.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [wiser_d2_routes_following_structure_2026a.md](../../results/2026a/wiser_d2_routes/reports/wiser_d2_routes_following_structure_2026a.md) | — |

**Evidence:** 10 nights (07-04 excluded); movement ~1.25% co-moving; Sen top leader 5/7 nights.

## 3. Canonical driver

`wiser/scripts/analyze_following_structure.py`

## 4. Canonical report

- [wiser_d2_routes_following_structure_2026a.md](../../results/2026a/wiser_d2_routes/reports/wiser_d2_routes_following_structure_2026a.md)

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- single-session weak short-lag/asymmetry -> candidate
- leader = temporal order, not intent

## 7. Superseded claims

_None._

Change log: [`change_log/2026-06-29-leader-follower-analysis.md`](../../change_log/2026-06-29-leader-follower-analysis.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_following_structure.py --cohort 2026a
```

---
*Status source: Leader-follower / route-following — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
