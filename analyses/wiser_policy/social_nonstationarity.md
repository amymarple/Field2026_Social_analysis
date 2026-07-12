# ⚠️ Is the social-on-leaving effect stable across the season, or does it habituate?

**Direction:** `wiser_policy` · **id:** `social_nonstationarity`  

## 1. Verdict

⚠️ **candidate.** Social-on-leaving is non-stationary across the 11 nights; rest-need vs social is disambiguated and co-departure/following contagion is negligible.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [wiser_policy_social_habituation_2026a.md](../../results/2026a/wiser_policy/reports/wiser_policy_social_habituation_2026a.md) | — |

**Evidence:** 11-night social extension.

## 3. Canonical driver

`wiser/scripts/analyze_social_habituation.py`

## 4. Canonical report

- [wiser_policy_social_habituation_2026a.md](../../results/2026a/wiser_policy/reports/wiser_policy_social_habituation_2026a.md)

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- group-level, identity-agnostic
- frame unverified

## 7. Superseded claims

_None._

Change log: [`change_log/2026-07-12-social-nonstationarity-and-following.md`](../../change_log/2026-07-12-social-nonstationarity-and-following.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_social_habituation.py --cohort 2026a
```

---
*Status source: Social non-stationarity (Module 5 extension) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
