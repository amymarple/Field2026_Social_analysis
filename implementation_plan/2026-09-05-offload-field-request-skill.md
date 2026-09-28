# Offload → field request as a skill (2026-09-05) — executed the same day

**Goal.** After every card offload + QC, the lab needs the field PC's timestamp records refreshed (PC-side session marks,
LED-sync log, drift log, incident log) and answers about sessions whose end the BLE data cannot anchor. Make that request
mechanical and specific, and check what came back.

**Design.**
- `ephys/field_request.py --cohort <key>`: derives the request from the QC outputs (index CSV → newest Stop on disk;
  chain CSV → ends the lab could not anchor that the newest PC marks do not cover, plus inconsistent fits; QC report →
  findings; cohort YAML → clock steps not yet settled by a Windows event or a final measurement; from-field/ → what is
  already delivered) and writes `field2026-sync/tasks/<date>_lab-request-after-offload.md`. `--push` commits + pushes;
  `--check` pulls and reports Responses / newly delivered files.
- `.claude/skills/offload-field-request/SKILL.md`: when to run (only after the four QC steps), the check → re-run
  `offload_qc_report.py` → push → report cycle, and the rule that the recording repo + incident log are the record.

**Out of scope.** Reading the field PC directly (this is the analysis PC); anything that writes to the recording rig.
