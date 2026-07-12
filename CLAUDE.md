# CLAUDE.md

The conventions for this repository are consolidated in **[CONVENTIONS.md](CONVENTIONS.md)** — the single
canonical constitution. Read it before any non-trivial change.

Quick reminders (all detailed in CONVENTIONS.md):
- This is the **analysis** repo. Recording lives in the separate `social_recording` repo — nothing that
  writes/manages raw capture belongs here.
- **Cohort-appendable:** code takes `--cohort`; results live at `results/<cohort>/<direction>/`; bulk
  artifacts go off-repo under `FIELD2026_ANALYSIS_OUT_ROOT`; a new cohort is a `cohorts/<key>.yaml` + a
  re-run, never a restructure.
- Navigate the science from **`analyses/`** (per-question cards) and **`summaries/`** (per-direction
  narrative) — both regenerated, never hand-edited.
- Medium/large changes need an `implementation_plan/` entry before and a `change_log/` entry after.
- Run `/analysis-definitions` for any deliverable; `/regime-aware-wiser-tracking` and
  `/regime-aware-cv-measurement` before interpreting WISER/CV behavior.
- Link-integrity rule: a moved file with a broken inbound reference is a failure.
