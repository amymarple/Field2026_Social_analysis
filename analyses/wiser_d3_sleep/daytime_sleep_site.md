# ⚠️ Does each animal have a stable daytime rest site, and how often does it relocate?

**Direction:** `wiser_d3_sleep` · **id:** `daytime_sleep_site`  

## 1. Verdict

⚠️ **candidate.** Per-animal daytime (05:00-21:00) rest site with tiered relocation: over 50 day-pairs {stable 31, major-switch 19}; ALL 5 animals switch house_1<->house_2 at least once, heterogeneous by rate.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [wiser_d3_sleep_SCIENTIFIC_SUMMARY_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_SCIENTIFIC_SUMMARY_2026a.md) | — |

**Evidence:** 11 days (06-28..07-08); rates 12395 5/10, 12407 5/10, others 3/10.

## 3. Canonical driver

`wiser/scripts/analyze_daytime_sleep_site.py`

## 4. Canonical report

- [wiser_d3_sleep_SCIENTIFIC_SUMMARY_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_SCIENTIFIC_SUMMARY_2026a.md)

## 5. Figures

- [S1_rest_sites.png](../../results/2026a/wiser_d3_sleep/figures/daytime_sleep_site/S1_rest_sites.png)
- [S2_across_day_shift.png](../../results/2026a/wiser_d3_sleep/figures/daytime_sleep_site/S2_across_day_shift.png)
- [S3_intraday_drift.png](../../results/2026a/wiser_d3_sleep/figures/daytime_sleep_site/S3_intraday_drift.png)

## 6. Blockers

- 'sleep' = low-speed proxy, not ephys-validated
- site precision gated by ~7 in jitter
- frame unverified

## 7. Superseded claims

the old '8/10 relocated' (jitter) and 3-day 'only 2 animals' (small-sample) readings

Change log: [`change_log/2026-07-02-daytime-sleep-site.md`](../../change_log/2026-07-02-daytime-sleep-site.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_daytime_sleep_site.py --cohort 2026a
```

---
*Status source: Daytime sleep-site + tiered relocation (Direction 3) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
