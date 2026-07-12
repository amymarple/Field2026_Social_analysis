# Change log — Duo 3 16MP keyframe 2 MB cap (partial daytime frames): root cause + repo integration

**Date:** 2026-07-09
**Status:** ✅ root cause confirmed at the byte level; camera-side fix pending (owner to apply in the
Reolink web UI); repo docs + tooling notes corrected. Read
[docs/methods/duo3_keyframe_2mb_cap.md](../docs/methods/duo3_keyframe_2mb_cap.md).

## What was found

The CH01/CH02 (and CH07/CH08, same Duo 3 family) **2160×7680 HEVC keyframes are hard-capped at
exactly 2,000,000 coded bytes by the camera encoder.** Bright daytime keyframes need 2.0–2.5 MB;
the overflow — the **bottom band of the frame — is never written to the file**, and because GOPs are
closed every P-frame in that GOP inherits the hole. Night IR keyframes compress to ~1.1 MB and never
hit the cap. Diagnosed by reassembling the keyframe NALU directly from raw mp4 bytes (slice NALU
exactly 2,000,000 B, self-consistent, error-free decode, bottom band still textureless → the data
does not exist in the file). Full write-up + measured impact (CH02 06-30 17:00 hour: 41 % of GOPs
capped) in the method doc.

## Correction to earlier entries (this supersedes them)

Earlier this week I logged two **wrong** mechanisms for the same symptom; both are now retracted:
- "coded-frame **data volume** limit / keyframe too big to decode" — WRONG. It is not a decoder
  limit; the bytes are missing from the file (encoder-side), so **no decoder can recover them**.
- "cold decode of the **first GOP** poisons the stream; **seeking anywhere** fixes it" — PARTLY
  wrong. Seeking helps only because it can land on an **intact** keyframe; seeking directly onto a
  **capped** keyframe still yields a broken frame, and capped GOPs occur throughout bright hours,
  not just at the file start. The real rule is: seek to the latest **intact** keyframe (packet
  < 1,999,000 B) and software-decode forward.
- The **only** conclusion that survives unchanged: **forcing B/W night mode 24/7 is NOT a fix** —
  it dodges the cap by discarding the daytime detail the tracker needs. (Now confirmed by the
  encoder analysis, and independently by the earlier measurement that grayscale saves only ~2 % of
  keyframe bytes — the cost is scene detail, which B/W removes and the cap would then not clip.)

## Files touched

- **NEW** `docs/methods/duo3_keyframe_2mb_cap.md` — copied-in authoritative diagnosis (from the
  standalone `C:\Users\Cornell\Documents\CV\` working folder, which also holds the `cvpipe/` decode
  defenses: intact-keyframe time-based `extract_frame`/`iter_frames`, `probe.find_capped_gops`,
  `scripts/probe_video.py`, `scripts/extract_frames.py`).
- `wiser/src/camera_calibration.py` — `grab_frame` docstring corrected to the cap
  mechanism; extraction stays seek-based; `_find_video` defaults CH01/CH02 `--extract` to a **night
  hour** (night is never capped → the reliable full-frame source for calibration).
- `change_log/2026-07-08-following-incidents-b2.md` — decoder-limit bullet corrected/pointer added.

## Consequences for CV analysis

- **Night (IR) is clean** — the whole night-active behavioural window (21:00–05:00) is unaffected;
  full frames, safe for tracking.
- **Daytime capped GOPs** lose the bottom band silently; software concealment / VLC-HW stale-fill
  can look plausible. Any daytime CH01/CH02 tracking must **mask bottom-band detections in capped
  GOP time ranges** (`find_capped_gops`), and must use **time-based intact-keyframe seeking**, never
  frame-number addressing (VFR, jittered PTS).
- **Calibration** uses a **night frame** for CH01/CH02 (full, no cap).

## Follow-ups

- **Camera fix APPLIED ~evening 2026-07-09 — but the ALTERNATIVE lever, not §6 Step 1.** Owner kept
  **I-frame Interval 2×**, raised **Max Bit Rate 10240 → 12228 Kbps**, and switched **CBR → VBR**.
  Rationale: if the 2 MB ceiling is the CBR rate-control's peak-frame (VBV buffer) limit rather than a
  fixed firmware cap, VBR + a higher max-rate raises the allowed peak keyframe size so the full daytime
  keyframe fits — a valid, untested alternative to shrinking the keyframe via more frequent IDRs.
  **Regime boundary:** footage before this change keeps the capped-GOP daytime bottom-band loss.
  **Verify 2026-07-10** on the *new* footage: `cvpipe/scripts/probe_video.py <bright-afternoon-hour>`
  → want `CAPPED-KF : none`, and a re-extracted daytime CH01/CH02 frame should show a full bottom band.
  If it still caps, fall back to §6 Step 1 (I-frame 2×→1×). Logged in FIELD_OBSERVATIONS Day 12.
- Confirm which units received the change (both Duo 3 = CH01/CH02; CH07/CH08 too if same model).
- Consider vendoring `cvpipe/`'s `find_capped_gops` masking into the CV tracking pipeline so daytime
  bottom-band detections are auto-masked (still needed for all pre-fix footage regardless).
