# ⚠️ Do the rats move less on later/rainy nights, and is that habituation or rain?

**Direction:** `wiser_d1_nightly` · **id:** `nightly_habituation_vs_rain`  

## 1. Verdict

⚠️ **candidate.** Nightly active distance falls with habituation (229->152 m/valid-hr over 11 nights); rain vs habituation is NOT separable.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | — | — |

**Evidence:** n=5, 11 nights; wet 122 vs dry 164 m confounded (wet nights are late-sequence + raise dropout); 6/30 DiD CI spans 0.

## 3. Canonical driver

`wiser/scripts/analyze_nightly_progression.py`

## 4. Canonical report

- _(off-repo run; see change log below)_

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- rain and habituation confounded (wet nights late + low-N)
- weather drives dropout AND behavior
- n=5

## 7. Superseded claims

_None._

Change log: [`change_log/2026-06-30-nightly-progression.md`](../../change_log/2026-06-30-nightly-progression.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_nightly_progression.py --cohort 2026a
```

---
*Status source: Nightly movement (habituation vs rain) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
