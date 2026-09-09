# FM64 salvage test (2026-09-07) — DONE 2026-09-09, FM64 usable with a template-shape filter

**Status. DONE 2026-09-09 01:23 — VERDICT: de-glitched FM64 is sortable ONLY WITH a template-shape filter.** The decisive test ran on SF12 with the
channel map settled on 2026-09-08 (the operator's earlier attempts used superseded XMLs and were discarded together with those sorts): matched 3-h morning
windows of `0_20260901_080334.683` (FM64, 908 ticks/s, de-glitched: 11,684,684 ticks -> 225) and `11_20260902_083748.804` (FM65, untouched), the same XML,
the same settings, one after the other. Result: the de-glitch leaves a residue that Kilosort4 sorts into extra 'units' whose templates are a band-pass-filtered
single-sample impulse (a sharp peak with symmetric ringing, no real repolarisation). They are 36-38 % of accepted units on FM64 against 5 % on FM65, and the
measure separates them cleanly: the neighbour/peak ratio of the peak-channel template is bimodal on FM64 (quartiles 0.23 / 0.92) and unimodal on FM65
(0.79 / 0.91). Removing them leaves 77 normal-shaped accepted units on FM64 against 59 on FM65 for the same 3 h, with matching SNR (4.5 vs 4.3) and amplitude
(46 vs 41 uV) — i.e. the real units survive the de-glitch. Step 3's literal criterion fails (accepted one-sample units exist) while the yield criterion passes
(well-isolated 26 vs 20 = 130 %). Practical rule adopted: FM64 sessions may be sorted, but every unit with neighbour/peak ratio < 0.4 must be rejected before
any analysis; `ephys/template_width_check.py` computes it. Step 4 (donor-match rule) is not needed for this decision and stays unstarted.

**Question.** Can the pre-FM65 sessions (FM64, 2026-08-31 19:00 → 2026-09-01 18:20, 17–22 h per logger, the earliest
surviving night after release with all six loggers) be used after de-glitching — for LFP certainly, for spike sorting
unknown. FM62 (08-31 daytime, ~4 h per logger) is NOT part of this: broadband / wide-impulse regimes the median rule
cannot fix and corrupt sync lanes (no field-PC time) — written off. Night 1 (08-30) is a `recovery.bin` question, not
a de-glitch question.

**What is already known (session index 2026-09-06, `ephys_spikes_session_index_2026c.csv`; change_log 2026-09-02).**
- Defect B (15-s housekeeping injection, −21,650 ADC synchronised) is removed completely by `deglitch_wild.py`.
- Defect A (per-sample substitution by a fixed donor channel): the 5-point-median rule replaces only samples with
  |dev| > max(10·1.4826·MAD, 500 ADC ≈ 100 µV). Ticks > 1200 ADC drop by ≥ 99.7 %; 0.17–0.39 % of samples replaced.
  Substitutions whose donor−victim offset is below the threshold survive; their number has never been measured.
- FM64 defect load per logger (summed over 64 ch): SF08/09/10/11/12 300–2,500 ticks/s; **SF07 6–21 ticks/s** (two
  orders of magnitude lower — SF07's FM64 is practically FM65-quality).
- Evidence that the residue matters for spikes: `probe_map_check.py` on de-glitched FM64 windows (events ≥ 3 samples
  below −3 σ, so a single substituted sample cannot trigger) is still dominated by the substitution defect on
  SF08/10/11/12 (`nn_agree` ≤ 0.12–0.38 vs 0.62–0.78 on SF07 FM65). The victim channel carries a one-sample echo of the
  donor's spikes; ≤ 100 µV single-sample impulses after a 500–8000 Hz band-pass sit in the amplitude range of the
  units (median 20–35 µV, `ephys_spikes_ks4_unit_yield_2026c.md`).
- Kilosort4 ran end-to-end on de-glitched FM64 (SF10 `5_20260901_054403.494` 50 s; SF08 `2_20260901_002327.839` 1-h
  window, output on the since-dropped G: drive) — feasibility only, never compared with FM65 on the same logger.
- FM64 sessions have field-PC time (chain verdicts OK); alignment is not the problem.

**LFP use (no test needed).** After de-glitch the residue is ≤ 100 µV for one 20-kHz sample: after decimation to
1250 Hz that is ≲ 6 µV over ~1 ms, and the strict SWR detector requires ≥ 20 ms band-limited events. Stage the FM64
sessions and use them for theta / SWR / state / behaviour coupling as they are; document the firmware in every output.

**Spike test (the queued work).**
1. Stage SF10 `1_20260901_080143.036` (FM64 day, 08:01–12:58, 4.96 h, 2,240 ticks/s, removal 0.999) with the default
   de-glitch and sort it exactly like SF10 `9_20260902_083247.835` (FM65 day, already sorted: 148 candidates < 3 Hz,
   10 well-isolated, median amp 32 µV, bad ch 32 34 56). Same probe config, same reject list, same `post_mode`.
2. Compare per shank: candidate units < 3 Hz, well-isolated count, median amplitude / SNR, ISI-violation ratio, and the
   template width on the channels the index flags as substitution victims (a one-sample-wide template = defect residue).
3. Decision rule: FM64 counts as sortable if the well-isolated count per shank is ≥ 70 % of the FM65 session's and no
   accepted unit has a one-sample-wide template. Otherwise FM64 stays LFP-only for SF08–SF12 (SF07 sortable regardless,
   per its tick load — confirm with the same comparison on SF07 `2_20260901_002100.939` vs `15_20260902_082418.755`).
4. If the test fails, one more option before giving up: a **donor-match rule** for defect A — for each victim channel
   identify its fixed donor (the field note's test: median |x_victim − x_donor| at tick samples ≈ 1 ADC), then replace
   x_victim(t) when |x_victim(t) − x_donor(t)| ≤ 2 ADC AND |dev(t)| > 3·1.4826·MAD. Validate with the existing synthetic
   injection test (`ephys/selftest.py`: 100 % of injected glitches replaced, 0.65 % of spike-peak samples altered at
   K = 10 / FLOOR = 500) before it touches any staged copy; report the extra spike-peak alteration it causes.

**Cost.** One 5-h session sorts in roughly 3–7 h on the RTX 5070 Ti at the current pipeline speed (8-h sessions took
4.6–13.4 h, `ephys_spikes_sort_runs_2026c.csv`); staging ~20 min; the donor-match variant is a day of work.

**Gain if it passes.** +17–22 h per logger (one more night + a day), i.e. 6 → 7 nights per logger, including the
earliest surviving night after release.

**Out of scope.** FM62 sessions, `recovery.bin`, anything on the recording rig; no raw session folder is ever written.

**Links.** `ephys/README.md` (Why a cleaning step exists), `ephys/deglitch_wild.py`, `ephys/stage_session.py`,
`ephys/run_sort_session.py`, `change_log/2026-09-02-ephys-spike-sorting-pipeline.md` (Verification, Channel map
finding 3), field2026-sync `from-field/2026-09-01_fm59-62-signal-defects.md`.
