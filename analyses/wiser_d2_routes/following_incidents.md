# ⚠️ How frequent is strict trailing, and who leads (incident-level)?

**Direction:** `wiser_d2_routes` · **id:** `following_incidents`  

## 1. Verdict

⚠️ **candidate.** Trailing is frequent but brief: 2046 strict-following episodes (median 3 s) over 11 nights; all 4 top ordered pairs are Sen->X (Sen the dominant lead).

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [wiser_d2_routes_following_incidents_2026a.md](../../results/2026a/wiser_d2_routes/reports/wiser_d2_routes_following_incidents_2026a.md) | — |

**Evidence:** 11 nights; Sen->Siesta 1.82/hr, ->Hypnos 1.70, ->Dormi 1.47, ->Nox 1.41; 2046/2046 routed to a camera queue.

## 3. Canonical driver

`wiser/scripts/analyze_following_incidents.py`

## 4. Canonical report

- [wiser_d2_routes_following_incidents_2026a.md](../../results/2026a/wiser_d2_routes/reports/wiser_d2_routes_following_incidents_2026a.md)

## 5. Figures

- [episode_duration_hist.png](../../results/2026a/wiser_d2_routes/figures/following_incidents/episode_duration_hist.png)
- [episodes_by_night.png](../../results/2026a/wiser_d2_routes/figures/following_incidents/episodes_by_night.png)
- [episodes_per_hour_by_pair.png](../../results/2026a/wiser_d2_routes/figures/following_incidents/episodes_per_hour_by_pair.png)

## 6. Blockers

- camera map is a PLACEHOLDER (confirmed:false)
- video recall not yet claimed (needs marked events)
- leader = temporal order

## 7. Superseded claims

_None._

Change log: [`change_log/2026-07-08-following-incidents-b2.md`](../../change_log/2026-07-08-following-incidents-b2.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_following_incidents.py --cohort 2026a
```

---
*Status source: Following incidents + video audit (Phase B2) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
