# Scientific report — July-4 fireworks and coordinated following

*Standalone, current-state report (2026-07-12). Tests a field observation — "during the July 4th
fireworks (~21:00), increased group-level movement, more following" (FIELD_OBSERVATIONS Day 7) — against
WISER following-episode data and the camera-mic audio. **Status: ⚠️ Candidate.** One fireworks night;
a timing coincidence, not a validated mechanism.*

## Biological picture

On the night of 2026-07-04, fireworks were audible in the paddock. The field observer noted apparent
increased group following, but flagged it as "not a simple fear/escape response" and "not confirmed."
Working only with what the sensors resolve — WISER lagged co-movement (module-8 "following"), coarse and
in an unverified inch frame, plus **relative** camera-mic level (not calibrated SPL) — the data show a
**real, acoustically time-locked burst of coordinated following on 07-04**. The single most important
limitation is that WISER cannot tell **social following** from a **synchronized startle bolt to shelter**:
both produce close, heading-aligned co-movement. So this is reported as a fireworks-associated *coordinated
co-movement* episode, not as demonstrated social following.

![Fireworks → following time-course](plots/fireworks_following_audio_psth.png)

*Both camera mics (A) rise together into the shaded fireworks-active window (21:25–22:15, defined by
sustained level); the 07-04 following rate (B, red) spikes above the other-10-nights matched-clock control
(grey band) at the acoustic peak. The following also ramps up slightly before the peak — the coincidence is
with the fireworks window, not a clean one-volley-one-burst response.*

## Finding 1 — 07-04 following is elevated, and the elevation is time-localized (not a whole-night level shift)

A whole-night average is a single data point and only weakly elevated (07-04 movement-normalized following
0.0175 vs a dry-normal-night mean 0.0136; **n = 1**). Splitting the night into 10-min bins and comparing
each bin to the **same clock window on the other 10 nights** (real n = 10 controls) localizes the effect:
two sharp bursts, **21:30 (z = +2.4)** and **22:20 (z = +5.2)**, separated by near-zero bins — the bursty
pattern expected from discrete fireworks volleys, which the hour-average washes out (whole 21:00–22:00
window z = +0.5 only). The 22:20 burst survives multiple-comparison correction (z > 5 over ~48 bins/night);
the 21:30 burst is more marginal.

## Finding 2 — the following bursts coincide with acoustically-confirmed fireworks (two independent mics)

Both CH01 and CH02 mics independently place the fireworks at **21:25–22:55, peaking 21:35–21:45** (peak
level near 0 dBFS-relative, ~10–15 dB above the pre/post baseline), silent before 21:00 and after 23:00.
The 07-04 following-episode count tracks this: cross-correlation of following vs audio-peak is **r ≈ 0.37
(CH01) / 0.34 (CH02) at lag 0**, the loudest audio bins (21:35–21:45) coincide with the peak following
bins, and the 22:20 following burst falls on the 88th–90th-percentile-loudest minute of the window. CH02
reproduces CH01 with a best-lag of −5 min (near zero), so the coincidence is not a single-channel artifact.

## Finding 3 — WISER cannot resolve the mechanism; the co-movement is close and coordinated

The burst episodes are tight: 4–18 in separation, heading cosine 0.93–1.00, 1–19 s lag — coordinated close
co-movement consistent with **either** following **or** a startle co-flight. This is the unresolved
construct: timing coincidence does not distinguish them. A focused **video watch-list** (96 episodes across
the two bursts, highest-confidence clean-routing clips at 21:35–21:38 on CH03/CH04 and 22:18 on CH03) is
staged to settle it on camera.

## What is not claimed

- **Not** "fireworks cause social following." The construct (following vs startle co-flight) is unresolved.
- **Not** a rain effect: AWN shows 07-04 was **dry in-window** (0.00 mm), so this is not confounded by rain;
  separately, genuinely rainy nights (06-30, 07-06) show *less* following, not more.
- **Not** a clean stimulus–response: following ramps from ~21:00, before the acoustic peak, and drops while
  the audio is still loud — so it is locked to the fireworks *window*, not to individual volleys.

## Unresolved / next step

The one decisive check is **video** at the burst times (21:35, 22:20) — is it following or a bolt to
shelter? The watch-list (`fireworks_0704_video_watchlist.csv`) is ready. Confirmation on more disturbance
nights (thunder, etc.) and a movement-normalized burst rate would strengthen it.

## Technical references

Change log: `change_log/2026-07-12-fireworks-following-audio.md`. Drivers:
`scripts/analyze_fireworks_timecourse.py` (10-min between-night test), `scripts/analyze_fireworks_audio_align.py`
(audio↔following), `scripts/analyze_following_weather.py` (weather cross-check),
`scripts/make_fireworks_watchlist.py`, `scripts/plot_fireworks_psth.py`. Audio features:
`audio/outputs/audio_features_CH0{1,2}_2026-07-04.csv`.

---

## Quantitative appendix — how each quantity was computed

Following throughout = **Phase-B2 strict lagged-following episodes** (module 8): a sustained
leader→follower trail where the follower is within 24 in of where the leader was, headings aligned
(cos > 0.5), at a lag of 1–30 s; herd-level, "leader" = temporal order, inch frame UNVERIFIED.

- **frac_bouts_following** — fraction of a follower's movement bouts overlapping any episode; range [0,1];
  movement-normalized (separates *more following* from *more moving*). 07-04 = 0.0175; dry-normal mean
  0.0136; matched dry+burrow+late night 07-05 = 0.0121 (07-04 = 1.45×).
- **Between-night bin z** — for a 10-min bin, $z = (n_{0704} - \bar n_{\text{other}})/s_{\text{other}}$
  over the 10 non-07-04 nights at the SAME clock. 21:30 z = +2.4 (39 vs 12.3±11.0); 22:20 z = +5.2
  (17 vs 3.6±2.6). Whole 21:00–22:00 window z = +0.5 (bursts washed out by averaging).
- **audio peak / leq (dBFS-relative)** — per 1-min window, max instantaneous level (`peak_dbfs_relative`,
  for transient volleys) and mean level (`leq_dbfs_relative`, sustained). RELATIVE full-scale ref, NOT SPL.
  Fireworks-active window = longest contiguous run with either mic leq > −50 dBFS-rel (21:25–22:15).
- **cross-correlation lag** — Pearson r of following-count vs audio-peak (5-min bins) shifted ±30 min;
  lag-0 r ≈ 0.37 (CH01) / 0.34 (CH02); best lag −5 min (CH02) → coincidence at lag ≈ 0. The lag absorbs the
  UNVERIFIED camera↔WISER clock offset plus any real response delay, so its exact value is not interpretable.
- **AWN night rain** — Σ(Rain Rate mm/hr × Δt) over 21:00–05:00 local. 07-04 = 0.00 mm (dry); wet nights
  06-30 = 0.30, 07-06 = 2.39.

*Decision rule: a candidate association is reported when (i) the bin-level effect exceeds the matched-clock
control (z > 2) AND (ii) it coincides with an independent acoustic confirmation (r > 0, lag ≈ 0). Both hold.
A causal or social-following claim requires video (pending) — NOT made here. Code verification (the scripts
run) is not biological validation. n = 1 night; frame UNVERIFIED; 07-04 also a burrow night.*
