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

## Caveats / not done

- Probe channel→shank mapping unverified (finding 2). µV scale relative. Cross-modal time alignment unverified
  until `WILD_generate_pc_time.py` fits pass (run on the RAW folders; staged copies omit `analogin.dat`).
- The 30-s probe windows are samples; a regime confined to an unsampled stretch is missed (5 windows reduce
  but do not remove this).
- SF07 has no offloaded sessions yet; FM65 sessions (copied 2026-09-02 onward) are unevaluated — re-run the
  index when they land; their `measured_verdict` is the evidence that FM65 is clean.
- No scientific claim is made; `analyses/registry.yaml` unchanged (no question entry yet).
