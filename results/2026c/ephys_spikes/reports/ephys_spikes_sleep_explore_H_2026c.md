# Sleep-behaviour explore — H: the house-entry clock after the battery rounds (cohort 2026c)

Plan [implementation_plan/2026-10-08-sleep-behaviour-explore.md](../../../../implementation_plan/2026-10-08-sleep-behaviour-explore.md) §13 Amendment 5 (rules written before results). Driver `ephys/sleep_perturb.py runH` (commit 9d7e5d3+dirty); bulk `D:\Field2026_analysis_out\2026c\sleep_explore_H_20261010_1432`; 100 replicates; runtime 9 min. **Technical ledger.**

## Reading (main session, 2026-10-10; claims #62, #63; #57–#60 updated)

**Question (plan §13):** with a clock anchored at the rat's own entry into its house (WISER), what happens between
release and entry, which clock the arousal follows, whether the first REM after entry is reproduced, and what the
opening NREM is.

**Short answer.**
- The opening "NREM" is the rat lying motionless in the field after release.
- Waking is highest in the field before the house entry, raised for the first hour in the house, and below the model
  1–3 h after entry, on both scorings.
- In the morning, the first REM after the first NREM in the house is reproduced.
- After evening rounds the first REM needs more NREM than the model on both scorings — the one REM-side residual.

- **House entries.**
  - All 94 post-round records have an entry within 60 min of release (both scorings).
  - Median 5.3 min after release (IQR 0–11.3); morning 7.2 min, evening 1.6 min.
  - It matches the field record on 09-05 exactly: SF07 16.7 min, SF09 2.7 min.
  - 31 / 94 have a house visit already running at the record start (t_H = 0): released next to a house, or WISER jitter
    within the 14-in buffer. Not separable here.
- **H4, the opening NREM (#62) — pre-registered reading "settling", not a scorer-edge artefact.**
  - Over the opening NREM bout (median 133 s; 49 / 51 records), the head IMU is still in 99–100 % of usable seconds,
    vs 97–98 % in length-matched NREM bouts in a house and 1–2 % in field WAKE. VeDBA ratio to the matched NREM is
    1.00 / 0.85.
  - WISER: none of the bout is in a house. Maximum displacement 7.4–7.7 in (≈ the 4–7-in jitter; house NREM 4.7–5.3 in,
    field WAKE 372 in).
  - So the rat lies motionless in the field right after release, then wakes and walks into a house. Sleep or awake
    immobility (e.g. freezing after handling) cannot be told apart by the head IMU or WISER. The list of episodes is
    in `ephys_spikes_sleep_explore_H_h4_opening_2026c.csv` (record start times in the bulk `house_entries.csv`) for a
    video check by the user.
- **H1, field vs house (#63; held-out, perturbation-blind; all 6 animals).**
  - Field before entry: WAKE O/E 1.73 [1.35, 2.21] (FINAL) / 1.65 [1.33, 2.11] (pass2med). REM O/E 0.68 / 0.53 (few
    REM in the field).
  - First hour after entry: WAKE 1.26 [1.01, 1.58] / 1.34 [1.18, 1.52].
  - 1–3 h after entry: WAKE 0.84 [0.71, 0.99] / 0.87 [0.76, 0.98] — below the model on both scorings. With the release
    clock (S2) the CIs had touched 1.
  - REM in the first hour after entry: FINAL 1.27 [1.02, 1.66], pass2med 1.06; 1–3 h: 1.00 / 0.84 [0.75, 0.93].
- **H2, which clock: unresolved.** Release vs entry clock for the arousal: −0.018 % [−0.114, +0.082] (FINAL),
  +0.006 % [−0.034, +0.050] (pass2med). The two clocks differ by minutes against τ_A of 20–40 min.
- **H3, the first REM after entry** (conditional on the observed states up to the first NREM after entry).
  - Morning: reproduced on both scorings (L_s' 15.0 / 15.4 min inside; L_N' inside except FINAL base, where the
    observed is slightly earlier: 11.8 vs 11.9–16.4).
  - Evening, on the NREM clock: above on both scorings — FINAL 22.9 min vs ≤ 21.0 / 22.3 (base / + A), pass2med 24.1 vs
    ≤ 17.0 / 17.8. On the wall clock: FINAL inside (58 vs 23–86), pass2med above (74 vs ≤ 54).
  - Onset after entry: ~10 min (morning), ~14 min (evening).
- **What changes:**
  1. The post-round sequence is: release → lying still in the field (~2 min, half the rounds) → waking and walking (WAKE
     ~1.7× the model) → house entry (median 5 min) → sleep onset (~10–14 min later) → the first hour in the house with
     WAKE ~1.3× → 1–3 h with fewer wakes than the model.
  2. The morning first-REM delay of #57 is the field period.
  3. After evening rounds the first REM needs more NREM than predicted: #60, now seen on both scorings with the entry
     clock.
  4. The calm phase 1–3 h after entry is clear descriptively. Part T's two-phase term (release clock) had no held-out
     gain. Whether it is better timed by the entry is a possible next test.

## Definitions

```
Part H of the sleep-behaviour explore (plan §13, Amendment 5, written before results): a post-round recording starts at
the rat's release into the paddock (field operator, 2026-10-10); the rat walks into its house on its own minutes later.
Part H anchors a second clock at the WISER house entry and asks what the ~2 min of NREM that opens half the records is.

Usage:  python ephys/sleep_perturb.py runH [--scorings final pass2med] [--reps 100] [--workers 8]

Definitions (rounds, records, scorings, bases as parts S / P / L; s = seconds since the post-round record start):
  house entry t_H   start of the first WISER house visit overlapping [t0, t0 + 60 min): default tracks (V3 / B2; fixes
                    flagged m_silence / m_off_animal / m_tag_validity dropped, m_handling kept), houses re-centred on the
                    cohort-3 rest clusters (house_1 (417.7, 716.9), house_2 (621.2, 732.6), the wiser_rois.json rectangles
                    moved), semimarkov_decisions.hysteretic_visits (14-in buffer, 5-s bins, enter 10 s, exit 30 s);
                    t_H = max(visit start - t0, 0) (a visit already running at t0 gives 0, flagged). No visit or no fixes
                    -> no anchor.
  H1   S's held-out perturbation-blind steps (pb_rem, pb_wake), anchored rounds, s < 3 h: "field, before entry" (s < t_H),
       "after entry 0-1 h", "after entry 1-3 h" (entry clock s - t_H); O/E = sum [y = k] / sum p_k, block-bootstrap CI.
  H2   post-entry steps (t_H <= s < 3 h): part P's one-phase arousal with the release clock s vs the entry clock s - t_H,
       base = B-full trained without the post-round 3 h, cross-fitted by date parity; Delta held-out log-loss % (entry -
       release), block-bootstrap CI. "Follows the entry" = CI < 0 on both scorings; "follows release" = CI > 0 on both.
  H3   t_N' = the first NREM bout start at or after t_H; conditional simulation with every observed bout before t_N'
       forced (part P's generative base, without and with A on the release clock); L_s' = t_R - t_N' and L_N' (NREM
       clock), KM medians, observed vs 100 replicates, morning / evening; reproduced = inside the 95 % range. Also the
       observed t_H and t_N' - t_H (KM medians).
  H4   records whose first bout is NREM: over the opening bout, head IMU (imu_seconds_cache; of the usable seconds: share
       still, share locomoting, mean VeDBA_1s) and WISER (share of seconds in a house, maximum displacement from the first
       position, inches) vs (a) matched NREM bouts of the same animal (length within +-50 %, in a house = >= 50 % of the
       bout's positioned seconds in a house, not in the 3 h after a round) and (b) field WAKE bouts >= 60 s. Rule:
       "scorer-edge artefact likely" = still share >= 0.2 lower AND VeDBA >= 1.5x the matched NREM (medians); "settling"
       = still share within 0.1; otherwise unresolved.
```

## Verdicts

| scores | part | verdict | numbers |
|---|---|---|---|
| final | H2 | unresolved | Delta (entry - release) -0.018 % [-0.114, +0.082], entry better 4/6 |
| final | H3 | reproduced | morning conditional, base Ls'_KM_median_min obs 15.0 vs 13.3-20.1 (inside); morning conditional, base LN'_KM_median_min obs 11.8 vs 11.9-16.4 (below); morning conditional, base + A Ls'_KM_median_min obs 15.0 vs 13.3-20.0 (inside); morning conditional, base + A LN'_KM_median_min obs 11.8 vs 11.0-15.8 (inside); evening conditional, base Ls'_KM_median_min obs 58.1 vs 22.5-82.5 (inside); evening conditional, base LN'_KM_median_min obs 22.9 vs 12.4-21.0 (above); evening conditional, base + A Ls'_KM_median_min obs 58.1 vs 24.7-86.4 (inside); evening conditional, base + A LN'_KM_median_min obs 22.9 vs 13.7-22.3 (above) |
| final | H4 | settling | still share opening 1.00 vs matched NREM 0.98 (field WAKE 0.02); VeDBA ratio 1.00; opening bout in a house 0.00 |
| pass2med | H2 | unresolved | Delta (entry - release) +0.006 % [-0.034, +0.050], entry better 2/6 |
| pass2med | H3 | not reproduced | morning conditional, base Ls'_KM_median_min obs 15.4 vs 11.2-17.3 (inside); morning conditional, base LN'_KM_median_min obs 11.8 vs 9.6-13.8 (inside); morning conditional, base + A Ls'_KM_median_min obs 15.4 vs 11.8-17.7 (inside); morning conditional, base + A LN'_KM_median_min obs 11.8 vs 9.4-13.3 (inside); evening conditional, base Ls'_KM_median_min obs 73.8 vs 15.2-49.6 (above); evening conditional, base LN'_KM_median_min obs 24.1 vs 9.7-17.0 (above); evening conditional, base + A Ls'_KM_median_min obs 73.8 vs 14.3-54.1 (above); evening conditional, base + A LN'_KM_median_min obs 24.1 vs 10.5-17.8 (above) |
| pass2med | H4 | settling | still share opening 0.99 vs matched NREM 0.97 (field WAKE 0.01); VeDBA ratio 0.85; opening bout in a house 0.00 |

## House entries

| scores | round_records | anchored | with_nrem_after_entry |
|---|---|---|---|
| final | 94 | 94 | 94 |
| pass2med | 94 | 94 | 94 |

t_H (min) over the distinct post-round starts: median 5.3, IQR 0.0-11.3, none within 60 min 0 of 94, a visit already running at the start 31.

## H1: field before entry vs after entry (held-out, perturbation-blind)

| scores | cell | transition | steps | observed | expected | OE | ci_lo | ci_hi | animals |
|---|---|---|---|---|---|---|---|---|---|
| final | after entry 0-1 h | WAKE | 9966 | 439 | 349.4972 | 1.2561 | 1.0054 | 1.5841 | 6 |
| final | after entry 0-1 h | REM | 9966 | 193 | 151.8949 | 1.2706 | 1.0159 | 1.6616 | 6 |
| final | after entry 1-3 h | WAKE | 20565 | 535 | 637.8013 | 0.8388 | 0.7099 | 0.9945 | 6 |
| final | after entry 1-3 h | REM | 20565 | 457 | 457.577 | 0.9987 | 0.8795 | 1.1541 | 6 |
| final | field, before entry | WAKE | 2034 | 120 | 69.5205 | 1.7261 | 1.3476 | 2.2063 | 6 |
| final | field, before entry | REM | 2034 | 16 | 23.6121 | 0.6776 | 0.4537 | 0.9775 | 6 |
| pass2med | after entry 0-1 h | WAKE | 10102 | 459 | 341.9219 | 1.3424 | 1.1833 | 1.5241 | 6 |
| pass2med | after entry 0-1 h | REM | 10102 | 191 | 181.0538 | 1.0549 | 0.8798 | 1.2944 | 6 |
| pass2med | after entry 1-3 h | WAKE | 20701 | 538 | 618.6173 | 0.8697 | 0.7613 | 0.9842 | 6 |
| pass2med | after entry 1-3 h | REM | 20701 | 471 | 564.3095 | 0.8346 | 0.7534 | 0.9296 | 6 |
| pass2med | field, before entry | WAKE | 2069 | 111 | 67.1248 | 1.6536 | 1.3265 | 2.106 | 6 |
| pass2med | field, before entry | REM | 2069 | 21 | 39.5743 | 0.5306 | 0.3116 | 0.8153 | 6 |

## H2: which clock carries the arousal

| scores | steps | wakes | rounds | delta_entry_minus_release_pct | ci_lo | ci_hi | animals_entry_better | animals | release_a | release_tau_s | release_ll | entry_a | entry_tau_s | entry_ll |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| final | 39419 | 1380 | 89 | -0.0179 | -0.1139 | 0.082 | 4 | 6 | 0.7014 | 1200.0 | -5699.4743 | 0.5964 | 1200.0 | -5700.344 |
| pass2med | 39910 | 1425 | 90 | 0.0059 | -0.0335 | 0.0503 | 2 | 6 | 0.5855 | 2400.0 | -5861.239 | 0.7468 | 1200.0 | -5861.3856 |

## H3: the first REM after the house entry

| scores | kind | variant | stat | observed | rounds | sim_mean | sim_2.5% | sim_97.5% | side |
|---|---|---|---|---|---|---|---|---|---|
| final | morning | observed | tH_median_min | 7.17 | 50 | nan | nan | nan | nan |
| final | morning | observed | onset_after_entry_median_min | 10.51 | 50 | nan | nan | nan | nan |
| final | morning | conditional, base | Ls'_KM_median_min | 15.0 | 50 | 16.83 | 13.35 | 20.11 | inside |
| final | morning | conditional, base | LN'_KM_median_min | 11.83 | 50 | 13.97 | 11.87 | 16.41 | below |
| final | morning | conditional, base + A | Ls'_KM_median_min | 15.0 | 50 | 16.99 | 13.3 | 19.97 | inside |
| final | morning | conditional, base + A | LN'_KM_median_min | 11.83 | 50 | 13.67 | 11.0 | 15.85 | inside |
| final | evening | observed | tH_median_min | 1.56 | 44 | nan | nan | nan | nan |
| final | evening | observed | onset_after_entry_median_min | 14.38 | 44 | nan | nan | nan | nan |
| final | evening | conditional, base | Ls'_KM_median_min | 58.13 | 44 | 40.66 | 22.54 | 82.48 | inside |
| final | evening | conditional, base | LN'_KM_median_min | 22.92 | 44 | 16.7 | 12.42 | 21.0 | above |
| final | evening | conditional, base + A | Ls'_KM_median_min | 58.13 | 44 | 44.32 | 24.67 | 86.44 | inside |
| final | evening | conditional, base + A | LN'_KM_median_min | 22.92 | 44 | 17.21 | 13.67 | 22.27 | above |
| pass2med | morning | observed | tH_median_min | 7.17 | 50 | nan | nan | nan | nan |
| pass2med | morning | observed | onset_after_entry_median_min | 10.11 | 50 | nan | nan | nan | nan |
| pass2med | morning | conditional, base | Ls'_KM_median_min | 15.43 | 50 | 13.97 | 11.21 | 17.31 | inside |
| pass2med | morning | conditional, base | LN'_KM_median_min | 11.77 | 50 | 11.47 | 9.61 | 13.78 | inside |
| pass2med | morning | conditional, base + A | Ls'_KM_median_min | 15.43 | 50 | 14.44 | 11.82 | 17.68 | inside |
| pass2med | morning | conditional, base + A | LN'_KM_median_min | 11.77 | 50 | 11.39 | 9.41 | 13.3 | inside |
| pass2med | evening | observed | tH_median_min | 1.56 | 44 | nan | nan | nan | nan |
| pass2med | evening | observed | onset_after_entry_median_min | 14.09 | 44 | nan | nan | nan | nan |
| pass2med | evening | conditional, base | Ls'_KM_median_min | 73.78 | 44 | 27.31 | 15.22 | 49.64 | above |
| pass2med | evening | conditional, base | LN'_KM_median_min | 24.05 | 44 | 13.1 | 9.74 | 17.03 | above |
| pass2med | evening | conditional, base + A | Ls'_KM_median_min | 73.78 | 44 | 29.95 | 14.35 | 54.09 | above |
| pass2med | evening | conditional, base + A | LN'_KM_median_min | 24.05 | 44 | 13.33 | 10.49 | 17.77 | above |

## H4: the opening NREM (medians)

| scores | opening_bouts | open_still | open_loco | open_vedba | open_house_share | open_disp_in | open_len_s | matched_still | matched_loco | matched_vedba | matched_disp_in | fieldwake_still | fieldwake_vedba | fieldwake_disp_in | still_diff | vedba_ratio | reading |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| final | 49 | 0.995 | 0.0 | 0.067 | 0.0 | 7.428 | 133.0 | 0.982 | 0.0 | 0.067 | 4.655 | 0.019 | 2.741 | 371.809 | 0.013 | 0.998 | settling |
| pass2med | 51 | 0.989 | 0.0 | 0.065 | 0.0 | 7.703 | 133.0 | 0.973 | 0.0 | 0.076 | 5.328 | 0.009 | 2.849 | 372.551 | 0.016 | 0.853 | settling |

