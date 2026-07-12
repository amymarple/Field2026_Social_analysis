# ⚠️ Does post-film glass fog degrade detectability, and how severe is it?

**Direction:** `cv_shelter` · **id:** `fog_dynamics_vs_detectability`  

## 1. Verdict

⚠️ **candidate.** Post-anti-fog-film fog severity + fog dynamics vs detectability characterized; the recall gap is a coverage/definition limit, not an optical/fog failure (does not concentrate in degraded/foggy strata).

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [cv_shelter_postfilm_fog_severity_2026a.md](../../results/2026a/cv_shelter/reports/cv_shelter_postfilm_fog_severity_2026a.md) | — |

**Evidence:** postfilm fog severity 2026-07; phaseA fog dynamics.

## 3. Canonical driver

`cv/fog_risk.py`

## 4. Canonical report

- [cv_shelter_postfilm_fog_severity_2026a.md](../../results/2026a/cv_shelter/reports/cv_shelter_postfilm_fog_severity_2026a.md)

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- fog is a covariate on the sensor path, not behavior
- through-glass regime confounds counts

## 7. Superseded claims

_None._

Change log: [`change_log/2026-07-09-duo3-keyframe-cap.md`](../../change_log/2026-07-09-duo3-keyframe-cap.md)

## 8. Exact rerun command

```bash
see cv/fog_risk.py + docs/methods/shelter_failure_modes.md
```

---
*Status source: Fog dynamics vs detectability — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
