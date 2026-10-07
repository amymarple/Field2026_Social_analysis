# LFP and sleep scores copied from the BioHPC workdir to storage, verified (2026-10-06)

User request: keep the derived ephys on storage (the workdir is not meant for it). Copy first, reconcile, then report;
nothing deleted.

## What changed

- New `ephys/server/copy_to_storage.sh`.
  - It never deletes anything.
  - It refuses to write into a destination folder it did not create (marker file) and checks free space.
  - It resumes with `rsync`.
- Destination: storage `SocialFieldRat2026/3rd_rat/analysis/` (= `Q:\hc997\…` here).

| Destination | Source (workdir `/workdir/hc997/ephys_2026c/`) | Files | Bytes |
|---|---|---|---|
| `analysis/lfp/` | `lfp/` (203 `.lfp` + `.lfp.json` + `lfp_md5.txt`) + `make_lfp*.log` | 410 | 790,208,513,168 (736 GiB) |
| `analysis/sleep/` | `sleep/` (`imu_nremgate`, `imu_remclean`, `_errors`; **without the hard-linked `.lfp`**) + `sleep_states_1s/` → `states_1s/` + `imu_sleep_bundle/` + `score_sleep*.log` | 4,770 | 150,355,265,333 (141 GiB) |

- Each folder also carries `README.md` (layout and provenance), `MD5SUMS` (`md5sum -c` format) and `VERIFY.txt`.
- `cohorts/2026c.yaml raw_data_roots.biohpc` gains `lfp` and `sleep`.
- The CLAUDE.md map L row is updated.

## Verification

- **V1: path and size lists identical,** for both parts.
- **V2: MD5 of every source file equals the MD5 of the destination file.** Sources were read on the local workdir disk.
  Destinations were read with `dd iflag=direct`, which bypasses the host's NFS page cache, so the bytes came back from
  the storage server. PASS for both parts.
- **V3: all 203 `.lfp` match `lfp_md5.txt`,** the manifest written when the LFP was made on 09-28, so the source did not
  change in between. PASS.
- **Self-test before the run** (synthetic tree on the workdir; scratch script, not kept):
  - normal copy: PASS;
  - rerun: skipped;
  - destination without the marker: refused;
  - one byte changed with size and mtime kept: `rsync` skipped it, V2 caught it.
- **Independent check from the analysis PC through Q:** a different client.
  - `SF07/9_20260901_192912.215.lfp` and `SF08/6_20260910_082629.685.lfp` match the copies made locally on this PC
    (MD5 `e4925d10…` and `b05fc129…`).
  - The rescored SF07 `5_20260910_082351` `score_sleep.json` and SSResults figure match the copies fetched on 10-06.
- **Timing:** copy 38 min + 26 min; verification 29 min + 8 min.

## Not done

- **The workdir copies are kept** until the user decides. Pending rescoring reads the LFP from the workdir:
  - SF12 on shank-2/3 channels;
  - SF07 `2_20260905` with a fixed threshold;
  - LFP-EMG for the IMU-refused sessions.

  The sleep folders on storage have no `.lfp`; a rescore from storage needs the session's `.lfp` staged into the folder.
- No note in field2026-sync (the storage map) yet.

## Update 2026-10-07: pass-2 versions added, workdir sleep tree deleted, notes in all three repos

- **User decision:** delete the workdir sleep folder, keep the workdir LFP for now, and have every agent analyse from
  storage from now on.
- **The workdir sleep tree had grown since the first copy.** The pass-2 session (`field2026-social-analysis-94`) had
  added:
  - `imu_fixch` (incl. `SleepScoreRaw.npz`), `pass2_remclean`, `pass2med_remclean`;
  - `sleep_states_1s_{pass2,pass2med,nremgate}`;
  - 5 `_errors` records.

  Its writes ended at 14:20:13, and it confirmed nothing else would write there.
- **Script changes** to `ephys/server/copy_to_storage.sh`:
  - `UPDATE=1` adds new / changed files to an already verified copy and re-verifies everything (the previous
    result kept as `VERIFY_previous.txt`);
  - every `sleep_states_1s_<x>` folder now goes to `sleep/states_1s_<x>/`;
  - a fifth self-test case covers `UPDATE`. A first update attempt at 14:18 overlapped the last pass-2 run and was
    stopped (only `copy_to_storage.sh` and `rsync` were killed).
- **Update copy:** 14:21–16:12, `analysis/sleep/` = **11,711 files, 349 GiB, RESULT PASS**.
  - V1 (paths + sizes) and V2 (MD5 vs an O_DIRECT read-back) pass.
  - Through Q:, `states_1s_pass2med/SF07/2_20260905_093310.289.states.npz` matches the pass-2 session's local copy
    (`b4496c1e…`).
- **Deleted:** `/workdir/hc997/ephys_2026c/sleep`, after confirming no file had changed since 14:21:30 and nothing was
  running. That was 10,712 files + 1,000 `.lfp` hard links.
  - The 203 LFPs stay (link count 1; 3 re-checked against `lfp_md5.txt`).
  - Kept on the workdir: `lfp/`, `imu_sleep_bundle/`, `sleep_states_1s*`.
- **`analysis/sleep/README.md` rewritten.** It states the score to use: `imu_remclean`, with SF07 `2_20260905_093310`
  from `pass2med_remclean`, per the pass-2 session and `ephys/configs/sleep_final_2026c.yaml`. `imu_fixch` and
  `pass2*` are controls.
- **Rule recorded:**
  - CONVENTIONS.md (cohort-appendable principle) and CLAUDE.md quick rules: derived data lives on storage, analyse
    from there, the workdir is scratch.
  - field2026-sync `0af194e`: data-guide rows + `from-lab/2026-10-07_cohort3-lfp-and-sleep-on-storage.md`.
  - Field_2026_Social_Recording `62eb9a6`: a CLAUDE.md data-lifecycle line, plus a repaired `\3rd_rat` → 0x03
    control byte in its calibration backup path.
  - The storage-change notice went to the 8 local sessions that can receive messages.
