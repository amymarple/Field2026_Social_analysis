# STATUS.md — cross-cohort × per-direction status index

The top-level scientific status board for this repo, keyed by **cohort × direction**. It is a thin index:
the per-question detail lives in the `analyses/` cards, the narrative in `summaries/<direction>.md`, and the
authoritative WISER row-by-row tracker in [`wiser/ANALYSIS_STATUS.md`](wiser/ANALYSIS_STATUS.md). Update this
board in the same change that promotes/retracts a finding.

Legend: ✅ done/validated · ⚠️ candidate (interpret with caveat) · ⛔ blocked · ◻️ placeholder.

## Cohorts

| Cohort | Window | Notes |
|---|---|---|
| `2026a` | 2026-06-28 → 2026-07-08 (11 nights; motifs to 07-10) | First outdoor social cohort. 6→5→4 animals (Sova 06-29, Hypnos 07-09). Inch frame unverified. See `cohorts/2026a.yaml`. |

## Direction × cohort

| Direction | 2026a | Navigation | Headline status |
|---|---|---|---|
| `wiser_baseline` | ✅ | [summary](summaries/wiser_baseline.md) · [cards](analyses/wiser_baseline/) | Jitter floor ~7 in; live-DB-safe hourly occupancy. |
| `wiser_d1_nightly` | ⚠️ | [summary](summaries/wiser_d1_nightly.md) · [cards](analyses/wiser_d1_nightly/) | Habituation settling; rain vs habituation **not separable** (n=5). |
| `wiser_d2_routes` | ⚠️ | [summary](summaries/wiser_d2_routes.md) · [cards](analyses/wiser_d2_routes/) | Corridors robust; route "vocabulary" falsified (verdict C, continuous manifold); herd-not-dyads following. |
| `wiser_d3_sleep` | ⚠️ | [summary](summaries/wiser_d3_sleep.md) · [cards](analyses/wiser_d3_sleep/) | Daytime rest sites + heat-gated dispersal (~32 °C); "sleep" = low-speed proxy, not ephys-validated. |
| `wiser_policy` | ⚠️ | [summary](summaries/wiser_policy.md) · [cards](analyses/wiser_policy/) | Environment+dwell+group-social semi-Markov choice model; individual policy negligible; IRL NO-GO. |
| `cv_shelter` | ⚠️ | [summary](summaries/cv_shelter.md) · [cards](analyses/cv_shelter/) | Through-glass CH05/CH06 occupancy; view-quality-gated; counts a lower bound (wall-edge blind zone). |
| `audio_soundscape` | ✅ (Phase 1) / ⚠️ (Phase 2) | [summary](summaries/audio_soundscape.md) · [cards](analyses/audio_soundscape/) | Relative camera-mic dBFS + band-limited indices (within-dataset only). |
| `crossmodal` | ⚠️ | [summary](summaries/crossmodal.md) · [cards](analyses/crossmodal/) | CV×WISER sleep-site reconciliation (asymmetric; κ base-rate-warned); fireworks time-locked to following. |

## Cross-cohort

`aggregate/` is empty until a second cohort exists. No cross-cohort claims yet.

## Parked

See [`PARKED_ITEMS.md`](PARKED_ITEMS.md) for items whose recording-vs-analysis status is unresolved and that
were intentionally not migrated pending a human ruling.
