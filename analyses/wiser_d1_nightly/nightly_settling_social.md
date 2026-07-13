# ⚠️ Does the group's use of space settle/stabilize across nights?

**Direction:** `wiser_d1_nightly` · **id:** `nightly_settling_social`  

## 1. Verdict

⚠️ **candidate.** Settling strengthens: home use up, outside down (246->174 m/valid-hr), edge-cosine 0.50->0.81; the exploration graph simplifies.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | — | — |

**Evidence:** n=5 paired, 11 nights.

## 3. Canonical driver

`wiser/scripts/analyze_nightly_behavior.py`

## 4. Canonical report

- _(off-repo run; see change log below)_

## 5. Figures

- [B1_home_fraction.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B1_home_fraction.png)
- [B2_timebudget.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B2_timebudget.png)
- [B3_transitions.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B3_transitions.png)
- [B4_outside_movement.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B4_outside_movement.png)
- [B5_cohesion.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B5_cohesion.png)
- [B6_social_shared.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B6_social_shared.png)
- [B7_graph_2026-06-28.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B7_graph_2026-06-28.png)
- [B7_graph_2026-06-29.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B7_graph_2026-06-29.png)
- [B7_graph_2026-06-30.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B7_graph_2026-06-30.png)
- [B7_graph_2026-07-01.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B7_graph_2026-07-01.png)
- [B7_graph_2026-07-02.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B7_graph_2026-07-02.png)
- [B7_graph_2026-07-03.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B7_graph_2026-07-03.png)
- [B7_graph_2026-07-04.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B7_graph_2026-07-04.png)
- [B7_graph_2026-07-05.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B7_graph_2026-07-05.png)
- [B7_graph_2026-07-06.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B7_graph_2026-07-06.png)
- [B7_graph_2026-07-07.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B7_graph_2026-07-07.png)
- [B7_graph_2026-07-08.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B7_graph_2026-07-08.png)
- [B7_graph_size.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B7_graph_size.png)
- [B8_geometry_metrics.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B8_geometry_metrics.png)
- [B9_corridor_2026-06-28.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B9_corridor_2026-06-28.png)
- [B9_corridor_2026-06-29.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B9_corridor_2026-06-29.png)
- [B9_corridor_2026-06-30.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B9_corridor_2026-06-30.png)
- [B9_corridor_2026-07-01.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B9_corridor_2026-07-01.png)
- [B9_corridor_2026-07-02.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B9_corridor_2026-07-02.png)
- [B9_corridor_2026-07-03.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B9_corridor_2026-07-03.png)
- [B9_corridor_2026-07-04.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B9_corridor_2026-07-04.png)
- [B9_corridor_2026-07-05.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B9_corridor_2026-07-05.png)
- [B9_corridor_2026-07-06.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B9_corridor_2026-07-06.png)
- [B9_corridor_2026-07-07.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B9_corridor_2026-07-07.png)
- [B9_corridor_2026-07-08.png](../../results/2026a/wiser_d1_nightly/figures/nightly_settling_social/B9_corridor_2026-07-08.png)

## 6. Blockers

- sub-1 m proximity below jitter floor
- inch frame unverified
- n=5

## 7. Superseded claims

_None._

Change log: [`change_log/2026-06-30-nightly-behavior.md`](../../change_log/2026-06-30-nightly-behavior.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_nightly_behavior.py --cohort 2026a
```

---
*Status source: Nightly behavior & social — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
