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

## Later the same day — the six-logger QC of the 09-05 offload, two fitter/report rules
- `pc_time_chain.py`: dense garbage-word bursts are dropped before fitting (a cluster of >= 20 words whose offsets span
  > 30 s; a real touch scatters <= ~100 ms). SF09 `3_20260903_175840.384` carried 1,233 such words at 09-03 23:33 that
  had outvoted its genuine anchors (fit 1,690 ppm); it now fits from the midnight touch at -26.8 ppm (rms 8.2 ms, tail
  7.1 h +- 2.8 ms). New column `n_garbage_dropped` (also 1,001 on the corrupt FM62 record SF10 `0_20260831_070700`).
- `offload_qc_report.py`: sessions listed in `cohorts/<key>.yaml ephys.field_flags` are excluded from the FM65 verdict
  and reported as "field-flagged" (SF10's two 09-05 zombie restarts, 2,339/s on a dying cell); and the 5 % of-FM64-median
  test gets a 5 ticks/s floor - SF7's FM64 median is only 13/s, so 2.6/s of ordinary transients had failed it.
- Result (229 sessions, 603.6 h; FM65 160 / 470.7 h): FM65 CLEAN on all six; all 20 new sessions >= 1 h fit natively
  at their loggers' usual drifts (SF7 -19..-24, SF8 -19..-20, SF9 -26..-27, SF10 -23..-25, SF11 -26, SF12 -20 ppm);
  overview OK 69 / 471.1 h, step-modelled 10 / 68.3 h, chained 3 / 12.7 h, start-only 10 / 25.0 h (unchanged set),
  corrupt 5 / 16.7 h. Daily logger-hours 09-03 126.7, 09-04 133.4, 09-05 51.2 (to the morning round).
