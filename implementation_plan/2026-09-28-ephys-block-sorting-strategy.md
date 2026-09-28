# Ephys preprocessing strategy for cohort 3 (2026c): sort per block, match units across blocks; local pilot (2026-09-28)

**Status.** PLAN, 2026-09-28. Pilot not started. Production and the pilot go to BioHPC `cbsuruiz01` (see
*Production on BioHPC*); the local-pilot section below stays as the fallback.

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

## Production on BioHPC (cbsuruiz01)

**The machine** (runbook `D:\FastenPC\BioHPC-server.md` and probe `server-profile.json`, both verified 2026-07-12/13;
a live re-probe is pending, see below):
- `cbsuruiz01.biohpc.cornell.edu`, user `hc997`, `ssh gpu` (key + 2FA cached about a week per IP).
- **2× RTX PRO 6000 Blackwell Max-Q, 96 GB each** (sm_120, driver 580.95 → CUDA 13.0 wheels OK).
- **No Slurm, no conda.** Jobs run directly under `nohup` (`D:\FastenPC\gpu-job.ps1 run`). The machine is shared;
  check `gpu-job.ps1 status` before launching.
- `module load python/3.12.7`; singularity/docker are available.
- `/workdir/hc997`: local scratch, 21 TB (4.6 TB free on 07-13), purged at 3 AM when the disk fills.
- `/home/hc997`: permanent, network-mounted.
- Storage NFS-mounted at `/fs/cbsuruizfs1/storage/hc997` (= `Q:\hc997` here). Cohort 3 raw:
  `…/SocialFieldRat2026/3rd_rat/WILD/SF7..SF12/<MAC>/<session>/`, the same layout as `E:\3rd_rat_spikes`.

**Environment** (one-time; everything in `/home/hc997` so the purge cannot touch it):
- `git clone` PreprocessPipeline and pin commit `eb3dad4` (2026-09-24).
- `python scripts/setup_uv.py` → a Python 3.11 `.venv` with torch 2.9.1 + CUDA 13.0, vendored Kilosort4 and Phy. uv
  fetches Python itself, so no conda is needed. It needs `uv`, `git` and GitHub access on the node.
- `git clone` this repo; `git pull` before each campaign.
- The pipeline's own GPU admission (start only when a GPU uses < 10 % VRAM; `src/execution/worker.py`) sits only on
  its GUI/worker path. Our driver calls `run_preprocess_session` directly and pins each worker with
  `CUDA_VISIBLE_DEVICES`, so another user's small job does not stall ours.

**Job runner.** Without Slurm this is our own queue: a new `ephys/server/run_block_queue.py`, one process per
worker, launched with `gpu-job.ps1 run`. Each worker loops:
1. **Claim** the next block from the block table with an atomic lock file. Blocks are resumable: a block is done when
   its `DONE.json` exists on storage, which survives the workdir purge.
2. **Stage** the member sessions by copying them from storage to `/workdir/hc997/ephys_2026c/stage/<block>/` (one
   sequential NFS read) and write the block XML.
   - This follows the runbook's rule: compute from `/workdir`, never against network storage. Preprocessing reads
     with many parallel workers, which NFS handles badly.
   - Symlink staging is only for the local pilot.
3. **Sort:** preprocess, then Kilosort4 per shank, then fast postprocess (the `run_sort_session.py` logic,
   generalised to multi-session blocks). Timings are recorded per stage.
4. **Archive to storage:** the Phy folders, `.lfp`, `session.mat`, MergePoints, manifests and log go to
   `…/3rd_rat/analysis/sort/<SFxx>/<block>/`, the name reserved in the 2026-09-24 reconciliation. Verify by size and
   hash, then write `DONE.json` (pipeline and repo commits, host, GPU, timings).
5. **Clean up:** delete the staged raw and the filtered `.dat` from `/workdir`. The `.dat` is regenerable; keep it only
   for blocks selected for curation.

- **Concurrency.** Start with 2 workers (one per GPU). Add a second worker per GPU only if the probe shows spare CPU
  and RAM: a 16-channel Kilosort4 job uses a few GB of VRAM, so CPU preprocessing is the likely bottleneck, not the
  96 GB GPUs.
- **Workdir budget.** About 250 GB per concurrent 12 h block (staged raw 110 + filtered 110 + LFP 7 + Kilosort
  scratch).
- **Storage growth.** About 10 GB per block (LFP + Phy), about 1.3 TB for the cohort.

**Code changes needed first:**
- a Linux machine block in `cohorts/2026c.yaml`, selected by `FIELD2026_MACHINE`. It holds `raw_data_roots.biohpc_node`
  with the `/fs/...` paths and a per-machine `ephys.analysis_root` (`/workdir/hc997/ephys_2026c`). `raw_data_roots.biohpc`
  holds the Windows `Q:/` view;
- `ephys/plan_blocks.py`;
- multi-session block staging;
- `ephys/server/run_block_queue.py`;
- an `ephys/server/README.md` runbook.

**Pilot on the server, not on this PC.** Production runs on the server's Linux stack, NFS and CPUs, so P1–P4 (same
blocks) run there. Throughput measured there is what sets the campaign's wall time; this PC keeps Phy curation.
P0 becomes the server env build.

**Live probe still to do.** Once `ssh gpu` works again (the 2FA cache had expired on 2026-09-28), a read-only probe
collects:
- CPU cores and RAM;
- current GPU and CPU load by other users;
- free `/workdir` and storage space;
- whether `uv`, `git` and GitHub are available;
- NFS read throughput (`dd` of 2 GB from one raw `amplifier.dat`).

Worker count and wall time are set from those numbers and P2.

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
