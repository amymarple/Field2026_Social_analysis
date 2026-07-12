# ⚠️ Do route bouts recur as a small set of reused motifs, and does the repertoire develop over time?

**Direction:** `wiser_d2_routes` · **id:** `route_motifs`  

## 1. Verdict

⚠️ **candidate.** Trajectories are strongly stereotyped: 97% of route bouts recur (<=3x jitter), broad repertoire (top-motif share only 3-10%/night), present from night 1 (not developing).

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [wiser_d2_routes_route_motifs_2026a.md](../../results/2026a/wiser_d2_routes/reports/wiser_d2_routes_route_motifs_2026a.md) | — |

**Evidence:** 13 nights (06-28..07-10); recurrence 92-99%/night; activity concentrates at 21:00.

## 3. Canonical driver

`wiser/scripts/analyze_route_motifs.py`

## 4. Canonical report

- [wiser_d2_routes_route_motifs_2026a.md](../../results/2026a/wiser_d2_routes/reports/wiser_d2_routes_route_motifs_2026a.md)

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- motif endpoints mostly open->open (corridor segments)
- inch frame unverified

## 7. Superseded claims

_None._

Change log: [`change_log/2026-07-11-motif-rerun-per-hour-day.md`](../../change_log/2026-07-11-motif-rerun-per-hour-day.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_route_motifs.py --cohort 2026a
```

---
*Status source: Route motifs (Phase B) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
