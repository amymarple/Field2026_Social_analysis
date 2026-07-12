# ⚠️ When an animal leaves a shelter, where does it go, and is destination conditioned on origin?

**Direction:** `wiser_policy` · **id:** `destination_settlement`  

## 1. Verdict

⚠️ **candidate.** ~60% of shelter departures END IN THE OPEN (open_field_termination); only 19% relocate to a named site, 13% same-site return. Gated choice fit: origin conditions destination (Delta-bits 0.63 / skill 14%).

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [wiser_policy_destination_choice_2026a.md](../../results/2026a/wiser_policy/reports/wiser_policy_destination_choice_2026a.md), [wiser_policy_destination_validation_2026a.md](../../results/2026a/wiser_policy/reports/wiser_policy_destination_validation_2026a.md) | [wiser_policy_destination_choice_07-05_2026a.md](../../archive/2026a/wiser_policy/reports/wiser_policy_destination_choice_07-05_2026a.md), [wiser_policy_destination_validation_07-05_2026a.md](../../archive/2026a/wiser_policy/reports/wiser_policy_destination_validation_07-05_2026a.md) |

**Evidence:** 8 nights; 1,110 stationary episodes -> 321 settlements, 295 departures; choice fit n=55 (exploratory).

## 3. Canonical driver

`wiser/scripts/analyze_destination_choice.py`

## 4. Canonical report

- [wiser_policy_destination_choice_2026a.md](../../results/2026a/wiser_policy/reports/wiser_policy_destination_choice_2026a.md)
- [wiser_policy_destination_validation_2026a.md](../../results/2026a/wiser_policy/reports/wiser_policy_destination_validation_2026a.md)

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- endpoints only (frame unverified, no route/direction claim)
- choice fit thin (n=55)

## 7. Superseded claims

the old named->named `build_destination_table` (blind to 60% open-field terminations)

Change log: [`change_log/2026-07-11-destination-settlement-rebuild.md`](../../change_log/2026-07-11-destination-settlement-rebuild.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_destination_choice.py --cohort 2026a
```

---
*Status source: Destination & settlement (Module 6) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
