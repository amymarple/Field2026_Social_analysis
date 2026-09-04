# Ephys (WILD neurologger) spike-sorting pipeline for the 3rd rat cohort — change log (2026-09-02)

Plan: [implementation_plan/2026-09-02-ephys-spike-sorting-pipeline.md](../implementation_plan/2026-09-02-ephys-spike-sorting-pipeline.md).
Data manifest: [data_manifests/2026-09-02-wild-ephys-cohort3.yaml](../data_manifests/2026-09-02-wild-ephys-cohort3.yaml).
Code: [`ephys/`](../ephys/README.md). Cohort registry: [cohorts/2026c.yaml](../cohorts/2026c.yaml). Direction key `ephys_spikes`.

## What was built

| piece | what it does |
|---|---|
| `cohorts/2026c.yaml` | registers the 3rd rat cohort (SF07–SF12) with an `ephys:` block: raw root `E:\3rd_rat_spikes`, animal→logger MAC map, firmware history (FM62 / FM64 / FM65), `clean_firmware_min: 65`, de-glitch defaults, probe config, PreprocessPipeline root |
| `ephys/wild_ce_params.py` | parses `CE_params.bin` (firmware @328, hw, RTC start, MAC, fs, Nch) per `Neurologger/Code/WILD_ReadHeader.m` |
| `ephys/build_session_index.py` | per-session index: firmware, start/end/duration, size, sidecar consistency, `deglitch_required` (firmware gate), and a MEASURED multi-window glitch probe (`ticks_per_s`, `tick_removal_frac`, `regime`, noise, bad-channel candidates). Writes `results/2026c/ephys_spikes/reports/ephys_spikes_session_index_2026c.{csv,md,json}` and mirrors `SESSION_INDEX.{csv,md}` to the data root |
| `ephys/deglitch_wild.py` | numerically identical port of field2026-sync `from-field/2026-09-01_deglitch_wild.py` (5-point median rule) with free output path, JSON manifest, before/after tick verification, optional sample window |
| `ephys/stage_session.py` | raw → off-repo clean working copy (`<OUT_ROOT>/2026c/ephys_stage/<SFxx>/<session>/`): de-glitch when firmware < 65 else verbatim copy; `info.rhd`, `CE_params.bin`, `time.dat`; Neuroscope XML with shank groups; `stage_manifest.json`; `--window-s` for test slices |
| `ephys/make_session_xml.py`, `ephys/configs/probes_2026c.yaml` | XML with per-shank channel groups + `skip` flags (placeholder mapping, see caveats) |
| `ephys/run_sort_session.py`, `ephys/configs/kilosort4_wild.yaml` | PreprocessPipeline driver: bandpass 500–8000 Hz, local CMR, per-shank high-amplitude artifact removal (5 σ, ±2 ms, linear), `.dat`/`.lfp` 1250 Hz, Kilosort4 per shank, postprocess → Phy; `sort_manifest.json` + `ephys_spikes_sort_runs_2026c.csv` |
| `ephys/probe_group_check.py` | data-side test of the assumed channel→shank grouping (LFP/HP correlation, ARI) |
| `ephys/selftest.py` | 18 offline checks (17 outside the pipeline env) |
| `E:\3rd_rat_spikes\CLAUDE.md` | on-disk note for agents: layout, `recovery.bin` purpose, firmware rule, caveats |
| conda env `preprocess` | pip-built (torch 2.9.1+cu128, spikeinterface 0.103.2, numpy 1.26.4, PreprocessPipeline installed `--no-deps`); the lab's `setup_env.py` conda solve could not finish on this PC (conda 4.12 classic solver, >20 min, 10 GB) |

## Definitions (all derived quantities)

| quantity | formula | plain text |
|---|---|---|
| `n_samples`, `duration_s` | `bytes(amplifier.dat)/(2·64)`, `n_samples/20000` | int16 samples per channel; seconds |
| `med5_c(t)` | `median(x_c[t−2..t+2])` (edge-replicated) | 5-point running median, ADC counts |
| `thr_c` | `max(10·1.4826·MAD_c, 500)`, `MAD_c = median|dev_c − median dev_c|`, `dev_c = x_c − med5_c` over 8 × 100k-sample blocks | per-channel replacement threshold (field defaults K = 10, FLOOR = 500 ADC) |
| glitch sample | `|dev_c(t)| > thr_c` → `x_c(t) := med5_c(t)` | the only modification made to the signal |
| `glitch_samples_per_s` | `Σ_c #glitch / duration` | replaced samples per second, summed over channels |
| tick | `|x(t) − (x(t−1)+x(t+1))/2| > 1200 ADC` | the defects-note impulse metric; `ticks_per_s` summed over channels |
| `tick_removal_frac` | `1 − ticks(after de-glitch of the window)/ticks(before)` | fraction of impulses the median rule removes |
| `regime` | `broadband` if `median_c std(x_c) > 2500 ADC`; `wide-impulse` if `ticks_per_s > 100` and `tick_removal_frac < 0.9`; else `normal` | whether the impulses are the 1–2-sample FM62/64 defect or something the median rule cannot fix |
| `measured_verdict` | glitchy > 10 ticks/s, clean < 1, else ambiguous; `+regime` suffix; session value = worst of 5 × 30-s windows | data-side evidence per session |
| `noise_uV` | `1.4826·median|hp|·0.195`, hp = 500–5000 Hz of the de-glitched window | robust spike-band noise, µV, RELATIVE (0.195 µV/ADC is the Intan default; the WILD header carries no scale) |
| bad-channel candidate | `noise_uV < 3` or `> 4·median` or `raw_std < 0.25·median` | advisory dead/broken list |
| ARI | adjusted Rand index between assumed shank labels and average-linkage clusters of `1 − r_LFP` | 1 = identical partition, ~0 = chance |

## Verification

- `python ephys/selftest.py`: 17/17 in base Python, **18/18 in the `preprocess` env** (adds the check that
  PreprocessPipeline reads the generated XML into a 4-shank chanMap with 63 connected channels). Synthetic
  de-glitch: 100 % of 20,119 injected glitches replaced, 0.65 % of spike-peak samples altered, ticks 54,706 → 0.
- **Port fidelity**: staging SF10 `5_20260901_054403.494` (the field validation session) reproduced the field
  numbers exactly — 108,584 samples replaced (0.17 %), ticks 23,679 → 64 (99.7 %).
- Other staged examples: SF8 `0_20260831_190133.486` (45 s, FM64) ticks 11,112 → 0; SF8
  `2_20260901_002327.839` window 3600 + 600 s (night, FM64) ticks 639,597 → 1; SF12 `1_20260831_071033.005`
  (FM62 morning-round record) ticks 5.0 M → 2.9 M (43 % — see finding 3).
- **Session index** (39 sessions, 60.8 h, SF08–SF12; SF07 not offloaded; 5 × 30-s probe windows per file):
  13 × FM62 (08-31 07:0x–08:31 starts), 26 × FM64 (08-31 19:0x → 09-01 05:4x). Every session measures
  glitchy (worst-window ticks/s 97–55,000 summed over 64 ch), so the firmware rule and the data agree.
  31 sessions are `normal` in all five windows (tick removal ≥ 0.94, all 26 FM64 sessions among them);
  8 sessions, all FM62 08-31 daytime, have at least one `broadband` (6) or `wide-impulse` (2) window
  (finding 3).
- **End-to-end sort** on SF10 `5_20260901_054403.494` (50 s of data, FM64, staged clean copy, per-shank
  Kilosort4 on the RTX 5070 Ti, then postprocess → Phy): completed in 4.5 min wall time (three pipeline bugs
  worked around first, finding 5). Per shank, Kilosort4 units → final units after dedup / merge / autosplit /
  noise labelling: shank 1 16 → 19 (4 noise), shank 2 16 → 18 (7), shank 3 14 → 17 (4), shank 4 14 → 15 (7);
  spikes 3,865 / 5,215 / 2,724 / 2,852. Channels 32, 34, 60, 62 excluded (auto-reject). Outputs:
  `G:\Field2026_analysis_out\2026c\ephys_sort\SF10\5_20260901_054403.494\Kilosort4_2026-09-02_184415_probe1_shank{1..4}[_spi]`,
  `sort_manifest.json`, row 1 of `results/2026c/ephys_spikes/reports/ephys_spikes_sort_runs_2026c.csv`. These
  counts are a pipeline smoke test on 50 s of data, not a unit yield claim.
- **Realistic slice**: SF8 `2_20260901_002327.839` window 3600 + 600 s (10 min, night 01:23, FM64, staged as
  `…__w3600s_600s`), per-shank Kilosort4 + postprocess: 16.7 min wall time; 3 high-amplitude artifacts
  removed; Kilosort4 units → final units (noise-labelled): shank 1 38 → 62 (29), shank 2 177 → 169 (47),
  shank 3 96 → 91 (44), shank 4 93 → 92 (39); spikes 86 k / 94 k / 73 k / 103 k. Channel 32 excluded. Row 2 of
  the runs CSV. The high unit counts per 16-channel shank (with the placeholder geometry and 10 min of data)
  are a curation starting point in Phy, not a yield claim.
- Full-session sorting (multi-hour, ~50 GB) has NOT been run yet; the driver is exercised on ≤ 10-min inputs.

## Findings that shape interpretation

1. **The de-glitch port is exact** (bullet above) and the FM64 single-sample defect is removable at ≥ 99.7 %.
2. **Placeholder probe mapping is not supported by the data.** `probe_group_check.py` on SF8 (40 s, FM64):
   ARI = −0.00, LFP r within = 0.76 vs between = 0.76 — no 16-channel block structure at all. The channel→shank
   map must come from the headstage-adapter pinout; until then units are valid per unit but no shank/depth
   claim is allowed (`probes_2026c.yaml` `verified: false`).
3. **A second, different noise regime exists on FM62 daytime data (8 of the 13 FM62 sessions).** Worst-window
   values: SF8 `0_20260831_070148.859` (35,000 ticks/s, removal 0.18, std 5,178 ADC), SF8
   `2_20260831_071541.642` (broadband in 4/5 windows, removal 0.40), SF8 `4_20260831_083120.285` (one
   wide-impulse window, removal 0.41), SF9 `0_20260831_070319.133` and `1_20260831_071357.350` (removal
   0.22–0.24), SF11 `0_20260831_072408.414` (55,000 ticks/s, std 5,302, channels 32–63 flat), SF12
   `1_20260831_071033.005` and `2_20260831_071845.540` (broadband windows, removal 0.23–0.39). These show
   2–7-sample impulses and raw std 4–8 × the night level; the 5-point median cannot and should not remove them.
   They are the morning battery-round records (rats in hand) and the 08-31 daytime troubleshooting period; the
   regime is intermittent within a session (`regime_by_window`), which is why the probe samples five windows.
   Treat as QC-fail candidates; the 26 FM64 sessions and 5 FM62 sessions are `normal` in every window.
4. **Dead / broken channels are stable per animal** (index `bad_channel_candidates`): SF8 ch 32; SF9 ch 2, 4,
   32, 36, 54, 56, 58, 62 (+52, 60 on short records) — consistent with the Notion "50 channels"; SF10 ch 32,
   34 (+2, 6, 56, 60–63 on some records); SF11 ch 32, 56, 60 on the 09-01 records. Copy the stable ones into
   `probes_2026c.yaml` after review.
5. **Two PreprocessPipeline bugs** (lab checkout left untouched; worked around in the driver, proposed fixes in
   `ephys/patches/`): Kilosort4 + shank partition passes full-width `bad_channels` to a channel subset
   (`IndexError: Channel '16' was not in probe['chanMap']`); the vendored KS4 amplitude feature crashes on a
   one-spike group (`TypeError: expected np.ndarray (got numpy.float64)`).

## Addendum 2026-09-03 — SF07 offload, FM65 evaluation, timestamp QC

- **SF07 offloaded** (17 sessions, 08-31 18:58 → 09-02 18:12; logger `D0DBEFEF3111`; slots 0–7 FM64, 8–16 FM65).
  Index regenerated: **56 sessions, 104.8 h** (13 FM62 / 34 FM64 / 9 FM65). New `ephys/offload_qc_report.py` renders
  `results/2026c/ephys_spikes/reports/ephys_spikes_offload_qc_2026c.{md,csv}` (timeline continuity, RTC/folder agreement,
  sidecars, FM-grouped glitch statistics, BLE field-PC-time fit verdicts).
- **FM65 verdict: CLEAN.** Every FM65 session measures ≤ 0.07 ticks/s in its worst of 5 windows (SF07 FM64 controls: 0.5–21/s;
  SF08–SF12 FM64: 100–2,000/s). Spike-band noise 8–16 µV on both firmwares (state-dependent, no firmware effect).
- **Device-side timestamps intact on 56/56**: `time.dat` gapless (10 blocks + ends per file), RTC start = folder name, header
  MAC = folder MAC, 34 back-to-back restarts with gaps 6.5–105 s and no overlap (ADC clock vs RTC < 0.1 %).
- **Timestamp storage verified by reading it**: RTC at `CE_params.bin` bytes 332–338; `time.dat` int32 counter; field-PC time
  as one packed word in `analogin.dat` lanes 14/15 (bits 0–19 ms-of-day mod 2²⁰, bits 20–31 BLE delay) that changes only on a
  console sync exchange, **one per 5.0 s while connected** (SF07 `2_20260901_002100.939`: 18 updates in 73 s at 5.0-s spacing).
  Hence a 10–30-s touch yields 2–6 anchors regardless of the 20 kHz rate.
- **Field-PC-time fits (`WILD_generate_pc_time.py`, all 56 sessions)**, long sessions ≥ 1 h: OK 11 (55 h; drift −98…+109 ppm,
  residual 7–43 ms); < 10 anchors 6 (15.5 h); anchors inconsistent 3 (14 h: SF07 `10_20260901_234332.691` −17,495 ppm ≈ 7 min
  while its ADC and RTC agree to 8 s, SF11 `2_20260901_002906.850` −5,725 ppm, SF10 `2_20260831_195630.973` +300 ppm);
  corrupt sync lanes 5 (17 h; the 8/31 daytime FM62 sessions decode 10⁵–10⁶ "anchors" = noise). The field PC's drift is
  measured linear (user), so the three inconsistent sessions point to a Resync during recording or a second console host;
  asked the field side via `field2026-sync/tasks/2026-09-03_check-cohort3-anchor-inconsistencies.md`.
- **Lost intervals** on the night of 9/1: SF10 03:07, SF11 03:22, SF08 03:32, SF09 03:34, SF12 04:57 early stops (battery).
- **Lab→field hand-off pushed** to `field2026-sync` (`dec68c8` + `1cb9438`, origin/main): `from-lab/2026-09-03_cohort3-offload-qc.md`
  + full report + timeline + index CSVs, the anchor-inconsistency task, and
  `tasks/2026-09-03_field-commit-sync-logs-for-cohort3.md` asking the field PC agent to commit the sync log, PC-drift CSV,
  console `sync_results`/`ble_messages` window (08-31 → 09-02), telemetry history, incident log and LED-sync files into
  `from-field/` so the lab side can cross-check the fits itself.
- **RESOLVED (2026-09-03, `ephys/pc_time_chain.py`): the three "inconsistent" sessions and the < 10-anchor sessions were
  artefacts of the reference generator, not clock problems.** Comparing every embedded anchor with the logger's own RTC
  start showed (a) a **day-wrap bug**: the field-PC ms-of-day wraps at 86,400,000 at local midnight and
  86,400,000 mod 2²⁰ = 416,768 ms, so every post-midnight anchor of a session that crosses midnight sits exactly 416.77 s
  "early" (−413.6 … −417.5 s measured on SF07/SF09/SF11 end clusters; −416.77 s / 6.65 h = −17,400 ppm = the SF07 session-10
  "jump"); the generator either discards those anchors or fits through them; (b) a **delay-word bias**: adding the 12-bit
  delay (700–2,600 ms) makes anchors disagree with delay-0 anchors of the same link by that amount, while the raw pc_ms agrees
  with the RTC to ±0.7 s in every case. With both handled and the user's round protocol encoded (a session without an end
  cluster borrows the next session's start cluster through the RTC, gaps ≤ 300 s): long sessions ≥ 1 h → **OK-native 6
  (27.3 h, drift −16 … −27 ppm, residual 6–50 ms), OK-chained 7 (39.0 h, drift −19 … −25 ppm except SF07 #6 +142 ± 97),
  start-cluster-only 7 (18.7 h; offset known to BLE precision, drift assumed from the logger's other sessions),
  corrupt 5 (16.7 h, the 8/31 daytime FM62 block)**. Adjacent sessions agree across a stop→start to within ±20 ms
  (`start_vs_prev_ms`), far inside the 1.5-s RTC budget, so borrowed anchors are practically native quality; the only
  larger jumps (SF07 #7→#8 −1.8 s, #11→#12 +1.3 s) sit at Resync rounds, as expected. Logger crystals run a uniform
  ≈ −21 ppm (−1.8 s/day) against the field PC. `--write-pc-time` regenerates `pc_time.dat` (console format) from these
  fits; the generator's `pc_time.dat` files are superseded and should not be used.
- **Field-side cross-check (field2026-sync `4ea3d37`, pulled 2026-09-03):** the field agent committed the console
  `ble_messages` export (08-31 → 09-02), a decoded table of every live-sync word sent, PC-side Rec Start/Stop marks,
  telemetry, the incident log and the LED-sync files. Reconciliation: the host sends **ms since the top of the hour**;
  the logger adds its RTC hour before packing, so the card holds **ms-of-day mod 2²⁰** — card and host words agree to
  0.1–0.8 s at every anchor checked (SF09 3_, SF07 2_/10_, SF11 1_), including both ends of SF07 10_. PC-side elapsed
  vs card sample count on 24 matched sessions > 10 min: median +0.4 s (≈ +22 ppm, the crystal), max 2.7 s; SF07 10_ =
  23,940.0 s (PC) vs 23,940.5 s (card) → no missing/extra samples, the "7 min" was purely the day-wrap decode. The
  −2.0 … −2.3 s outliers (SF07 6_, SF08 4_, SF09 1_, SF10 1_, SF12 2_) coincide with the documented w32time steps
  (8/31 09:00 +3.4 s, 9/1 13:09 +2.5 s) inside those sessions. No Resync and no second host in any window (0 `0x8A`
  frames 08-31 → 09-02). 63 PC-side session marks have no card counterpart yet = sessions recorded after the last
  offload (SF08–SF12 from 9/1 07:5x on, SF07 from 9/2 19:00). The field protocol now mandates ≥ 60 s per touch.
- **Derived-data root moved to the data drive (user decision 2026-09-03):** `E:\3rd_rat_spikes\analysis\` is now
  `ephys.analysis_root` for cohort `2026c` (`index/`, `pc_time/`, `stage/`, `sort/`, `tools/`; README inside). `_common`
  resolves stage/sort/tools roots from it, the index mirror moved from the data root into `analysis/index/`, and the
  corrected `pc_time.dat` + `pc_time_fit.json` were written for every usable session by `pc_time_chain.py --write-pc-time`.
  Rule restated: nothing is ever written into a raw session folder or next to `recovery.bin`.
- **Incident:** the G: artifact drive (`FIELD2026_ANALYSIS_OUT_ROOT`) and F: dropped off the analysis PC at ~23:50 EDT on
  09-02 (Get-Volume: G absent, F/H/I/J/K size 0). Staged copies, sort outputs and the patched Kilosort4 copy live on G: and
  are unreachable until it is remounted. The 56 PC-time fits were written to a C: temp dir and are not yet parked
  (destination pending the user's decision); the report was rendered from that temp copy. Two failed batch attempts had
  written summary JPGs into the raw session folders (the script's default); all 55 were removed, raw tree verified clean.
- Definitions added: `tick_removal_frac`, `regime`, `regime_by_window` (index); anchors kept/found, drift ppm,
  residual ms, CORRUPT SYNC LANES (> 10× the anchors possible at the 5-s cadence), BAD FIT (≥ 1 h with |drift| > 200 ppm
  or residual > 150 ms) — see the `offload_qc_report.py` docstring.

## Addendum 2026-09-03 (b) — channel map: FM65 did NOT fix it; verified XML for SF07, provisional for the other 4×16, data-derived for SF09

Inputs: the maker's repair tool and map (`D:\Downloads\correct_intan_dat_channel_order.py`, `v57_channel_mapping.csv`,
vendored as `ephys/vendor/…` and `ephys/configs/wild_ce64_channel_map_v57.csv`), the lab probe maps
(`ProbeMaps/Neuronexus`: A4x16-Lin-5mm-50s-300 for SF07/08/10/11/12, A5x12_16-Buz_lin for SF09 per the Notion
"4*16" / "5*12" column), and the author's note that the console re-orders raw slots on download so a raw rotation
becomes a conjugated permutation (exactly what the vendor tool encodes).

Method (`ephys/probe_map_check.py`): spike-triggered co-activation matrix on a 600-s de-glitched window
(events = −5 σ minima that stay below −3 σ for ≥ 3 samples, so a substituted single sample cannot trigger;
local events only; co-amplitude = 3-sample mean at the partner's minimum, σ units). Map-independent evidence =
each column's strongest partner and the connected components of pairs ≥ 2.5 σ. Candidates = 4 connector
orientations of the ProbeMaps XML (v1 raw pin grid, v2 rot180, v3 fliplr, v4 flipud; v1/v2 = the ProbeMaps
"version1/2", confirmed identical to `make_xml.m`'s normal/flipped) × raw-slot rotations −4…+4 per bank,
conjugated through the CE64 export map. Scores: `nn_agree` (strongest partner within 2 sites on the same shank)
and `pair_agree` (strong pairs on the same shank). Plain LFP/HP correlation was NOT discriminative (common
mode dominates, r ≈ 0.95 everywhere on SF07).

Findings:
1. **SF07 (4×16), FM65 sessions 15 and 10 and FM64 session 2**: winner = **normal XML (v1_raw), bank-0 rotation
   +1, bank-1 rotation 0** — `nn_agree` 0.78 (bank 0 = 1.00 with n = 7, bank 1 = 0.69 with n = 16) on session 15,
   0.62 on session 10, 0.32 on the glitchy FM64 session; identity (no rotation) 0.57 / 0.50 / 0.23; the reversed
   XML and the raw-map candidates ≤ 0.48. **So FM65 did not fix the channel order: bank 0 is still rotated by one
   raw slot, exactly the FM57 fault the vendor tool describes.** Bank 1 is in Intan order (the console map works).
2. **SF09 (5×12), FM64 session 3**: 74 strong pairs, 62 event-bearing channels — the richest data — yet **no
   orientation × rotation of the A5x12 XML exceeds 0.61 same-shank pairs** (a correct map gives ≈ 0.9+); data
   clusters straddle XML groups even within bank 0. Either the probe's pin table differs from the ProbeMaps
   A5x12_16-Buz_lin XML or this logger has a different fault. Delivered a **data-derived XML** (clusters as
   shanks, spectral order within each: 7 groups, 35 channels; 29 channels unassigned → skip) for per-shank
   sorting only. To resolve: the actual NeuroNexus package/pin sheet for SF09's probe, or an FM65 re-scan.
3. **SF08/SF10/SF11/SF12 (4×16, FM64 only so far)**: their FM64 windows carry the substitution defect and yield
   few clean pairs (SF08: 17 pairs, no clear winner; SF10: 18 pairs, top candidates v4_flipud rot +1/0 and
   v1_raw rot +1/+1 within noise of each other, `nn_agree` ≤ 0.36; SF11: 12 pairs, ≤ 0.38; SF12: 29 pairs but
   `nn_agree` ≤ 0.12 — the substitution defect dominates). They inherit SF07's mapping **provisionally** (the
   rotation is a firmware property shared by all loggers; the connector orientation is per implant and
   unconfirmed). Re-run the scan on each logger's first FM65 session; the cached matrices for these FM64
   windows are kept under `analysis/index/probe_map_cache/`.

Deliverables: `ephys/make_probe_xml.py` (ProbeMaps XML + orientation + rotations → XML in exported-column
numbering; never combine with the vendor data repair), `ephys/configs/xml/SF07_A4x16-Lin_v1raw_rot+1_0.xml`
(also used by SF08/10/11/12), `ephys/configs/xml/SF09_data_derived_3_20260831_190834.640.xml`,
`probes_2026c.yaml` re-keyed to `xml:` per animal with `verified` / `mapping_source`,
`make_session_xml.py` loads a per-animal XML (skips merged into rejects), cached co-activation matrices under
`E:\3rd_rat_spikes\analysis\index\probe_map_cache\`.

Definitions: event = local minimum of the median-referenced 500–5000 Hz signal below −5 σ_i with the two
neighbouring samples below −3 σ_i, at most 8 channels beyond 3 σ in the ±0.3-ms window; A[i,j] = median over i's
events of −mean(3 samples around j's minimum in the window)/σ_j; strong pair = ½(A[i,j]+A[j,i]) ≥ 2.5;
`nn_agree` = fraction of event-bearing channels whose argmax partner is on the same shank within 2 sites;
`pair_agree` = fraction of strong pairs on the same shank; rotation r of bank b in export space =
`restored_source_columns(bank=b, acquisition_rotation=r)` of the vendor tool.

## Addendum 2026-09-03 (evening) — SF08/SF09/SF10 offload, field-PC clock steps located, chain fit v2

- **Offload verified** for SF08 (18 of 19 card records; slot 10, a few-second record, not downloaded), SF09 (17/17), SF10
  (16/16): card-frame sums 99.969–99.974 % of the card listings (the same ~6.5 MB/record container overhead as SF07),
  76 folders size-consistent, 1.54 TB; every session with a field-PC mark matches its Rec Start→Stop span within +0.1…+0.9 s.
  SF10 `2_20260901_125856.163` + `3_20260901_171620.845` together equal one PC span (a stop→start the PC never logged).
- **Chain fit v2** (`pc_time_chain.py`): two-cluster native fit (offset from the start cluster, slope from the end cluster,
  robust line seeded on it), end clusters of 2 anchors accepted, discontinuity detector against the logger's median drift.
  Cohort-wide ≥ 1 h: native 34 (165 h), chained 1, start-only 9 (30 h), corrupt 5 (17 h; 8/31 daytime FM62).
- **Field-PC clock steps found and modelled.** Three FM64 sessions on three loggers (SF07 `6_`, SF09 `2_`, SF10 `2_`,
  9/1 12:54–17:16) showed device time lagging PC time by +2.5…+2.7 s after an event, and every session spanning the
  8/31 daytime showed the card 2.0–2.3 s "shorter" than the PC span. The field PC's 1-Hz **LED-sync log**
  (`from-field/2026-09-03_ledsync_*.txt`) locates the cause: the pulse scheduled 08-31 09:00:17 was sent 2,385.6 ms late
  and seconds :18–:19 were skipped (a +2.386-s forward step), and on 09-01 13:09:11–13 three scheduled seconds were skipped
  (≈ +2.6 s). So **the field PC runs SLOW (~2.1 s/day, the loggers' uniform −21…−27 ppm "drift" is that rate; the field
  log's "PC fast" label is inverted) and w32time stepped it FORWARD**; no samples were lost on any card. The steps are
  registered in `cohorts/2026c.yaml` (`ephys.field_pc_clock_steps`); the fit subtracts them and `pc_time.dat`/`pc_time_fit.json`
  add them back (`field_pc_clock_steps_inside`), because video, WISER and LED timestamps carry the same jump.
  The QC report's card-vs-PC-span check now names a known step instead of claiming sample loss.

## Addendum 2026-09-03 (late) — full index after the SF08/09/10 offload, coverage tables, integrity scan

- `build_session_index.py --workers 8` (ProcessPool over sessions; 113 sessions in ~25 min instead of ~2 h).
  Index: **113 sessions, 252.9 h** (13 FM62 / 54 FM64 / 46 FM65; SF11/SF12 still copying, their 9/1+ rows partial).
- **FM65 verdict per logger (worst-window ticks/s vs the same logger's FM64 median):** SF10 7.4 vs 1,403; SF8 2.5 vs
  1,217; SF9 2.7 vs 438; SF7 0.1 vs 13 → CLEAN; the residual 1–7/s on the noisier loggers are ordinary fast transients
  (not removed by the median rule, unlike the defect). `offload_qc_report.py` now uses this relative rule.
- **Timestamps, sessions ≥ 1 h (chain v2 + modelled steps):** OK-native 39 (180.7 h), OK-chained 4 (16.9 h),
  step-modelled 3 (12.8 h), start-only 11 (41.1 h), corrupt 5 (16.7 h). `pc_time.dat` + `pc_time_fit.json` written for
  97 sessions under `E:\3rd_rat_spikes\analysis\pc_time\` (steps included; `field_pc_clock_steps_inside` in the JSON).
- New `ephys/coverage_tables.py`: hourly minutes per logger per day (`ephys_spikes_hourly_coverage_2026c.{csv,md}`),
  per-second coverage per day (`ephys_spikes_coverage_1s_2026c_<date>.csv`, firmware code per logger per local second),
  raster figure (`ephys_spikes_coverage_raster_2026c.png`); all mirrored to `<analysis_root>/index/`.
- New `ephys/integrity_scan.py` (full 64-KiB block hashing + sampled channel tests): the 9 FM65 SF07 sessions (202 GB)
  have 0 repeated blocks, 0 blocks shared across session boundaries, no rail/flat/stuck/duplicated channels, no
  in-session channel-identity change.
- Offload verification SF08/09/10 against the card listings: 99.969–99.974 % (fixed ~6.5 MB/record overhead); SF08 slot 10
  (a few-second round-time test record, ~10–17 MB) was the only record not downloaded. SF12 `1_20260901_131223.398` is
  183 s longer than the PC's Stop mark because the 17:16:07 Stop did not take effect at the logger (stopped 17:19:10);
  no data lost.
- Field side: standing requests task (`tasks/2026-09-03_field-standing-requests-cohort3.md`, pushed): per-offload session
  marks + LED-sync log + drift log; 1-minute touches confirmed (median 15/17 anchors at start/stop vs 9/4 before); drift-log
  sign to be corrected (PC runs slow). **Field response 15:20 (commit `aaf055c`)**: routine adopted; marks refreshed to
  123 sessions (latest Stop 09-03 08:09); LED log 09-03 00:00–14:59 (no clock step; one 188-s pulser pause 13:55:57);
  drift-log sign confirmed inverted in labels only (`pc_drift_check.ps1` computes NTP − PC; PC slow +91 ms/h); no Resync
  ever reached a recording logger (71 RTC writes since 09-02 all on idle loggers; command id 0x8B); no battery pulled
  without Stop; SF07's 09-03 00:16 session auto-stopped by the logger at ~04:16:40 (3.40 V, FM65 low-battery
  Stop-and-Save). Lab cross-check: every SF08/09/10 session through 09-03 06:00 within +0.0…+0.8 s of its PC span.

## Addendum 2026-09-03 (final for this offload) — all six loggers through 09-03 morning

- SF11 (18 of 19 card records; slot 5, a few-second round-time record, not downloaded) and SF12 (16/16) offloads
  verified: 99.971 % / 99.976 % of the card listings, all folders consistent; cards released for formatting.
- **Index: 141 sessions** (13 FM62 / 56 FM64 / 72 FM65), all six loggers 08-31 07:0x → 09-03 ~06:50. FM65 = 188.5 h;
  per-logger FM65 worst-window ticks/s vs the logger's FM64 median (sessions ≥ 120 s): SF7 0.1/13, SF8 2.5/1,217,
  SF9 2.7/438, SF10 7.4/1,403, SF11 (long sessions) ≪ 319, SF12 1.4/572 → CLEAN. The one FM65 record measuring
  35.7 ticks/s is SF11 `10_20260902_075255.597`, a 4.5-s round-time test record (rats in hand); the report now ignores
  records < 120 s for the firmware verdict.
- **Timestamps, sessions ≥ 1 h:** OK-native 47 (236.7 h), chained 4 (16.9 h), step-modelled 3 (12.8 h), start-only
  10 (30.8 h), corrupt 5 (16.7 h, the 08-31 daytime FM62 block). Logger drifts vs the field PC: SF07 −21, SF08 −20,
  SF09 −27, SF10 −24, SF11 −27, SF12 −20 ppm. `pc_time.dat` + fit JSON written for 125 sessions.
- **Coverage** (hourly + per-second CSV per day + raster, mirrored to `E:\3rd_rat_spikes\analysis\index\`): 09-01
  112.1 logger-hours (six loggers), 09-02 128.1, 09-03 34.1 (cards pulled ~06:50); from 09-01 19:xx every logger is on
  FM65 with all six recording continuously except the round gaps (07–08 and 18–19 local) and SF07's 09-02 18:12 pull.
- Field side (commit `aaf055c`): routine adopted, no Resync on a recording logger, no pull without Stop, drift-log sign
  corrected in the docs; acknowledged in `tasks/done/…standing-requests…` (`0851677`).

## Caveats / not done

- Probe channel→shank mapping unverified (finding 2). µV scale relative. Cross-modal time alignment unverified
  until `WILD_generate_pc_time.py` fits pass (run on the RAW folders; staged copies omit `analogin.dat`).
- The 30-s probe windows are samples; a regime confined to an unsampled stretch is missed (5 windows reduce
  but do not remove this).
- SF07 has no offloaded sessions yet; FM65 sessions (copied 2026-09-02 onward) are unevaluated — re-run the
  index when they land; their `measured_verdict` is the evidence that FM65 is clean.
- No scientific claim is made; `analyses/registry.yaml` unchanged (no question entry yet).

## Addendum 2026-09-04 — second offload round (SF7/SF8/SF9/SF10 + SF11/SF12 through 09-03 ~16:30), foreign-logger filter

- **Offload size checks (card listing vs E:):** SF7 5/5 records, SF8 4/4, SF9 3/3 (99.978 %), SF10 3/3 (99.976 %) — all
  byte-complete, cards released. SF11 (4 folders, 82,501.945 MB) and SF12 (3 folders, 89,774.120 MB) copied; their card
  listings are still to be compared (expected card total ≈ E: total / 0.9998).
- **Index: 163 sessions, 373.7 h** (13 FM62 / 56 FM64 / 94 FM65; FM65 = 240.8 h). Daily logger-hours:
  2026-08-31 47.2, 2026-09-01 112.1, 2026-09-02 133.1, 2026-09-03 81.3. FM65 verdict unchanged: CLEAN on all six loggers.
- **Foreign-logger folders are now filtered** (`_common.iter_raw_sessions(..., cohort=)`): a MAC folder under an animal that
  is not the animal's registered logger (`ephys.loggers[*].mac`) is skipped by every script and listed under "Foreign
  logger folders (ignored)" in the index MD. Trigger: `SF11/2AD87D50B0FA/0_20260902_130113.385` (36 s, another
  logger's card) had produced a false OVERLAP + false FM65-glitchy flag. Convention: move such folders to
  `<root>/_other_loggers/<MAC>/` (top-level `_`-prefixed folders are skipped).
- **Channel-local impulses are no longer reported as FIRMWARE CLAIM VIOLATED.** The problems list applies the same
  top-2-channel-share ≥ 0.7 rule as the verdict paragraph and names the channels: SF8 `2_20260903_075352.907`
  (14.0 ticks/s on ch 34 + 1) and SF12 `3_20260903_080924.473` (11.7 ticks/s on ch 2 + 29) → flaky contacts /
  bad channels, to be added to `reject_channels` in `ephys/configs/probes_2026c.yaml` before sorting (not done here).
- **Field-PC clock step 2026-09-03 13:56:01 (+1.35 s, PC bugcheck reboot)** is registered in `cohorts/2026c.yaml` and
  modelled: the four sessions spanning it fit with their usual drifts once the step is subtracted — SF08 2_ −20.1 ppm
  (rms 17 ms), SF10 2_ −24.1 (7.9 ms), SF11 3_ −28.0 (21.5 ms), SF12 3_ −19.6 (8.5 ms) — vs the pre-step long-term
  drifts SF08 −20 / SF10 −24 / SF11 −27 / SF12 −20 ppm. Still marked PROVISIONAL until the field drift log confirms
  the size. `field_pc_outages` records the 09-01 04:20 and 09-03 13:56 reboots (PC-side modality gaps, not steps).
- **Timestamps (sessions ≥ 1 h):** OK-native 48 (241.9 h), step-modelled 7 (46.4 h), chained 4 (16.9 h), start-only 12
  (43.5 h: session ends before a card pull — SF07 4_, SF09 2_, SF08 3_ this round), corrupt 5 (16.7 h, the 08-31
  daytime FM62 block). `pc_time.dat` + fit JSON rewritten for 143 sessions under `E:/3rd_rat_spikes/analysis/pc_time/`.
- Kilosort4 batch sorting was stopped at the user's request (forked to another session); `unit_yield_report.py`
  stays as the reporting tool (hippocampal unit rule: count units with rate < 3 Hz).

## Addendum 2026-09-04 — Kilosort4 on one ~8.5-h FM65 session per logger: fast postprocess mode, unit-yield report

Batch (this session): SF07 `15_20260902_082418.755`, SF08 `13_20260902_082748.094`, SF09 `10_20260902_083015.335`,
SF10 `9_20260902_083247.835`, SF11 `12_20260902_083534.755`, SF12 `11_20260902_083748.804` (all 2026-09-02 08:2x starts,
FM65, staged verbatim under `E:\3rd_rat_spikes\analysis\stage\`, sorted under `…\analysis\sort\<SFxx>\<session>\`), per-shank
Kilosort4 with the pipeline defaults (500–8000 Hz, local CMR 20–200 µm, high-amplitude artifact removal 5 σ).

- **Timing on SF07 (8.51 h, 78 GB .dat):** preprocess 2.9 h (E: was still receiving card copies), Kilosort4 4 shanks 2.8 h
  (GPU), postprocess **2.7 h per shank** with the pipeline as shipped: it computes waveforms + PCs for EVERY spike
  (`random_spikes method="all"`, hard-coded in `src/postprocess/pipeline.py`) in two passes and then `run_for_all_spikes`
  for Phy `pc_features`, each a full pass over the .dat (~1.5 M spikes on shank 1).
- **`run_sort_session.py` now has a `post_mode`** (manifest key): **fast** (default from 2026-09-04) installs
  `_install_fast_postprocess_shim` — uniform 500 spikes per unit (`--post-max-spikes`) for waveforms/templates, PCA
  autosplit replaced by a passthrough (its per-spike projections need all spikes), no `spike_locations`, Phy export without
  `pc_features` (FeatureView empty; `open_phy.py --raw` shows Kilosort's own features). Unchanged: dedup, redundant-unit
  removal, automerge, spike amplitudes (all spikes), quality metrics, noise labels. **full** (`--post-full`) = pipeline
  behaviour. The pipeline checkout is untouched (module-level names are monkeypatched, like the KS4 partition shim).
  SF07 was already in its full postprocess when this landed and could not be stopped (process kills are denied by the
  auto-mode classifier here), so SF07 = `full`, SF08–SF12 = `fast`; the unit-yield report carries the mode per session.
- **`unit_yield_report.py`** now also reports sessions whose run is still in progress (any `Kilosort4_*` sorter folder;
  `sort_manifest.json` optional): shanks without a `_spi` folder are read from the raw Kilosort4 output (stage `ks4-raw`:
  KSLabel labels, ContamPct < 10 as the isolation proxy, the runner's 0.01-Hz low-rate rule applied), curated shanks as
  before (stage `post`). New columns `status`, `post_mode`, `stage`.
- **SF07 result (run finished 05:19, 545 min wall; `post_mode` full):** 227 Kilosort4 clusters → 217 after postprocess (shank 1 47 → 63, 2 44 → 60, 3 69 → 55, 4 67 → 39), **147 noise-labelled, 70 candidates (27 / 13 / 19 / 11 per shank), 65 below 3 Hz,**
  5 at ≥ 3 Hz, 6 well-isolated (ISI ratio < 0.5 & SNR ≥ 5). Noise rules hit (multi-count over the 147): SNR < 2 → 91, rate < 0.01 Hz → 76,
  amplitude < 15 µV → 54, presence < 0.1 → 53, ISI ratio > 5 → 51; 23 clusters fell to the SNR rule alone, none to the amplitude rule alone.
  Candidates: median amplitude 34 µV (p10 21, p90 68; relative 0.195 µV/count), median SNR 3.5. Because SNR/amplitude gates depend on the
  unverified WILD gain and on the 4 × 16 map, treat the 147 'noise' as a Phy to-check list, not as discarded. Phy: `open_phy.bat --animal SF07
  --session 15_20260902_082418.755 --shank k` (full pc_features present for this session only).
- **Fast mode validated on SF08 `13_20260902_082748.094` (9.9 h, 11:33):** preprocess 3.3 h, Kilosort4 4 shanks 2.2 h, **postprocess
  19 min for all four shanks** (vs 2.7 h per shank in full mode on SF07). 285 KS4 clusters → 227, 67 noise-labelled, 160 candidates
  (45 / 31 / 42 / 42), **146 below 3 Hz**, 14 at ≥ 3 Hz, 4 well-isolated; candidate median amplitude 25 µV, SNR 2.3–3.3 per shank;
  channel 32 (dead) auto-rejected. Fewer noise labels than SF07 partly because fast mode has no autosplit (no fragment clusters).
- **Channel-map re-check on the FM65 sessions (2026-09-04, `probe_map_check.py --rotation-scan --derive`, 600-s windows, user
  note "SF07's layout differs from the others"):** SF10 `9_20260902_083247.835` picks SF07's exact map (v1_raw, bank0 +1, bank1 0:
  same-shank pair agreement 0.89 of 54 strong pairs, NN 0.40, bank-0 order 0.76, bank-1 order 0.08) → SF10 = same probe/wiring as
  SF07. SF08 (19 strong pairs), SF11 (22) and SF12 (67): the co-activation clusters fall inside SF07's shank groups (purity 0.90 /
  0.96 / 0.88), so the **shank grouping of SF07's XML is valid for all four 4×16 loggers**, but the within-shank site order matches
  no orientation × bank-rotation of A4x16-Lin, A4x16-Poly2-5mm-20s-lin-160 or A4x16-Poly2-5mm-23s-200-177 (NN agreement ≤ 0.42
  everywhere; no single winner) → their probe design / connector orientation is unknown; per-shank sorting with SF07's groups is
  unaffected, depth order and geometry are not. `probe_map_check.py` now de-glitches in 1M-sample blocks (an 1800-s window had
  raised MemoryError at 43 GB).

## Addendum 2026-09-04 (later) — the 09-03 reboot step MEASURED, probe move registered

- **Field-PC clock step at the 09-03 13:56:01 bugcheck reboot is real and equals +1.28 s** (was PROVISIONAL 1.35 s).
  Two independent measurements, after the field side reported "no clock step across it":
  1. *Their drift log* (NTP minus PC, w32time stopped since 09-01 19:00). Clean samples (delay < 200 ms) fit
     +92.4 ms/h before the reboot and +91.0 ms/h after, with max residuals 10 ms / 4 ms; the two lines differ by
     **1.263 s** at 13:57:30. The 09-04 00:45 sample reads 3,523 ms where the no-step line predicts 4,782 ms.
  2. *BLE anchors*, free-step fit (one line + a step at the reboot, robust MAD gating) on the three sessions that keep
     anchors on both sides: SF08 `2_20260903_075352.907` +1.265 s (rms 7.9 ms), SF11 `3_20260903_080159.850` +1.281 s
     (18.9 ms), SF12 `3_20260903_080924.473` +1.319 s (7.6 ms). SF10 `2_` has no surviving pre-reboot anchor and
     cannot measure it.
  A boot-time clock change is not a w32time event and the LED scheduler restarts with the PC, which is why neither of
  the field side's usual indicators showed it; the Windows Kernel-General Id 1 export (requested in field2026-sync
  `tasks/2026-09-04_...`) is still outstanding and would pin all three steps to the millisecond.
- **SF09 open question closed from the card.** The field side flagged an RTC write at 09-03 16:50:47 that might have hit
  a recording logger. `SF9/68BDFFFF62DB/2_20260903_075655.297` holds 627,365,120 samples = 31,368.3 s, so it ran
  07:56:55.3 → 16:39:43.6 and self-stopped on low battery; the write landed 11 min later on an idle logger. No session
  was cut short by a Resync.
- **Probe advances registered** as `ephys.probe_moves` in `cohorts/2026c.yaml`: SF07 09-04 14:00:54 and SF11 09-04
  13:56:50, both 1/4 turn, `settle_h: 4`. The moves sit inside Stop→Start gaps so no session needs splitting, but
  pre- and post-move are different tissue: sort as separate epochs, never merge unit identities across a move.
- Field-side routine files in use: `2026-09-04_cohort3-pc-side-session-marks.csv` (146 sessions through 09-04 08:28,
  closes every 09-03 daytime session), both LED days, the drift log. Battery deaths before the 09-04 swap round
  (SF12 07:01 … SF11 07:41) explain the start-anchored-only ends on those sessions; EVO cards give ~13.0–13.7 h.
- **Channel map, test #2 — unit-footprint compactness (`ephys/footprint_map_check.py`, 2026-09-04).** User note: SF07, SF10, SF11,
  SF12 carry the same probe; the only possible difference is how the probe was plugged into the logger. The co-activation scan
  saturates at 20–70 strong pairs (1-h windows add nothing), so a second test: for the 40 largest Kilosort4 units per shank the
  spike-triggered average over all 64 exported columns of the preprocessed .dat gives a 64-column footprint; each candidate map
  (16 connector matings — per-connector 180° rotation, connector swap, mirror — × bank rotations −4..+4 = 1,296) is scored by the
  mean distance of the unit's 6 strongest columns from its peak column (lower = compact). **Validation on SF07: the verified map
  ranks 1/1296 (84 µm vs 90 µm for the runner-up).** SF08 (147 units): SF07's exact map ranks 1/1296 as well, but the best spread
  is 173 µm and only 46 % of unit energy lies within 100 µm (SF07: 64 %) — every candidate leaves SF08 broad, so SF08 is either a
  different probe (not in the user's same-probe list) or mostly low-SNR multi-unit. A channel-triggered variant on the raw staged
  data (`--trigger`, meant to decide SF11/SF12 before their sorts) FAILED validation twice (SF07's map ranked 781 then 159 of 1296)
  and is documented as unusable. **SF11 / SF12 therefore wait for their Kilosort4 output (SF11 ≈ 03:00, SF12 ≈ 09:00 on 09-05) and
  the unit test; the batch keeps SF07's grouping for them (co-activation cluster purity 0.96 / 0.88), which the test can then
  confirm or replace.** `probe_map_check.py --connector-scan` adds the same 16 matings to the co-activation scan.
- **Uncertainty of the step, honestly.** In a free-step fit the step and the slope are 0.96-0.99 anti-correlated, so the
  8-38 ms formal errors understate it; the 54 ms spread between the three loggers is the real scale, and the drift log's
  own back-extrapolation carries ~15 ms. Adopted **1.28 +- 0.04 s**. Refitting the four sessions with 1.28 s instead of
  1.35 s moves their drifts from -20.1/-24.1/-28.0/-19.6 to -17.4/-21.7/-25.4/-17.2 ppm - a systematic 2.5 ppm that is
  inside each logger's own session-to-session spread (e.g. SF11 ranges -23.8 to -30.2 ppm across its other sessions), so
  no verdict changes: overview stays OK 48 (241.9 h) / step-modelled 7 (46.4 h) / chained 4 (16.9 h) / start-only 12
  (43.5 h) / corrupt 5 (16.7 h). Worst-case residual PC-time error after the step is 40 ms, near the 33 ms video frame.
- **SF09 `10_20260902_083015.335` (8.5 h, done 17:02, 328 min, fast):** sorted on the DATA-DERIVED 7-group XML (35 channels; 29 columns
  unassigned → excluded, plus ch 32): 90 KS4 clusters → 87, 15 noise-labelled, 72 candidates (21 / 23 / 5 / 7 / 7 / 6 / 3 per group),
  **66 below 3 Hz**, 6 at ≥ 3 Hz, 4 well-isolated. Groups 3–5 (5–8 channels each) carry the highest-rate candidates (median 1.2–2.4 Hz).
  The 5×12 Buzsaki map is being re-tested with the 16 connector matings (co-activation + unit footprints) — if one fits, the
  29 excluded columns come back and SF09 is re-sorted.
- **SF09 channel map re-test (FM65 `10_20260902_083015.335`, 2026-09-04):** with the 16 connector matings × bank rotations, the
  ProbeMaps A5x12_16-Buz table still fits nothing — co-activation 93 strong pairs, best same-shank 0.51; unit-footprint test on
  60 KS4 units: best 185 µm, same-shank ≤ 0.50, no margin. So SF09's site→pin table is not the ProbeMaps one under any mating
  (a different adapter or probe revision); its data-derived groups remain the working map.
  Re-deriving the groups from the FM65 session (`--derive-xml`, 600 s) reproduces the FM64-derived map (core groups
  identical: [0 16 18 20 29 31 48 50 61], [17 35 38 39 40 41 46], [19 26 27 28 30], [34 43 45 53 57], [8 9]; 34 vs 35 channels
  assigned) — the ~30 unassigned columns are silent in both sessions (no strong co-activation), consistent with the field note
  "Logger Channels Count 50" → dead/unconnected sites, not a mapping problem. SF09's XML is kept; no re-sort.

## Addendum 2026-09-04 (III) — logger drift measured to be linear; fitter uses the last touch; FM65 fully verified

**Is the logger crystal drift linear?** Measured on 8 long, well-anchored sessions (6-11 h): a straight line fits to a
median 6 ms, worst 13 ms, and the hourly mean residuals stay inside +-14 ms with no bow. Between sessions of the same
logger the rate varies by 0.8 ppm (median deviation from that logger's median) / 2.0 ppm (sd); day- and night-session
medians differ by <= 1.5 ppm, so temperature is a minor term. Consequences:
- A session anchored only at its start drifts off by ~0.8 ppm x duration: 22 ms typical / 117 ms worst over 8 h,
  37 / 187 ms over 13 h.
- ONE 1-minute touch (~25 anchors, cluster centroid ~3 ms) part-way through measures the drift instead: at +6 h of a
  13 h session it pins it to 0.20 ppm, leaving ~5 ms at the end. Later is better than more.
- Predicting a session's drift from the logger's median beats predicting it from the immediately previous session
  (0.6 vs 1.5 ppm median error; adjacent restart pairs differ by 2.2 ppm median, 10.7 max), so the existing fallback
  stays as it is.

**Fitter change (`pc_time_chain.py`).** When there is no cluster within `END_WINDOW_S` of the end (battery auto-stop, or
a missed round), the fit now falls back to the LAST touch that sits at least `FAR_CLUSTER_MIN_FRAC` (0.30) into the
session, and extrapolates the remaining tail; new columns `tail_extrap_h` and `tail_extrap_unc_ms`, and the verdict
carries `[last touch X h, tail Y h extrapolated]`. `end_vs_next_ms` and the 0.8 x duration span gate are guarded so
they still refer to a genuine end cluster. selftest 20/20 (two new checks cover the foreign-MAC filter).
Result: natively fitted 55 -> 58 sessions (288.3 -> 311.2 h); assumed-drift 12 -> 10 sessions (43.5 -> 25.0 h), all of
them now 1-4 h with <= 60 ms end uncertainty. Rescued: SF08 `13_20260902_082748` (-19.0 ppm, 0.1 ppm from its logger's
median, 1.39 h tail), SF09 `2_20260903_075655` (-25.2, 1.6 ppm, 2.04 h tail), SF10 `2_20260901_125856` (-30.6, but
6.9 ppm from SF10's median: the 09-01 13:09:11 step lands 10 min into it, leaving a 2.2 h baseline on which an 80 ms
step-size error is 10 ppm - its quoted 6.3 ms tail uncertainty is formal and optimistic, ~50 ms is realistic).

**FM65 is now verified on both counts** (`cohorts/2026c.yaml` firmware_history updated): glitch defects absent
(measured across 94 sessions / 240.8 h), and the power-cut-safe commit confirmed - the operator tested a hard battery
pull mid-recording (2026-09-04) and the session survived, while the logger's own low-battery auto-stop closes files
byte-exact (SF09 `2_20260903_075655.297` 8.713 h, SF07 `4_20260903_001558.656` 4.039 h: amplifier.dat a whole number
of 128-byte samples, time.dat = 4 n, analogin.dat = 2 n). The earlier "sidecar inconsistency" flag on SF11
`3_20260903_080159.850` was a stale index run taken while that folder was still being copied; it is consistent.

**Field protocol consequence** (communicated to the field agent): the mid-night Stop->Start restart was insurance
against a power-cut loss and is no longer needed, so the operator's existing midnight touch becomes a mid-session
anchor rather than a session start, and a second 1-minute touch at 13:00-14:00 covers the daytime session, which dies
of battery (16:30-18:20) before the evening round. That removes both remaining holes (03:30-05:00 and 16:30-18:20)
and, as a bonus for sorting, makes each night a single continuous epoch. Restarting anyway is harmless: it does NOT
disturb the timestamps (no Resync is pressed, and 79 of 97 short restart boundaries show |start_vs_prev| <= 2 s, median
6 ms, i.e. the RTC runs straight through); it only costs ~12-58 ms on the tail of the post-restart session.
