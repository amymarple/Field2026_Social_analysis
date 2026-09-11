# ADC ("microphone") lane: contamination measured, sessions quarantined (2026-09-10)

**What happened.** The operator switched the WILD console's "microphone" ADC lane ON on all five loggers 14:40–14:56 ET on 2026-09-10
to record a body-temperature sensor (config block byte 28 = 0x08, param 625; `CE_params` `sampling_rates[2]` = 160000). The lane was
switched OFF again 20:41–21:05 the same evening after the noise was noticed in the field and measured at the lab.

**Measured (SF08, lane-OFF day session `6_20260910_082629.685` vs lane-ON `7_/8_/9_20260910_*`, same logger, same day).**
- `adc.dat` = int16 at 160 kHz (8 samples per amplifier sample): rail-to-rail noise (mean ~8,500, sd ~13,000, hits ±32767, 25 % of
  power > 10 kHz, 0.7 % < 1 Hz, discontinuities at every 512-sample block). A microphone input is AC-coupled: no temperature is recorded.
- Amplifier stream: a 312.5 Hz (= 625/2) train of near-full-scale plateau pulses (median 28,000 ADC ≈ 5.5 mV, ~1.2 ms wide, 0.4–4.4 ms)
  on 64/64 channels, ~18 % of samples, onsets block-locked (mod 64 samples) but staggered 0–4.3 ms across channels, so not common-mode
  (whole-probe median subtraction 250 → 314 ADC). Spike-band noise floor 44 → 250 ADC (×5.6), raw std 1,200 → 9,500, harmonic comb at
  multiples of 23.15 Hz to 300+ Hz. Identical at +10 min, +2 h, +3.4 h. `time.dat` consecutive (no sample loss: values corrupted).
- Verdict: firmware-side acquisition defect (plateaus, not copied ADC values; block-locked yet per-channel staggered; the ADC stream is
  itself block-corrupted) — not a console/download artefact. Battery telemetry also freezes in this mode; 4 of 5 loggers hung.
  Maker report: field2026-sync `from-lab/2026-09-10_maker-report-adc-mic-mode.md`.

**Handling (operator decision).** Lane-ON sessions are unusable and are moved out of the raw tree:
- `E:\3rd_rat_spikes\_quarantine_adc_lane_on\<SFxx>\<MAC>\<session>\` (+ README, `quarantine_manifest.csv`). A leading underscore
  makes the folder invisible to every ephys tool (`_common.iter_raw_sessions`; the per-animal summary loop in `build_session_index.py`
  now skips `_`/`analysis` too).
- New `ephys/quarantine_adc_sessions.py --cohort 2026c [--move]`: flags a session when ANY of (1) header byte 28 == 0x08 /
  `sampling_rates[2]` == 160000, (2) its [start, end] overlaps a registered ON window (`cohorts/2026c.yaml` `ephys.adc_lane.on_windows`,
  mic-ON → mic-OFF config-write times per logger from the field's `2026-09-10_adc-lane-contamination-boundaries.csv` — catches pieces
  that received the ON block mid-recording while their header still says OFF), (3) the pulse train itself (10-s windows at +60 s,
  middle, −60 s: runs of |x| > 5,000 ADC on ≥ 32 channels at ≥ 100 pulses/s). Reports the three signs side by side; `--move`
  relocates and appends to the manifest. Self-test on the quarantined SF08 sessions: all three signs agree (143 pulses/s on 64 ch, 20 %
  of samples). Procedure per offload: `check_offload_sizes.py` first (it counts every folder), then quarantine, then `run_qc.sh`.
- Registry: `ephys.adc_lane` (format, flag, verdict, windows); SF08's four pieces field-flagged for the record; the other loggers'
  09-10 day and night lane-ON pieces are quarantined at their offload (windows registered).

**Done 2026-09-10:** SF08 `7_20260910_144204.188`, `8_20260910_150945.224`, `9_20260910_184248.287`, `10_20260910_184306.556` (empty
record, fs 0) moved. Sessions before the switch-on and the lane-off night sessions from 20:44:13 / 21:02:46 / 20:49:12 / 20:56:12 /
21:05:19 are clean.
