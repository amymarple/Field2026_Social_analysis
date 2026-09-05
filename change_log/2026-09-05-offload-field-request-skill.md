# 2026-09-05 — offload → field request skill; exact field-PC clock steps from the Windows event log

## What changed
- New tool `ephys/field_request.py` and skill `offload-field-request` (see implementation_plan/2026-09-05-…). The request
  is derived from the QC outputs, so it only asks for what is missing: routine files through the newest Stop on disk,
  ends the lab could not anchor that the PC-side marks do not yet cover, inconsistent fits, findings, unsettled steps.
- `cohorts/2026c.yaml` `field_pc_clock_steps` now carry the EXACT w32time steps from the field PC's System log
  (Kernel-General Id 1, delivered as field2026-sync `from-field/2026-09-04_cohort3-pc-clock-change-events.csv`):
  2026-08-30 13:23:19 +2.3067 s (before any recorded session), 2026-08-31 09:00:19 +2.4164 s (was 2.386 at 09:00:17),
  2026-09-01 13:09:12 +2.5487 s (was 2.6 at 13:09:11). No other w32time step exists; W32Time off since 09-01 19:00.
  Windows does not log the boot-time clock load from the RTC, so the 2026-09-03 13:56 reboot step stays at its
  measured 1.28 ± 0.04 s (final); the drift-check task now also fires 5 min after every boot (field, 2026-09-05 01:16).
- Field answer on the console Scheduler: it is a device-side rule engine (rules written to the logger; Record Start,
  sleep, reboot), with no host-side periodic connect — so no auto-anchor. Two facts worth keeping: the console itself
  refuses RTC writes to a recording logger (it sends packed PC-time anchors instead), and a session tab left open
  reconnects whenever the animal comes back into range (the source of the opportunistic mid-session anchors).
- SF07 / SF11 second probe advances 2026-09-05 (1/4 turn each) and SF10's two 09-05 zombie-restart sessions registered
  from the recording repo's BATTERY_LOG and the incident log; CLAUDE.md now names the recording repo, the incident-log
  mirror and the Notion page as the record of field events.

## Effect on results
The 08-31 and 09-01 steps move by +30 ms and −51 ms; sessions spanning them refit on the next chain run (the 2026-09-05
full QC rerun picks the new values up). No verdict is expected to change; per-session drifts shift by < 0.5 ppm.
