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
4. **Keep the handling minutes.** User, 2026-10-10, reversing the earlier trim: post-handling sleep recovery is
   studied, so the first ~20 min after a round stay in the sort. The block table flags them as `handling_until`
   (block start + 20 min; renamed `post_release_until`) for the analyses.
   - Open point for the Fable pilot audit: K1 seeds its templates from the first ~1e4 isolated peaks of the file
     (`initialize/optimizePeaks.m`), which are the handling minutes. The lab's sessions also start right after
     plugging in.
   - The pilot sorts were made with the 20-min trim; the whole-vs-part comparison does not depend on it.
   - The sleep session's answer (2026-10-10):
     - The sleep pipeline uses no sorted units, so this choice changes no sleep result.
     - Its recovery windows run from the post-round record start: 0–1 h, 1–3 h, 0–6 h, until the first NREM / REM,
       and 1 or 3 h of payback (`ephys/sleep_stability.py`, `sleep_perturb.py`, `sleep_explore_d.py`). It also uses
       the 3 h before a round.
     - Corrected by the user (field operator) the same day: Record Start = the release into the field (indoor tests are
       separate sessions < 1 min). The 3–17 min to the WISER house re-entry is free behaviour in the paddock, not
       handling. The flag is now `post_release_until` (block start + 20 min).
     - Units tracked across a round are not needed now, only for future neural recovery work (cross-block matching).
       Never across a probe move.
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
  - Validation: a byte-for-byte comparison of full runs is impossible, because K1 on GPU is not run-to-run
    deterministic (atomicAdd); two unpatched runs of the same 30-min window gave 82,708 vs 55,953 spikes. The
    evidence is the deterministic MATLAB test `ephys/matlab/test_fullmpmu_patch.m`: the original vs the patched
    accumulation on 1.26 M simulated spikes, PASS.
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

## Pilot outcome and the post-hoc amendment of the rule (2026-10-10)

Sorted:
- SF10 day, SF07 3-file night, SF09 09-06 night, SF08 09-09 night: whole twice, first 2/3, last 2/3.
- SF10 also with whitening 32 and per shank.
- SF12 heavy block once.

Found and fixed:
- `zeroOutKcoords.m`: an all-dead channel group disabled the shank confinement (test PASS).
- Per-shank `nNeigh` = min(16, channels).
- Nfilt is set by the lab formula, 8 x connected channels rounded down to 32. The runner had used 512 for every animal
  in full-width mode.

**The rule fixed before scoring fails** on SF10, SF07 and SF08 and passes on SF09. It is kept on the record as failed.

The Fable audit (`D:/Field2026_analysis_out/2026c/k1_sort_strategy_20261009/AUDIT_FABLE_PILOT.md`) shows the failure
is a span effect, not degradation of long blocks:
- **Comparator:** r1-vs-r2 is the null for identical data, not for a change of the sorted span.
- **Span effect:** on the same middle-third window and the same units, a part agrees with the whole at least as well
  as with the other part, on all four blocks.
- **No end effect:** hourly recovery is flat across 12 h, and does not concentrate by amplitude, shank or state.
- **Rare clusters:** the reference set admitted clusters < 0.1 Hz, which never agree.

**Amended rule (post hoc, documented as such):**
- a paired same-window test;
- the null is part-vs-part on the overlap, and a block passes if part-vs-whole >= that null - 0.05;
- B's cross-shank template is kept, or a symmetric union is used;
- reference units >= 0.1 Hz;
- an hourly check;
- an informative-baseline requirement.

All four blocks pass. **Decision: sort whole blocks.** The 6-8 h overlapping sub-blocks are rejected: x1.63-1.68
sorted hours, 149-249 extra seams, each a span change of the size the rule flagged.

Open, the user's call:
- **The single unconfined template.** criterionNoiseChannels 1e-5 leaves ceil(1e-5 x 512) = 1 template unconfined. It
  collects common-mode noise and also absorbs real units: 18 of 40 SF09 r2 reference units have > 20 % of their
  spikes in r1's template. Options: keep it as QC, or confine all templates with criterionNoiseChannels >= 1 (e.g.
  100), tested on SF09 with 2 runs.
- **Template seeding.** Optionally shuffle the order of the seeding peaks before `optimizePeaks` under the existing
  rng(1). The seeding otherwise comes from the first 5-15 min after release. The lab accepts that.

## Production

- 124 FM65 blocks, with the 33 FM64 sessions after de-glitch staging.
- At most ~4 blocks in flight, limited by the RAID I/O.
- The queue deletes a block's staged data after VERIFY PASS on storage.
- Expected about 15–20 h with the `fullMPMU.m` patch.
