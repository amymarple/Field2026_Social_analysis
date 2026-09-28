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

## Addendum 2026-09-04 (IV) — timing precision vs what the analyses need

Report: `results/2026c/ephys_spikes/reports/ephys_spikes_timing_precision_vs_requirements_2026c.md` (mirrored to
`E:rd_rat_spikesnalysis\index\`). Headline: the ephys -> field-PC chain is 8-22 ms typical, <= 60 ms worst
(08-31 FM62 block excluded, no PC time there); place fields tolerate 100-300 ms, behaviour events one 50 ms frame, so
the chain is not the bottleneck by 5-10x - the position side is (WISER 0.26 s fix interval, 10-18 cm jitter; 50 ms
video frame). Not supported: ms-scale spike synchrony between animals (15-30 ms combined + a <= 50 ms constant BLE
latency, ESTIMATE) - needs a shared hardware TTL. Headline definitions (full set in the report):
- timing error as position error: $e_x = v\,\delta t$ (cm; $v$ cm/s, $\delta t$ s) - compare with sensor noise;
- end error of an assumed-drift session: $\delta_{	ext{end}}(T) = |\Delta b| 	imes 10^{-6} 	imes T 	imes 1000$ ms,
  with $\Delta b$ = a session's drift minus its logger's median (0.8 ppm median, 2.0 ppm sd);
- parabolic bow $eta = |c_2|/4$ (ms) on $	au=(t-ar t)/T$: 6 ms median, 13 ms worst over 6-11 h = linear.
- **Batch paused for the 2026-09-05 07:00 card offload (user decision 00:50):** SF11 and SF12 are held by renaming their staged XMLs
  to `<session>.xml.hold` (`E:\3rd_rat_spikes\analysis\stage\SF11\12_20260902_083534.755\`, `…\SF12\11_20260902_083748.804\`), so the
  running batch skips them in seconds ("session is not staged", rc≠0 in its summary — expected) and ends after SF10 (~02:00).
  Restore = rename the XMLs back and run `ephys/run_sort_session.py --partition shank --overwrite` for each (fast postprocess, ~6 h each).
  Reason: preprocessing (read 78 GB + write 78 GB on E:) and the Kilosort4 .dat reads would slow the copies 20–40 %.
- **SF10 `9_20260902_083247.835` (8.5 h, done 06:28 on 09-05, 806 min, fast):** preprocess 3.8 h, **Kilosort4 9 h** (shank 1 alone
  5.6 h — SF10's "super noisy shank" of the 8/25 field note; shanks 2–4 1.8 / 0.7 / 1.0 h), postprocess 30 min. 301 KS4 clusters →
  237, 68 noise-labelled, 169 candidates (52 / 36 / 41 / 40), **148 below 3 Hz**, 21 at ≥ 3 Hz, 10 well-isolated; channels 32, 34, 56
  auto-rejected. Batch ended 06:28 with SF11/SF12 skipped (held). Five of six loggers sorted; SF11/SF12 after the 09-05 offload.

## Addendum 2026-09-05 — recovery images duplicated to F:, offload throughput measured

- The six raw card images `E:rd_rat_spikes\SFxx
ecovery.bin` (3.07 TB) were copied to `F:rd_rat_spikes\SFxx
ecovery.bin`
  (SanDisk Extreme 4 TB) between 09-04 19:14 and 09-05 06:29, hashing the source stream during the copy and re-reading each
  destination afterwards: all six sha256 pairs match (`F:rd_rat_spikes
ecovery_images_manifest.json`). Purpose: E: had
  2.98 TB free against ~2.1 TB per offload round; deleting the E: originals (operator's decision, not done here) frees 2.9 TB.
- E: (WD Red Pro 20 TB, 84 % full, free space on the inner tracks) reads a single stream at 103-114 MB/s there, against the
  268-285 MB/s outer-track spec, so it absorbs about two simultaneous 50 MB/s card exports, not three. Card-copy history
  from file timestamps: one card 50 MB/s (the WILD console's per-card ceiling), two cards on independent USB root ports
  49 + 49 with no loss, two cards behind one extender 25 + 25. Plan adopted for the 09-05 batch: two cards to E:, two to
  D: (SATA SSD, 217 MB/s measured), two to F:, each reader on its own root port, one console instance per card; the D:/F:
  copies are consolidated into E: afterwards with verification.
- **SF10 connector mating = A180 (2026-09-05 06:40).** Unit-footprint test on SF10's 150 Kilosort4 units: `A180 +1/0` (the 2×16 Omnetics
  connector on RHD2164 rows 0–1, Intan ch 16–47, rotated 180° in its socket) 171.9 µm vs 180.5 µm (2nd, m+A180) vs 198.4 µm for SF07's
  map (rank 9/1296); the co-activation `--connector-scan` had already put A180 first on SF10 (NN 0.51 vs 0.40). This is the user's
  "plugged in differently" case. Consequence: the four column SETS per shank are the same as under SF07's map (shank labels 2↔3
  swap), so the 09-04 SF10 sort used the right grouping; only the site ORDER inside shanks 2 and 3 was wrong (spatial templates,
  Phy waveform layout, depth). New XML `ephys/configs/xml/SF10_A4x16-Lin_A180_rot+1_0.xml` (`make_probe_xml.py --orientation A180`,
  16 matings now supported), `probes_2026c.yaml` SF10 → A180 (verified), staged XML replaced (old copy kept as `.xml.sf07map`);
  SF10 re-sort queued after SF11/SF12 (its noisy shank makes Kilosort4 take ~9 h).
- **Audit of `correct_intan_dat_channel_order.py` (user request 2026-09-05; file `D:\Downloads\…`):** byte-identical to the vendored
  copy `ephys/vendor/correct_intan_dat_channel_order.py` (md5 809899d3…, committed d465cc5 on 09-03); its `--self-test` passes; its
  embedded CE64 map equals `configs/wild_ce64_channel_map_v57.csv`; `probe_map_check.v57_source_columns(r)` and
  `rotation_permutation(+1, 0)` reproduce `restored_source_columns(bank=0, rotation=r)` exactly for r = −1, +1, +2 (first source
  columns 30, 0, 28, 31, 26, 29, …); an independent re-derivation (slot r holds logical channel r+1 → console map → repair) restores
  the fault-free export. Direction convention confirmed: "Intan channel i lives in exported column P[i]", which the SF07 footprint
  validation (rank 1/1296) already tested empirically. No change needed.
- **Queue restarted 2026-09-06 18:10 (user: "run; I copy cards again ~06:00–07:00 tomorrow, schedule around it"):** `batch_sort_queue.sh`
  runs SF11 `12_20260902_083534.755` → SF12 `11_20260902_083748.804` → SF10 re-sort with the A180 XML, each followed by the
  unit-footprint connector test and the yield report. A job is started only if its estimate (7.5 h / 7.5 h / 15 h) ends before
  the daily 05:30–07:30 blackout, otherwise the queue sleeps until 07:30. Expected: SF11 done ~01:40 on 09-07, SF12 held to
  07:30 → ~15:00, SF10 ~15:00 → ~06:00 on 09-08 is too close to the window, so it also waits (starts 07:30 on 09-08).
- **Offload window corrected (user 18:30: the copies run ~06:00–16:00, not 06:00–07:00):** the running queue (05:30–07:30 rule) is
  allowed to finish SF11 only (SF12/SF10 XMLs held → skipped); `batch_sort_queue_v2.sh` (blackout 05:30–16:30, waits for
  queue v1 to end) then runs SF12 from 16:30 on 09-07 (~00:00) and the SF10 re-sort right after. Because a full SF10 re-run
  (~15 h) never fits the 16:30→05:30 gap, the re-sort uses the new `ephys/resort_shanks.py`: Kilosort4 only on the two shanks
  whose site order changed under A180 (partitions 2 and 3 = columns 1–17 and 32–47), re-using the preprocessed .dat, old
  folders moved to `<sort_root>/SF10/_superseded/<session>/A180_<ts>/`, then one fast postprocess over all four shanks
  (~4 h; caveat recorded in the manifest: the .dat's local CMR neighbourhoods on those shanks follow the old site order).
- **SF11 `12_20260902_083534.755` (8.5 h, done 22:45 on 09-06, 276 min, fast, sorted with SF07's grouping):** 233 KS4 clusters → 206,
  81 noise-labelled, 125 candidates (28 / 29 / 28 / 40), **115 below 3 Hz**, 10 at ≥ 3 Hz, 3 well-isolated; candidate median amplitude
  20 µV, SNR ≈ 2 — the weakest signals of the cohort (consistent with the LFP verdict that SF11 sits above the pyramidal layer).
  Footprint mating test (146 units): no winner — v1_raw +3/0 164.7 µm, m+A180 +1/0 165.3, SF07's map 175.0 (rank 18); all 16
  matings within 6 %. Like SF08, SF11's small, broad units do not decide the within-shank order; the shank grouping is the same
  under every candidate that scores well (column sets identical to SF07's map), so the sort stands with "order unverified".
  Sharper variant (`footprint_map_check.py --peak-cols 1-17,32-47`, i.e. only units whose peak lies on the two shanks whose site
  order differs between the matings; `--top-k 3`): SF07 keeps v1_raw (58.6 vs 64.1 µm), SF10 keeps A180 (123.8 vs 130.9, SF07's map
  rank 17) — the test discriminates when footprints are compact. SF11 (73 such units, 200 or 1000 spikes each): every top candidate
  is a MIRRORED mating (m+A180, m+A180+B180, v3_fliplr; 128–175 µm) and SF07's map ranks 6–21, but the leaders differ by 1–2 %, so
  SF11 is recorded as "probably mirrored (flipped over), exact mating undecided"; its shank column sets are the same under all of
  them, so the sort stands.
- **SF10 shank 1 is dead (user Phy inspection 2026-09-07, confirmed in the data):** columns 48–63 show 0.0–0.5 threshold crossings/s
  per channel on the preprocessed .dat (other shanks up to 13–35/s), noise alternating 12 / 7 µV by pin row, column 56 flat; its 97
  Kilosort4 clusters have median ContamPct 47 % and Kilosort4 spent 5.6 h on them. The A180 verdict does not rest on it: with
  only units peaking on the two changed shanks, A180 still leads (169.8 vs 179.1 µm; SF07's map rank 16), and an interpretable
  check — the fraction of units whose 2nd-strongest column is an adjacent site — goes from 0.15 (SF07 order) to 0.60 (A180 order)
  on columns 32–47, close to the untouched shank 4 (0.68). Changes: `SF10_A4x16-Lin_A180_rot+1_0.xml` regenerated with columns
  48–63 as skip, `probes_2026c.yaml` SF10 `reject_channels` = 48–63, staged XML updated; `resort_shanks.py` now also supersedes the
  Kilosort4 folders of a shank that has no partition left (shank 1 → `_superseded/`), so the re-sort yields shanks 2, 3 (new) + 4.
  The yield report's SF10 "shank 1: 52 candidates" row is junk until the re-sort lands.
- **SF09 map rebuilt as 5 shanks (user 2026-09-07: "SF9 is wrong, this is 8 shanks, it has only 5"):** the 7 co-activation clusters +
  a 29-column skip group were fragments, not shanks. Average-linkage clustering of the 500–5000 Hz inter-channel correlation of the
  54 live columns (FM65 `10_20260902_083015.335`, 600 s; LFP correlation is useless here, r > 0.9 across the whole probe) gives five
  groups of 12 / 8 / 11 / 11 / 12 sites that contain the co-activation clusters intact (A = clusters 2+6, B = 4, C = 1, D = 5,
  E = 3+7) and absorb the 19 silent live columns; within-shank site order = Fiedler order of the within-shank correlation
  (consecutive-site r 0.20–0.39; approximate depth, no geometry). 10 dead columns [2 4 32 36 52 54 56 58 60 62] skipped (Notion:
  50 live channels). New XML `SF09_data_derived5_10_20260902_083015.335.xml`, config + staged copy updated, old 7-group XML
  superseded; SF09 full re-sort queued (`batch_sort_queue_v3.sh`, after queue v2 and outside 05:30–16:30, ~7 h).
- **Start pushed to 18:00 on 09-07 (user 16:00: copies done, offload QC running on E:):** the three staged XMLs are parked as `.hold2`
  so queues v2/v3 fail fast at 16:30 and end; `batch_sort_queue_v4.sh` (not before 18:00, then the 05:30–16:30 rule) runs
  SF12 sort (~6.5 h) → SF10 shank 2+3 re-sort (~3.5 h) → SF09 5-shank re-sort (~7 h, expected to be deferred to 16:30 on 09-08),
  each followed by the footprint test (SF12, SF10) and the yield report.
- **Paused 2026-09-07 18:15 (user "先暂停"):** SF10 and SF09 staged XMLs parked as `.xml.paused` (queue v4 will fail fast on them and
  end); the running SF12 sort (started 18:00, preprocessing) cannot be stopped from this session (process kills are denied) —
  PIDs handed to the user. Resume = rename `.paused` → `.xml` and launch a new queue; SF12 must be re-run with `--overwrite` if
  it was killed mid-way.
- **Resumed 2026-09-07 23:25; queue v5 (SF10 re-sort tonight) + v6 (free day 09-08).** The 18:00 SF12 run had been killed
  mid-preprocess and left no output, so it is re-run from scratch. Order changed to use the ~6 h before the offload window
  for the short job: v5 = SF10 shanks 2+3 re-sort (A180 XML, dead shank 1 dropped), started 23:24. The user then said
  2026-09-08 is a free day (no card copying), so `batch_sort_queue_v6.sh` waits for the re-sort's `resorts[]` marker and
  runs with NO blackout on 09-08 (05:30–16:30 rule resumes 09-09): SF12 full sort → SF09 5-shank re-sort →
  **FM64 salvage test** (implementation_plan/2026-09-07-fm64-salvage-test.md step 1/3, user request): stage + sort
  SF10 `1_20260901_080143.036` (FM64 day, de-glitched, 2,240 ticks/s) and SF07 `2_20260901_002100.939` (FM64 night, the
  low-defect logger), each with the same probe config / reject list / post_mode as that logger's already-sorted FM65 session,
  for the per-shank comparison (candidates < 3 Hz, well-isolated, amplitude/SNR, ISI, template width on victim channels;
  decision rule: FM64 sortable if well-isolated ≥ 70 % of FM65 and no one-sample-wide templates). Each finished job parks its
  staged XML as `.xml.done` so the still-sleeping queue v5 fails fast instead of repeating a job.
- **SF10 A180 re-sort done (2026-09-08 00:23, 58 min) + two bugs fixed.**
  (a) *Stale partition manifest*: PreprocessPipeline's postprocess prefers `sorter_partition_manifest.json` over a directory
  scan (`_find_sorting_output_dirs_from_manifest`), and the file still listed the 09-04 folders — three of which had just been
  moved to `_superseded/`, so only the untouched shank 4 was postprocessed and the two re-sorted shanks got no Phy folder.
  `resort_shanks.py` now rewrites that manifest from the folders on disk before the postprocess (old copy kept as
  `.pre-<tag>-<ts>`) and has `--post-only` to repair a session without re-running Kilosort4; SF10 repaired with it (11 min).
  (b) *Backup folders counted as shanks*: `unit_yield_report.py` globbed `Kilosort4_*_probe*_shank*`, which also matches the
  pipeline's `*_spi.preserved-<ts>` / `*.attempt-<ts>` copies — they appeared as two bogus "shank 0" rows and doubled SF10's
  spike total. Both suffixes are now skipped.
  **SF10 after A180 (3 live shanks; shank 1 dead and dropped):** 175 KS4 clusters → 139, 25 noise-labelled, 114 candidates
  (45 / 29 / 40), **96 below 3 Hz**, 18 at ≥ 3 Hz, 7 well-isolated; candidate median amplitude 36 µV, SNR 3.1–4.8.
  Versus the 09-04 sort with SF07's map (4 shanks incl. the dead one): 169 candidates / 148 < 3 Hz / 10 well-isolated —
  not comparable head-on because the dead shank's 52 junk candidates are gone; on the two changed shanks alone the counts
  went 36 + 41 = 77 candidates (SF07 map) → 45 + 29 = 74 (A180), i.e. the map change did not cost units.
- **SF12 `11_20260902_083748.804` (9.7 h, done 05:53 on 09-08, 329 min, fast):** 296 KS4 clusters → 211, 41 noise-labelled,
  170 candidates (28 / 56 / 42 / 44), **146 below 3 Hz**, 24 at ≥ 3 Hz, **23 well-isolated** — the best isolation of the cohort
  (shank 3 alone: 13 well-isolated, median amplitude 62 µV, SNR 6.0). No channels rejected. With this, all six loggers have one
  sorted ~8.5-h FM65 session; SF09's 5-shank re-sort started 05:53.
- **SF09 5-shank re-sort done (2026-09-08 10:12, 259 min, fast).** With the corrected map (5 shanks, 54 live columns; the old
  XML had 7 co-activation fragments + 29 unassigned): 267 KS4 clusters → 195, 49 noise-labelled, 146 candidates
  (45 / 14 / 28 / 20 / 39), **136 below 3 Hz**, 10 at ≥ 3 Hz, 10 well-isolated; candidate median amplitude 30 µV, SNR 2.4–3.2.
  Versus the superseded 7-group sort (72 candidates, 66 < 3 Hz, 4 well-isolated): **+74 candidates, +70 units < 3 Hz,
  +6 well-isolated** — the 19 live columns the old map discarded were carrying units. The old folders are archived under
  `sort/SF09/_superseded/10_20260902_083015.335/7groups_2026-09-04_131239/`.
- **`unit_yield_report.py`: only the CURRENT run of a session is counted.** `run_sort_session.py --overwrite` writes a new
  timestamped folder set and leaves the previous one in place, so SF09 briefly reported 12 shanks (7 old + 5 new) and doubled
  totals. The report now takes the folders listed in `sort_manifest.json` (`result.sorter_output_dirs` + any `resorts[].kilosort4_dirs`),
  falls back to the newest timestamp when no manifest paths survive, inherits untouched shanks from an earlier run ONLY after a
  partial re-sort (`resorts` present, the SF10 case), and ignores `_spi` folders whose sorter folder still exists (superseded run).
- **SF12 mating test (2026-09-08, 150 KS4 units):** A180-family candidates lead the footprint ranking (m+A180 193 µm, A180 199,
  SF07's map 210 / rank 15), but the interpretable adjacency check — fraction of units whose 2nd-strongest column is an adjacent
  site — is 0.03–0.15 under every candidate, including the shank that A180 does not touch (SF10's untouched shank scores 0.41,
  SF07 0.78). So none of the 16 matings × rotations describes SF12's within-shank order; like SF08 and SF11 its shank grouping is
  valid (column sets identical under all leaders) and its site order stays open. **XML status: SF07 verified, SF10 = A180 (re-sorted),
  SF09 = 5 data-derived shanks (re-sorted); SF08 / SF11 / SF12 grouping-only.** Nothing further to run on the map question
  without new information (probe photos, which physical shank is where, or a pin table for these implants).
- **Channel-map test #3 — LFP depth profile (`ephys/lfp_profile_check.py`, 2026-09-08; user: "the sharp wave must go smoothly from
  positive to negative along the shank, match the LFP, not units").** Ripple-triggered average of the 1–50 Hz LFP (30 min of the
  daytime session, 870–1,450 ripples per logger) gives a per-column sharp-wave (SPW) amplitude; a within-shank order is scored by the
  total variation of that profile (1.0 = monotonic). Validation: on SF07 its verified map ranks 1/144 and shank 4 reads +31 → +71 µV
  monotonically; the profiles are all positive there (shanks above / in the pyramidal layer, no reversal). **SF10 (user-marked broken
  columns 2, 32, 34 + dead shank 1):** the connector-B shank (columns 0, 16, 18–31; untouched by A180) shows the textbook profile
  +22 … +127 (pyramidale) → −311 / −123 / −197 (radiatum), tv 1.95, so its order is right; on the two connector-A shanks the A180 order
  is jagged (tv 2.58 / 3.44, the radiatum sites 11, 15 and 43, 47 scattered among oriens sites) and **no mating × rotation in the
  family fixes them** (brute force over 16 × 81). The large negative "sharp waves" I had first excluded as broken contacts are the
  radiatum signal the user described. Resolution: **data-derived within-shank order** for those two shanks — positive-SPW sites by
  ripple power ascending (oriens → pyramidale), then negative-SPW sites by SPW descending (radiatum); the rule reproduces the verified
  connector-B order (Spearman 0.97, tv 1.40) and yields tv 1.19 / 1.38 with one reversal each on the connector-A shanks. New XML
  `SF10_A4x16-Lin_dataorder_20260908.xml` (`lfp_profile_check.py --derive-xml --keep-groups 1 4`; grouping = A180/SF07 sets, shank 1
  dead, broken 2/32/34 skip at the end of their group); config updated; SF10 shanks 2+3 queued for another re-sort after the FM64 job.
  Caveat: a data-derived order is a depth ORDER, not a pin table — 50 µm pitch assumed, and sites with similar ripple power can swap.
  On SF08 / SF11 the SPW profiles are too small (median 20–28 µV) for the test; SF12 pending the user's broken-channel list.

## Addendum 2026-09-08 (evening) — within-shank order by LFP only: SF10 cross-session check, shank-4 impedance, dead-column placement

User's method statement (2026-09-08, verbatim in spirit): do NOT order sites by matching units; use the LFP — the sharp wave goes
gradually positive → negative from oriens/pyramidale into radiatum, ripple power peaks in the pyramidal layer, the theta phase
gradient is a third handle; three references for a candidate order: ① the author's XML rotation (`vendor/correct_intan_dat_channel_order.py`,
`configs/v57_channel_mapping.csv`), ② LFP polarity, ③ a physically possible way of plugging the probe in. Ten-minute windows are
enough; no Kilosort. Everything below reads a **10-min COPY** made with `stage_session.py --window-s` into
`E:\3rd_rat_spikes\analysis\stage\<animal>\<session>__w<start>s_600s` (raw session folders opened read-only, never written).

- **`lfp_profile_check.py` v2** (theta phase + ripple-power profiles, `--physical` candidate family from `probe_map_check.physical_variants`
  = the 16 matings × per-connector pin shifts −2…+2 with their predicted dead columns, `--permute-tail`, `--raw` mode reading the copy
  at 20 kHz with an IIR anti-alias + stride to 1250 Hz, `--offset-min` negative = from the end, spike-band 300–3000 Hz correlation of the
  first 2 min for the spacing estimate). SF07 on its first 10 min: its own verified map ranks 1 by SPW, 2 combined — a self-check of the tool only; the user
  set SF07 aside as a control ("only positive ripple channels") and its mating differs from the other animals, so its map is never a reference for them.
- **SF10, last 10 min of `15_20260903_055614.833` (496 ripples), under `SF10_A4x16-Lin_dataorder_20260908.xml`:** the order derived on
  09-02 reproduces on this independent window — shank 2 `+12 … +41 → +66 → +130 (ripple 71) → −241 → −606`, tv 1.24, one reversal;
  shank 3 `+17 … +40 → +104 → +116 (55) → +1 (59) → −52 (61) → −170`, tv 1.37; theta phase −13° → +50° along shank 2.
- **Shank 4 "puzzle" resolved as IMPEDANCE, not order (user's diagnosis, confirmed by the data).** Under the standard order the profile
  alternates in pairs; the two families are exactly the two connector-B pin rows: the eight odd-Intan sites (row 2; cols 27 25 29 23 31 21 0 19)
  read SPW +30 +27 +44 +38 +68 +57 −170 −127, the eight even-Intan sites (row 3; cols 22 24 20 26 18 28 16 30) read +9 +7 +16 +11 +17 +17 +13 −53:
  4× smaller, LFP rms (1–100 Hz) 967 vs 1199, theta phase offset +3° vs −5°, and the even sites correlate with EACH OTHER in the spike band
  at r 0.47 regardless of distance (odd–even 0.26, odd–odd 0.21, between shanks 0.11) — attenuated signal plus shared noise = poor contact /
  high impedance on one connector row. Scaling the even sites ×3.5 makes the shank monotone. Brute force over the deep five sites (120 orders)
  finds nothing that smooths all three profiles (best 6.58 vs current 7.59, rank 17/120), consistent with an amplitude problem. Order kept.
  Side observation for the field: the dead shank 1 is exactly connector-B pin columns 0–7 and the attenuated set is exactly connector-B row 3
  — both fit a poorly seated connector B rather than a dead probe shank.
- **Spike-band spacing / gap estimate WITHDRAWN as a distance measure** (caveat now in the tool's docstring): high-impedance sites look
  isolated (SF10 cols 3, 17, 15, 47 correlate with nothing), the reference scale from shank 4 was inflated by the even-site shared noise,
  and the four "≈2-site gaps" it flagged in shank 2's flat oriens region are sites whose data-derived order is arbitrary there (similar ripple
  power), not missing sites. It stays printed as a prompt to look at a site's amplitude, never as evidence for placing a dead column.
- **Dead columns must sit at their physical position, not at the end of the group (user).** Agreed in principle; on SF10 it cannot be done
  yet: connector A's wiring is unknown — the 3600 physical matings × rotations all leave the connector-A shanks jagged (best spw tv 2.2 vs the
  data order's 1.24/1.37). What the pins do say: the three broken connector-A channels 34 / 32 / 2 are three ADJACENT
  pins of one row (row 0, c6 c7 c8) straddling the two shank blocks — a contact patch on the connector, not three dead electrode sites; and on
  both connector-A shanks every live row-0 site is shallow (shank 2: 7/7 at +20…+41; shank 3: 5/6, one at +104) while the pyramidale →
  radiatum sequence sits on the odd-position row-1 pins, mirror-symmetric between the two shanks (shank 2 c11 c13 c15 = +130 −241 −606;
  shank 3 c4 c2 c0 = +116 −170 −52). So col 2 is most likely shallow, not between 7 and 11, and shank 2's +130 → −241 → −606 over two
  consecutive pins is the same steepness as shank 4's +13 → −170 over one pitch: no missing site is needed. The dead columns therefore stay
  `skip=1` at the end of their group until the wiring is identified; the XML is unchanged and still awaits the user's Neuroscope check.
- **SF08** first 10 min of `18_20260903_060030.122` (440 ripples, col 32 flat). SF07's XML enters ONLY as the shank column sets (identical under
  all 16 matings, and confirmed for SF08 by co-activation on 09-04 and by today's spike-band partners) — its ORDER is SF07's own mating and is
  no reference for any other animal (user, 2026-09-08: "SF7 和其他 animal 接法不同你不能比"). Under the ProbeMaps standard order all four
  shanks are jagged (spw tv 2.7–4.6, 1–4 reversals) and none of the 3600 physical matings × rotations is smooth (best spw tv 3.0) — SF08's deep sites sit on
  different pins than SF10's (row-1 c8–c10 and row-0 c14–c15 on connector A; row-2 c0–c3 on connector B), i.e. a different wiring, consistent
  with the user's note that only SF07/10/11/12 share a probe. **Candidate LFP-derived XML `SF08_A4x16-Lin_dataorder_20260908.xml`**
  (all four groups re-ordered: positive-SPW sites by ripple power asc, then negative-SPW sites by SPW desc; col 32 skip at the end of group 2;
  spw tv 1.20 / 1.18 / 1.23 / 2.48): shank 1 `+9 … +54 → +73 (rip 36) → +30 (38) → −63 −63 −182 −270`, shank 2 `+15 … +83 → +53 (43) → −175 → −308`,
  shank 3 `+7 … +55 → +32 (38) → −56 −114 −274`, shank 4 `+6 … +59 +75 → +23 (39) +73 (39) → −47` (shank 4 barely reaches the reversal). Copy
  placed as `stage/SF08/18_20260903_060030.122__w0s_600s/amplifier.xml` so the analysed 10 min open directly in Neuroscope; `probes_2026c.yaml`
  still points SF08 at SF07's XML until the user's check. Spike-band correlation check on the same copy (no impedance split by connector row
  here): the bank-0 grouping of the +1 rotation is confirmed by partners (col 1 ↔ 14/5, col 0 ↔ 29/16/28, col 16 ↔ 18/22/31); the top halves
  of the shanks have ripple power at the noise floor (21–23), so their LFP order is unconstrained — the correlation chain (57 52 54 50 56 61 48
  on shank 1; 18 22 20 27 on shank 4) is offered as a tie-breaker, not used in the XML. **Flags for the user:** cols 53 and 55 carry the same
  signal (r 0.97, identical SPW / ripple / theta / rms) — a duplicated channel, one should become skip; col 47 correlates with nothing (≤ 0.12)
  and has an outlying theta phase (−17° among −2…−3°) — suspect site; on shank 3 the correlation puts col 1 (−114) right next to the ripple peak
  col 14 (r 0.34) while the SPW order inserts col 17 (−56, isolated) between them — undecidable from 10 min, left in SPW order.
  **Physical-wiring support for SF08's order (user's question after approving it in Neuroscope): NONE found.** Besides the 3600 pinout-family
  candidates, `ephys/wiring_pattern_check.py` (test #4) tried 64 regular routings of each shank's 2 × 8 pin block (zigzag, serpentine,
  row-major, centre-outward fan-out, the four ProbeMaps shank routings × reverse / row swap / mirror): the data order ranks 1 on every shank
  (score 3.8–5.7 vs best regular 6.0–9.9, all with ≥ 1 extra reversal), and consecutive data-order sites sit on neighbouring pins at chance
  level (1–3 of 15; 0–2 of 5 among the deepest six). So SF08's order is supported by the LFP only; a real (possibly irregular) vendor pinout
  could still explain it, but that needs the probe design + package site-map table, which is not on this PC.
- **SF12**, last 10 min of `15_20260903_002228.142` (22752–23352 s, 561 ripples, copied with `stage_session.py --window-s`; the user had asked
  for this session, all channels good): candidate LFP-derived XML `SF12_A4x16-Lin_dataorder_20260908.xml` (copy as `amplifier.xml` in the staged folder;
  spw tv 1.41 / 1.08 / 1.33 / 1.58; profiles reach −301 / −839 / −245 / −673 µV in radiatum — a deep, clean recording). **Its order is SF08's**: Spearman
  +0.94 / +0.66 / +0.95 / +0.91 per shank between the two data-derived orders (same exported-column numbering), deepest-five overlap 4/5 on three shanks;
  against SF10 only +0.25 / +0.25 / +0.49 (deepest-five overlap 1–2/5). So SF08 and SF12 share one wiring and SF10 another; the user's statement that
  SF07/10/11/12 carry the same probe with different plugs is not what the LFP shows for SF10 vs SF12: the physical-mating scan on SF12 (3600
  candidates of the ProbeMaps pinout × matings × pin shifts × rotations) leaves every shank jagged (best spw tv 3.05–3.25, 2–3 reversals, vs the
  data order's 1.08–1.58), exactly as on SF08 — SF08/SF12 follow one pinout that is not the ProbeMaps one under any plug.
  **Data-quality flag — bridged connector pins.** Eight clusters of SF12 columns carry one signal each (spike-band r 0.90–0.95 with independent
  amplifier noise, identical SPW / ripple / theta / rms): {33,37} {43,45} {34,36,38} {44,46} {8,10} {12,14,17} {1,3,5} {21,23} — 19 columns, 11 redundant.
  Seven of the eight clusters are ADJACENT pins of one connector row (e.g. 12/14/17 = row-0 c13 c14 c15; 1/3/5 = row-1 c8 c9 c10; 21/23 = row-2 c13 c14),
  so these are bridged pins (solder / debris / moisture in the Omnetics), not electrode sites — invisible in Neuroscope because each column shows real
  signal. SF08's 53/55 pair (r 0.97) is the same thing (connector-B r2c2/r2c3). For sorting, all but one member of each cluster should become skip;
  which member is the electrode's own pin cannot be told from the data (the bridged pins see the same potential). Left for the user's decision;
  the candidate XML keeps all 64 live.
  **Bridged, not high-density (user's objection "未必是重复可能是更 high density", tested with `ephys/bridged_pins_check.py`).** A correlation cannot
  separate one electrode node seen by two amplifiers from two sites 20 µm apart; the difference a−b can: bridged pins differ only by the amplifiers'
  own noise. All 11 SF12 cluster pairs: spike-band rms of a−b 2.3–2.7 µV (0.33–0.43 of a channel's 6–7.6 µV, ≈ √2 × the 1.7 µV input noise), LFP
  residual 1.4–3 %, excess kurtosis 0.1–0.6 (two pairs 2–4), threshold events in a−b 0.00–0.16 /s while the channels themselves fire 1–12 spikes/s.
  Eight neighbouring distinct-site controls on the same copy: rms ratio 0.8–1.6, LFP residual 32–97 %, kurtosis 3–67, events 3.7–11.7 /s; even the two
  quietest shallow neighbours (57/52) keep a 7 % LFP residual. Two electrodes cannot lose every spike difference and 97 % of the LFP gradient, so the
  clusters are single nodes. SF08's 53/55: ratio 0.23, LFP 1.3 %, kurtosis 0.0, events 0.00 /s vs 8.4 /s on the channel — bridged as well.
  **User's Neuroscope reading of SF12 (candidate XML):** "shank 2's impedance looks bad overall" — the 32–47 block has 9 of 16 columns inside four
  bridged clusters (11 distinct nodes), which is what makes it look dead-ish; its spike-band rms (median 7.3 µV, 6.2–11.0) and LFP rms (163 µV) are
  the same as the other blocks'. **Physical shank order set by the user: blocks 48–63, 0/16/18–31, 1–15+17, 32–47 (ProbeMaps shanks 1, 4, 3, 2)** —
  the XML's groups were re-ordered accordingly (repo file + staged `amplifier.xml`); the ProbeMaps block → shank assignment does not hold for the
  SF08/SF12 wiring, and SF08's XML (same wiring) still has the old 1-2-3-4 order pending the user's word.
- **Adopted (user, 2026-09-08 evening).** `probes_2026c.yaml` now points SF08 and SF12 at their data-order XMLs (`verified: true` = user-inspected
  in Neuroscope; SF08 approved as is; SF12's group order was briefly set to the user's Neuroscope reading 1,4,3,2 and then put BACK to SF08's
  1,2,3,4 at the user's request — "估计是碰到 hippocampus curvature 了": the apparent shank re-ordering is the hippocampus curving under the
  four shanks, not the wiring, so both animals keep the same block → group order); staged `amplifier.xml` copies refreshed; the sort folders of the
  already-sorted SF08/SF12 sessions are untouched (re-sort is a separate decision; today = XML only, FM64 test parked). **Bridged pins: documented,
  NOT skipped.** I had first marked the duplicates `skip=1` ("Mark 吧"), the user then corrected: "短接不要标 skip，在 doc 上标注即可，不要改 XML" —
  hardware fault, LFP / ripple features unaffected. The skip marks were removed again (spike groups rebuilt = anatomical order minus skipped), the
  XML notes and the yaml `reject_channels` (SF08 [32] flat only, SF12 []) carry the cluster lists as documentation, and the clusters are listed here:
  SF12 {33,37} {43,45} {34,36,38} {44,46} {8,10} {12,14,17} {1,3,5} {21,23}; SF08 {53,55}. Consequence for sorting: a spike near a bridged node appears
  identically on 2–3 columns — Kilosort will fit one template spanning them, which is harmless for unit counts; bear it in mind when reading
  footprints. `ephys/selftest.py` 20/20 after the config change.
- **SF09 (A5x12_16-Buz_lin-5mm-100-200-160_177), last 10 min of `16_20260903_001828.515` (22691–23291 s, 455 ripples; dead 2 4 32 36 52 54 56 58 60 62).**
  User's instruction: take the shank GROUPING from the ProbeMaps `version2` XML (the 16-site middle shank = "middle finger") and order the sites of each
  of the five shanks by the LFP. `version2` = `version1` with the probe connector rotated 180° on the pin grid (checked: 64/64 channels map exactly);
  which one applies depends on how the connector was plugged. Grouping XMLs in exported columns (bank-0 +1 rotation): `SF09_A5x12-Buz_v2grouping_rot+1_0.xml`
  (v2 shanks = cols 14 7 13 8 17 5 15 6 11 10 12 9 / 2 29 1 24 4 22 3 25 30 26 0 28 / 61 31 57 27 53 23 49 19 48 16 51 21 50 18 52 20 / 59 32 56 33 54 34
  55 35 58 62 60 63 / 39 44 38 45 37 46 36 47 40 43 41 42) and `SF09_A5x12-Buz_v1grouping_rot+1_0.xml`. **Candidate `SF09_A5x12-Buz_v2grouping_dataorder_20260908.xml`**
  (LFP order inside the v2 groups, dead columns skip at the end; copy as `amplifier.xml` in the staged folder) — NOT adopted, `probes_2026c.yaml` still points
  at the 5-shank co-activation XML. Caveats from the same copy: (1) under the v2 grouping only shank 1 (11 positive-SPW sites + col 17) and shank 5 (10 radiatum
  sites + col 47) read as one population each; shanks 2, 3, 4 interleave pyramidal (+150…+350 µV) and radiatum (−60…−730 µV) columns, so their LFP order is a
  sort of two populations, not a depth sequence; v1 is worse (spw tv 2.5–7.0, up to 10 reversals). (2) The spike-band correlation splits SF09 into a
  pyramidal population (32 cols, bank 0 plus 47 48 50 59 61 63) and a radiatum population (18 cols, bank 1 plus 3 and 17) with 4 isolated columns (21 25 51 55);
  inside them the partner structure shows blocks {16 18 20 31 0 29 (+48 50 59 61 63)}, {19 26 27 28 30 22 24 23 15 47}, {5–14 + 1}, {39 46 40 35 41 38 17 3 42 37 33 44},
  {34 45 53 57 43 49}. The v2 grouping puts 42/54 live columns into their block, v1 38/54, the 09-07 co-activation XML 50/54 — i.e. neither plug of the
  ProbeMaps map reproduces the blocks the spikes define. Whole blocks being pyramidal or radiatum fits a Buzsaki-tip design (8 clustered tip sites + linear
  sites above) sitting at different depths per shank, but that is an interpretation for the user's Neuroscope check, not a result.
- **SF09 geometry decides the question, and it favours `version1` (user: "我觉得 47-36 更像是 middle finger 呢因为更深" → "所以或许是 ver1 按照 v1
  reorder 吧").** `ProbeMaps/Neuronexus/A5x12-16-Buz-lin-5mm-100-200-160-177_electrodes_coordinates.csv`: the four 12-site shanks carry all their sites
  within **110 µm** (staggered, 10 µm steps — Buzsaki tip clusters, one depth each), while the middle 16-site shank spans **2700 µm** (13 sites at
  100 µm pitch from the tip plane down to −1200 µm, plus 3 sites at 500 µm steps up to +1500 µm). Consequences: (1) only the middle shank has a
  within-shank DEPTH order at all — ordering the 12-site tip clusters by LFP is meaningless (110 µm cannot resolve layers), it only changes the display
  order; (2) only the middle group may contain both SPW polarities, every tip cluster must be sign-uniform (a sign flip cannot come from impedance,
  unlike amplitude — see SF10). Scored on the staged copy (446 ripples): **version1** gives a textbook middle shank — 16 live sites reading
  `+272 +202 +200 +172 +155 +147 +127 → −153 −213 −220 −378 −479 −490 −619 −681 −857 µV` (spw tv 1.13), i.e. pyramidale → radiatum → deep, and two of
  its tip clusters are sign-uniform (group 4: nine positives + one −62; group 5: eleven positives + one −187). **version2** violates the criterion in
  four of its five groups. version1's remaining problem: groups 1 and 2 (cols 55 51 48 50 53 59 57 49 and 61 34 63 40 41 38 33 37, each with four dead
  columns) mix +136 with −733 and +149 with −784 — impossible for 110 µm clusters, so part of those columns belongs elsewhere; bank 1 carries 8 of the
  10 dead columns, which leaves those two clusters half-blind. **Candidate `SF09_A5x12-Buz_v1grouping_dataorder_20260908.xml`** (staged as
  `amplifier.xml`, the version2 candidate kept beside it as `v2grouping_order.xml`) — not adopted, awaiting the user's Neuroscope check. The user's
  reading is confirmed in substance: seven of the twelve columns of the 36–47 block (39 42 43 44 45 46 47) sit in version1's middle shank, and they are
  its deep half; the shallow half is bank 0 (14 12 11 13 7 15 + 47).
- **SF09 re-run after the user's datasheet reading ("middle finger 应该有三个 cortical channel，51 肯定是 21 肯定是，那这么说现在的 shank 依然
  不能确定，SF9 需要重跑").** The A5x12-16-Buz datasheet: the centre shank carries 3 sites at 500 µm steps (1500 µm above the dense part, i.e. in cortex)
  plus 13 sites at 100 µm over 1200 µm; the four side shanks are tip clusters (12 sites, 20 µm spacing, 110 µm total). **The three cortical sites are
  columns 21, 51, 55** — the only columns whose ripple power is at the floor (13.3 / 15.6 / 17.4 vs 29–110 elsewhere) and which correlate with nothing
  (max r to any other column 0.12 / 0.09 / 0.18); the user had identified 21 and 51, the data adds 55 and rules out 25 (ripple 28.7, max r 0.20).
  Because a tip cluster's sites are 20 µm apart they must correlate strongly and read one depth, so the grouping was rebuilt from the spike-band
  correlation instead of any ProbeMaps mating: **`ephys/configs/xml/SF09_reconstructed_20260908.xml`** (staged as `amplifier.xml`; the version1 and
  version2 candidates kept beside it as `v1grouping_order.xml` / `v2grouping_order.xml`). Centre shank = 21 51 55 + the ladder −62 −187 −313 −377 −423
  −479 −490 −538 −619 −681 −733 −744 −784 −857 µV (cols 0 29 59 57 41 43 17 38 3 42 49 33 37 44): steps median 56 µV, ripple power falling monotonically
  80 → 29, and neighbour correlation 0.27 against 0.15 for sites ≥ 4 apart — a chain, as a 100 µm array should be. Side shanks: A = 15 19 22 23 24 25 26
  27 28 30 47 (r 0.37, SPW +156…+355), B = 1 5 6 7 8 9 10 11 12 13 14 (r 0.25, +127…+260), C = 16 18 20 31 48 50 61 63 (r 0.42, +209…−158),
  D = 34 35 39 40 45 46 53 (r 0.32, −10…−378). **Corrected after the user asked why there was a sixth group** ("不对不应该有组 6 吧"): columns 0, 29
  and 59, which I had put at the shallow end of the centre ladder, correlate far better with side shank C (0.39 / 0.40 / 0.36) than with the centre
  (0.15 / 0.16 / 0.17) and belong to C; the centre keeps 11 live ladder sites (−377 … −857 µV, steps median 51 µV) plus the 3 cortical columns. With
  that correction the **counts close exactly on the design 12/12/16/12/12**: side A 11 live + 1, side B 11 + 1, side C 11 + 1, side D 7 + 5,
  centre 14 + 2 = the ten dead columns, with the two bank-0 dead (2, 4) in the two all-bank-0 side shanks and the eight bank-1 dead split 1/5/2 over
  C, D and the centre. So there is no sixth group any more: every dead column sits INSIDE a shank with `skip=1` (the user's standing rule), and the
  centre shank's dense part being entirely negative is what the geometry predicts — it hangs 1200 µm BELOW the side-shank tips, while its three
  cortical sites are 500–1500 µm above them. Groups are written in the physical row order side, side, CENTRE, side, side, the side shanks sorted by
  depth (+355…+156, +260…+127, +209…−313 straddling the reversal, −10…−378), which assumes the depth gradient across the 800 µm row is monotone
  (hippocampal curvature). **Not determined:** which particular bank-1 dead column belongs to which of C / D / centre — flat channels carry no
  correlation (group spread 0.03–0.05), only the counts are fixed; and side C spans 522 µV, which needs the tip cluster to straddle the sharp-wave
  reversal (possible over 110 µm, since the gradient is steepest there).
- **Dead columns are PACE MAKERS, not tail padding (user, 2026-09-08: "dead channel 不能在最后，因为这样会影响对 channel 物理位置的判断，dead
  channel 的归属可以根据 LFP 梯度 difference 给出，我知道到底是谁未知但我们需要这样的 pace maker").** Each dead column is now inserted where its shank's
  sharp-wave gradient shows the largest gap (greedy, recomputed after each insertion), `skip=1`, so every live site keeps its physical position; the identity
  of the dead site stays unknown and the XML says so. Applied to SF09 (2 → side 1 between 47 and 25, gap 46 µV vs median step 13; 4 → side 2 between 9 and 10;
  36 and 52 → the centre ladder between 38/3 (81 µV) and 37/44 (73 µV); 32 → side 4 between 29 and 59, 127 µV vs median 43; 54 56 58 60 62 → side 5, which has
  5 dead of 12 and takes one in nearly every gap), to **SF08** (32 between 36 and 45, gap 228 µV vs median step 5) and to **SF10** (2 between 7 and 11,
  372 µV vs median 9; 34 between 39 and 45, 115 µV; 32 between 47 and 43, 118 µV; the all-dead shank 1 left as it is). The rule replaces the withdrawn
  correlation-gap estimator inside `lfp_profile_check.py --derive-xml`; staged `amplifier.xml` copies refreshed; `ephys/selftest.py` 20/20.
- **Bridged duplicates now skipped IN PLACE (user, 2026-09-08: "SF12 将重复连接点放到 skip 里但注意要占位").** The earlier decision (document only)
  is superseded: on SF12 the eleven redundant columns of the eight bridged clusters (37 45 36 38 46 10 14 17 3 5 23 — the lowest column of each cluster
  stays live) carry `skip=1` while keeping their position in the depth order, so the remaining sites are not shifted; SF08's 55 likewise (53 stays live).
  Sorting now runs on 16/11/11/15 channels per shank for SF12 and 15/15/16/16 for SF08. Which member of a bridged cluster is the electrode's own pin is
  unknown — bridged pins see the same potential — so the choice of the surviving column is arbitrary and recorded as such. `probes_2026c.yaml`
  `reject_channels` updated (SF12 eleven columns, SF08 [32, 55]); SF10 needed nothing new here (no bridged clusters; its three broken columns were already
  placed as gradient pace makers). Staged `amplifier.xml` copies refreshed, selftest 20/20.
- **Is SF07's probe denser? No — SF07 carries a large COMMON-MODE signal (user's impression "感觉 SF7 density 更高", tested with LFP only;
  unit footprints from the existing sorts are not admissible because those sorts used the older XMLs — user, 2026-09-08).** Measured on the staged
  10-min copies: ripple extent (channels whose ripple-band power, baseline of the shank removed, reaches 50 % of that shank's peak) is 4.8 of 16 on
  SF07 against 4.5 (SF08), 3.8 (SF12), 2.7 (SF10) and 5.2 of 10.8 (SF09) — no clear difference. What IS different is that SF07's profiles are almost
  flat: sharp-wave range per shank 31–60 µV (second session 67–144) against 122–938 µV elsewhere, and ripple power peak/floor 1.1–1.4 (second session
  1.9–2.8) against 1.8–7.6. Density cannot explain that, for two reasons. (1) The flatness holds BETWEEN shanks 300 µm apart: the 300–3000 Hz
  correlation between different shanks is 0.50 / 0.58 on SF07's two sessions against 0.08–0.18 on the others, and the first principal component takes
  51 % / 59 % of the variance against 12–23 % — a common signal on all 64 channels, not proximity. (2) A 20 µm pitch instead of 50 µm would compress the
  depth coverage 2.5×, so the sharp-wave range could shrink 2.5×; observed is 5–15×. Both SF07 sessions behave the same, so this is a property of that
  implant/logger (reference or ground path), not of one window; together with "only positive sharp waves" it is why SF07 is unusable as a control for
  the LFP method. Its shank GROUPING (verified twice) is unaffected — the common mode is shared by all channels and cancels in the depth profile.
- Artefacts: `results/2026c/ephys_spikes/reports/ephys_spikes_lfp_profile_check_2026c.csv` (candidate rankings, 09-02 runs); the 09-08
  profile / permutation / physical / parity outputs are in the session scratchpad (`sf10_last10_profile.txt`, `sf10_last10_physical.txt`,
  `sf10_parity_seriation.txt`).

## Addendum 2026-09-08 (night) — the Neurologger repo settles the shank membership on hardware grounds

Operator's question: "读一下 datalogger repo 可以确定 shank member 是一定的么 …这个必须要准". Answer: **yes for the four-shank animals**, and the
evidence is hardware, not inference. Three independent pieces, all checked in this session rather than taken on trust:

- **`PCB/Datalogger/WILD64_HDI.sch` (Autodesk Eagle XML) is a real netlist** and fixes Omnetics pin ↔ RHD2164 input for all 64 inputs
  (parsed here: 64 `IN*` nets, each with one `S1`/`S3` pin and one `U$1` pin; `S1` = front / Intan-chip side, `S3` = back / microSD side;
  GND = T18 & B1, REF = T1 & B18). There is no firmware source in the repo (`Firmware/` holds only .hex/.bin), so the export reorder itself
  cannot be audited there.
- **`docs/images/WIrelessEphys_Github_8_connectors.jpg` is the only statement of the export order** — panel 1 "Channel order in Amplifier.dat
  (Reordered)" prints, at each connector pin, the amplifier.dat column; panel 2 "Original channel order" prints the Intan input at the same pin.
  Read directly from the image here and checked three ways: panel 2 reproduces the schematic netlist 64/64 (mirrored on S1, as drawn on S3);
  the 20 green "same definition" pins all satisfy column == Intan under the composition; and the composition matches an independent transcription.
- **Panel 1 is byte-for-byte the pin grid this repo already uses** (`probe_map_check.INTAN64_PINS`): rows 46 44 … 16 / 47 45 … 17 /
  49 51 … 15 / 48 50 … 14. So the firmware's INTENDED export order puts at every pin the column number a standard Intan headstage would give
  that pin — which is exactly why ProbeMaps Intan numbers can be read as exported columns. The one-slot bank-0 rotation we correct with
  `rotation_permutation(+1, 0)` is the measured deviation from that intent (the FM57-type fault, validated on SF07: agreement 1.00 vs 0.29).

**Consequence — the grouping is mating-invariant.** On the A4x16-Lin each shank occupies exactly one 2×8 pin block, and the four column sets
`{48–63}`, `{32–47}`, `{1–15, 17}`, `{0, 16, 18–31}` are identical under all 16 possible matings (checked by enumeration). However the probe was
plugged in — either connector, either orientation, mirrored or not — those four sets are the four shanks. They are the sets our XMLs already use,
so **SF07 / SF08 / SF10 / SF11 / SF12 shank membership is certain**. What the hardware does NOT fix, and what the LFP work had to settle, is which
physical shank each set is and the site order inside it.

**SF09 is the exception.** On the A5x12-16-Buz only shanks 1 and 5 sit in a single pin block; shanks 2, 3 and 4 straddle two blocks, so their
membership depends on the mating and cannot be read off the hardware. SF09's grouping therefore still rests on the data reconstruction
(`SF09_reconstructed_20260908.xml`), not on the netlist.

**Discrepancy to keep in mind:** the console table `ephys/configs/wild_ce64_channel_map_v57.csv` (`WILDIntanmapped`) agrees with the figure's
column→Intan map on 32 of 64 columns and differs by pairwise swaps on columns 0–15 and 48–63. Our XMLs do not use that table (they use the vendor
rotation script), but the two documents are not the same map and only the figure is corroborated by the netlist.

## Addendum 2026-09-09 (01:23) — FM64 salvage answered on SF12 with the settled map: sortable only with a template-shape filter

Operator's instruction (2026-09-08 21:30): delete the Kilosort output made with the superseded XMLs, then run ONE animal to find out whether de-glitched
FM64 can be spike-sorted, finishing before the 06:00 card offload.

- **Deleted** (analysis folder only, raw folders and `recovery.bin` untouched): `sort/SF08/13_20260902_082748.094`, `sort/SF09/10_20260902_083015.335`,
  `sort/SF09/_superseded`, `sort/SF11/12_20260902_083534.755`, `sort/SF12/11_20260902_083748.804` — 434 GB. SF07 (map never changed) and SF10 (today's edit
  moved only skip channels) were kept. The numbers of the deleted runs live on in commit 2a6c47c.
- **Design.** SF12, matched 3-h morning windows, same XML (`SF12_A4x16-Lin_dataorder_20260908.xml`, spike groups 16/11/11/15), same settings, sequential:
  FM64 `0_20260901_080334.683` (08:03, 908 ticks/s; de-glitch removed 11,684,684 ticks, 225 left; staged 29 min, sorted 88 min) and FM65
  `11_20260902_083748.804` (08:37, untouched; staged 20 min, sorted 81 min).
- **Result.**

  | | accepted templates | one-sample | impulse-shaped (ratio < 0.4) | FWHM median | candidates | < 3 Hz | well-isolated |
  |---|---|---|---|---|---|---|---|
  | FM64 de-glitched | 125 | 45 (36 %) | 48 (38 %) | 3.0 | 183 | 144 | 26 |
  | FM65 control | 62 | 3 (5 %) | 3 (5 %) | 4.0 | 101 | 85 | 20 |

  The artefacts are a band-pass-filtered single-sample impulse — e.g. `-4.7 -6.1 +7.2 -11.0 +22.5 +76.0 +18.6 -17.6 -2.3` against a real spike's
  `+55.6 +56.4 +45.2 -23.4 -118.9 -154.9 -137.9 -108.0`. The neighbour/peak ratio of the peak-channel template separates them: bimodal on FM64
  (quartiles 0.23 / 0.92, deciles 0.20 / 0.96), unimodal on FM65 (0.79 / 0.91). On FM64 the impulse population fires faster (1.5 vs 0.8 Hz) with lower SNR
  (3.2 vs 4.5) and smaller amplitude (31 vs 46 uV) than the normal-shaped population, which itself matches FM65's (SNR 4.3, 41 uV).
- **Verdict.** De-glitched FM64 is usable for spike sorting **provided units with neighbour/peak ratio < 0.4 are rejected**; the real units survive the
  de-glitch (77 normal-shaped units on FM64 vs 59 on FM65 in the same 3 h). Without that filter roughly two units in five would be defect residue.
  This also answers the SF07 puzzle only partly: SF07's FM64 gave 55 % one-sample at 13 ticks/s, far more than SF12 at 908 ticks/s, so on SF07 the residue is
  not the whole story — its 51-59 % common-mode component is the likelier cause and its FM64 sort should not be used.
- Not tested here: whether the surviving units' waveforms are subtly distorted by the 0.3-0.55 % of samples the de-glitch replaces.

## Addendum 2026-09-09 (02:35) — correction: Kilosort1 CAN run on this PC; KS4 was not a speed choice

Operator: "其实 KS4 不适合海马，这个我们对比过了。所以我们依然在用 KS1。KS4 是更快么？" — no, speed was never the reason. The record since
2026-09-02 said MATLAB R2021b cannot drive the Blackwell GPU, so Kilosort1/2.5 were unusable and Kilosort4 was the only sorter. **That record was wrong,
and is corrected here.** Tested tonight on this machine:

- `gpuDevice` on R2021b Update 2 fails with `parallel:gpu:device:DeviceTooNew` (compute capability 12.0 against the bundled CUDA 11.0) **but the error
  itself points at the way out**: `parallel.gpu.enableCUDAForwardCompatibility(true)`. With it, MATLAB recompiles its GPU libraries once (521 s here) and
  then reports `NVIDIA GeForce RTX 5070 Ti | CC 12.0 | supported 1 | toolkit 11.0`; a 2000×2000 single matmul matches the CPU to 1.8e-4 and a 2^20 FFT runs.
- Visual Studio Community 2019 is installed and is a supported compiler for R2021b. From a copy of the lab checkout at
  `E:rd_rat_spikesnalysis	ools\KiloSort1_field2026` (the lab checkout stays untouched), all three KiloSort1 CUDA MEX files compile with
  `mexcuda -largeArrayDims <f>.cu NVCC_FLAGS='-allow-unsupported-compiler -gencode=arch=compute_80,code=compute_80'` — PTX only, JIT'd by the driver —
  and `mexWtW2` then executes on the GPU (output 32×32×121 for nt0 = 61, all finite).
- The pipeline already supports KS1: `sorter/Kilosort1_config.yaml` (the lab's parameters: Th 6/10/10, lam 12/40/40, full whitening, 500–8000 Hz) and a
  MATLAB launcher in `src/preprocess/sorter_runner.py`.

**Consequences for what is on record.** The channel-map / XML work is sorter-independent and stands. Everything at the unit level — the yield tables in
`results/2026c/ephys_spikes/`, and tonight's FM64 verdict (38 % of accepted units are de-glitch residue with an impulse-shaped template) — was measured with
Kilosort4 and has to be re-measured with KS1 if KS1 is the lab's sorter: the residue is a property of the data, but the fraction a sorter turns into units,
and the 0.4 neighbour/peak cut that separates them, are KS4-specific.

**Not yet done:** a full KS1 run. Three things need settling first — pointing the pipeline at the compiled copy, making sure the MATLAB session the pipeline
launches has forward compatibility enabled (it is a session setting), and sanity-checking a KS1 output under forward compatibility, which MathWorks warns
"might show unexpected behavior". The natural test is the SF12 3-h FM64/FM65 windows already staged, so KS1 and KS4 can be compared on identical data.
Not started tonight: it would still be running during the 06:00 card offload.
