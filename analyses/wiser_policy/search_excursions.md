# ⚠️ Do animals return to known sites vs explore, and is movement area-restricted or global?

**Direction:** `wiser_policy` · **id:** `search_excursions`  

## 1. Verdict

⚠️ **candidate.** Return vs explore shows NO return-bias beyond layout (null); area-restricted vs global search is geometry-only and DBV-capped (coarse).

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [wiser_policy_search_excursions_2026a.md](../../results/2026a/wiser_policy/reports/wiser_policy_search_excursions_2026a.md) | — |

**Evidence:** 11 nights (Phase 4).

## 3. Canonical driver

`wiser/scripts/build_search_excursions.py`

## 4. Canonical report

- [wiser_policy_search_excursions_2026a.md](../../results/2026a/wiser_policy/reports/wiser_policy_search_excursions_2026a.md)

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- geometry, not 'foraging strategy'
- DBV-capped (fine kinematics not resolvable)
- frame unverified

## 7. Superseded claims

_None._

Change log: [`change_log/2026-07-12-phase4-search-excursions.md`](../../change_log/2026-07-12-phase4-search-excursions.md)

## 8. Exact rerun command

```bash
python wiser/scripts/build_search_excursions.py --cohort 2026a
```

---
*Status source: Return vs explore / ARS (Modules 9-10) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
