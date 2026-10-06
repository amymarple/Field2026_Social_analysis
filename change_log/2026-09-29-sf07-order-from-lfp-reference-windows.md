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

## 2026-10-05 (night): correct-order template, `--lfp` plain window

**Template.** The user supplied a session whose order is correct: HYC3 `day26`, standard A4x16-Lin, 109–140 min (NREM).
- Copied read-only from `W:\data\PPP\HYC3\day26` to `G:\3rd_rat_spikes\analysis\inspect\template_HYC3_day26\`
  (SHA-256 verified).
- Its shanks 1–2 (CA1) show the textbook profile along the true order:
  - The SPW rises smoothly. The top sites are negative, so the sign is not a depth label.
  - The SPW peaks 1 site above the ripple maximum and reverses within 2 sites below it.
  - Only 4 sites lie above the ripple half-maximum.
  - Theta phase is flat above the layer and shifts fast below it.
  - On shank 2 the SPW reaches its trough 4 sites below the layer, then rises again to a positive peak where theta power
    peaks (SLM). Below the trough the profile folds.

**`lfp_profile_check.py --lfp` without `--states`** reads a plain window (`--offset-min`, `--minutes`) of any session `.lfp`.
The channel count and rate come from the sidecar or from `--xml`.

**Seriation prototype (scratch, not yet in the repo).** It finds the shortest path through the sites in normalised (SPW,
ripple, theta phase, log theta power) space.
- Template: CA1 shank 1 recovered exactly. Errors fall only in the fold below the radiatum trough and in the featureless
  cortex top.
- SF10 shanks 2–4: ρ 0.98–0.99 to the adopted order.
- SF08: ρ ≥ 0.98 on most shanks. The exceptions are single sites (47, 53, tip col 3).
- SF07 shanks 2–4: equal to the LFP-derived order. Shank 1 gives the same path with the orientation flipped.

## 2026-10-06: `swr_layer_order.py` — seriation of the SWR layer profile, multi-day consensus, proposed orders

**Literature** (summary by a reading agent; Mizuseki 2011, Csicsvari 1999, Schomburg 2012, Buzsáki 1986, Suzuki & Smith 1987,
Oliva 2016, Liu 2022 consensus, Paleologos 2025):
- The ripple maximum marks mid stratum pyramidale and is flat over ±1 site.
- The ripple keeps its phase above and through the layer. It reverses 150–200 µm below, where its envelope grows again.
- The sharp wave is positive in oriens/pyramidale and reverses just below the layer. It is most negative about 200 µm below
  the reversal and weakens toward SLM.
- Theta phase is constant above the layer and shifts below it.
- A reference that picks up the sharp wave moves signs, not differences.

**New `ephys/swr_layer_order.py`.** Reads saved profiles; no raw data.
- Features per site:
  - SPW;
  - signed ripple = amplitude × the event-averaged 130–200 Hz correlation with the shank's ripple-maximum site (new
    `ripple_corr` in the profile npz);
  - theta phase;
  - log theta power.
- Each feature is range-scaled per shank. The order is the exact shortest open path (Held–Karp). Distances are summed over
  days, which gives a consensus: the order is the wiring and does not move with depth.
- Orientation comes from four votes:
  - the reversed-ripple side is the bottom;
  - theta departs more on the bottom side, compared at equal distances from the ripple maximum;
  - the SPW maximum lies at or above the ripple maximum;
  - without a reversal, the larger-ripple end is the bottom.
- Dead, skipped and `--exclude` columns stay after their predecessor in the reference XML.

**Validation.** On the template the method recovers CA1 shank 1 exactly and puts the orientation right on all four shanks.
The errors are confined to the fold below the radiatum trough and to the featureless cortex top.

**Profiles re-run with `ripple_corr`.** Every array reproduces exactly. The one exception is SF07 09-02, whose theta now
comes from the final `imu_remclean` REM: max 6°.
- New SF10 windows: 09-03 06:38 (staged) and 09-09 08:10 (read from raw E:, because the staged folder lacks
  `CE_params.bin`). Both are IMU-gated.

**Proposed orders** (`G:\3rd_rat_spikes\analysis\inspect\<SF>_*\<SF>_layer_order_consensus.xml`). None is in `configs/`
yet; they await the user's Neuroscope check.
- **SF07:** a large change on shanks 1–3. Against the current spike-verified XML: ρ 0.89 / 0.47 / 0.78 / 0.99. Against
  the earlier LFP-derived order: 0.99–1.00.
- **SF08:** shanks 1–2 identical (col 47 excluded: it correlates with nothing and has an odd theta phase).
  - Shank 3: two neighbour swaps.
  - Shank 4: top 18, 27, 22, 20 → 20, 27, 18, 22 and 21/19 swapped. The SPW is monotone along the new top on all three days.
- **SF10:** shank 2: 17 and 3 move up 2–3, and 5 moves down 2. All three days are smoother.
  - Shank 3: two neighbour swaps.
  - Shank 4 kept: impedance split, and the days disagree.

The Neuroscope review sets (`CURRENT` / `PROPOSED`, `.rip.evt`) are in each folder.

**User decision 2026-10-06:** SF07 takes the proposed order; SF08 takes the proposed shank 4; SF10 is left as is for now.
- New repo XMLs:
  - `ephys/configs/xml/SF07_A4x16-Lin_lfporder_20261006.xml`;
  - `ephys/configs/xml/SF08_A4x16-Lin_lfporder_20261006.xml` (the adopted shanks 1–3 plus the consensus shank 4; 32 and 55
    stay skipped).
- `probes_2026c.yaml` now points SF07 and SF08 at them; `mapping_source` starts with a CURRENT note.
- The old XMLs stay in the repo. SF11 keeps the old SF07 XML for grouping only; the grouping is identical.
- Placed as `<session>.xml` in the full-day stage sessions SF07 `15_20260902_082418.755`, SF07 `2_20260901_002100.939` and
  SF08 `13_20260902_082748.094`. Each mapping was verified against the repo XML. The previous files are kept as
  `.xml.pre_20261006`.
- `.xml.done` (sort provenance) was not touched. Neither were the users' Neuroscope `amplifier.xml` files, which still
  carry the old orders.

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
