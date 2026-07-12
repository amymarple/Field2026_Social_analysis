# wiser/audit/ — ad-hoc adversarial audit scratch

Preserved, agent-driven, **read-only** adversarial audits of WISER findings — one-off scrutiny scripts, not
pipeline code and not wired into any driver. They are kept as a provenance record of how a claim was
stress-tested. Their inputs are typically the off-repo bulk run CSVs (under
`$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/…`), so they are not guaranteed runnable without that bulk present;
the canonical in-repo reports live under `results/<cohort>/<direction>/`.

For the *structured*, persisted measurement audits, use the `wiser-measurement-auditor` /
`cv-measurement-auditor` subagents (`.claude/agents/`) instead — this folder is for ad-hoc scratch.

| File | What it audits |
|---|---|
| `scratch_env_change_audit.py` | Whether the "social effect is small & stationary" leaving-hazard claim survives an environment-change lens (held-out social×regressor interactions, permutation null, jackknife fragility). |
| `scratch_habituation_power_out.json` | Power-analysis output companion to the habituation/social scratch audit. |
