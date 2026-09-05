---
name: offload-field-request
description: >-
  Run after every neurologger card offload once the QC has finished (index -> PC-time chain -> QC report -> coverage).
  It turns the QC outputs into the request the field-PC agent needs to act on — which timestamp/log files to refresh
  and through what time, which sessions have an unanchored end and need their PC-side Stop / auto-stop / Resync
  facts, which findings the field should check, which earlier requests are still open — pushes it to field2026-sync,
  and on the next run checks what came back and feeds it into the QC. Trigger phrases: "after QC", "拷完数据",
  "QC 之后", "push to field agent", "what do we need from the field PC", "field request", "refresh the marks".
---

# Offload → field request

The field PC (recording rig) holds the only record of PC-side time: session Start/Stop marks, the 1 Hz LED-sync log,
the NTP drift log and the incident log. The lab needs them refreshed after every offload to (a) check card durations
against PC spans, (b) anchor session ends the BLE data cannot, (c) locate clock steps. This skill makes that request
specific and mechanical.

## When

After `ephys/build_session_index.py` → `pc_time_chain.py --write-pc-time` → `offload_qc_report.py` →
`coverage_tables.py` have run on the new offload (the scratch runner `qc_full.sh` does all four). Never before: the
request is derived from those outputs.

## Steps

1. **Check what the last request produced** (pulls field2026-sync):
   ```bash
   python ephys/field_request.py --cohort 2026c --check
   ```
   If routine files newer than the previous request landed (marks / LED / drift / incident), re-run
   `python ephys/offload_qc_report.py --cohort 2026c` so the card-vs-PC span check uses the new marks, and re-read
   `results/2026c/ephys_spikes/reports/ephys_spikes_offload_qc_2026c.md`. Read the Response of any answered request in
   `tasks/done/` and act on it (a Resync on a recording logger, a battery pulled without Stop, a new clock step →
   update `cohorts/2026c.yaml` and re-run `pc_time_chain.py`).
   Also `git pull` the recording repo `C:/Users/Cornell/Documents/GitHub/Field_2026_Social_Recording` and read the new
   `BATTERY_LOG_cohort3.md` rows: probe moves, session splits and battery deaths go into `cohorts/2026c.yaml`
   (`probe_moves`, `field_flags`) before anything is interpreted.
2. **Write and push the new request**:
   ```bash
   python ephys/field_request.py --cohort 2026c --push
   ```
   It writes `field2026-sync/tasks/<date>_lab-request-after-offload.md` with: the routine files needed and through
   what time (from the newest session on disk vs what from-field already covers); every session ≥ 1 h whose end is
   unanchored, extrapolated or inconsistent (from the chain CSV) with the question to answer; QC findings worth a
   field look (foreign folders, channel-local impulses, overlaps); clock steps still lacking a Windows event record;
   the open tasks list. Skim the file before pushing when something unusual happened that day (a reboot, a probe
   move) and add one line about it under the relevant section — the generator only knows what the QC knows.
3. **Tell the user** in one short block: what was pushed, what is still outstanding from the field side, and any
   Response that changed a verdict. Do not paste the whole task file.

## Rules

- Requests go through `field2026-sync/tasks/` (commit + push is authorised for that repo); the field agent answers
  by appending `## Response` and moving the file to `tasks/done/`.
- Nothing here reads the field PC directly (this is the analysis PC); the field agent collects and commits.
- The recording repo and the incident log are the record of field events; field2026-sync is the channel. Keep the
  cohort registry consistent with them.
- Do not ask for what is already covered (the generator shows what from-field has); do not re-ask answered items.
