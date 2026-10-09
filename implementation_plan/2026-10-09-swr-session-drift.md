# Electrode movement from the LFP: per-session laminar profiles and within-session ripple trends (cohort 2026c) — plan

2026-10-09, written before computing. Requested by the spike-sorting session ("Kilosort"). It must decide whether
Kilosort1 (no drift correction) may join sessions of one probe block across battery rounds.

## (a) Per-session laminar profile vs the block reference

- **Scan.** `ephys/swr_channel_scan.py`, unchanged, run on every session of the SWR quality table that has LFP and final
  states, with `--hours 1` (the 1-h window with the most NREM). The block reference sessions are scanned the same way.
  For each live column it gives:
  - `ratio` = the NREM ripple-envelope ratio;
  - `spw_ref_uV` = the team-style sharp wave at the session's own ripple events.
- **Comparison** with the block's `reference_session` (`configs/swr_channels_2026c.yaml`):
  - **whole probe:** Pearson r of log(ratio) and of spw_ref over the live columns;
  - **per shank** (final channel order, top → bottom):
    - the depth of the ratio maximum, Δpeak in channel steps;
    - the best integer depth shift s ∈ [−4, 4] that maximises the correlation of the session profile with the reference
      (≥ 8 overlapping sites; done for log ratio and for spw_ref separately);
    - the SW sign change (interpolated zero crossing along depth) when both have one.
- **Movement candidate (fixed now):** |s| ≥ 1 in the same direction on ≥ half of the shanks with a ripple (shank max ratio
  ≥ 2), in BOTH profiles; or whole-probe r < 0.8 in both.
- **Also reported:** the shift of each session relative to the previous session of the same block. This is the
  battery-round step.

## (b) Within-session hourly trend

- **Events:** SWR events from storage (kept, NREM), per session in 1-h bins since the session start (≥ 30 events per
  bin).
- **Per bin:**
  - y_amp = log(median amplitude / the session's median);
  - y_shk = the same for each shank's `env_ratio_shank<k>` and for `env_ratio_noise`.
- **Model per animal × block:** WLS, weights = events. It has a session fixed effect, elapsed hours since the session
  start, and a 2-harmonic clock (time of day). SEs are clustered by session.
- **Reported:**
  - the elapsed-hour slope in % per hour, with its 95 % CI;
  - per session, the last-2-h / first-2-h ratio.
- **Reading:** a slope beyond ± 2 % per hour with its CI excluding 0 is a within-session amplitude trend. It is not a
  displacement by itself: ripple amplitude also follows state and depth.

## Output

- `ephys/swr_session_drift.py`: `scan`, `profiles`, `hourly`, `--selftest`.
- Bulk: `$OUT_ROOT/2026c/swr_session_drift_<ts>/`.
- Report: `results/2026c/ephys_spikes/reports/ephys_spikes_swr_session_drift_2026c.md` + CSVs.
- Storage is read-only.
