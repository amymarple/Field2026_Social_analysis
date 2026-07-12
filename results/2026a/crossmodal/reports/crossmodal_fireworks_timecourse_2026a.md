# Fireworks (07-04) following — time-resolved test

**Status:** ⚠️ candidate. Addresses the n=1 limit by binning the night into 10-min windows: the fireworks are time-localized (~21:00 EDT), so 07-04's fireworks WINDOW is compared to the SAME clock window on the other 10 nights (n=10 controls). Reads Phase-B2 `strict_following_episodes.csv`. Generated 2026-07-12T17:40:40.012171.

## Between-night matched-clock test (the real-n test)

21:00-22:00 window: 07-04 = **100** episodes vs other 10 nights **74.7±52.1** → **z = 0.49**, rank **4/11**, above **70%** of control nights.

## Within-07-04 time-course (is it a spike or a raised level?)

First-hour 14.86/bin vs rest-of-night 2.14/bin = **6.93x**. Control nights' own early bump = 4.52x, so 07-04's early concentration is z=1.32 vs controls (>~1.5 ⇒ a genuine fireworks-time spike; ~0 ⇒ just the normal early-night bump).

### Per-10-min-bin z, first 2 h (07-04 vs other nights at each clock)

| clock   |   n0704 |   ctrl_mean |   ctrl_sd |     z |
|:--------|--------:|------------:|----------:|------:|
| 21:00   |       7 |        12.7 |     13.35 | -0.43 |
| 21:10   |      15 |        16.8 |     16.04 | -0.11 |
| 21:20   |      15 |        12.1 |     13.25 |  0.22 |
| 21:30   |      39 |        12.3 |     11    |  2.43 |
| 21:40   |      24 |         9.8 |      9.02 |  1.57 |
| 21:50   |       0 |        11   |     10.9  | -1.01 |
| 22:00   |       4 |         6.6 |      5.64 | -0.46 |
| 22:10   |       5 |         5.3 |      3.43 | -0.09 |
| 22:20   |      17 |         3.6 |      2.59 |  5.17 |
| 22:30   |       4 |         3.4 |      1.58 |  0.38 |
| 22:40   |       3 |         3.5 |      2.42 | -0.21 |
| 22:50   |       0 |         4.1 |      5.84 | -0.7  |

## Verdict

Splitting the night into 10-min bins DOES give real n for the between-night test: in the 21:00-22:00 fireworks window 07-04 had 100 following episodes vs 74.7±52.1 on the other 10 nights (z=0.49, rank 4/11, above 70% of them). So the fireworks window is NOT a between-night outlier — the whole-night elevation is not localized to the ~21:00 fireworks time. CAVEATS unchanged: episode count is not movement-normalized (matched clock only partly controls it); fireworks time is approximate (~21:00, not logged), so the window may be mis-set; startle co-flight to shelter would also raise this count and is not the same construct as social following (the observer noted it did NOT look like simple escape); 07-04 is also a burrow night. Mechanism still needs the video (B2 queue).

## Definitions

- **following-episode count per 10-min bin** — # of Phase-B2 strict lagged-following episodes whose `t_start_local` falls in the bin. NOT movement-normalized at this resolution.
- **between-night z** — (07-04 window count − mean of other nights' same-clock window) / their SD (n=10 controls).
- **within-night ratio** — first-hour mean per-bin count ÷ rest-of-night mean per-bin count; z-scored against the other nights' own ratios to ask whether 07-04 concentrates MORE early than a typical night.

## Scope

Fireworks time approximate (~21:00, exact NOT logged) — window may be mis-set. Episode count not movement-normalized (matched clock partly controls it). Startle co-flight ≠ social following (construct). 07-04 also a burrow night. Frame UNVERIFIED. Video (B2 queue) remains the mechanism check.
