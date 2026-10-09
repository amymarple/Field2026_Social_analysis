# When do the rats sleep at night? Night sleep / wake with WISER location; is "night NREM" the start of the main sleep? (2026c)

Plan, 2026-10-09, written before computing.

## The user's request

The user asked for a detailed look, with WISER, at when the rats wake and sleep at night. The user suspects that the
night NREM with the high ripple rate (00–04 h) is the start of the main sleep, not a nap.

## Questions

- **Q1.** Per animal and night: when is the animal asleep and when awake? Where is it (house_1, house_2, field, or
  unknown), and is it moving?
- **Q2.** Is the night NREM part of the main sleep period, or are these naps inside the active phase?
- **Q3.** Do the ripple rate and NREM depth follow time since the main sleep began, rather than clock time?
- **Q4.** At the same depth, how do naps and the main sleep's start compare?

## Data (read-only)

- **Sleep:** the FINAL 1-s states (`states_1s_final`).
  - Inclusion: `sleep_schedule.included_sessions`, i.e. user `noise`, SF12 contact failure, < 0.5 h, valid_until, the
    paddock end and 09-11 19:40 excluded.
  - Records: `sleep_cycles_v2.build_records` (splits ≤ 60 s joined).
  - Clock: start_local + s, as every sleep analysis.
- **WISER:** the 2026c default tracks (`wiser/src/default_tracks.py`; V3 / B2). Positions are in the UNVERIFIED WISER
  inch frame; only membership in the confirmed house rectangles is used.
  - house_1 = (411.5, 718.6), house_2 = (613.6, 717.3); 36.4 × 26.6 in; `wiser/configs/wiser_rois.json`, as used for
    cohort 3 by the failure audit.
  - Each rectangle is grown by the audit's 14-in buffer against jitter (median ≈ 7 in, p95 ≈ 15 in).
  - Fixes flagged `m_handling` / `m_silence` / `m_off_animal` are ignored.
- **Ripples and depth:** the swr_temperature run's kept NREM events (tiers validated / good, same exclusions), and the
  raw spectral slope of `imu_fixch` (swr_depth.py).

## Definitions

- **Biological night of date D:** sunset D → sunrise D+1 (`sleep_quant.sun_times`).
- **Location per second:** the zone of the nearest valid fix within ± 5 s.
  - Zones: house_1 / house_2 if inside the buffered rectangle, else field. Unknown if no fix within ± 5 s, or the fix is
    masked.
  - A signal gap is unknown, never "left".
- **Moving per second:** the head-IMU state from the default track's fix (`imu_state` 3 = locomoting, 2 = active,
  1 = still, 0 = unusable). Unusable counts as unknown.
- **Sleep periods:** SLEEP units (Watson-type, as `sleep_schedule.episode_units`): a maximal stretch of a record with no
  wake bout > 120 s and no unknown epoch, trimmed to its sleep, ≥ 20 min.
  - Short sleep = sleep seconds outside any SLEEP unit.
- **Long wake:** a wake bout ≥ 30 min (sensitivity 20 / 60 min), merged across sleep interruptions < 120 s.
- **Main sleep onset (MSO)** of night D: the start of the first sleep epoch after the last long wake that ends between
  sunset D and sunrise D+1 + 2 h.
  - It is defined only if the record covers at least the 3 h after it, or reaches sunrise. Otherwise flagged censored.
  - Text: when the animal stops its last long active bout of the night and settles for the main sleep.
- **Naps:** night sleep (NREM + REM) between sunset D and the MSO.
- **Main sleep:** sleep from the MSO on.
- **Time since onset** $\tau$: $t - \text{MSO}$ (h). It is carried into the next day's records until the next long wake.
  The morning-round gap is handled: unknown state, $\tau$ keeps counting.

## Analyses

- **A1, per animal × night raster.**
  - Rows = nights; x = 17:00 D → 13:00 D+1.
  - Strips: the 1-s state (WAKE / NREM / REM / no record), the WISER zone (house_1 / house_2 / field / unknown), and
    IMU locomotion.
  - Marked: sunset, sunrise, MSO, long wakes.
- **A2, per night table.**
  - MSO clock time; the last long wake (start, duration, share in the field).
  - Minutes of naps vs main sleep inside the night.
  - The share of the night's NREM that is after MSO.
  - The zone at MSO.
- **A3, summary.**
  - The MSO time distribution per animal.
  - The share of night NREM after MSO, pooled and per animal.
  - The share of wake and sleep in the field vs a house, by hour.
- **A4, ripples and depth vs $\tau$.**
  - Kept NREM ripple rate and depth (z within block) in 30-min bins of $\tau$ (0–14 h, spanning the morning gap), mean
    ± SEM over animals.
  - Within block: $r = \alpha_{a,b} + f(\tau) + \beta\,\text{hour harmonics}$, comparing the clock-only, τ-only and both
    models by held-out-day likelihood. Leave-one-date-out, WLS weights = NREM minutes.
  - Reading: H_main is supported if τ predicts the rate better than the clock (ΔlogL > 0 in ≥ 4 animals), and the
    00–04 h NREM is mostly after MSO (> 50 %).
- **A5, naps vs the main sleep start.** Rate and depth in naps vs in the first 2 h after MSO: per animal means, and at
  matched depth (rate ~ depth + nap within block).

## Rules

- **WISER claims stay coarse:** house vs field only (rectangle membership with a buffer), no position in the physical
  field, gaps reported as unknown with their share. Jitter floor and anchors are stated in the report.
- **Stillness is not sleep:** sleep comes from the ephys states only.
- **Handling:** sessions start / end at battery rounds. The first and last 10 min of each record are marked as
  handling-adjacent and kept, but flagged in the raster.
- **Output:**
  - `ephys/night_sleep_wiser.py` (`run`, `--selftest`);
  - report `results/2026c/ephys_spikes/reports/ephys_spikes_night_sleep_wiser_2026c.md` + CSVs + figures (one raster per
    animal, one summary);
  - run folder `$OUT_ROOT/2026c/night_sleep_wiser_<ts>/` (per-second animal tables cached).

## Amendment 1 (2026-10-09, the user's nap definition; written before computing)

The user: a nap must come before the main sleep starts, and must have plenty of activity before and after it (going out
to explore).

**Strict nap.** A sleep stretch inside the night's active phase that is flanked by exploration on both sides.
- **Sleep stretch:** sleep epochs (NREM / REM) merged across wake gaps < 120 s; an unknown epoch ends it. It needs
  ≥ 5 min from first to last sleep epoch, with ≥ 3 min NREM.
- **Active phase of night D:** from the start of the first long wake (≥ 30 min) beginning after 15:00 of D (the end of
  the day's main sleep) to the night's MSO.
  - If D has no MSO, the active phase ends at sunrise D+1 + 2 h. Such naps are flagged.
- **Flanks:** the 30 min before the stretch's first sleep epoch and the 30 min after its last. Each flank must meet
  both conditions:
  - ≥ 50 % of its seconds WAKE;
  - ≥ 5 min in the field (WISER zone field, known seconds only).
  - A flank not covered by the record is unverifiable, and the stretch is then not counted as a strict nap.

**Other night sleep.** Pre-MSO night sleep stretches that are not strict naps, kept as their own category.

**Outputs.**
- **Circadian NREM figure:** per clock hour, P(NREM) split into main sleep (τ defined) / strict naps / other.
- **Nap onset frequency:** strict-nap onsets per animal-night per clock hour, mean ± SEM over animals. It is marked
  on the circadian NREM depth / ripple-rate panel.
- **Per night:** the number of naps, their durations, and their zone (house / field).

## Amendment 2 (2026-10-09, written before recomputing): smoothed house / field membership

The user: "the in-the-field part can be smoothed; ask the other agents for the best algorithm".

**Answers.**
- IMU-video校准 (the WISER session): `semimarkov_decisions.hysteretic_visits` on the V3 track x / y, houses only.
  - Parameters: 5-s bins, 14-in buffer, enter 10 s, exit 30 s, near 0.5 / far 0.2, flicker merge 30 s.
  - Sensitivity: exit 10 / 60 s; buffer 21 in.
  - Caveats: the house rectangles are cohort-1 placements; the rain nights; the `qc_i1` windows.
- field2026-social-analysis-9b: the same rectangle caveat (house_1 moved only on 09-18, after the cohort). Handling
  windows (lids lifted at every catch, `cv/configs/cohort3_lid_events.json`, ± 5 min margin) are not exploration.

**Rectangle check.** Both sources put the cohort-3 houses away from the cohort-1 rectangles:
- house_1: 416.2, 716.8 (day-sleep NREM positions); 417.7, 716.9 (certified still segments). About 5 in off.
- house_2: 619.3, 732.3 and 621.2, 732.6. About 16 in off, at the rectangle's +y end.

**Membership (primary).**
- Rectangles: the cohort-1 sizes / orientation, re-centred on the IMU-certified still medians of the failure audit.
  Those are independent of the nap analysis: house_1 (417.7, 716.9), house_2 (621.2, 732.6).
- Rule: `hysteretic_visits` on V3 x / y; masked fixes (handling, silence, off-animal) dropped.
- Per second:
  - house_k inside a visit to house_k;
  - field when no visit and a fix lies within ± 5 s;
  - else unknown.
- Seconds inside a lid event ± 5 min are handling: removed from the flanks (not covered).

**Sensitivity.**
- exit 10 s; exit 60 s;
- the cohort-1 rectangles with a 21-in buffer;
- field seconds inside a `qc_i1` window not counted;
- the unsmoothed nearest-fix rule (the first run).
- Naps on the rain nights (09-03, 09-09, 09-10 morning) are reported apart.

## Amendment 3 (2026-10-09, written before computing): the nap advantage under depth control; REM vs SWR

The user asked two things:
- does the nap advantage survive controlling NREM depth?
- draw the REM share per NREM in figure C, to see whether REM and SWR compete or exclude each other.

**N1, nap vs main sleep at equal depth.**
- **Units:**
  - each strict nap (primary membership);
  - each 30-min τ chunk of the main sleep with ≥ 5 eligible NREM min. "First 2 h" = τ < 2 h.
  - Per unit: kept NREM SWR events, eligible NREM minutes, mean depth z (the raw `imu_fixch` slope, z within
    animal × block).
- **Model:**
  - $r_u = \alpha_{a,b} + \beta \tilde D_u + \gamma\,\mathrm{nap}_u$, WLS with weights = NREM minutes, SEs clustered by
    biological night, $t(G-1)$;
  - γ is reported with and without $\tilde D$, against all main sleep and against its first 2 h;
  - per-animal γ.
- **Depth-matched:** within animal × block, quintiles of depth over the eligible NREM seconds. The nap − main rate
  difference per quintile, averaged with weights = min(nap, main) NREM minutes.
- **Reading:** the nap advantage survives depth when γ (with depth) has a CI excluding 0, is positive in ≥ 4 animals,
  and the depth-matched difference is positive.

**R1, circadian REM share.** Per clock hour, REM seconds / NREM seconds (all included records), mean ± SEM over animals.
Drawn in figure C with depth and ripple rate.

**R2, across bins.**
- 30-min clock bins within animal × block with ≥ 5 eligible NREM min.
- Model: $r_k = \alpha_{a,b} + \beta_{REM}\,s_k + \beta_D \tilde D_k$ + hour harmonics (k = 1, 2), WLS, SEs clustered by
  date. $s_k$ = REM / (NREM + REM) in the bin.
- β_REM per 10 percentage points; per-animal signs.

**R3, NREM → REM vs NREM → WAKE transitions.**
- Transitions: NREM runs ≥ 120 s followed by ≥ 30 s of REM, or by ≥ 30 s of WAKE.
- Ripple rate (kept events / eligible NREM seconds) in 15-s bins over the last 120 s of the run, relative to the same
  run's −300 … −120 s baseline.
- Per animal: (last 60 s rate) / baseline, REM-bound vs WAKE-bound. Animal-level paired difference, $t(n-1)$.

**Reading.** Competition or exclusion is supported when:
- R2's β_REM < 0 beyond depth and hour, in ≥ 4 animals;
- and R3 shows a pre-REM drop below the run's own baseline that the pre-WAKE runs do not show.
- Otherwise, a shared circadian pattern is not evidence of competition.

**Output.** `ephys/swr_rem_naps.py` (`run`, `--selftest`); report `…swr_rem_naps_2026c.md`; the circadian figure with
REM / NREM in panel C.
