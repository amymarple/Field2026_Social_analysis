# SF07 within-shank order re-derived on user reference windows; profiles saved (2026-09-29)

**What.** The user judged SF07's map not fully right on `2_20260901_002100.939` 271–275 min and asked for the order to be
re-derived there, then cross-checked on `15_20260902_082418.755` 56–80 min. The rule: the layer-profile gradient is
invariant to probe moves. No sorting was run, and no config changed: `probes_2026c.yaml` still points to the old SF07 XML
until the user checks the candidates in Neuroscope.

**Code**
- `ephys/make_lfp.py`: window mode (`--start-seconds` / `--max-seconds`; frame k ↔ sample start + 16k).
  - `--src <dir>` converts a staged copy; a `deglitch_manifest.json` there prevents a second de-glitch.
  - `--out-name` sets the output name.
  - Self-test adds: a window equals the same frames of a full conversion (0 LSB).
  - Regression: SF07 `9_…` 600–660 s equals the existing full-session LFP (0 LSB).
- `ephys/lfp_profile_check.py`:
  - `--no-deglitch`, for already de-glitched staged folders.
  - `--save-profile OUT.npz`: per-column SPW / ripple / theta, ripple times, ripple-triggered waveforms ±100 ms, per-column
    rms, spike-band correlation, and the grouping(s). The user asked to keep these.
- `ephys/configs/lfp_reference_windows_2026c.yaml`: the user's windows. SF07 now; the other animals to follow.

**Result.** Outputs in `G:\3rd_rat_spikes\analysis\inspect\SF07_xml_reorder\`: Neuroscope pairs, `README.txt`, profiles.
- Every site has a positive SPW in both windows, with no polarity reversal (the probe sat high before 09-04). The order is
  the monotonic amplitude gradient.
- Site SPW amplitude ranks are the same on both days: Spearman 0.98.
- Independent orders on the two days: ρ 0.988 / 0.968 / 0.985 / 0.991 (shanks 1–4); 61/64 sites within ±1 position.
- Current map vs the reference-derived order: ρ 0.885 / 0.391 / 0.782 / 0.985. Shank 2 is the most wrong.
- Mean SPW total variation on the other day's window: 3.08 for the current map, 1.47 for the reference-derived order
  (1 = monotonic).

## SWR gradient check (user: no reversal needed; the SWR must grow and lengthen along the shank)

`ephys/swr_gradient_order.py` works from the saved profiles, with no raw data. Per site it computes SPW amplitude,
SPW FWHM, ripple amplitude and ripple FWHM of the ripple-triggered averages. It scores each candidate order by
Spearman ρ(position, feature).

**On the 09-02 window (824 ripples, independent of the 09-01 derivation):**
- **Order B (derived 09-01):** SPW / ripple amplitude ρ .99/.99, .96/.97, .97/.99, .99/.99 (shanks 1–4).
- **Current map:** .89/.90, .47/.46, .82/.81, .99/.99.
- **Widths:** B's SPW / ripple width ρ is .97/.82, .98/.71, .98/.87 on shanks 2–4. Shank 1's SPW width is flat.

**Width features are weak here.** The ripple FWHM is quantized at 0.8 ms, and in the 94-ripple window it is constant on
shanks 3–4. A mean-rank order over all four features reproduces across days at ρ 0.88–0.97, worse than the
ripple-amplitude order (0.97–0.99). So ripple amplitude is the most reliable single gradient.

**Outputs on G:** per-site features `profiles/swr_features_*.csv`; combined-order XMLs `SF07_swr_order_*.xml`.

## 2026-10-05: IMU gate, SF07 re-check, SF08 cross-check (user: the LFP is the reference, not the spike-verified map)

**IMU gate.** New `lfp_profile_check.py` options `--imu-csv` / `--imu-thr` / `--imu-offset-s` / `--imu-gate-s`. A ripple
counts only if the animal is IMU-still (`make_imu` per-second VeDBA below the animal's valley threshold, reliable) for
every second within ±2 s. This keeps NREM and quiet-wake SWRs and drops movement artefacts in the ripple band. Full NREM
scoring is not needed for this purpose.

**SF07.**
- Reference window: 13 of 95 ripples kept. The window is only 59 % still, and 82 detections fell during or next to movement.
- Cross-check window: 462 of 824 kept.
- Gated orders: on the cross-check window the gated order equals the ungated one (ρ 0.997–1.000). 13 clean reference events
  reproduce it at ρ 0.994–1.000.
- Neuroscope event files `*.rip.evt` (kept / moving) were written for a manual spot-check.

**SF08** (adopted `SF08_A4x16-Lin_dataorder_20260908.xml`, which is byte-identical in mapping to the Neuroscope-re-saved
`amplifier.xml`).
- 09-03 06:00 window: 206 of 440 ripples kept.
- 09-09 08:07 window: 520 of 589 kept.
- Along the same order the signed SPW rises steadily on both days, and the ripple maximum sits at the deep end on both.
- On 09-09 the radiatum reversal is below the tip and the top sites read negative: the shank sat higher, consistent with
  Notion 09-09 "probe sat high; moved down" at 18:10.
- Verdict: **the order passes.**

**Method caveats** (now in the docstrings):
- The `--derive-xml` rule assumes negative SPW = radiatum. It orders a shifted profile backwards (SF08 09-09).
- `swr_gradient_order.py` uses absolute amplitude and is valid only without a reversal (SF07).
- The sign of a site is not a depth label. The gradient direction and the ripple maximum are.

**Outputs:** `G:\3rd_rat_spikes\analysis\inspect\SF08_xml_check\` (README, derived XMLs, gated and ungated profiles,
logs) and the SF07 folder (gated XMLs and profiles, `*.rip.evt`).

## 2026-10-05 (late): NREM bout mode

User: the layer profile belongs to NREM SWRs, so take short NREM segments from the sleep score instead of IMU-gating a
window.

**New mode in `lfp_profile_check.py`:** `--lfp <session .lfp> --states <SleepState.states.mat>`.
- Bouts of `--state` (default NREM) are trimmed by `--edge-s` (5 s) and kept if ≥ `--bout-min-s` (15 s) remain.
- Each bout is cut to its middle `--bout-max-s` (60 s). Bouts are optionally limited to `--range-min A B` and spread
  evenly over the range up to `--max-bout-min` (20 min).
- Ripples are z-scored on NREM only. Filters and the Hilbert transform run per bout, and ripples < 150 ms from a join are
  dropped.
- Theta comes from REM bouts of the same range.
- `--states` without `--lfp` gates the ripples of a window instead.
- The npz adds `ripple_peaks_session_s` and `segments_session_s`.
- `--imu-offset-s` became `--session-offset-s` (the old name still works).
- Regression: window mode reproduces the saved 09-01 reference profile exactly (all arrays identical).

**SF07, 09-02 session** (NREM of the `imu_nremgate` review copy = `imu_remclean` NREM, identical, unedited):
- NREM inside the user's 56–80 min window: 7 bouts, 16.6 min, 558 ripples.
- 22 short bouts over the whole session: 17.2 min, 566 ripples.
- Both orders match the window-derived C: ρ 0.997–1.000, every site within ±1.
- They agree with the gated 09-01 order at ρ 0.994–1.000.
- Against the current spike-verified map: ρ 0.90 / 0.46 / 0.80 / 0.99.
- The order holds across the whole 8.5-h session.
- The 09-01 evening session `9_20260901_192912.215` has essentially no scored NREM.

## Definitions
- **Ripple:** 130–200 Hz band, |Hilbert| envelope smoothed 8 ms, z-scored per column. An event is max_z > 4 for ≥ 20 ms,
  events are merged within 50 ms, and the peak is the argmax of the summed z.
- **SPW profile:**
  $\mathrm{SPW}_c = \frac{1}{N}\sum_{i=1}^{N}\overline{x^{(1\text{–}50)}_c}[t_i-15\,\mathrm{ms},\,t_i+15\,\mathrm{ms}]\times0.195$ µV.
  The mean 1–50 Hz LFP of column c around each ripple peak $t_i$. Relative µV. Positive = above the CA1 reversal.
- **Total variation:** $\mathrm{tv}=\sum_k|p_{k+1}-p_k|\,/\,(\max p-\min p)$ of a profile $p$ along a candidate order.
  1 = monotonic, larger = jagged.
- **Order agreement:** Spearman ρ between the positions of the same 16 columns in two orders. 1 = identical order.
- **SWR features (per site c, ripple-triggered averages over ±100 ms, baseline = median at |t| ≥ 80 ms):**
  - $A_{spw}(c)=\max_t s\,(\mathrm{spw}_c(t)-b)$, where $s$ is the dominant SPW sign;
  - $D_{spw}(c)$ = full width at half maximum (ms) around t = 0;
  - $A_{rip}(c)=\max_t(\mathrm{env}_c(t)-b)$;
  - $D_{rip}(c)$ = FWHM of the envelope.
  Larger / longer = closer to the pyramidal layer. Units: µV, ms.
- **Monotonicity:** Spearman ρ between position along the order and a feature. 1 = the feature rises steadily.
