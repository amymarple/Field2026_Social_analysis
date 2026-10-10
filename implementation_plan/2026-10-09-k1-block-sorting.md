# Cohort-3 spike sorting with Kilosort1 per block, lab settings, on BioHPC (2026-10-09)

This plan amends `2026-09-28-ephys-block-sorting-strategy.md`: the sorter is now **Kilosort1 (K1)** instead of
Kilosort4.
- The block idea and the cross-block matching stay.
- The evidence behind it is in `D:/Field2026_analysis_out/2026c/k1_sort_strategy_20261009/`:
  - `SOTA.md`: literature;
  - `RECORD_probe_handling.md`: field record;
  - `AUDIT_FABLE.md`: the Fable audit of the draft;
  - `DRAFT_STRATEGY.md`;
  - `k1_block_table_draft.csv`;
  - `k1_pilot_footprint_drift.csv`.
- The LFP movement tests are `results/2026c/ephys_spikes/reports/ephys_spikes_swr_session_drift_2026c.md` (commit
  c47f8e5).

## Decisions (user, 2026-10-09)

1. **Sorter: K1.** The user's colleague compared K1 and KS4 and prefers K1 for hippocampus; no KS4 comparison.
2. **Lab settings first** (neurocode `spikeSorting/KilosortWrapper/KilosortConfiguration.m`):
   - **All 64 channels in one K1 run.** Units can span shanks when an XML is not exact, so we do not partition by
     shank.
   - **`criterionNoiseChannels = 1e-5`:** every template is confined to the shank of its peak channel
     (`mainLoop/zeroOutKcoords.m`). PreprocessPipeline leaves this unset, its runner then writes 0.2 (20 % of
     templates may span shanks), and all pilot runs up to 2026-10-09 used 0.2.
   - **`whiteningRange = 64`:** whole-probe whitening, the lab value. The pipeline default has been 32 since 09-30.
   - **Kept as in the lab:** Nfilt = 8 × channels (512), Th [6 10 10], lam [12 40 40], `ForceMaxRAMforDat` 15e9.
3. **Sort unit = block:** the continuous recording of one logger between two handling events.
   - Files are joined across roll-overs (gap < 5 min).
   - Never join across a battery round, probe advance, firmware change or regime step.
   - The LFP shows SF09, SF10, SF07 (per block) and SF08 block 2 stable across rounds. Matching across rounds is
     therefore easy there, and joining across rounds is not needed.
4. **Trim the handling minutes** (first ~20 min of a post-round block) before sorting. K1 seeds its templates from the
   first ~1e4 isolated peaks of the file (`initialize/optimizePeaks.m`), and whitening uses the whole file.
5. **Cut contact-failure periods** out of blocks, and disconnect failing shanks per block (`connected = 0`). See
   "Per-block exclusions".
6. **Copy to the server's local `/workdir`** before sorting (user: OK). Blocks are built there.
7. **Both GPUs** (user, 2026-10-09). Jobs are pinned by `CUDA_VISIBLE_DEVICES`, because Slurm has
   `ConstrainDevices=no`.

## Code changes

- **`fullMPMU.m` patch (K1 final pass), applied to a copy of the pipeline's K1 in the tools dir.** The original grows
  `st3` with `cat` every batch and outgrows the 5e6-row `cProj` / `cProjPC` preallocation, so the final pass is
  quadratic in the spike count. In the SF12 day session, 2,935 of 5,357 s were final pass.
  - The patch preallocates and doubles; outputs must be identical.
  - Validated locally: the same 30-min window is sorted with the original and the patched copy, and spike_times,
    spike_clusters and amplitudes are compared byte for byte.
- **`ephys/run_k1_block.py`** (new): runs K1 on one block through PreprocessPipeline `execute_sorting_job`:
  - lab config;
  - `criterionNoiseChannels` set by overriding the runner default;
  - the patched K1 copy;
  - a chanMap from the final XML with the `linear` layout (SF09 stays `linear` until its XML is settled);
  - per-block disconnected channels;
  - MATLAB env (`MW_CUDA_FORWARD_COMPATIBILITY`, `CUDA_CACHE_MAXSIZE`, `PREPROCESS_RUNTIME_DIR`, the
    online-licensing wrapper on the server);
  - a run JSON.
- **`ephys/plan_blocks.py`** (new): the block table. Each block lists its member segments as (session, start
  sample, end sample). It applies:
  - clipping at `valid_until` and the paddock end 09-12 10:10 (missing from the draft table);
  - the handling trim;
  - the contact-failure cuts;
  - the per-block disconnected shanks;
  - the regime / matching-chain id from the LFP test.
- **`ephys/server/build_block_dat.py`** (new): writes `<block>.dat` from the staged sessions on `/workdir`, plus a
  MergePoints-like JSON with segment boundaries in block samples.
- **Storage:** a `sort` part in `ephys/server/copy_to_storage.sh` (an unknown part must refuse, not copy nothing).
  Jobs end through `run_then_store.sh`.

## Per-block exclusions (from the field record and the LFP test)

- **SF11:**
  - after `valid_until` 09-07 06:10;
  - from 09-02 19:08:52 the probe is not in CA1. Sort as tier 2 and never match across that step.
- **SF12:**
  - shank 1 off from 09-07 18:00;
  - shanks 1 and 4 off from 09-10 14:53:45;
  - all channels open 09-11 09:47:47 → ~18:03 (cut);
  - end at 23:30;
  - regimes → 09-06 08:09 | → 09-08 07:26 | after.
- **SF08:** matching-chain split at ~09-06 19:43 (slow settling before it).
- **SF10:** the last 3 sessions (09-10 21:00 → 09-11 19:22) sit 1–2 sites deeper. Flag them.

## Pilot (server, before production)

- **Blocks:**
  - SF10 09-02 day;
  - SF07 09-01/02 night (3 files joined);
  - SF09 09-06 night (largest post-round ripple dip);
  - SF08 09-09 night (advance inside the block);
  - one SF12 block with about 10 M spikes, for RAM and time.
- **Variants:** each block is sorted whole, as its first two-thirds and as its last two-thirds.
- **Score:** spike-level recovery and purity of overlap-defined true pairs, against the union of whole-block
  clusters. Not 1:1 cluster matching, because K1 oversplits.
- **SF10 day settings comparison:**
  - lab settings, 64 channels, whitening 64;
  - lab settings with `whiteningRange` 32;
  - per-shank partitions.
- **Concurrency:** all pilot sorts run together on both GPUs. This also tests the licence, I/O and concurrency.

## Production

- 124 FM65 blocks, with the 33 FM64 sessions after de-glitch staging.
- At most ~4 blocks in flight, limited by the RAID I/O.
- The queue deletes a block's staged data after VERIFY PASS on storage.
- Expected about 15–20 h with the `fullMPMU.m` patch.
