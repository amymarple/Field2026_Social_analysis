# ⚠️ Does each animal have an individually stereotyped trajectory, or is stereotypy shared?

**Direction:** `wiser_d2_routes` · **id:** `trajectory_stereotypy`  

## 1. Verdict

⚠️ **candidate.** Space-use stabilizes (0.15->0.89 over 11 nights) but is mostly SHARED/road-driven — residual individual correlation ~ -0.01, label-perm 0/10 above null.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [wiser_d2_routes_trajectory_stereotypy_2026a.md](../../results/2026a/wiser_d2_routes/reports/wiser_d2_routes_trajectory_stereotypy_2026a.md) | — |

**Evidence:** 11 nights (Phase A re-run); only Dormi shows any individual residual.

## 3. Canonical driver

`wiser/scripts/analyze_trajectory_stereotypy.py`

## 4. Canonical report

- [wiser_d2_routes_trajectory_stereotypy_2026a.md](../../results/2026a/wiser_d2_routes/reports/wiser_d2_routes_trajectory_stereotypy_2026a.md)

## 5. Figures

- [occupancy_grid.png](../../results/2026a/wiser_d2_routes/figures/trajectory_stereotypy/occupancy_grid.png)
- [pairwise_similarity.png](../../results/2026a/wiser_d2_routes/figures/trajectory_stereotypy/pairwise_similarity.png)
- [pathdensity_grid.png](../../results/2026a/wiser_d2_routes/figures/trajectory_stereotypy/pathdensity_grid.png)
- [pooled_corridor.png](../../results/2026a/wiser_d2_routes/figures/trajectory_stereotypy/pooled_corridor.png)
- [speed_distribution.png](../../results/2026a/wiser_d2_routes/figures/trajectory_stereotypy/speed_distribution.png)
- [stabilization.png](../../results/2026a/wiser_d2_routes/figures/trajectory_stereotypy/stabilization.png)
- [time_coupling_controls.png](../../results/2026a/wiser_d2_routes/figures/trajectory_stereotypy/time_coupling_controls.png)

## 6. Blockers

- inch frame unverified
- stereotyped != memory

## 7. Superseded claims

_None._

Change log: [`change_log/2026-07-07-trajectory-stereotypy.md`](../../change_log/2026-07-07-trajectory-stereotypy.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_trajectory_stereotypy.py --cohort 2026a
```

---
*Status source: Trajectory stereotypy (Phase A) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
