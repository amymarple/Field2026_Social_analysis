# `ephys/` — WILD neurologger spike-sorting pipeline (direction `ephys_spikes`)

Cohort-agnostic tooling for the head-mounted **WILD CE64 neurologgers** (64 ch @ 20 kHz int16 on SD, BLE
sync) introduced with the 3rd rat cohort (`cohorts/2026c.yaml`). It prepares clean, provenance-tracked
working copies of raw sessions and drives the lab's
[PreprocessPipeline](https://github.com/yoshihito-saito/PreprocessPipeline) (spikeinterface 0.103.2 + Kilosort4)
on them. Raw data are **never modified**; every derived file carries a manifest.

```
raw offload (E:\3rd_rat_spikes\<SFxx>\<MAC>\<slot>_<date>_<time>.<ms>\)          <- read-only
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
| `wild_ce_params.py` | `CE_params.bin` parser (firmware @328, RTC start, MAC, fs, Nch); layout from `Neurologger/Code/WILD_ReadHeader.m` |
| `signal_probe.py` | 30-s probe: glitch samples/s, ticks/s, spike-band noise (µV), dead/broken channel candidates |
| `build_session_index.py` | the session index (CSV/MD/JSON + data-root mirror) |
| `deglitch_wild.py` | the cleaning step (free output path, report, manifest, before/after tick verification) |
| `make_session_xml.py` | Neuroscope XML with shank groups + `skip` flags from `configs/probes_<cohort>.yaml` |
| `stage_session.py` | raw → clean staged working copy + `stage_manifest.json` |
| `run_sort_session.py` | PreprocessPipeline driver (preprocess → Kilosort4 → postprocess) + `sort_manifest.json` |
| `probe_group_check.py` | data-driven check of the assumed channel→shank grouping |
| `offload_qc_report.py` | per-offload QC report: per-animal session timeline + gaps/overlaps, RTC-vs-folder, sidecar sizes, measured FM64-vs-FM65 glitch statistics, BLE PC-time fit verdicts (from `pc_time_chain.py` when present) |
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

## Known limits (read before interpreting units)

- **Channel → shank mapping is a placeholder** (sequential 16-channel blocks; SF09 5×12 = [12,12,16,12,12]).
  No pinout table exists in the repos or on disk; every earlier `amplifier.xml` is a single 64-ch group. Units
  are valid per unit; shank/depth claims are blocked until `probes_2026c.yaml` is confirmed
  (`verified: true` + source). `probe_group_check.py` is the data-side test.
- Staged folders omit `analogin.dat`/`digitalin.dat`/`supply.dat`: PreprocessPipeline's Intan ADC check
  would reject the 1250 Hz WILD lanes. PC-time anchors come from the raw folder via
  `Neurologger/Code/WILD_generate_pc_time.py` (BLE anchors live in `analogin.dat` lanes 14/15).
- MATLAB R2021b cannot run Kilosort1/2.5 on the RTX 5070 Ti (Blackwell needs CUDA ≥ 12.8) → Kilosort4 only.
- Sessions are treated one at a time (no multi-session concatenation yet); a 12-h session is ~50 GB raw and
  the same again for the staged copy and the filtered `.dat`.
- Time alignment to video/WISER is **unverified** until the per-session PC-time fit passes its gates.
