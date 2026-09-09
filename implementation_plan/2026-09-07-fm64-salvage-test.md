# FM64 salvage test (2026-09-07) — QUEUED, not started

**Status.** RUNNING since 2026-09-07 23:45 (operator: "que 一个 FM64 noise 对 spike sorting 影响"; 2026-09-08 is a free day,
no card offload). 2026-09-08 update: SF10 `1_20260901_080143.036` (FM64 day) staged + sorted (queue v6, 10:12 → 12:33, 55/59/58 units
on the three live shanks) and step 2 run on it: **39 % of its accepted units have one-sample-wide templates vs 3–8 % on the FM65
sessions (`ephys/template_width_check.py`, `results/2026c/ephys_spikes/reports/ephys_spikes_template_width_2026c.csv`) → the
de-glitched FM64 day FAILS the step-3 criterion for SF10.** SF07 `2_20260901_002100.939` (FM64 night): staged 12:33 → 13:20
(`stage_manifest.json` deglitch_applied = true, 156,221 ticks → 343; the conda wrapper printed rc=127 AFTER the stage's own
done line — a wrapper artefact, the copy is complete), Kilosort4 on the staged copy from 13:20 (four shanks sorted by 16:04,
postprocess in progress). Steps 2–3 on SF07 and the final comparison follow when it lands; step 4 (donor-match rule) is not started.

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
