# Ephys record-quality skill, Notion-aware recording-inquiry, cohort YAML fix (2026-09-28)

Plan: [ephys block-sorting strategy](../implementation_plan/2026-09-28-ephys-block-sorting-strategy.md). This entry
covers the record-quality layer the plan relies on. The pilot itself has not run yet.

## Changes

- **New skill `regime-aware-ephys`** (`.claude/skills/`, mirrored to `.agents/skills/`). It fires before choosing,
  staging, sorting, matching or interpreting cohort-3 neurologger data and carries:
  - the procedure: pull both sibling repos, read the newest incident log, the per-offload QC requests and the Notion
    cohort page, look up the session index, and list the sources checked in the deliverable;
  - the hard rules: firmware, probe advances with their unstable windows, contact/implant loss, ADC lane, gaps and
    unanchored ends, channels, channel maps, non-paddock data;
  - the fleet-wide interpretation windows;
  - where the QC lives;
  - the known gaps between the field record and `cohorts/2026c.yaml`.

  The record was compiled from the Notion page (edited 2026-09-24), field2026-sync `c19ed6c`/`1d409fe` and
  Field_2026_Social_Recording `be3193e`, via the `recording-inquiry` subagent (every item cited) and a direct Notion
  fetch.
- **`recording-inquiry` agent.** It now has the Notion fetch/search tools and treats the Notion cohort page as a third
  source; the per-offload QC requests and the probe-advance/implant notes are in its lookup table.
- **`cohorts/2026c.yaml`.** Added SF12's second probe advance (09-10, post-move session from 08:35:07, pre-move ends
  07:43:01), which was missing; the source is Notion's animal table and the 09-10 observation log. There are now 9
  `probe_moves`.
- **`CLAUDE.md`.**
  - The ephys section points to the skill and to the sorting-strategy plan.
  - The `.claude/` inventory lists the skill.
  - The drift-log sign is corrected: `offset_ms` = NTP − PC, positive = PC slow. The code computes the standard NTP
    θ; the rig script's docstring is inverted, per `field2026-sync/from-field/2026-09-07_pc-clock-drift-analysis.md`
    §0, verified against `pc_drift_check.ps1`.

## Findings recorded, not yet fixed

The following sit in the skill's *Known gaps* list:
- lane-ON `field_flags` exist for SF08 only;
- no 09-12 10:10 paddock-end clip;
- `field_pc_outages` times;
- the construction end and the 09-02 storm are missing;
- SF12 shank-1/4 degradation is not encoded per shank;
- the temperature run is not registered;
- the FM65 "UNEVALUATED" / "VERIFIED" contradiction;
- the Notion animal table's stale SF11 time.

Conflicts between sources are reported in the skill, not resolved: the 09-04 battery deaths (incident log vs
BATTERY_LOG), and SF12's temperature-run implant-loss time.

## Verification

- `cohorts/2026c.yaml` parses and has 9 `probe_moves`. No code reads `probe_moves` yet (the planned
  `ephys/plan_blocks.py` will).
- `python ephys/selftest.py`: 20/20 PASS.
- The skill loaded and is listed as available in the session.
