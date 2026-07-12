# ⚠️ Do rest onset (evening) and wake (morning) times differ by site?

**Direction:** `wiser_d3_sleep` · **id:** `evening_morning_sleep`  

## 1. Verdict

⚠️ **candidate.** Site + morning structure hold; the `sleep_end` metric was RETIRED and replaced by `wake_hour` (the earlier evening/morning endpoint was unreliable).

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [wiser_d3_sleep_evening_morning_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_evening_morning_2026a.md) | — |

**Evidence:** 11 nights.

## 3. Canonical driver

`wiser/scripts/analyze_evening_morning_sleep.py`

## 4. Canonical report

- [wiser_d3_sleep_evening_morning_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_evening_morning_2026a.md)

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- 'sleep' = low-speed proxy
- wake = speed-onset above jitter (a lower bound)

## 7. Superseded claims

the `sleep_end` metric (retired -> `wake_hour`)

Change log: [`change_log/2026-07-08-evening-morning-sleep.md`](../../change_log/2026-07-08-evening-morning-sleep.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_evening_morning_sleep.py --cohort 2026a
```

---
*Status source: Evening vs morning sleep (Direction 3) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
