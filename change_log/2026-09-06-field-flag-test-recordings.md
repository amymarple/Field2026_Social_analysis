# 2026-09-06 — `field_flag` plumbing: test recordings made from another PC stay indexed but out of PC-time, coverage and analysis

**Trigger.** During the 09-06 12:30–13:34 signal check (third 1/4-turn advance of the SF07 and SF11 probes) the operator ran both
loggers on separate 64 GB test cards from a *different PC's* WILD console to see whether the probes had reached the hippocampus,
and copied the three records into the raw tree (`SF7/D0DBEFEF3111/0_20260906_123827.548` 0.6 min, `1_20260906_123931.995` 21.4 min,
`SF11/1DFE7F77721C/0_20260906_124136.884` 33.8 min). Their BLE anchors carry that PC's clock, so no field-PC time can be derived,
and whether they enter any analysis is undecided (operator: "we have to be cautious"). Raw folders are never renamed or moved.

**Registry** (`cohorts/2026c.yaml`): the three sessions are `field_flags` entries with a new optional attribute `pc_time: false`;
the 09-06 probe moves (SF07 13:29:42, SF11 13:33:38, prev stops 12:31:20 / 12:32:32, 0.25 turn, settle 4 h) are registered from
the recording repo BATTERY_LOG 9/6 row, the incident log 13:45 entry and the Notion Sep 6 row.

**Code.**
- `ephys/build_session_index.py`: new column `field_flag` (text from `ephys.field_flags`, suffixed `[no field-PC time]` when
  `pc_time: false`), a Definitions row for it, and a "Field-flagged sessions" section in the index md. The index stays the
  complete inventory.
- `ephys/pc_time_chain.py`: sessions flagged `pc_time: false` are removed from the per-animal session list *before* decoding, so
  they are neither fitted nor used as a neighbour cluster by the chained fit; they appear in the chain CSV/md with verdict
  `excluded: <flag>` and no `pc_time.dat` is written for them. Other flagged sessions (the SF10 zombie restarts) are still
  fitted as before.
- `ephys/coverage_tables.py`: sessions with a non-empty `field_flag` are not counted; the hourly md header lists them with
  their durations. (This also removes the two SF10 09-05 zombie sessions, 1.08 h, from the coverage - they were already
  "exclude from analysis".)
- `ephys/offload_qc_report.py` needed no change: flagged sessions were already left out of the FM65 verdict and reported as
  "field-flagged"; the PC-time column now shows the chain's `excluded` verdict for the test recordings.

**Definitions.** `field_flag` (index column) = the flag text of the `ephys.field_flags` entry naming the session, empty otherwise;
plain text: the field record says this session is not a real recording (zombie restart) or a test recording, so it is kept in
the inventory and left out of every derived table until the operator decides. `pc_time: false` (registry attribute) = the
session's BLE anchors were written by a console on a PC other than the field PC; `pc_time_chain` treats it as having no
anchors and never borrows its clusters.

**Checks.** `ephys/selftest.py` 20/20; chain test run on SF07 alone showed the two test sessions as `excluded` and the
neighbouring 09-05 sessions unchanged (`5_20260905_133036` OK-chained via next:15, `6_20260905_133118` OK-native). Size check of
the two test cards against the console listing: SF7 2 records / 3,447.257 MB → 99.634 % (residual = record overhead), SF11
1 record / 5,276.764 MB → 99.841 %; both SAFE TO FORMAT.

**Open.** Whether the test recordings are ever analysed is the operator's call; until then they carry the flag. If they are
included, their only time coordinate is the logger RTC (folder name) - no alignment to video / WISER is possible for them.

## Addendum 2026-09-07 — `valid_until`: a session whose neural signal ended before its Stop

SF11's implant detached during the night session `13_20260906_195234.827` (measured: intact to 06:10:00, torn off
06:10:30–06:15:00, open circuit from 06:15:10, Stop 08:12:41). A field flag would have excluded the whole 12.3-h session;
instead a new registry list `ephys.valid_until` (`cohorts/2026c.yaml`) records `{animal, session, valid_until}` and

- `ephys/build_session_index.py` writes a `valid_until` column, notes the tail, and passes `max_samples` to
  `ephys/signal_probe.py::probe_window_stats` so the 5 probe windows lie inside the valid part (the open-circuit tail
  cannot set the session's firmware verdict; checked: verdict `ambiguous`, 3.07 ticks/s, all windows `normal`);
- `ephys/coverage_tables.py` counts the session only up to `valid_until` and lists the truncation in the hourly header
  (10.29 h counted, 2.04 h tail not counted).

`pc_time_chain.py` is untouched: the BLE anchors continued to the Stop, so the fit covers the whole file and the boundary is a
plain time on that axis. Sorting/staging of that session must clip at `valid_until` (not automated; the index column is
the source).
