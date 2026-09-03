# Ephys (WILD neurologger) spike-sorting pipeline for the 3rd rat cohort — plan (2026-09-02)

## Goal

Stand up a cohort-appendable, provenance-first spike-sorting path for the WILD CE64 neurologger
recordings of the 3rd rat cohort (SF07–SF12, released 2026-08-30 ~19:00 ET; raw offloads under
`E:\3rd_rat_spikes`). The path must (1) index every offloaded session with its **firmware version**
(FM62 → stop-only commit + glitches; FM64 → glitch "artificial spikes"; FM65 → maker-fixed, unevaluated),
(2) **de-glitch** every pre-FM65 session before any filtering/sorting using the field-validated
`from-field/2026-09-01_deglitch_wild.py` algorithm, and (3) drive the lab's
[PreprocessPipeline](https://github.com/yoshihito-saito/PreprocessPipeline) (spikeinterface 0.103.2 +
Kilosort4) on the cleaned, staged copies — never on the raw folders.

## Inputs

- Raw sessions: `E:\3rd_rat_spikes\<SFxx>\<logger MAC>\<slot>_<YYYYMMDD>_<HHMMSS>.<ms>\` — Intan-style
  "one file per signal" export from the WILD logger (`amplifier.dat` int16 64 ch @ 20 kHz, `info.rhd`,
  `CE_params.bin` header, `time.dat`, `analogin.dat` 16 ch @ 1250 Hz misc lanes incl. BLE PC-time anchors,
  `digitalin.dat`, `supply.dat`, empty `adc.dat`/`misc.dat`). `recovery.bin` per animal = raw 512 GB card
  image kept for a future forensic recovery of the FM59–62 uncommitted sessions (night 1) — never parsed here.
- Field notes: Notion "4-Rat 3rd cohort — full (SF07–SF12)"; field2026-sync `from-field/`
  (`2026-09-01_fm59-62-signal-defects.md`, `2026-09-01_deglitch_wild.py`, `2026-08-31_cohort3-night1-lfp-loss.md`).
- Reference pipeline: `C:\Users\Cornell\Documents\GitHub\PreprocessPipeline` (read-only dependency, imported
  by path; not vendored).

## Design

New modality folder `ephys/` (cohort-agnostic, `--cohort`), direction key `ephys_spikes`, cohort `2026c`.

| Step | Script | Output |
|---|---|---|
| 0 | `ephys/wild_ce_params.py` | parser for `CE_params.bin` (fs, Nch, firmware, hw, RTC start, MAC, SD) |
| 1 | `ephys/build_session_index.py --cohort 2026c` | `results/<cohort>/ephys_spikes/reports/ephys_spikes_session_index_<cohort>.{csv,md}` + mirrored `SESSION_INDEX.*` at the data root; per-session firmware, duration, size, **measured glitch rate** on a 30-s probe, bad-channel candidates |
| 2 | `ephys/deglitch_wild.py` | vendored port of the field algorithm (identical numerics: 5-pt running median, `thr = max(10·1.4826·MAD, 500 ADC)`), output path free, `deglitch_report.csv` + JSON manifest, tick-metric verification |
| 3 | `ephys/stage_session.py` | `<OUT_ROOT>/<cohort>/ephys_stage/<animal>/<session>/` = cleaned `amplifier.dat` (or verbatim copy when FM ≥ 65), `info.rhd`, `CE_params.bin`, `time.dat`, `<session>.xml` (probe groups from `ephys/configs/probes_<cohort>.yaml`), `stage_manifest.json` |
| 4 | `ephys/run_sort_session.py` | PreprocessPipeline `run_preprocess_session` (bandpass 500–8000, local CMR, high-amp artifact removal per shank, LFP 1250) + Kilosort4 (per-shank partition) + `run_postprocess_session` (dedupe/merge/split/metrics/noise labels → Phy folder), under `<OUT_ROOT>/<cohort>/ephys_sort/<animal>/<session>/` |
| QC | `ephys/probe_group_check.py` | LFP/HP inter-channel correlation blocks to test the assumed shank grouping |
| test | `ephys/selftest.py` | offline synthetic checks (parser, de-glitch ≥99 % removal + spike preservation, XML, index) |

Sidecar policy: staged folders deliberately omit `analogin.dat`/`digitalin.dat`/`supply.dat` — the pipeline's
Intan ADC-layout check infers sidecar width from the 20 kHz amplifier sample count and would reject the
1250 Hz WILD lanes; PC-time anchors are derived from the RAW folder with `WILD_generate_pc_time.py`
(Neurologger repo), not from the stage.

Firmware gate: `deglitch_required = firmware_version < clean_firmware_min` with `clean_firmware_min: 65` in
`cohorts/2026c.yaml`; overridable per run (`--force-deglitch` / `--skip-deglitch`). The measured 30-s glitch
rate in the index is the evidence that FM65 sessions are actually clean once they are offloaded.

## Known unknowns (flagged, not silently assumed)

- **Probe channel → shank mapping is UNVERIFIED.** `probes_2026c.yaml` ships sequential 16-channel blocks
  (SF09: Buzsaki 5×12 = [12,12,16,12,12]) as a placeholder; the correlation check is the data-side test.
  Sorting results are valid per unit but shank geometry claims are not until the mapping is confirmed.
- MATLAB R2021b cannot drive Kilosort1/2.5 on the RTX 5070 Ti (Blackwell needs CUDA ≥ 12.8) → Kilosort4.
- µV scaling uses the Intan default 0.195 µV/ADC (WILD header gives none) — relative, unverified.

## Verification

`python ephys/selftest.py` passes offline; the index runs over all 37 offloaded sessions; a ≤2-min FM64
session (SF10 `5_20260901_054403.494`, the field validation session) de-glitches to the field numbers
(~99.7 % tick removal, ~0.17 % samples replaced); one ~10-min FM62 session sorts end-to-end with Kilosort4.
