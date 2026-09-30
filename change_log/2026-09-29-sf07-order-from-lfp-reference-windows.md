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

## Definitions
- **Ripple:** 130–200 Hz band, |Hilbert| envelope smoothed 8 ms, z-scored per column. An event is max_z > 4 for ≥ 20 ms,
  events are merged within 50 ms, and the peak is the argmax of the summed z.
- **SPW profile:**
  $\mathrm{SPW}_c = \frac{1}{N}\sum_{i=1}^{N}\overline{x^{(1\text{–}50)}_c}[t_i-15\,\mathrm{ms},\,t_i+15\,\mathrm{ms}]\times0.195$ µV.
  The mean 1–50 Hz LFP of column c around each ripple peak $t_i$. Relative µV. Positive = above the CA1 reversal.
- **Total variation:** $\mathrm{tv}=\sum_k|p_{k+1}-p_k|\,/\,(\max p-\min p)$ of a profile $p$ along a candidate order.
  1 = monotonic, larger = jagged.
- **Order agreement:** Spearman ρ between the positions of the same 16 columns in two orders. 1 = identical order.
