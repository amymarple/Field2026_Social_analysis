# Field-PC timestamps copied to F: and verified; the algorithm backed up offsite (2026-09-21 → 2026-09-22)

**Why.** After the raw tree was backed up and verified (`change_log/2026-09-20-raw-tree-backup-verified.md`), the remaining
single-copy material was the derived data on `D:\3rd_rat_spikes\analysis` — 1.41 TB with no backup at all. Of that, the
per-sample field-PC timestamps (`pc_time`, 398.4 GB) are the part every downstream alignment depends on. The operator asked for
the timestamps and the scripts needed to use them to be copied onto the portable SanDisk, and for the algorithm itself to be
backed up offsite.

## The timestamps exist in three layers

| layer | what it is | size | copies after this work |
|---|---|---|---|
| **anchors** | the field PC's ms-of-day embedded by the console in `analogin.dat` lanes 14/15, ~one word per 5 s of BLE connection | part of the raw data (`analogin.dat` = 0.212 TB) | E: and the WD Elements backup — 2, both verified |
| **fit parameters** | per session: offset, drift, verdict, clock steps. The scientific content, and the only layer not cheaply reproducible without the raw anchors. | **0.48 MB** (429 JSON) | D:, F:, the analysis repo, the sync repo, GitHub — 5 |
| **expanded** | `pc_time.dat`, uint32 ms-of-day per amplifier sample, 4 B/sample = 1/32 of `amplifier.dat` | **398.4 GB** (429 files) | D: and F: — 2 |

Coverage of the fits: **1,258.5 of 1,258.6 h of FM65 paddock recording (99.99 %)**. The 0.09 h missing are 39 battery-swap
fragments of a minute or less with 0–4 anchors. FM64 (115 h) is covered, 19 h of it from a start cluster only. FM62 (18 h,
08-31 daytime) has no usable anchors — a corrupt sync lane, and that material is written off anyway. The five home-cage sessions
of 09-12 (46.4 h) are deliberately excluded: started from another laptop, so their anchors are not field-PC time.

## 1. Offsite backup of the algorithm (2026-09-21)

`field2026-sync` commit `8b595b3`, `from-lab/2026-09-21_pc-time-algorithm-backup/` — 280 KB, pushed to GitHub. Holds
`pc_time_chain.py`, `2026c.yaml` (the registry it reads: clock steps, `pc_time_accept`, field flags, `valid_until`), all 429
`pc_time_fit.json` as a 50 KB tarball, the 2026-09-16 fit report for all 494 sessions, a README, and a **new standalone
regenerator** `regen_pc_time.py` (numpy only; expands the JSONs back to `pc_time.dat`, or verifies an existing tree byte for
byte, without the raw data or this repo).

**Rebuild costs, measured on this PC:**

| path | time | needs |
|---|---|---|
| from the 50 KB tarball (`regen_pc_time.py`) | ~67 min | that folder + numpy |
| re-derive from the raw anchors (`pc_time_chain.py --write-pc-time`) | ~90 min (20 min fit + 67 min write) | the raw tree as well |
| copy 398 GB from a backup | ~20 min | a copy to be present |

Generation runs at 99 MB/s (25 Msamples/s, single-threaded numpy). Use the full path when the registry changes (a corrected
clock step, a new `valid_until`); the short path would faithfully reproduce the old numbers.

**Both paths verified deterministic.** Re-fitting SF07 on 2026-09-21 reproduced the 2026-09-16 report exactly: 88 sessions, zero
differences in offset, drift, anchor count or verdict. `regen_pc_time.py --verify` reproduced SF11's 58 sessions (40.3 GB) from
the tarball alone, byte for byte, 0 differing.

## 2. Copy to F: (2026-09-22)

**The drive.** SanDisk Extreme Pro 4 TB USB SSD (serial 24361Q402891), the one that dropped off 2026-08-24 and was written off in
the storage-health baseline. It enumerates again. It is an appropriate home for regenerable derived data and **must not hold
anything unique**.

**It needed repair first.** `Get-Volume` reported `HealthStatus Warning`, `OperationalStatus Full Repair Needed`; a read-only
`chkdsk F:` found *"Corruption was found while examining the volume bitmap"* with file and folder verification complete and
**0 KB in bad sectors** — the free-space map was inconsistent, so a write could have allocated clusters that were actually in
use. The operator ran `chkdsk F: /f`; Windows corrected it (occupied space moved by 24 MB, no files lost) and the volume is now
Healthy / OK.

**What was already on F::** 260.4 GB under `F:\3rd`, the aborted 08-31/09-01 offload. **99.6 % of it duplicates the verified
E: copy** file-for-file by size; the only non-duplicate is a stray top-level MAC folder holding SF11
`0_20260831_072408.414` truncated to 19 % (`amplifier.dat` 978 MB against 5.14 GB on E:) — the fragment that was being written
when the drive died. Nothing on F: is unique; the 260 GB can be reclaimed whenever the operator wants. Left untouched here.

**The copy**, as a Scheduled Task (`run_copy_pc_time_to_F.cmd`, `ExecutionTimeLimit` PT0S):

```
robocopy "D:\3rd_rat_spikes\analysis\pc_time"            "F:\cohort3_pc_time\pc_time" /E /COPY:DAT /DCOPY:DAT /R:2 /W:5 /XJ
robocopy "D:\3rd_rat_spikes\analysis\_to_F_bundle\scripts" "F:\cohort3_pc_time\scripts" /E /COPY:DAT /DCOPY:DAT /R:2 /W:5 /XJ
```

858 files / 398.4 GB plus 9 files / 918 KB, **FAILED 0, Mismatch 0**, 344 MB/s, 19 min. `F:\cohort3_pc_time\scripts\` is the
sync-repo bundle plus `backup_manifest.py` and the 494-session index, so the drive is self-sufficient: it carries the data, the
recipe, and the tools to check both.

**Verification.** SHA-256 manifests of both trees, hashed in parallel as Scheduled Tasks (319 and 303 MB/s, 21 min each) and
compared: **IDENTICAL — 858 files, 0.398 TB, 0 size mismatches, 0 SHA-256 mismatches.** All 858 modification times differ by
+0.008 to +2.0 s, which is exFAT's 2-second timestamp granularity against NTFS, not a data difference.

## Where the evidence lives

| | |
|---|---|
| Manifests + comparison | `D:\3rd_rat_spikes\analysis\backup_manifests\pc_time_sha256_{D,F}.csv`, `pc_time_sha256_compare_D_vs_F.md` |
| Copy log | same folder, `robocopy_pc_time_to_F.log` |
| Staged bundle (what went to F:) | `D:\3rd_rat_spikes\analysis\_to_F_bundle\scripts\` |
| Algorithm backup | `field2026-sync` `from-lab/2026-09-21_pc-time-algorithm-backup/` |

## What is still single-copy on D:

`stage` 676 GB, `sort` 336 GB, `index` + `tools` 0.1 GB. All regenerable, and both `stage` and `sort` will be redone when the
sorting is finalised, so backing them up now would be wasted. Revisit once the sort is settled.
