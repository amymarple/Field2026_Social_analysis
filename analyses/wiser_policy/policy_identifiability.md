# ⚠️ Beyond a shared layout + weather baseline, does identity or social state predict leaving/destination?

**Direction:** `wiser_policy` · **id:** `policy_identifiability`  

## 1. Verdict

⚠️ **candidate.** Environment+dwell explains leaving hazard (skill 0.13-0.26); INDIVIDUAL is detectable but NEGLIGIBLE (~0.001 bits); real-time GROUP social state is a ROBUST predictor of leaving (~0.012 bits, +on all 8 nights, jitter-floor-safe). Endpoint = environment+dwell+group-social semi-Markov choice model; no IRL.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [wiser_policy_identifiability_audit_2026a.md](../../results/2026a/wiser_policy/reports/wiser_policy_identifiability_audit_2026a.md), [wiser_policy_identifiability_report_2026a.md](../../results/2026a/wiser_policy/reports/wiser_policy_identifiability_report_2026a.md), [wiser_policy_identifiability_SCIENTIFIC_SUMMARY_2026a.md](../../results/2026a/wiser_policy/reports/wiser_policy_identifiability_SCIENTIFIC_SUMMARY_2026a.md) | — |

**Evidence:** 8 nights, hysteretic ROI-state decision unit; social survives day-shuffle z~30.

## 3. Canonical driver

`wiser/scripts/analyze_policy_identifiability.py`

## 4. Canonical report

- [wiser_policy_identifiability_audit_2026a.md](../../results/2026a/wiser_policy/reports/wiser_policy_identifiability_audit_2026a.md)
- [wiser_policy_identifiability_report_2026a.md](../../results/2026a/wiser_policy/reports/wiser_policy_identifiability_report_2026a.md)
- [wiser_policy_identifiability_SCIENTIFIC_SUMMARY_2026a.md](../../results/2026a/wiser_policy/reports/wiser_policy_identifiability_SCIENTIFIC_SUMMARY_2026a.md)

## 5. Figures

- [temporal_effects.png](../../results/2026a/wiser_policy/figures/policy_identifiability/temporal_effects.png)

## 6. Blockers

- inch frame unverified (topology + coarse >=14 in only)
- social is group-level, identity-agnostic
- individual + social policy NOT identifiable beyond shared layout -> IRL/reward-feasibility NO-GO

## 7. Superseded claims

the contaminated raw point-in-ROI decision unit (M4/M5 invalidated; social flipped NO-GO->GO)

Change log: [`change_log/2026-07-10-decision-unit-hysteretic-social.md`](../../change_log/2026-07-10-decision-unit-hysteretic-social.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_policy_identifiability.py --cohort 2026a
```

---
*Status source: Agent-policy identifiability (modules 5+6) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
