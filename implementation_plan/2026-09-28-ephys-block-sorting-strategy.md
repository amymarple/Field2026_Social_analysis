# Ephys preprocessing strategy for cohort 3 (2026c): sort per block, match units across blocks; local pilot (2026-09-28)

**Status.** PLAN, 2026-09-28. Pilot not started. Production run later on BioHPC GPUs.

## Decision

1. **The sorting unit is a *block*:** one stretch of continuous FM65 recording on one logger. A block is one session, or
   several sessions joined across gaps under 5 min (logger restarts in the middle of a recording). It never spans a
   battery round (30 min–2 h), a probe move, a firmware change or a field-flagged session.
2. **Identity across blocks is recovered afterwards by unit matching**: adjacent blocks per shank, chained within
   one probe position. There is no Kilosort run over a concatenation of days.
3. **Production runs on server GPUs** as one Slurm job per block, all independent. **This PC runs a pilot** that
   validates the current pipeline version, measures throughput and measures how accurate the matching is.

## What the data are (session index, 2026-09-28)

| Logger | FM65 h (not field-flagged) | FM64 h (de-glitch + width filter) | FM62 h (written off) |
|---|---|---|---|
| SF07 | 228.8 | 22.1 | 0 |
| SF08 | 231.4 | 17.0 | 4.4 |
| SF09 | 230.1 | 18.9 | 4.4 |
| SF10 | 226.7 | 18.3 | 4.3 |
| SF11 | 121.3 (implant lost 09-07) | 18.6 | 0.6 |
| SF12 | 220.3 (contact failing 09-11) | 20.1 | 4.3 |

- **Size.** About 1,257 h of FM65 (1,244 h after `valid_until` clipping, change_log 2026-09-17). At 64 ch × 20 kHz × int16
  = 9.2 GB/h that is about 11.5 TB of raw data.
- **Most sessions are tiny.** 245 of 409 FM65 sessions are under 1 min (Resync/test blips, 1.5 h in total). The sessions
  of 4 h or more carry 97 % of the hours.
- **Gaps between consecutive FM65 sessions of at least 1 min (158 gaps):**

  | Gap | Count | Meaning |
  |---|---|---|
  | < 10 s | 13 | restart inside a continuous recording |
  | 10–60 s | 20 | restart inside a continuous recording |
  | 1–5 min | 3 | restart inside a continuous recording |
  | 5–30 min | 10 | |
  | 30 min–2 h | 104 | battery rounds |
  | > 2 h | 8 | |

- **Blocks.** Joining gaps under 5 min gives **128 blocks**: 30 of them join several sessions, the median is 11.3 h and
  the maximum 15.2 h. 119 blocks are 4 h or longer. The rhythm is a ~12 h night block plus one or two day blocks per
  logger per day.

## Why not concatenate everything

- **Scale.** An animal is about 2 TB. The pipeline writes a filtered copy of the same size plus the `.lfp`. That makes one
  Kilosort4 job of several days per shank, with no parallelism, and any failure restarts it. Earlier runs on this GPU
  took **9–13 h of wall time for one 8.5 h block** (`ephys_spikes_sort_runs_2026c.csv`, 2026-09-04/05; the raw data and
  the outputs shared one USB disk). The whole cohort is therefore on the order of **50 GPU-days serial** — it has to be
  split into independent jobs regardless.
- **Non-stationarity Kilosort cannot model here.**
  - Drift correction is off (`nblocks: 0` in `ephys/configs/kilosort4_wild.yaml`), because a 16-channel shank
    partition is too small to estimate drift.
  - The connector is re-mated at every battery round.
  - Probes were moved (units must never be merged across a move).
  - Firmware changed, implants declined (SF11, SF12), and there were noise regimes and field events (09-11 19:40:
    five females added).

  The longer the span, the more a drifting unit is split and the more converging neighbours are merged.
- **The lab's multi-day mode solves a different problem.** It was built for daily sessions of an hour or two (the
  "Day10–Day245" runs); 24/7 logging is about 10× more data per animal. It also needs at least two "session" folders.
  Without an explicit `server_root` it writes next to the sources — here that would be inside the read-only raw tree.
- **Matching is unusually easy here.** Adjacent blocks are separated by a battery round of about an hour. The probe
  barely moves in that time, so adjacent-block matching is the easy case, and a chain of adjacent matches gives
  day-scale identity. Its confidence falls with chain length, and the chain breaks at a probe move.

## Pipeline (per animal)

**0. Block table** (new `ephys/plan_blocks.py`)
- Input: the session index plus `cohorts/2026c.yaml`.
- Output: one row per block, with its member sessions, hours, probe-position epoch (from `ephys.probe_moves`, which
  is informational today) and `valid_until` clipping.
- FM64 blocks go to a separate list (de-glitch, then the template-width filter). FM62, the field-flagged sessions and
  the blips under 1 min are dropped. The table is written under `results/2026c/ephys_spikes/reports/`.

**1. Stage without copying** (FM65)
- Create a block folder on the working disk: one sub-folder per member session. Each sub-folder holds `amplifier.dat`
  as a **symlink** to the raw file, plus copies of `info.rhd`, `time.dat`, `CE_params.bin`, and the block XML.
- The pipeline concatenates the sub-folders and records MergePoints.
- This removes the byte-for-byte FM65 copy `stage_session.py` makes today (about 115 GB per night block).
- A raw folder cannot be handed to the pipeline directly. Its `digitalin.dat` is 4 B/sample, twice the 16-bit word
  that the pipeline's input validation (added 2026-09-24) expects, and `analogin.dat` is at 1250 Hz. The pipeline's
  own WILD support only reads *merged* folders that carry a `wild_preprocess_run.json`.
- Symlinks work unprivileged here through Python (Developer Mode). The link is the same raw file (first row
  identical) and reads at about 220 MB/s from the USB HDD. PowerShell `New-Item` needs admin.
- FM64 keeps the de-glitched copy.

**2. Sort each block** with PreprocessPipeline, current parameters:
- 500–8000 Hz, local CMR 20–200 µm, per-shank high-amplitude artifact removal;
- Kilosort4 per shank, then the fast postprocess.

Pin the pipeline commit in `sort_manifest.json`.

**3. LFP.** Keep every block's `.lfp` (1250 Hz, 1/16 of the raw size, ≈ 0.7 TB for the cohort). State scoring, SWR
and theta work run on it and need no spike sorting.

**4. Match across blocks**, per shank and within a probe-position epoch:
- Match each block to the next, then chain.
- First tool: UnitMatch (van Beest, Bimbard et al., *Nature Methods*; `github.com/EnnyvanBeest/UnitMatch`, Python port
  `UnitMatchPy`). It works on Kilosort output plus raw waveforms from two halves of each block.
- Fallback without the dependency: correlation of the mean template over the peak-channel neighbourhood, peak
  position, and ACG/rate similarity, assigned with the Hungarian algorithm.
- The acceptance threshold comes from a split-half ground truth (pilot P3).
- UnitMatch was validated on Neuropixels. How it does on 16-channel shanks is unknown; the pilot measures it.
- Output: one per-animal identity table (`block`, `shank`, `cluster_id` → `global_unit_id`, match score, chain length).

**5. Curation.** Phy only on the blocks the first analyses need. Do not curate 128 blocks × 4 shanks up front.

## Production on the server

- **Job.** One block per job: 16–32 CPU cores for preprocessing, 1 GPU for Kilosort4 (16-channel shanks use little
  VRAM, so 2–4 shank jobs can share a GPU), and CPU for the postprocess. The pipeline already has Slurm execution and
  automatic GPU selection.
- **Inputs.** The raw tree on BioHPC storage (`…\3rd_rat\WILD\SF7..SF12\<MAC>\<session>\`, reconciled 2026-09-23).
- **Outputs.** First to the workdir, then to storage `…\3rd_rat\analysis\{index,sort}`; the 2026-09-24 reconciliation
  note reserved those names.
- **What to keep.** Keep the Phy folders, `.lfp`, `session.mat`, MergePoints and the manifests. Keep a block's filtered
  `.dat` (≈ raw size, regenerable) only while that block is being curated.
- **Wall time.** Set from the throughput pilot P2 measures (hours of compute per hour of data) × 1,250 h ÷ the number of
  GPUs.

## Local pilot on this PC

- **Machine.** RTX 5070 Ti 16 GB, 24 threads, 128 GB RAM.
- **Raw input.** Read from `E:\3rd_rat_spikes` — here the WD Elements USB HDD, the 2026-09-20 byte-verified copy of the
  raw tree; the Red Pro master is not attached. Read-only.
- **Working disk.** `D:\3rd_rat_spikes\analysis` (SATA SSD, 1.5 TB free), with sub-folders `stage\` and `sort\`.
- **Pipeline checkout.** `D:\Documents\ayalab\PreprocessPipeline`, commit `eb3dad4` (2026-09-24). The cohort YAML's
  `C:/…` path does not exist here, so set `PREPROCESS_PIPELINE_ROOT`.
- **Logger.** SF07 throughout, because it is the logger with the verified channel map.

| Step | What | Why | Output |
|---|---|---|---|
| P0 | Build the `preprocess` env: `scripts/setup_env.py --platform windows --torch-channel cu130` (Python 3.11, spikeinterface 0.103.2, torch 2.9.1 for Blackwell sm_120). The old env is gone; `phy2` here is Python 3.7 and `spikeinterface_env` is broken (MKL). Then run `ephys/selftest.py`: its chanMap check is no longer skipped. | nothing runs without it | env + selftest PASS |
| P1 | Smoke test on a 30-min window of SF07 `15_20260902_082418.755`, **with our three runtime shims off**: KS4 partition `bad_channels` (fixed upstream 2026-09-10), vendored-KS4 scalar amplitude, Windows log lock. Also check the 2026-09-24 Intan input validation against a staged folder. | retire each shim upstream has fixed | shim verdicts |
| P2 | Throughput on **block B** = SF07 `15_20260902_082418.755` (09-02 08:24, 8.51 h, clean), linked staging + SSD. It was sorted on 2026-09-04 (545 min, 227 Kilosort4 units, 70 candidates), which gives a direct before/after comparison. Time every stage. | server job size and wall time | h compute / h data, per stage |
| P3 | **Split-half ground truth:** sort block B's two halves (0–4.25 h and 4.25–8.51 h) separately and match them. Same electrode, no gap, so every stable unit should find itself. | the matching threshold, precision and recall | ROC of the match score |
| P4 | **A real gap:** sort **block A** = SF07 `9_20260901_192912.215` + `10_20260901_234332.691` + `11_20260902_062241.295` (09-01 19:29 → 09-02 07:34, 12.1 h; joins gaps of 14 s and 9 s, so it also tests multi-session linked staging). Then match A ↔ B across the ~50 min battery round. | match rate across a real round | identity table for A–B |

- **Record check** (`/regime-aware-ephys`, 2026-09-28). Blocks A and B are FM65 and clean. Neither contains a probe
  advance, an ADC-lane piece or a field flag, and SF07 is not among the 09-01 night early stops. The 09-02 ~10:30 storm
  falls inside block B: that matters for interpretation, not for sorting. Re-run the skill's procedure (pull, incident
  log, QC requests, Notion) before starting the pilot.
- **Disk budget.** About 400 GB on `D:`: block A 111 GB + block B 78 GB of filtered `.dat`, and the halves 2 × 39 GB
  staged + 78 GB filtered.
- **GPU time.** About 30 h, if earlier throughput holds.

**New code**
- `ephys/plan_blocks.py`;
- `stage_session.py --link` and multi-session block staging;
- `ephys/match_units.py` (a UnitMatchPy wrapper plus the fallback).

**Ledger.** A `change_log/` entry with the measured numbers. Update `CLAUDE.md`'s ephys code map when the new
entry points exist.

## Open questions for the user

- The block definition joins gaps under 5 min. Should night + next-day blocks also be joined when no battery round
  separates them? None do today, but it is a choice to confirm.
- UnitMatchPy as a dependency, or the in-repo fallback only?
- Which blocks does the first science question need? That sets the curation order.
