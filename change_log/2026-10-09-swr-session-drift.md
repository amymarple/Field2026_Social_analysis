# Electrode movement from the LFP: laminar profiles per session and within-session ripple trends (2026-10-09)

Plan (before computing): [implementation_plan/2026-10-09-swr-session-drift.md](../implementation_plan/2026-10-09-swr-session-drift.md).
Requested by the spike-sorting session ("Kilosort"). The decision it informs: may Kilosort1 (no drift correction) join
the sessions of one probe block across battery rounds?

## What changed

- **New `ephys/swr_session_drift.py`**, with commands:
  - `scan`: `swr_channel_scan.py --hours 1` on every session with LFP + final states, 5 in parallel; 176 sessions,
    85 min, 0 failures;
  - `profiles`, `hourly`, `report`;
  - `--selftest`.
- **Report:** `results/2026c/ephys_spikes/reports/ephys_spikes_swr_session_drift_2026c.md`, with CSVs `_profiles_by_session`,
  `_profiles_by_shank`, `_hourly_slopes`, `_hourly_first_last`.
- **Bulk:** `$OUT_ROOT/2026c/swr_session_drift_20261009_1942/` (per-session scans, hourly bins).

## Definitions (headline)

- **Profiles:** per live column, the NREM ripple-envelope ratio and the sharp wave (spw_ref).
- **Whole-probe correlations:** r of each profile with the block reference session.
- **Shift:** per shank, the best integer depth shift s ∈ [−4, 4] (≥ 8 sites; s > 0 = deeper).
- **Movement candidate:** |s| ≥ 1 with one sign on ≥ half of the eligible shanks in both profiles, or r < 0.8 in both.
- **Hourly:** kept NREM events in 1-h bins; log(bin median / session median). WLS on session fixed effects + elapsed
  hours + 2-harmonic clock, SEs clustered by session.

## Results

**(a) Profiles.**
- **Stable across every battery round** (r_spw ≥ 0.85–0.96, shifts 0; no candidate):
  - SF09 and SF10, each 1 block (SF10's SW profile drifts +1–2 sites in its last 3 sessions, 09-10 21:00 → 09-11 19:22,
    r_spw down to 0.67; not a candidate under the rule);
  - SF07 in each of its 4 blocks;
  - SF08 block 2.
- **SF07 one outlier:** session `3_20260901_054126` has an inverted ratio profile (r −0.84), but its SW r is 1.00. This is a
  1-h-window artefact, not movement.
- **SF08 block 1, no documented advance:** from the cohort start to 09-06 08:00, 18 of 18 sessions are candidates.
  - The profiles sat 2–3 sites shallower than the 09-08 reference (shift_ratio −2.5 to −3, shift_spw −2; r_spw 0.03–0.37).
  - They converged gradually (09-04 evening r_spw 0.59, 09-05 0.57–0.73, 09-06 morning 0.65).
  - They have been stable from the 09-06 evening session onwards (r ≥ 0.93).
  - Consecutive sessions are similar, so this is a slow settling, not a step at a round.
- **SF12 block 1:**
  - Before 09-06 the profiles are a stable regime that differs from the 09-06 reference (r 0.43–0.70, shift 0). The step
    is at the 09-06 morning battery round, with no documented advance.
  - Stable 09-06 → 09-07.
  - From 09-08 07:26 the SW profile inverts (r_spw −0.46 to −0.58, shift +1.5). This is the connector contact, and it is
    not flagged by the rule because the ripple profile stays at r 0.85.
- **Low-contrast blocks** (SF11 after 09-02 19:08, SF12 block 3): not SWR-specific. Their candidates are not
  interpretable.

**(b) Hourly.**
- No within-session amplitude trend beyond ± 2 %/h in any block (largest −0.65 %/h, SF07 block 1).
- Per session, the last 2 h / first 2 h is 0.98, IQR 0.94–1.03 (119 sessions).
- The only per-shank trend beyond 2 %/h is SF12 block 1 shank 1: −2.6 %/h, [−4.6, −0.5], the loosening contact.

## Reading for joining sessions

- **Join freely:** SF09; SF10 (watch its last 1.5 days); SF07 within each block; SF08 block 2.
- **Split:**
  - SF08 block 1 at about 09-06 19:43 (earlier sessions drift by 2–3 sites over 6 days);
  - SF12 block 1 at the 09-06 morning round and at 09-08 07:26.
- **Not CA1:** SF11 after 09-02 19:08 and SF12 block 3.
- **Within a session:** no amplitude drift seen.
- The shifts are in channel steps of the final order. They come from the LFP laminar profile, not from unit footprints.

## Verification

- `python ephys/swr_session_drift.py --selftest` → PASS (shift recovery, zero crossing, sign rule).
- 176 / 176 scans returned 0.
- Storage was read only.
