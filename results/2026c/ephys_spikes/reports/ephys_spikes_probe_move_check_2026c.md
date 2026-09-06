# Did the SF07 / SF11 probes actually move at the logged 1/4-turn advances? — cohort `2026c`

Generated 2026-09-06 by `ephys/probe_move_check.py` (10-min windows, `..._features.csv` / `..._pairs.csv`, figure
`figures/ephys_spikes_probe_move_check_2026c.png`) and `ephys/probe_move_timeseries.py` (5-min window every hour from 09-04 08:30 to the
09-06 test recordings, `..._timeseries.csv`, figure `figures/ephys_spikes_probe_move_timeseries_2026c.png`) from the raw sessions on
`E:\3rd_rat_spikes`. Regenerate; do not hand-edit. Revised 2026-09-06 (operator: the effect of a turn is only visible ≥ 3 h later —
comparisons within the first hours after a restart are therefore NOT used as evidence; everything below rests on windows ≥ 3.5 h after a
turn, spaced across the following day(s), plus the hourly series).

**Question (operator, 2026-09-06 13:55, incident log):** three 1/4-turn advances each on SF07 and SF11 (09-04, 09-05, 09-06) produced
little visible signal change; the microdrives may be slipping. Does the recorded signal show a displacement?

## Answer

**SF07: no displacement, at any delay.** With the 10 min before the 09-04 turn as reference, the gamma-profile fingerprint stays at
r = 0.96–1.00 in every hourly window for 47 h — +3.5 h 0.98, +4.5 h 0.99, +6.5 h 0.98, +12.5 h 0.96, +18.5 h 0.95, the whole 09-05
day 0.98–0.99, +24.5…27.5 h (after the second turn) 0.98, and the 09-06 12:44 test recording 0.96 — with best along-shank shift 0 on
every shank throughout (a transient dip to 0.84–0.86 at 09-05 04:30–05:30, before the second turn, recovers by 06:30). Three turns
would add up to ≈ 4–5 sites if they were real; one site (50 µm) alone would pull r down to 0.85–0.87 (calibration below). The drive did
not advance the probe on 09-04 or 09-05; for 09-06 the same holds if the turn preceded the test recording (12:31–12:38), otherwise the
post-restart session (still on the card) decides.

**SF11: no whole-probe displacement on 09-04 or 09-05; a shank-2-local change before 09-06 12:46.** Versus the pre-09-04 reference the
fingerprint runs 0.80–0.88 in afternoon windows and 0.94–0.97 in night windows (a state pattern, identical before and after the turns:
the 09-05 afternoon, before the second turn, is 0.83–0.84 too); versus the pre-09-05 reference the post-turn windows are 0.96–0.99.
Shanks 1 and 4, whose profiles have site-scale structure, keep r = 0.92 / 0.98 from 09-04 13:30 all the way to the 09-06 test
recording. In that test recording shank 2 has lost ×4 LFP power in every band (gamma −0.62, theta −0.69 log10) and ~25 % of its
spike-band amplitude, and shank-3 channels 3 and 17 dropped ×6–10; shank 3 had been drifting since the 09-05 morning. A 1/4 turn moves
all four shanks together and would re-map every channel — two unchanged shanks exclude that. What changed on shank 2 (tissue under that
shank, or its signal path) cannot be decided from the recording; it happened between 09-05 18:08 and 09-06 12:46 (night + morning
sessions still on the EVO card). Check shank-2 impedances at the next handling; the post-restart 09-06 session and the 2026-09-07 drive
test decide.

| logger | logged advance | evidence windows (all ≥ 3.5 h after the turn) | verdict |
|---|---|---|---|
| SF07 | 09-04 14:00 | +3.5 h → +47 h hourly, r = 0.95–1.00, shift 0 | no displacement |
| SF07 | 09-05 13:31 | +3.2 h → +4.3 h (0.98–0.99 vs pre-turn-2), 09-06 test 0.97 | no displacement |
| SF07 | 09-06 13:29 | 09-05 evening → 09-06 12:44 test: 0.98, 0 of 64 channels changed | none before the test recording; post-restart session pending |
| SF11 | 09-04 13:56 | +3.5 h → +24 h: 0.80–0.97 (state pattern), shanks 1/4 stable | no displacement |
| SF11 | 09-05 15:11 | +1.3 h / +2.3 h vs pre-turn-2: 0.99 / 0.96 (only 2.9 h on disk); 09-06 test vs pre-turn-2: shanks 1/4 0.98 / 0.85 | no whole-probe displacement |
| SF11 | 09-06 13:33 | 09-05 evening → 09-06 12:46 test: shank 2 ×4 power loss, shank 3 partial, shanks 1/4 unchanged | shank-local change, not a translation; cause open |

**Sensitivity.** The gamma-band profile along each shank has site-scale structure: shifting a window's own SF07 profile by one site
(50 µm) lowers its whole-probe correlation from 1.00 to 0.85–0.87 (per shank 0.74 / 0.5 / −0.1…−0.3 / 0.3), and for SF11 to ≈ 0.0–0.2.
SF07 shank 4 is smoother (less sensitive); shanks 1–3 carry the evidence. No-move control pairs (same session 5 h apart, across a night
with a battery swap, across the morning swap) give r = 0.94–0.99 (SF07) and 0.71–0.98 (SF11) — the move comparisons sit inside these
ranges.

**Consequence for sorting (provisional).** If the drives did not advance, SF07 09-04/09-05(/09-06) and SF11 09-04/09-05 are probably the
same tissue across the "moves"; the UNSTABLE windows stay as logged (conservative) until confirmed by unit/waveform matching across the
boundaries. SF11 shank 2 after 09-05 18:08 is a separate question.

## Method

Pair check (`probe_move_check.py`): 10-min windows — "pre" = the last 10 min of the pre-move session ending 60 s before its Stop;
"settled" = the last 10 min of the post-move session (4.3–5.5 h after the restart; SF11 09-05 only 2.8 h); "test" = minutes 5–15 of the
09-06 test recording; the "+30 min" windows are kept in the CSV but carry no weight. Hourly series (`probe_move_timeseries.py`): a
5-min window at every full hour + 30 min from 09-04 08:30 to 09-05 17:30 plus the 09-06 test recording, each compared with the last
window before turn 1 (ref1, 13:30 09-04) and before turn 2 (ref2, 12:30 / 14:30 09-05). Per-channel features are computed on the raw
20 kHz amplifier stream after subtracting each channel's chunk median; LFP features on a 1250 Hz decimation.

## Definitions

| quantity | formula | plain text |
|---|---|---|
| `log_<band>` | `log10( mean_{f ∈ band} P_c(f) )`, Welch PSD, 2-s Hann segments, 1250 Hz; bands delta 1–4, theta 5–10, beta 15–30, gamma 30–80, ripple 120–200 Hz | log band power of channel c in the window (arbitrary ADC² units; only differences between windows are used) |
| `mua_rate_hz` | `#{ onsets of x_hp,c(t) < −5·1.4826·median\|x_hp,c\| } / T`, x_hp = 300–3000 Hz Butterworth (pair check: order 3 zero-phase over 10 min; series: order 2 single-pass over the first 59 s) | multi-unit event rate per channel: negative threshold crossings at −5 robust SD |
| `spike_band_mad_adc` | `1.4826 · median\|x_hp,c\|` | spike-band amplitude floor of the channel (ADC): neural background + electrode/amplifier noise |
| `ripple_events_per_min` (pair check only) | envelope `e_c = smooth_10ms(\|Hilbert(x_120–200,c)\|)`, `z_c = (e_c − median e_c)/(1.4826·MAD e_c)`; events = runs of `z_c > 4` lasting ≥ 20 ms; count / 10 min | ripple-band burst rate per channel; a loose detector (state-dependent; it does not certify hippocampal SWRs) |
| profile | `p_c = q_c − median_c q_c` over the 64 channels of one window (for rates: `q = log10(rate + 0.01)`) | the spatial fingerprint of where each channel sits: feature relative to the probe median, so a global state/gain change drops out |
| `r` (fingerprint correlation), `_r_vs_ref1/2` | Pearson correlation of `p` between two windows over the 64 channels | 1 = channels see the same tissue in both windows; a re-mapping of tissue to channels (a move) lowers it toward the shifted-self value |
| per-shank `r`, `_shank_r_vs_ref` | the same correlation over the 16 channels of one shank, demeaned within the shank | shape change of one shank's profile, independent of its level |
| shift test, `_shift_vs_ref` | for shank s and shift k ∈ [−3, 3]: `corr(p_pre[i], p_post[i+k])` over the overlapping sites in the xml order; best k (gain = `corr(best) − corr(0)` in the pair CSV) | which displacement along the shank best explains the later window; 0 = no displacement. Valid for SF07 (site order verified by `probe_map_check`); for SF11 only the shank grouping is verified, so shifts are not interpretable and only whole-probe / per-shank correlations are used |
| sensitivity calibration | `corr(p[i], p[i+1])` within each shank of a single window | what r a true one-site (50 µm) move would produce; the move comparisons must fall well below it to claim a move |
| per-shank level, `_shank<k>_median` | `median_{c ∈ shank} q_c` (NOT median-normalised) | level of a whole shank, to separate a shank-specific attenuation from a global state change (0.3 log10 = ×2, 0.6 = ×4) |

Caveats: behavioural state differs between windows (theta / ripple-band / MUA levels swing by up to ×10 between an evening active window and
a morning sleep window; the spike-band floor doubles during active periods), which is why only the median-normalised spatial profile,
the reference-relative series and the no-move controls carry the conclusion; the SF11 site order is unverified; the 09-06 comparisons
span an unobserved night (sessions still on the EVO cards); the SF11 post-turn-2 session on disk is only 2.9 h long.
