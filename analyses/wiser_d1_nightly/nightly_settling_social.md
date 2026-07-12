# ⚠️ Does the group's use of space settle/stabilize across nights?

**Direction:** `wiser_d1_nightly` · **id:** `nightly_settling_social`  

## 1. Verdict

⚠️ **candidate.** Settling strengthens: home use up, outside down (246->174 m/valid-hr), edge-cosine 0.50->0.81; the exploration graph simplifies.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | — | — |

**Evidence:** n=5 paired, 11 nights.

## 3. Canonical driver

`wiser/scripts/analyze_nightly_behavior.py`

## 4. Canonical report

- _(off-repo run; see change log below)_

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- sub-1 m proximity below jitter floor
- inch frame unverified
- n=5

## 7. Superseded claims

_None._

Change log: [`change_log/2026-06-30-nightly-behavior.md`](../../change_log/2026-06-30-nightly-behavior.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_nightly_behavior.py --cohort 2026a
```

---
*Status source: Nightly behavior & social — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
