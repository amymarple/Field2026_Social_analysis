# crossmodal/ — cross-modal analyses (code index)

`crossmodal` is a **research direction** (its results land in `results/<cohort>/crossmodal/` and it has its
own `analyses/crossmodal/` cards + `summaries/crossmodal.md`). The **driver code**, however, physically lives
in the WISER import graph — those scripts `import wiser_analysis_utils`, `camera_router`, `following_incidents`,
etc., and rely on `wiser/src` being on `sys.path`. Relocating them here would break those imports for no
benefit (the link-integrity rule forbids that). So this file is the index; the code stays where its imports
resolve.

| Cross-modal analysis | Canonical driver | Direction outputs |
|---|---|---|
| CV × WISER sleep-site reconciliation | `wiser/scripts/analyze_sleep_site_cv_crossval.py` | `results/<cohort>/crossmodal/` |
| Fireworks ↔ following (audio time-lock) | `wiser/scripts/analyze_fireworks_audio_align.py` | `results/<cohort>/crossmodal/` |
| Fireworks following time-course (PSTH) | `wiser/scripts/analyze_fireworks_timecourse.py`, `wiser/scripts/plot_fireworks_psth.py` | `results/<cohort>/crossmodal/` |
| Following vs weather/fireworks | `wiser/scripts/analyze_following_weather.py` | `results/<cohort>/crossmodal/` |
| Fireworks video watch-list | `wiser/scripts/make_fireworks_watchlist.py` | `results/<cohort>/crossmodal/` |
| WISER → camera routing / video audit | `wiser/src/camera_router.py`, `wiser/scripts/audit_following_video.py` | `results/<cohort>/crossmodal/` |
| Audio × WISER activity + weather panel | `audio/scripts/plot_soundscape_day.py`, `audio/analysis/wiser_activity.py`, `audio/analysis/weather.py` | `results/<cohort>/crossmodal/` |

Audio Phase-2 panels that merge audio with WISER activity / AWN weather live in `audio/` (they import the
audio pipeline); their cross-modal outputs are keyed under the `crossmodal` direction too.
