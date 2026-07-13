# ⚠️ Do the animals reuse spatial corridors, and are the corridors shared or individual?

**Direction:** `wiser_d2_routes` · **id:** `route_corridor_structure`  

## 1. Verdict

⚠️ **candidate.** Corridors are robust to QC and shared/environment-driven: cross-rat edge similarity 0.90 >> within-rat 0.35.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | — | — |

**Evidence:** 11 nights; night-to-night IoU only ~27%.

## 3. Canonical driver

`wiser/scripts/analyze_route_structure.py`

## 4. Canonical report

- _(off-repo run; see change log below)_

## 5. Figures

- [RS0_all_rats_scatter.png](../../results/2026a/wiser_d2_routes/figures/route_corridor_structure/RS0_all_rats_scatter.png)
- [RS10_self_route_reuse.png](../../results/2026a/wiser_d2_routes/figures/route_corridor_structure/RS10_self_route_reuse.png)
- [RS11_edge_effect.png](../../results/2026a/wiser_d2_routes/figures/route_corridor_structure/RS11_edge_effect.png)
- [RS1_corridor_map.png](../../results/2026a/wiser_d2_routes/figures/route_corridor_structure/RS1_corridor_map.png)
- [RS2_per_rat_occupancy.png](../../results/2026a/wiser_d2_routes/figures/route_corridor_structure/RS2_per_rat_occupancy.png)
- [RS3_route_reuse.png](../../results/2026a/wiser_d2_routes/figures/route_corridor_structure/RS3_route_reuse.png)
- [RS4_occupancy_similarity.png](../../results/2026a/wiser_d2_routes/figures/route_corridor_structure/RS4_occupancy_similarity.png)
- [RS5_straightness.png](../../results/2026a/wiser_d2_routes/figures/route_corridor_structure/RS5_straightness.png)
- [RS6_shared_edges.png](../../results/2026a/wiser_d2_routes/figures/route_corridor_structure/RS6_shared_edges.png)
- [RS7_edge_usage.png](../../results/2026a/wiser_d2_routes/figures/route_corridor_structure/RS7_edge_usage.png)
- [RS8_baseline_compare.png](../../results/2026a/wiser_d2_routes/figures/route_corridor_structure/RS8_baseline_compare.png)
- [RS9_straightness_vs_disp.png](../../results/2026a/wiser_d2_routes/figures/route_corridor_structure/RS9_straightness_vs_disp.png)

## 6. Blockers

- inch frame unverified (no physical-road claim)
- roadway-vs-camera audit undone (needs georeference)

## 7. Superseded claims

_None._

Change log: [`change_log/2026-06-29-route-structure-analysis.md`](../../change_log/2026-06-29-route-structure-analysis.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_route_structure.py --cohort 2026a
```

---
*Status source: Route structure — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
