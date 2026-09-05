# CLAUDE.md

The conventions for this repository are consolidated in **[CONVENTIONS.md](CONVENTIONS.md)** — the single
canonical constitution. Read it before any non-trivial change.

Quick reminders (all detailed in CONVENTIONS.md):
- This is the **analysis** repo. Recording lives in the separate **`Field_2026_Social_Recording`** repo
  (`C:/Users/Cornell/Documents/GitHub/Field_2026_Social_Recording`, github amymarple/Field_2026_Social_Recording) — nothing that writes/manages raw capture belongs here.
- **What is actually going on in the field (rounds, battery swaps/deaths, probe moves, session splits, Resyncs, PC
  incidents) is recorded THERE, not here:** `BATTERY_LOG_cohort3.md` (per-round log, updated several times a day),
  `change_log/`, the per-subsystem `README_*.md` (led_sync, pc_drift, neurologger_daily_resync, health_check, usb_copy, …),
  plus the Notion page "4-Rat 3rd cohort full (SF07–SF12)": https://app.notion.com/p/4-Rat-3rd-cohort-full-SF07-SF12-3c23b0530d4a8152a204cce3afa11671 .
  `git pull` it and read those before interpreting a gap, a split session, a drift verdict or a unit-yield change; keep the
  cohort registry (`cohorts/<key>.yaml`: probe_moves, field_pc_clock_steps, outages, firmware) consistent with it. The
  `field2026-sync` repo is the message channel to the field-PC agent, not the record.
- **Cohort-appendable:** code takes `--cohort`; results live at `results/<cohort>/<direction>/`; bulk
  artifacts go off-repo under `FIELD2026_ANALYSIS_OUT_ROOT`; a new cohort is a `cohorts/<key>.yaml` + a
  re-run, never a restructure.
- Navigate the science from **`analyses/`** (per-question cards) and **`summaries/`** (per-direction
  narrative) — both regenerated, never hand-edited.
- Medium/large changes need an `implementation_plan/` entry before and a `change_log/` entry after.
- Run `/analysis-definitions` for any deliverable; `/regime-aware-wiser-tracking` and
  `/regime-aware-cv-measurement` before interpreting WISER/CV behavior.
- Link-integrity rule: a moved file with a broken inbound reference is a failure.
