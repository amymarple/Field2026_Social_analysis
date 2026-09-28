# `ephys/` — WILD neurologger spike-sorting pipeline (direction `ephys_spikes`)

Cohort-agnostic tooling for the head-mounted **WILD CE64 neurologgers** (64 ch @ 20 kHz int16 on SD, BLE
sync) introduced with the 3rd rat cohort (`cohorts/2026c.yaml`). It prepares clean, provenance-tracked
working copies of raw sessions and drives the lab's
[PreprocessPipeline](https://github.com/yoshihito-saito/PreprocessPipeline) (spikeinterface 0.103.2 + Kilosort4)
on them. Raw data are **never modified**; every derived file carries a manifest.

```
raw offload (E:\3rd_rat_spikes\<SFxx>\<MAC>\<slot>_<date>_<time>.<ms>\)          <- read-only
   (a <MAC> folder that is NOT the animal's registered logger in cohorts/<cohort>.yaml ephys.loggers = a FOREIGN logger's
    card: skipped by every script, listed in the index MD; move it to <root>\_other_loggers\<MAC>\)
   |  build_session_index.py   firmware + duration + MEASURED glitch probe per session
   v
results/<cohort>/ephys_spikes/reports/ephys_spikes_session_index_<cohort>.{csv,md,json}   (+ SESSION_INDEX.* mirrored at the data root)
   |  stage_session.py         firmware gate -> deglitch_wild.py (FM < 65) or verbatim copy; XML from probes_<cohort>.yaml
   v
<OUT_ROOT>/<cohort>/ephys_stage/<SFxx>/<session>/   amplifier.dat (clean) + info.rhd + CE_params.bin + time.dat + <session>.xml + manifests
   |  run_sort_session.py      PreprocessPipeline: bandpass/CMR/artifacts -> .dat/.lfp -> Kilosort4 (per shank) -> postprocess -> Phy
   v
<OUT_ROOT>/<cohort>/ephys_sort/<SFxx>/<session>/    + sort_manifest.json ; one row in results/.../ephys_spikes_sort_runs_<cohort>.csv
```

`<OUT_ROOT>` = `FIELD2026_ANALYSIS_OUT_ROOT` (this machine: `G:\Field2026_analysis_out`) **unless the cohort declares
`ephys.analysis_root`** — cohort `2026c` does (`E:\3rd_rat_spikes\analysis\`, user decision 2026-09-03 after G: dropped
off the PC): then `stage/`, `sort/`, `tools/`, `pc_time/` and the `index/` mirror live under that folder. Nothing is ever
written into a raw session folder.

## Why a cleaning step exists ("artificial spikes")

Every cohort-3 session recorded before the 2026-09-01 ~19:30 firmware upgrade (header `firmware_version`
**FM62 / FM64**) carries two single-sample acquisition defects that look like spikes in Neuroscope but are
50 µs wide (field2026-sync `from-field/2026-09-01_fm59-62-signal-defects.md`):

- **A — channel substitution**: an isolated sample carries another fixed channel's value (both polarities,
  ~100–1,400 ticks/s summed over 64 ch, continuous, channel-specific).
- **B — 15-s housekeeping injection**: one-sample deflections to ≈ −21,650 ADC synchronised across channels
  (slow-ADC mux corrupting the amplifier frame).

`deglitch_wild.py` is a byte-for-byte numerical port of the field-validated
`from-field/2026-09-01_deglitch_wild.py` (5-point running median; replace samples with
`|x − med5| > max(10·1.4826·MAD, 500 ADC)`; validated 99.7 % tick removal, 0.17 % samples replaced,
spike-safe on SF10 `5_20260901_054403.494`). **FM65** (maker fix) sessions are copied verbatim, and the index's
measured `ticks_per_s` is the evidence that they really are clean.

Firmware history (user + Notion, confirmed from headers): FM62 = stop-only file commit (night-1 loss) +
glitches; FM64 = glitches; FM65 = fixed, unevaluated until offloaded. `recovery.bin` per animal is the raw card
image kept for a future forensic recovery of the FM59–62 uncommitted sessions; never parsed here.

## Commands

```bash
# 0. offline self-test (no field data; base python is enough)
python ephys/selftest.py

# 1. index (firmware + measured glitch probe per session; mirrors SESSION_INDEX.* to the data root)
python ephys/build_session_index.py --cohort 2026c

# 2. stage one or more sessions (de-glitch by the firmware gate; --force-deglitch / --skip-deglitch override)
python ephys/stage_session.py --cohort 2026c --animal SF10 --session 5_20260901_054403.494

# 3. sort (run inside the PreprocessPipeline `preprocess` conda env: conda activate preprocess)
python ephys/run_sort_session.py --cohort 2026c --animal SF10 --session 5_20260901_054403.494 --partition shank
#   postprocess mode (manifest key post_mode): default `fast` since 2026-09-04 = features on <= 500 spikes/unit (--post-max-spikes),
#   no PCA autosplit, no Phy pc_features -> minutes per shank on an 8-h session; `--post-full` = the pipeline's all-spike passes (~2.7 h per shank)

# QC: does the assumed shank grouping match the data? (LFP correlation blocks, ARI)
python ephys/probe_group_check.py --cohort 2026c --animal SF8 --session 0_20260831_190133.486

# Timestamp QC: the field's BLE PC-time anchor fit, per RAW session, written OFF the raw tree
#   (the script's default drops pc_time.dat + a JPG into the raw folder; always pass -o and --summary-plot <path>;
#    a G:\ output path fails with WinError 3 in this script, so write to a C:\ temp dir and move)
python C:/Users/Cornell/Documents/GitHub/Neurologger/Code/WILD_generate_pc_time.py E:/3rd_rat_spikes/SF7/D0DBEFEF3111/<session> \
       -o <tmp>/SF07/<session>/pc_time.dat --summary-plot <tmp>/SF07/<session>/pc_time_fit_summary.jpg > <tmp>/SF07/<session>/pc_time_summary.txt
#   then move <tmp>/SF07/<session> to G:/Field2026_analysis_out/2026c/ephys_pc_time/SF07/<session>/

# Offload QC report (timeline continuity, RTC/folder agreement, sidecars, FM64-vs-FM65 measured glitch stats, PC-time fits)
python ephys/offload_qc_report.py --cohort 2026c      # -> results/2026c/ephys_spikes/reports/ephys_spikes_offload_qc_2026c.{md,csv}

# 4. unit yield over every sorted session (< 3 Hz hippocampal count, candidates, well-isolated, per shank; runs still in progress are
#    included — shanks without a _spi folder are read from the raw Kilosort4 output, stage `ks4-raw`)
python ephys/unit_yield_report.py --cohort 2026c      # -> results/2026c/ephys_spikes/reports/ephys_spikes_ks4_unit_yield_2026c.{md,csv} + figure

# 5. MANUAL INSPECTION in Phy (conda env phy2, phy 2.0b6): opens the postprocessed _spi folder (or --raw for the KS4 folder)
python ephys/open_phy.py --cohort 2026c --list
python ephys/open_phy.py --cohort 2026c --animal SF07 --session 15_20260902_082418.755 --shank 1
#   Phy needs the filtered 64-ch .dat next to the shank folders (params.py: dat_path = ../<session>.dat) — keep the
#   session folder under <analysis_root>/sort/ intact. Curation (good/mua/noise, merges) is saved in that folder's
#   cluster_group.tsv / cluster_info.tsv; re-run unit_yield_report.py afterwards to count curated units.
#   Sessions postprocessed in `fast` mode have no pc_features.npy (FeatureView empty); use --raw (Kilosort's own features)
#   or re-run run_sort_session.py --post-full for the sessions you curate in depth.
```

Small example sessions (all pre-FM65, so all go through de-glitching; staged 2026-09-02):

| animal | session | firmware | length | de-glitch result | use |
|---|---|---|---|---|---|
| SF8 | `0_20260831_190133.486` | FM64 | 45 s | ticks 11,112 → 0 | fastest smoke test |
| SF10 | `5_20260901_054403.494` | FM64 | 50 s | 108,584 samples replaced, ticks 23,679 → 64 (= the field validation numbers) | reference session; first full sort (4 shanks → Phy in 4.5 min, 2026-09-02) |
| SF8 | `2_20260901_002327.839` `--window-s 3600 600` | FM64 | 10 min (night, 01:23) | ticks 639,597 → 1 | realistic Kilosort4 run on a night slice |
| SF12 | `1_20260831_071033.005` | FM62 | ~8 min | ticks 5.0M → 2.9M (43 %) | **counter-example**: morning battery-round record; wide (≥3-sample) impulses that the median rule cannot remove |
| SF8 | `0_20260831_070148.859` | FM62 | ~10.6 min | see index (`regime`) | same regime as above |

The two FM62 morning-round records (07:0x–07:2x, rats in hand) and the FM62 daytime sessions of SF8/SF9
(08-31, raw std 4–8× the night level, >15k ticks/s of 2–7-sample impulses) are a **different noise regime**
from the single-sample FM62/64 defect. `build_session_index.py` flags them (`regime = wide-impulse` /
`broadband`, `tick_removal_frac`); treat them as QC-fail candidates, not as "cleaned by de-glitching". Night
FM64 sessions (raw std ≈ 550–1000 ADC, 340–840 ticks/s, single-sample) are the well-behaved case.

## Files

| file | role |
|---|---|
| `_common.py` | cohort registry (`ephys:` block of `cohorts/<key>.yaml`), output roots, session-name parsing, fingerprints |
| `check_offload_sizes.py` | after each card export: predicted card bytes (amplifier x 65/64) vs the console's Records / Total File Size listing, sidecar sizes, still-growing check -> SAFE TO FORMAT / CHECK / WAIT per card. Selects each card's folders as the N newest on disk (slot numbers restart at 0 per format, so they are not unique); `--since` is only an override |
| `field_request.py` | after QC: writes the request to the field-PC agent into field2026-sync/tasks (routine files needed through the newest Stop on disk, ends the lab could not anchor that the PC marks do not cover, findings, unsettled clock steps); `--push`, `--check`. Driven by the `offload-field-request` skill |
| `run_qc.sh` | the whole post-offload QC in one command: index (8 workers) -> pc_time_chain --write-pc-time -> offload_qc_report -> coverage_tables -> mirror to <analysis_root>/index/. `bash ephys/run_qc.sh 2026c` |
| `wild_ce_params.py` | `CE_params.bin` parser (firmware @328, RTC start, MAC, fs, Nch); layout from `Neurologger/Code/WILD_ReadHeader.m` |
| `signal_probe.py` | 30-s probe: glitch samples/s, ticks/s, spike-band noise (µV), dead/broken channel candidates |
| `build_session_index.py` | the session index (CSV/MD/JSON + data-root mirror) |
| `deglitch_wild.py` | the cleaning step (free output path, report, manifest, before/after tick verification) |
| `make_session_xml.py` | Neuroscope XML with shank groups + `skip` flags from `configs/probes_<cohort>.yaml` |
| `stage_session.py` | raw → clean staged working copy + `stage_manifest.json` |
| `run_sort_session.py` | PreprocessPipeline driver (preprocess → Kilosort4 → postprocess) + `sort_manifest.json` |
| `probe_group_check.py` | data-driven check of the assumed channel→shank grouping |
| `footprint_map_check.py` | channel-map test #2: unit-footprint compactness over 1,296 connector matings × bank rotations (needs a sorted session; validated on SF07 — its verified map ranks 1/1296). `--trigger` (raw channel-triggered) failed validation, do not use |
| `resort_shanks.py` | re-sort SELECTED shanks of a sorted session with a new XML, re-using the preprocessed .dat (Kilosort4 on those partitions only, old folders → `<sort_root>/<animal>/_superseded/…`, one fast postprocess over all shanks). Used for SF10 after the A180 mating was found; caveat: the .dat's local CMR neighbourhoods follow the old site order |
| `lfp_profile_check.py` | channel-map test #3 (user's method, 2026-09-08): per-shank depth profiles of the ripple-triggered sharp wave, ripple power and theta phase, scored by total variation (1 = monotonic), over the 16 matings × bank rotations or `--physical` (pin shifts with predicted dead columns); `--raw DIR --xml` reads a staged 10-min copy directly (no sort folder); `--bad` for user-marked broken columns; `--permute-tail`; `--derive-xml --keep-groups` writes a DATA-DERIVED within-shank order (positive-SPW sites by ripple power asc, then negative-SPW by SPW desc). Validated on SF07 (rank 1) and SF10's connector-B shank (Spearman 0.97); SF10's derived order reproduced on a second session. The printed spike-band "gap" estimate is NOT a distance when site impedances differ (see the docstring) |
| `wiring_pattern_check.py` | channel-map test #4: is a data-derived within-shank order a REGULAR pin routing (zigzag / serpentine / row-major / fan-out / ProbeMaps shank routings × symmetries) on the shank's 2 × 8 pin block? Scores like test #3 on a staged copy; SF08 2026-09-08: no (data order ranks 1, neighbouring-pin fraction at chance). Negative results do not exclude an irregular vendor pinout |
| `bridged_pins_check.py` | are two columns with near-identical signals ONE electrode node (bridged connector pins) or two close sites of a high-density design? Difference-signal test: bridged pairs leave only amplifier noise (spike-band ratio ~0.35, LFP residual 1-3 %, no spike events); distinct neighbours keep spikes and an LFP gradient. SF12 2026-09-08: 8 clusters (19 columns) bridged; SF08 53/55 bridged |
| `template_width_check.py` | FM64 salvage step 2: one-sample-wide Phy templates (defect residue) per accepted unit; FM65 baseline 3–8 %, SF10 FM64 39 % |
| `offload_qc_report.py` | per-offload QC report: per-animal session timeline + gaps/overlaps, RTC-vs-folder, sidecar sizes, measured FM64-vs-FM65 glitch statistics (per-logger relative rule), BLE PC-time fit verdicts (from `pc_time_chain.py`), card-duration-vs-field-PC-span check with known clock steps |
| `coverage_tables.py` | hourly minutes per logger per day, per-second coverage CSV per day (firmware code per logger per local second), raster figure; mirrored to `<analysis_root>/index/` |
| `integrity_scan.py` | repeated/overlaid-data test (blake2b of every 64 KiB block, within a session and across neighbours) + per-channel corruption tests (rail, flat, stuck, duplicate, identity drift) on sampled windows; `--firmware 65 --full-hash` |
| `pc_time_chain.py` | **the timestamp fit to use**: decodes the BLE field-PC anchors from `analogin.dat` lanes 14/15, models the 86,400,000-ms day wrap and the 2^20 packing, does NOT add the delay word, chains a session's missing end to the next session's start through the RTC (round protocol), reports per-session drift/offset/verdict, and with `--write-pc-time <root>` regenerates `pc_time.dat` (console format) + `pc_time_fit.json` per session. Supersedes the reference generator's output for this cohort. |
| `configs/probes_2026c.yaml` | per-animal probe groups / layout / reject channels — **UNVERIFIED placeholder mapping** |
| `configs/kilosort4_wild.yaml` | Kilosort4 parameters (upstream lab defaults, `n_jobs` sized for this PC) |
| `patches/*.patch` | proposed upstream fixes for PreprocessPipeline / its vendored Kilosort4 (see below); the lab checkout is never modified |
| `selftest.py` | synthetic end-to-end checks |

### PreprocessPipeline bugs found on 2026-09-02 (worked around, not patched in place)

| symptom | cause | how `run_sort_session.py` handles it | upstream proposal |
|---|---|---|---|
| Kilosort4 + `--partition shank`: `IndexError: Channel '16' was not in probe['chanMap']` | `execute_sorting_job` passes full-recording `bad_channels` although the recording is already the shank subset | runtime shim on `spikeinterface.sorters.run_sorter` drops `bad_channels` when any index lies outside the recording | `patches/preprocesspipeline-ks4-partition-bad-channels.patch` |
| vendored KS4 clustering: `TypeError: expected np.ndarray (got numpy.float64)` | lab amplitude feature turns a one-spike group into a NumPy scalar | Kilosort4 is copied to `<OUT_ROOT>/<cohort>/ephys_tools/Kilosort4_field2026/` with `np.atleast_1d` applied (`KS4_TEXT_PATCHES`), and that copy is passed as `sorter_path` | `patches/kilosort4-vendored-scalar-amplitude.patch` |
| Windows: `PermissionError: [WinError 32] … sorter_output\kilosort4.log` after a successful sort | Kilosort4 leaves its log FileHandler open; the pipeline then moves the file while flattening the folder | the same shim closes every logging FileHandler under the sorter folder as soon as `run_sorter` returns | `patches/preprocesspipeline-windows-ks4-log-lock.patch` |

Every `sort_manifest.json` records the Kilosort4 path used and the patches applied.

## Definitions (every derived quantity)

| symbol | formula | meaning / units |
|---|---|---|
| `n_samples` | `bytes(amplifier.dat) / (2 · n_channels)` | int16 samples per channel |
| `duration_s` | `n_samples / fs` | s; `end_local = start_local + duration_s` (logger wallclock = field-PC local time at Resync, EDT) |
| `med5_c(t)` | `median(x_c[t−2 … t+2])`, edge-replicated | 5-point running median, ADC |
| `MAD_c` | `median_t |dev_c − median(dev_c)|`, `dev_c = x_c − med5_c`, on 8 × 100k-sample blocks | robust scale of the residual, ADC |
| `thr_c` | `max(K·1.4826·MAD_c, FLOOR)`, K = 10, FLOOR = 500 ADC | per-channel replacement threshold (field defaults) |
| glitch sample | `|dev_c(t)| > thr_c` → `x_c(t) := med5_c(t)` | the only modification the cleaning step makes |
| `glitch_samples_per_s` | `Σ_c #glitch / duration` | replaced samples per second summed over channels (includes rare true-spike peaks) |
| `ticks_per_s` | `Σ_c #{ |x(t) − (x(t−1)+x(t+1))/2| > 1200 ADC } / duration` | the defects-note impulse metric; clean data ≈ 0 |
| `measured_verdict` | glitchy > 10 ticks/s, clean < 1, else ambiguous | data-side evidence per session (30-s window from the middle) |
| `noise_uV` | `1.4826 · median|hp| · 0.195`, hp = 500–5000 Hz of the de-glitched window | robust spike-band noise, µV **relative** (0.195 µV/ADC is the Intan default; the WILD header carries no scale) |
| bad-channel candidate | `noise_uV < 3` or `noise_uV > 4·median` or `raw_std < 0.25·median` | advisory dead/broken list (SF8 ch 32 is the known example) |
| ARI (probe check) | adjusted Rand index between assumed shank labels and average-linkage clusters of `1 − r_LFP` | 1 = identical partition, ~0 = chance; > 0.8 with within > between supports the mapping |

Sorting-stage definitions (bandpass, local CMR radius, high-amplitude artifact σ, Kilosort4 thresholds) are those
of PreprocessPipeline and are recorded verbatim in each `sort_manifest.json` (`preprocess_config`, sorter YAML).

## Channel map (which exported column is which probe site)

Established 2026-09-03 with `ephys/probe_map_check.py` (spike-footprint co-activation, map-independent) —
see the change log for the numbers:

- WILD Console applies its CE64 export map on download (`configs/wild_ce64_channel_map_v57.csv`), so bank 1
  (exported columns 32–63) is in Intan-headstage order and the ProbeMaps XML applies to it directly.
- **Bank 0 (columns 0–31) is rotated by one raw slot on FM64 AND FM65** (SF07 sessions 10 and 15 verified:
  agreement 1.00 on bank 0 with the correction vs 0.29 without). FM65 did not fix the channel order. The
  correction is the conjugated permutation in `vendor/correct_intan_dat_channel_order.py` (FM57 "+1" fault).
- Do not repair the data; use an XML in exported-column numbering instead: `ephys/make_probe_xml.py`
  writes it from the ProbeMaps XML + orientation + per-bank rotation, and `probes_<cohort>.yaml` points each
  animal at its XML (`xml:`). The vendor tool and an exported-column XML must never be combined.
- Verified: **SF07 = A4x16-Lin-5mm-50s-300, orientation v1_raw (the ProbeMaps "version1"), rot bank0 +1, bank1 0**
  (`configs/xml/SF07_A4x16-Lin_v1raw_rot+1_0.xml`). SF08/SF11/SF12 use the same file for the shank COLUMN SETS only (identical under all
  matings; grouping confirmed by co-activation) — SF07's within-shank ORDER is its own mating and is not a reference for
  any other animal (user, 2026-09-08); their order comes from test #3 below. **SF09 (5×12)** matches none of the 4 orientations × bank
  rotations of the ProbeMaps A5x12 XML (74 strong pairs, best 0.61 same-shank); it uses a DATA-DERIVED XML
  (`configs/xml/SF09_data_derived_3_20260831_190834.640.xml`: co-activation clusters as shanks, ordered along
  each shank spectrally, 35 channels in 7 groups + 29 unassigned/skipped) — valid for per-shank sorting only,
  no geometry claims.
- **Test #3 — LFP depth profile (2026-09-08, `lfp_profile_check.py`; user's method: order sites by the LFP, not by units).** On a shank crossing CA1 the sharp wave goes gradually positive (oriens / pyramidale) → negative (radiatum), ripple power peaks in the pyramidal layer and the theta phase shifts monotonically; a correct order makes all three profiles smooth. Ten minutes of a sleep-rich session suffice, read from a `stage_session.py --window-s` COPY (raw folders stay read-only). **SF10** (`configs/xml/SF10_A4x16-Lin_dataorder_20260908.xml`, user-inspected in Neuroscope): shank 4 keeps the standard order, shanks 2/3 use the data-derived order, which reproduced on a second session; shank 1 dead, columns 2/32/34 broken. SF10 shank 4's jagged look is IMPEDANCE, not order: its eight even-Intan sites (connector-B row 3) carry 4× smaller sharp waves, 20 % less LFP and a shared spike-band noise (r 0.47 with each other at any distance) — read amplitude before re-ordering.
- **Dead / broken columns are PACE MAKERS, never tail padding (user, 2026-09-08).** Each dead column is written `skip=1` at the position where its shank's sharp-wave gradient shows the largest gap (greedy, recomputed after each insertion), so every live site keeps its physical position; which site a dead column actually is stays unknown and the XML says so. Do not use the spike-band correlation "gap" estimate for this — high-impedance sites look isolated and mimic gaps; the sharp-wave gradient is the reliable quantity. Group membership follows from the counts when a known design constrains them (SF09: 12/12/16/12/12). `lfp_profile_check.py --derive-xml` applies the rule; SF08, SF09 and SF10 were re-written with it.
- **Probe GEOMETRY is part of the test (SF09, 2026-09-08).** `ProbeMaps/Neuronexus/<design>_electrodes_coordinates.csv` gives the site coordinates: on
  A5x12_16-Buz the four 12-site shanks span 110 µm each (Buzsaki tip clusters — no depth order to find, LFP ordering there is meaningless) and the
  16-site middle shank spans 2700 µm (the "middle finger"). A tip cluster must be SPW-sign-uniform, the middle shank must cross the reversal; the
  criterion picks `version1` over `version2` for SF09 (`version2` = `version1` with the connector rotated 180° on the pin grid, 64/64 channels).
  Amplitude can be scaled by impedance (SF10) but a sign flip cannot — use signs, not amplitudes, to judge a grouping.
- **Hardware evidence (2026-09-08, `Neurologger` repo).** `PCB/Datalogger/WILD64_HDI.sch` (Eagle XML netlist) fixes Omnetics pin ↔ RHD2164 input;
  `docs/images/WIrelessEphys_Github_8_connectors.jpg` panel 1 fixes amplifier.dat column ↔ connector pin and is exactly `INTAN64_PINS` here, so the
  firmware's intended export order is the standard Intan headstage numbering and ProbeMaps ids can be read as columns (the +1 bank-0 rotation is the
  measured firmware deviation). On the A4x16-Lin each shank is one 2×8 pin block and the four column sets {48–63}, {32–47}, {1–15,17}, {0,16,18–31}
  are the same under all 16 matings → **shank membership is certain**; the shank identity and the within-shank order are not. On the A5x12-Buz (SF09)
  three shanks straddle two pin blocks, so its grouping rests on the data reconstruction instead.
- Re-check: `python ephys/probe_map_check.py --cohort 2026c --animal SFxx --session <s> --probe <probe> --seconds 600 --rotation-scan --cache-dir E:/3rd_rat_spikes/analysis/index/probe_map_cache`
- Re-check #2 (after sorting; decisive when co-activation has < 100 strong pairs): `python ephys/footprint_map_check.py --cohort 2026c --animal SFxx --session <s> --cache-dir E:/3rd_rat_spikes/analysis/index/footprint_cache` — ranks the 16 connector matings (per-connector 180° rotation, swap, mirror; `probe_map_check.py --connector-scan` tests the same set) × bank rotations by how compact the sorted units' 64-column footprints are. 2026-09-04: SF10 = SF07's map (co-activation); SF08 = SF07's map ranks first but all candidates stay broad; SF11 (sorted 09-06) and SF12 (sorted 09-08) undecided — no mating in the family makes their footprints compact (adjacent-site fraction ≤ 0.15 under every candidate, vs 0.41–0.78 where the map is right); sorts valid, within-shank order open.

## Known limits (read before interpreting units)

- **Channel → shank mapping**: verified for SF07; SF10 = grouping verified + within-shank order from the LFP depth profile
  (test #3, user-inspected, reproduced across sessions; dead columns at the end of their group until the wiring is known);
  provisional (grouping only) for SF08 / SF11 / SF12; data-derived (no geometry) for SF09. Shank/depth claims are blocked until each animal's entry in
  `probes_2026c.yaml` says `verified: true`.
- Staged folders omit `analogin.dat`/`digitalin.dat`/`supply.dat`: PreprocessPipeline's Intan ADC check
  would reject the 1250 Hz WILD lanes. PC-time anchors come from the raw folder via
  `Neurologger/Code/WILD_generate_pc_time.py` (BLE anchors live in `analogin.dat` lanes 14/15).
- **Kilosort1 DOES run here (2026-09-09, corrected).** MATLAB R2021b refuses the RTX 5070 Ti natively (`parallel:gpu:device:DeviceTooNew`,
  compute capability 12.0 vs the bundled CUDA 11.0), but `parallel.gpu.enableCUDAForwardCompatibility(true)` recompiles the GPU libraries once
  (~9 min) and then works: matmul and FFT match the CPU. With Visual Studio 2019 the three KiloSort1 CUDA MEX files compile from a copy of the
  lab checkout at `E:rd_rat_spikesnalysis	ools\KiloSort1_field2026` using
  `mexcuda -largeArrayDims <f>.cu NVCC_FLAGS='-allow-unsupported-compiler -gencode=arch=compute_80,code=compute_80'` (PTX only, the driver JITs it),
  and `mexWtW2` executes on the GPU with finite output. The pipeline already carries `sorter/Kilosort1_config.yaml` and a MATLAB launcher, so KS1 is
  a real option; Kilosort4 was used so far because this was believed impossible. MathWorks warns that forward compatibility can behave unexpectedly,
  so a KS1 run must be sanity-checked (no NaNs, yield in the expected range) before its units are trusted.
- Sessions are treated one at a time (no multi-session concatenation yet); a 12-h session is ~50 GB raw and
  the same again for the staged copy and the filtered `.dat`.
- Time alignment to video/WISER is **unverified** until the per-session PC-time fit passes its gates.
