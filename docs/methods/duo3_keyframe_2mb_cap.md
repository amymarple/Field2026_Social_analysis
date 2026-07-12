# Method: Reolink Duo 3 16MP keyframe 2 MB cap → partial daytime frames

> **Provenance.** Byte-level diagnosis performed 2026-07-09 in the standalone working folder
> `C:\Users\Cornell\Documents\CV\` (not in this repo). That folder also holds the defensive
> decode pipeline (`cvpipe/`), the probe/extract scripts, and the proof-frame artifacts referenced
> in §5/§8 below. This file is the copied-in, authoritative record; the change log entry
> `change_log/2026-07-09-duo3-keyframe-cap.md` logs it into the repo workflow. It **supersedes**
> the earlier, partially-wrong "coded-frame data-volume / cold-decode first-GOP" explanation in
> `change_log/2026-07-08-following-incidents-b2.md` and the CH01/CH02 note in `wiser`.

---

## 1. Symptom

When seeking/scrubbing daytime recordings in a player, ~20% of the frame (bottom band)
renders black/incomplete, and "loads" only after scrubbing back and forth. Sequential
playback looks fine. Night (IR) recordings never show the problem.

## 2. Root cause

**The camera's HEVC encoder hard-caps every keyframe (IDR) at exactly 2,000,000 coded
bytes.** Bright daytime scenes at 16.6 MP need 2.0–2.5 MB per keyframe; whatever
doesn't fit is silently discarded by the encoder. The bottom band of the frame is
**never recorded**, and because GOPs are closed, every P-frame of that GOP inherits
the hole (they can only reference the capped keyframe).

Proof: the keyframe NALU was reassembled directly from raw mp4 bytes, bypassing all
demuxer/decoder packet handling. The NALU structure is self-consistent, the slice
NALU is exactly 2,000,000 bytes, decode is error-free — and the bottom band still
comes out with zero texture. The data does not exist in the file.

Why night is immune: IR keyframes compress to ~1.1 MB and never hit the cap.
Why noon is milder than late afternoon: overhead light flattens texture (cheap to
encode); low sun creates long shadows and high contrast (expensive), so keyframes
overflow the cap more often and by more.

### Measured impact (CH02)

| File | Capped GOPs | Time affected | Band lost per capped GOP |
|---|---|---|---|
| 2026-06-30 17:00–18:00 | 633 / 1653 | **41%** of the hour | 5–23% of frame height |
| 2026-06-30 12:00–13:00 | 325 / 1707 | **20.6%** | 3–14% |
| 2026-06-29 03:00–04:00 (night) | 0 / 1799 | 0% | — |

Capped GOPs **cluster**: the band can be missing continuously for many seconds.
Capped keyframes are detectable without decoding: packet size ≥ 1,999,000 B
(observed values: exactly 2,000,090 and 1,999,427 including container overhead).

## 3. Why every viewer shows something different

The missing region is filled by whatever the decoder does with unwritten pixels:

| Decode path | What the hole looks like | Notes |
|---|---|---|
| ffmpeg software (v4.2–v8.1), VLC with HW decode **disabled** | white/gray smear, zero texture | "honest failure" |
| ffmpeg NVDEC (`-hwaccel cuda`, `hevc_cuvid`) | solid green (0,152,0) | also mangles capped GOPs even when decoding sequentially — never use NVDEC on these files |
| ffmpeg D3D11VA | white smear | same parsing layer as software |
| **VLC default (D3D11VA "Automatic")** | **looks like a perfect frame** | GPU surface pool is recycled without clearing → the hole shows pixels from a frame decoded fractions of a second earlier. With a static camera this is indistinguishable from real content. **Do not use VLC-HW screenshots as evidence of recorded content.** |
| Any ffmpeg-based consumer **seeking directly onto** a capped keyframe (incl. cv2) | gray garbage frames, `Could not find ref with POC n` | this is the scrubbing artifact from the original symptom |

The original "loads after scrubbing back and forth" behavior = the D3D11VA surface
pool filling with nearby frames' pixels. Nothing was loading; stale memory started
matching the scene.

Verified with VLC itself: `Tools → Preferences → Input/Codecs → Hardware-accelerated
decoding → Disable` → the band appears at the same positions ffmpeg shows it.

## 4. Consequences for CV analysis

- In capped GOPs the bottom band is unusable **regardless of decoder**. Software
  concealment (or D3D11VA stale fill) looks plausible — an animal moving through the
  band appears frozen, vanished, or duplicated. Silent wrong data, worse than
  visible corruption.
- Everything **above** the band is always complete and correct, in every GOP.
- Frame-accurate extraction must not seek directly onto capped keyframes, and must
  not use frame-number addressing at all (streams are ~20 fps average with heavily
  jittered timestamps: inter-frame gaps 0.5–267 ms).

## 5. Pipeline defenses (implemented in `C:\Users\Cornell\Documents\CV\cvpipe/`)

- `extract_frame()` / `iter_frames()` — seek to the latest **intact** keyframe at or
  before the target, software-decode forward to the exact time. No garbage frames,
  PTS-accurate, verified bit-exact against sequential ground truth.
- `probe.find_capped_gops(video)` — packet-level scan returning the time ranges
  where the bottom band was never recorded. **Mask bottom-band detections in these
  ranges** during tracking/analysis.
- `scripts/probe_video.py <file>` — per-file report incl. `CAPPED-KF` percentage.
- `scripts/extract_frames.py` — extracted frames from capped GOPs are prefixed
  `CAPPEDGOP_`; flat/green concealment additionally flagged `SUSPECT_`.
- NVDEC is not used anywhere; all decoding is software (ffmpeg 8.1.2, conda `cv` env).

## 6. Camera-side fix (stops the ongoing loss)

Settings page: camera web UI → Stream → Main Stream (apply to **both** Duo 3 units).
Current: 7680×2160, 20 fps, Max Bit Rate 10240 Kbps CBR, I-frame Interval 2x.

1. **Step 1 (try first): I-frame Interval 2x → 1x, keep 10240.** Doubling keyframe
   frequency roughly halves each keyframe's CBR budget (~1.0–1.1 MB/keyframe) —
   under the 2 MB cap, with night quality essentially unchanged and snappier seeking.
2. **Step 2 (only if step 1 still caps): Max Bit Rate 10240 → 8192.** Slight
   softening everywhere incl. night keyframes (~1.1 → ~0.8 MB).
3. Keep resolution, 20 fps, color mode. **Do not switch to B/W night mode as a
   "fix"** — it only avoids the cap by removing the detail the tracker needs.

**Verification:** record a bright afternoon hour (worst case: low-sun 16:00–18:00),
then `python scripts\probe_video.py <file>` → want `CAPPED-KF : none`.
Settings are global (24/7); night can only get slightly softer, never corrupted.

## 7. Dead ends ruled out (for the record)

- ~~Sparse IDR / intra-refresh / long GOP~~ — GOP is a normal 2 s with true IDRs.
- ~~NVDEC hardware/driver fault as root cause~~ — NVDEC handles intact GOPs fine;
  its green band is concealment of genuinely missing data (though its additional
  sequential-decode failures on capped GOPs are real; avoid it regardless).
- ~~VFR/OpenCV seek bug as root cause~~ — real (cv2 position-seek does produce
  broken grabs; frame-number addressing is invalid on these streams) but a separate
  issue; fixed by the pipeline's time-based intact-keyframe seeking.
- ~~mp4 sample-splitting / remux damage~~ — packaging is valid and self-consistent;
  `audio_in` files are straight transfers of the recorder's originals.
- ~~Decoder version~~ — ffmpeg 4.2.2 and 8.1.2 agree.

## 8. Key artifacts (in `C:\Users\Cornell\Documents\CV\`)

- `proof_frames/` — side-by-side evidence: pipeline vs cv2-seek vs NVDEC-green vs
  VLC-software-decode of the same moments.
- `inspect_frames_v2/` — full-res labeled extractions from the 06-30 17:00 file.
- `verify_seek_report.csv` — old-vs-new seek method comparison (SSIM/MAD).
- Reproduce any measurement: see commands in section 5 scripts.
