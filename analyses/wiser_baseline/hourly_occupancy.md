# ✅ Where do the animals spend time, hour by hour (live-DB-safe occupancy maps)?

**Direction:** `wiser_baseline` · **id:** `hourly_occupancy`  

## 1. Verdict

✅ **confirmed.** Per-hour scatter/heatmaps computed from a strictly read-only view of the live WAL DB; the in-progress hour is never plotted.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | — | — |

**Evidence:** Live-DB-safe hourly occupancy over the recording window.

## 3. Canonical driver

`wiser/scripts/plot_hourly_occupancy.py`

## 4. Canonical report

- _(off-repo run; see change log below)_

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- inch frame unverified (no physical/directional claim)

## 7. Superseded claims

_None._

Change log: [`change_log/2026-06-28-hourly-occupancy-maps.md`](../../change_log/2026-06-28-hourly-occupancy-maps.md)

## 8. Exact rerun command

```bash
python wiser/scripts/plot_hourly_occupancy.py
```

---
*Status source: Hourly occupancy maps — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
