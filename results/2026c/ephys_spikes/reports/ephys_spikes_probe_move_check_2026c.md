# Did the SF07 / SF11 probes actually move at the logged 1/4-turn advances? — cohort `2026c`

Generated 2026-09-06 by `ephys/probe_move_check.py` from the raw sessions on `E:\3rd_rat_spikes` (10-min windows). Companion files:
`ephys_spikes_probe_move_check_2026c_features.csv` (per window × channel), `ephys_spikes_probe_move_check_2026c_pairs.csv`
(per comparison), figure `figures/ephys_spikes_probe_move_check_2026c.png`. Regenerate; do not hand-edit.

**Question (operator, 2026-09-06 13:55, incident log):** three 1/4-turn advances each on SF07 and SF11 (09-04, 09-05, 09-06) produced
little visible signal change; the microdrives may be slipping. Does the recorded signal show a displacement?

## Answer

| logger | logged advance | data on disk | verdict |
|---|---|---|---|
| SF07 | 09-04 14:00 | pre `8_20260904_080936`, post `11_20260904_140054` | **no displacement** — fingerprint identical 30 min after the restart (gamma-profile r = 0.99, theta 0.98, ripple-band 0.97; best shift 0 sites on all shanks) and after 5.3 h (0.97), same as the no-move controls (0.94–0.99) |
| SF07 | 09-05 13:31 | pre `2_20260905_093310`, post `6_20260905_133118` | **no displacement** — r = 1.00 at +30 min, 0.99 at +4.3 h, shift 0 everywhere |
| SF07 | 09-06 13:29 | 09-05 evening vs the 12:44 test recording `1_20260906_123931` | **no change since 09-05 evening** (r = 0.98, 0 of 64 channels changed by > 0.15 log units). If the turn preceded the test recording (12:31–12:38) it did not move the probe either; if it followed, the post-restart session (still on the card) decides |
| SF11 | 09-04 13:56 | pre `7_20260904_082050`, post `9_20260904_135650` | **no displacement** — r = 0.96 at +30 min, 0.85 settled; controls 0.71–0.98 |
| SF11 | 09-05 15:11 | pre `3_20260905_094205`, post `7_20260905_151133` | **no lasting displacement** — at +30 min the gamma profile was disrupted (r = 0.11; 13 channels, mostly shank 3, up to ×10 higher gamma) but by +2.8 h it was back to the pre-move profile (r = 0.89; 1 channel changed). A real advance does not revert |
| SF11 | 09-06 13:33 | 09-05 evening vs the 12:46 test recording `0_20260906_124136` | **something changed, but not a translation of the probe**: shank 2 lost ×4 power in every band (gamma −0.62, theta −0.69, MUA −0.59 log10) including a 20 % drop of its spike-band noise floor, shank 3 channels 3 and 17 dropped ×6–10, while shanks 1 and 4 kept their profile shape (r = 0.98 / 0.90). A 1/4 turn moves all four shanks together and would re-map every channel |

**Sensitivity.** The gamma-band profile along each shank has site-scale structure: shifting a window's own SF07 profile by one site (50 µm)
lowers its whole-probe correlation from 1.00 to 0.85–0.87 (per shank 0.74 / 0.5 / −0.1…−0.3 / 0.3), and for SF11 to ≈ 0.0–0.2. Every
move comparison stays at 0.96–1.00 (SF07) and 0.85–0.96 (SF11 settled / +30 min), i.e. a displacement of one site or more is excluded for the
09-04 and 09-05 advances on both loggers. SF07 shank 4 is smoother (less sensitive); shanks 1–3 carry the evidence.

**Reading of the SF11 09-06 change.** A whole-shank attenuation that also lowers the electrode noise floor looks like a signal-path change
on that shank (impedance / contact / reference) or a shank sitting at a tissue boundary — not the probe advancing. It happened somewhere
between 09-05 18:08 and 09-06 12:46 (night + morning sessions still on the card; the 09-06 turn may or may not precede the test recording).
Check shank-2 impedances at the next handling; the post-restart session and the 2026-09-07 drive test decide.

**Consequence for sorting (provisional).** If the drives did not advance, SF07 09-04/09-05/09-06 and SF11 09-04/09-05 are probably the same
tissue across the "moves"; the UNSTABLE windows stay as logged (conservative) until confirmed by unit/waveform matching across the boundaries.

## Method

Windows: 10 min (600 s) per condition; "pre" = the last 10 min of the pre-move session ending 60 s before its Stop; "+30 min" = 30–40 min
after the post-move Record Start; "settled" = the last 10 min of the post-move session (4.3–5.5 h after the restart; SF11 09-05 only 2.8 h);
"test" = minutes 5–15 of the 09-06 test recording. Controls (no move in between): the same session 5 h apart (A0→A), across the night with a
battery swap (B→C: 19:2x → 08:2x/08:3x), and across the morning swap (C→D). Per-channel features are computed on the raw 20 kHz
amplifier stream after subtracting each channel's chunk median; LFP features on a 1250 Hz decimation.

## Definitions

| quantity | formula | plain text |
|---|---|---|
| `log_<band>` | `log10( mean_{f ∈ band} P_c(f) )`, Welch PSD, 2-s Hann segments, 1250 Hz; bands delta 1–4, theta 5–10, beta 15–30, gamma 30–80, ripple 120–200 Hz | log band power of channel c in the window (arbitrary ADC² units; only differences between windows are used) |
| `mua_rate_hz` | `#{ onsets of x_hp,c(t) < −5·1.4826·median\|x_hp,c\| } / 600 s`, x_hp = 300–3000 Hz Butterworth (order 3, zero-phase) | multi-unit event rate per channel: negative threshold crossings at −5 robust SD |
| `spike_band_mad_adc` | `1.4826 · median\|x_hp,c\|` (median over 2-min chunks) | spike-band noise floor of the channel (ADC), neural background + electrode noise |
| `ripple_events_per_min` | envelope `e_c = smooth_10ms(\|Hilbert(x_120–200,c)\|)`, `z_c = (e_c − median e_c)/(1.4826·MAD e_c)`; events = runs of `z_c > 4` lasting ≥ 20 ms; count / 10 min | ripple-band burst rate per channel; a loose detector (state-dependent; it does not certify hippocampal SWRs) |
| profile | `p_c = q_c − median_c q_c` over the 64 channels of one window (for rates: `q = log10(rate + 0.01)`) | the spatial fingerprint of where each channel sits: feature relative to the probe median, so a global state/gain change drops out |
| `r` (fingerprint correlation) | Pearson correlation of `p` between two windows over the 64 channels | 1 = channels see the same tissue in both windows; a re-mapping of tissue to channels (a move) lowers it toward the shifted-self value |
| shift test | for shank s and shift k ∈ [−3, 3]: `corr(p_pre[i], p_post[i+k])` over the overlapping sites in the xml order; best k and its gain `corr(best) − corr(0)` | which displacement along the shank best explains the post window; 0 with gain 0 = no displacement. Valid for SF07 (site order verified by `probe_map_check`); for SF11 only the shank grouping is verified, so shifts are not interpretable and only whole-probe / per-shank correlations are used |
| sensitivity calibration | `corr(p[i], p[i+1])` within each shank of a single window | what r a true one-site (50 µm) move would produce; the move comparisons must fall well below it to claim a move |
| per-shank change | `median_{c ∈ shank}(q_c,post − q_c,pre)` in log10 units (0.3 = ×2, 0.6 = ×4) | level change of a whole shank, NOT median-normalised, to separate a shank-specific attenuation from a global state change |

Caveats: behavioural state differs between windows (theta / ripple-band / MUA levels swing by up to ×10 between an evening active window and
a morning sleep window), which is why only the median-normalised spatial profile and the no-move controls carry the conclusion; 10-min
windows; the SF11 site order is unverified; the 09-06 comparisons span an unobserved night (sessions still on the EVO cards).
