# Raw neurologger tree backed up E: → L: and verified byte-for-byte (2026-09-17 → 2026-09-20)

**Why.** From the end of the cohort-3 offloads (2026-09-17) `E:\3rd_rat_spikes` was the only copy of the raw WILD data
(`change_log/2026-09-17-cohort3-ephys-offload-complete.md`, `change_log/2026-09-12-storage-health-baseline.md`). The replacement
portable drive arrived and mounted as **L:** on 2026-09-17; the operator asked for the whole raw tree to be copied there with the
most reliable method and then QC'd. This entry records the copy, its three-stage verification, the two things that interfered,
and how to re-verify either copy in future.

## Drives

| | E: (source) | L: (backup) |
|---|---|---|
| Device | WDC WD202KFGX-68CKWN0, 20 TB, SATA, Disk 1 | WD Elements 25A3, 22 TB (21.83 TiB), USB, Disk 4 |
| File system | NTFS, 8 KB clusters | NTFS, 8 KB clusters (empty before the copy) |
| SMART | readable without elevation, table below | USB bridge: needs an elevated `smartctl -d sat /dev/pd4`, not yet read |

## What was copied

`E:\3rd_rat_spikes` → `L:\3rd_rat_spikes`, the complete raw tree: the six animal folders, the six ~512 GB `recovery.bin` card
images, `_quarantine_adc_lane_on\`, and the two root files (`CLAUDE.md`, `analysis_MOVED_TO_D_2026-09-10.txt`).

| | |
|---|---|
| Files / directories | 4,813 / 547 |
| Bytes | 18,171,025,147,170 (18.171 TB = 16.526 TiB; robocopy prints TiB as "t") |
| Method | `robocopy /E /COPY:DAT /DCOPY:DAT /R:2 /W:5 /XJ /NP /TS /FP /LOG+:` — single-threaded (two HDDs, huge files), **never `/MIR`** (must never delete on the destination while the source is the only copy), no ACLs |
| Copy time | 20 h 45 min for the 13.7 TB of the second run + 3 h 57 min for the 3.1 TB of the first run; 202 MB/s average |

## Timeline and the two interferences

- **2026-09-17 17:19:46** — robocopy started from the analysis session's shell. **21:21:23 killed**: the Claude desktop app
  auto-updated (package 2.2553.0.0 registered 21:22:25) and took its child process tree with it. SF10 (806 files, 3.10 TB) was
  complete; `SF11\recovery.bin` was left preallocated to full length with a zero tail. No sleep, reboot, disk or USB event in the
  System log. Every file already on L: was re-checked against E: by size and timestamp (0 differences) and the half-written
  `recovery.bin` was deleted from L: before the restart.
- **2026-09-18 12:52:08** — restarted as a **Windows Scheduled Task** (`Cohort3_backup_E_to_L`, `ExecutionTimeLimit` PT0S, launcher
  `run_backup_E_to_L.cmd`), i.e. under the Task Scheduler service and outside any agent or app process tree. `/E` skipped the
  806 finished files (size + timestamp) and resumed at `SF11\recovery.bin`. **2026-09-19 09:37:43 finished**: exit code 1 (= files
  copied), Copied 4,007, Skipped 806, Mismatch 0, **FAILED 0**, Extras 0.
- **2026-09-19 09:38:07** — 24 s after robocopy ended, Windows Automatic Maintenance started its weekly `ScheduledDefrag`
  (`defrag.exe -c -h -o -$`, all volumes). On E: it moved clusters with 144 KB kernel-level reads and writes, unattributed to any
  user process, and throttled the E: hashing that had just begun to 6–7 MB/s (a direct 512 MB read of another E: file still ran at
  170 MB/s, so the drive itself was fine). The operator stopped it from an elevated shell (~12:00) and **chose to leave the task
  enabled**; it runs weekly when the disks go idle, moves data but does not change it, and only matters when it coincides with a
  large transfer — check `Get-Process defrag` before and during any future copy or hash of E:.

## Verification — three stages, all passed

1. **robocopy summary**: FAILED 0, Mismatch 0, Extras 0 (log: `D:\3rd_rat_spikes\analysis\backup_manifests\robocopy_E_to_L_2026-09-17_to_19.log`).
2. **Dry run** `robocopy … /L` on 2026-09-19 09:39: 4,813 files "same" by size and timestamp, 0 to copy, 0 extras, exit 0
   (`robocopy_E_to_L_dryrun_2026-09-19.log`).
3. **Full SHA-256 manifests of both trees, compared file by file** (`ephys/backup_manifest.py`, new): every byte of E: and of
   L: read once, in parallel, as two Scheduled Tasks (`run_manifest_E.cmd`, `run_manifest_L.cmd`); 16 MB sequential reads with
   the read and the digest overlapped (this CPU hashes at 535 MB/s, the disks deliver 210–250 MB/s, so the overlapped loop is
   disk-bound; the first, serial version ran at 150 MB/s). E: 20.9 h wall (including the defrag-throttled morning), L: 21.4 h;
   226 / 216 MB/s in the final runs. **Result: IDENTICAL — 4,813 files in both, 18,171,025,147,170 bytes, 0 size mismatches,
   0 SHA-256 mismatches, 0 timestamp differences.**

   Shared hashes inside a tree are all structural, not duplicated downloads: 1,020 zero-length files (`adc.dat`, `misc.dat`),
   521 identical `info.rhd`, 38 identical `amplifier.xml`, and `time.dat` counters of equal length — including the SF07/SF08
   final-night pair (`14_20260911_191449.075` and `5_20260911_191715.923`, both exactly 1,091,970,816 samples = 15.166 h, the
   same length to the sample although started 2.5 min apart: a firmware/console record-length cap rather than a coincidence; not
   pursued here). No `amplifier.dat` or `recovery.bin` hash occurs twice.

Stage 3 doubles as the **full-surface read verification** the storage-health baseline deferred: every sector holding data on E:
was read twice (copy + hash) and on L: once, without a single read error.

## E: SMART after reading the whole tree twice (2026-09-20 09:5x, `smartctl -H -A /dev/pd1`)

PASSED. Attributes 1, 5, 7, 10, 196, 197, 198, 199 all **0** — unchanged from the 2026-09-12 baseline. Power-on hours 1,578;
temperature 35 °C (lifetime max 41 °C). No `disk`, `Ntfs`, `storahci`, USB or `partmgr` error/warning in the System log for either
disk from 2026-09-17 17:00 to 2026-09-20 10:00. `Get-PhysicalDisk`: both Healthy / OK.

## Where the evidence lives

| | |
|---|---|
| Manifests (archived, ~760 KB each) | `results/2026c/ephys_spikes/reports/ephys_spikes_raw_tree_sha256_2026c_E_2026-09-20.csv`, `…_L_2026-09-20.csv` — columns `relpath,size,mtime_utc,sha256` |
| Comparison report | `results/2026c/ephys_spikes/reports/ephys_spikes_raw_tree_sha256_2026c_compare_E_vs_L_2026-09-20.md` |
| Logs, launcher scripts, working copies | `D:\3rd_rat_spikes\analysis\backup_manifests\` (robocopy logs, hashing logs with per-file MB/s, the three `.cmd` launchers) |
| Tool | `ephys/backup_manifest.py` — `hash --root … --out … [--resume]` (rows fsync'd per file; resume keeps rows whose size+mtime match, also from an interrupted run's `.partial`), `compare --a … --b … [--report …]` (exit 0 only when identical) |

## How to re-verify either copy later

```powershell
python ephys/backup_manifest.py hash --root L:\3rd_rat_spikes --out D:\3rd_rat_spikes\analysis\backup_manifests\raw_tree_sha256_L_<date>.csv
python ephys/backup_manifest.py compare --a results\2026c\ephys_spikes\reports\ephys_spikes_raw_tree_sha256_2026c_E_2026-09-20.csv --b D:\3rd_rat_spikes\analysis\backup_manifests\raw_tree_sha256_L_<date>.csv
```

A full pass reads 18.2 TB and takes ~21 h at 230 MB/s. Run it as a Scheduled Task with `ExecutionTimeLimit` = PT0S (copy the
launcher pattern from `run_manifest_L.cmd`), not from an agent or app shell, and check that `ScheduledDefrag` is not running.
A single file can be checked in seconds with `Get-FileHash -Algorithm SHA256` against its manifest row.

## State of the data now

Two verified, byte-identical copies of the raw tree: **E:** (working copy, read by the pipeline) and **L:** (backup; keep it
unplugged or read-only between uses). Derived data stay on `D:\3rd_rat_spikes\analysis`. The SD cards are no longer the only
second copy of the final and home-cage sessions; the remaining reason not to format them is the maker's ADC-lane re-download test
(`change_log/2026-09-10-adc-lane-quarantine.md`).

## Lessons recorded

- Any job longer than an hour on this PC runs as a Scheduled Task (no time limit, `MultipleInstances IgnoreNew`), never from an
  agent shell: the desktop app's auto-update killed the first robocopy after 4 h. `Stop-ScheduledTask` on an interactive task does
  not kill the `python` child; terminate it explicitly before restarting a task that writes the same files.
- Automatic Maintenance starts `ScheduledDefrag` as soon as the disks go idle after a long transfer; on a 20 TB HDD it runs for
  hours and starves a concurrent sequential reader. Check for it before interpreting a slow read.
- Full-surface verification of a backup is a hash manifest of both sides, not a robocopy summary; the manifest is the artefact to
  keep, because it lets either copy be re-verified alone.
