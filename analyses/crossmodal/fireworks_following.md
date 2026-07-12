# ⚠️ Do fireworks (a loud acoustic startle) trigger following/co-flight?

**Direction:** `crossmodal` · **id:** `fireworks_following`  

## 1. Verdict

⚠️ **candidate.** Following bursts on 07-04 (z=2.4 at 21:30, z=5.2 at 22:20 vs matched-clock controls) are acoustically TIME-LOCKED to the fireworks (CH01/CH02 mics, r~0.35 lag0); rain does NOT raise following.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [crossmodal_fireworks_audio_align_2026a.md](../../results/2026a/crossmodal/reports/crossmodal_fireworks_audio_align_2026a.md), [crossmodal_fireworks_following_2026a.md](../../results/2026a/crossmodal/reports/crossmodal_fireworks_following_2026a.md), [crossmodal_fireworks_timecourse_2026a.md](../../results/2026a/crossmodal/reports/crossmodal_fireworks_timecourse_2026a.md) | — |

**Evidence:** n=1 night; a 96-episode video watch-list is staged to resolve following-vs-startle-co-flight.

## 3. Canonical driver

`wiser/scripts/analyze_fireworks_audio_align.py`

## 4. Canonical report

- [crossmodal_fireworks_audio_align_2026a.md](../../results/2026a/crossmodal/reports/crossmodal_fireworks_audio_align_2026a.md)
- [crossmodal_fireworks_following_2026a.md](../../results/2026a/crossmodal/reports/crossmodal_fireworks_following_2026a.md)
- [crossmodal_fireworks_timecourse_2026a.md](../../results/2026a/crossmodal/reports/crossmodal_fireworks_timecourse_2026a.md)

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- n=1 night
- clock alignment unverified
- construct (following vs startle co-flight) needs video

## 7. Superseded claims

_None._

Change log: [`change_log/2026-07-12-fireworks-following-audio.md`](../../change_log/2026-07-12-fireworks-following-audio.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_fireworks_audio_align.py --cohort 2026a
```

---
*Status source: Fireworks <-> following (audio time-lock) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
