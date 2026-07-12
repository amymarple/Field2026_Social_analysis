# ✅ What is the environmental soundscape at the paddock over time (relative level + indices)?

**Direction:** `audio_soundscape` · **id:** `soundscape_features`  

## 1. Verdict

✅ **confirmed.** Resumable extraction of relative camera-mic level (dBFS, NOT calibrated SPL) + band-limited ecoacoustic indices from CH01/CH02 hourly-MP4 audio; comparable only within this dataset.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | — | — |

**Evidence:** CH01/CH02 (mics enabled ~2026-06-29 12:00); 16 kHz mono (~8 kHz ceiling).

## 3. Canonical driver

`audio/scripts/extract_audio_features.py`

## 4. Canonical report

- _(off-repo run; see change log below)_

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- relative dBFS, not absolute SPL
- band-limited indices (within-dataset only)
- rat USVs >20 kHz out of scope

## 7. Superseded claims

_None._

Change log: [`change_log/2026-06-29-environmental-audio-pipeline.md`](../../change_log/2026-06-29-environmental-audio-pipeline.md)

## 8. Exact rerun command

```bash
python audio/scripts/extract_audio_features.py --config audio/configs/audio_analysis.analysis_pc.yaml --channel CH01 --date 2026-06-29
```

---
*Status source: Environmental audio pipeline (Phase 1) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
