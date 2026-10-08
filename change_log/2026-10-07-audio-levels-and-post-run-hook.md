# In-house microphone and camera audio levels on storage; the server post-run hook (2026-10-07)

Part of plan [2026-10-07-sleep-internal-schedule.md](../implementation_plan/2026-10-07-sleep-internal-schedule.md) §4 D.

## What changed

- **`ephys/mic_band_levels.py`** — per-second band levels on the field-PC clock.
  - **Mics:** UltraMic WAVs, MIC01 384 kHz and MIC02 250 kHz.
    - Bands b0 50–500 Hz, b1 0.5–4 kHz, b2 4–20 kHz, b3 20–40 kHz, b4 40–100 kHz.
    - 20-ms Hann frames; per second, the mean and the max frame power in dB re full scale.
  - **Cameras:** CH01–CH08 MP4 audio, AAC 16 kHz.
    - Decoded on the stream timestamps (ffmpeg `aresample=async=1:first_pts=0`), so gaps are filled at their place
      and left out.
    - Bands c0–c2, 50 Hz–8 kHz.
  - **Timing rules:**
    - WAV samples are spread over the name span. MIC01 runs ~210 ppm fast against the PC clock.
    - Files more than 0.1 % short are end-anchored (the device starts after the file is created).
    - `timing_err_s` gives the error bound per file. All-zero frames are left out.
  - `--redo`; one `extract_log_<ts>.csv` per run.
  - `--selftest`: tones, a click, the full-scale calibration, the end-anchored case, and a 3-s timestamp-gap MP4.
- **`ephys/server/run_then_store.sh`** — **post-run hook** (user rule 2026-10-07).
  - It runs a job; only if the job exits 0, it calls `copy_to_storage.sh` with `PARTS=<part> UPDATE=1`.
  - That copy is verified: paths, sizes, MD5 vs an O_DIRECT read-back.
  - It is documented in CLAUDE.md, and the running sessions were told.
- **`ephys/server/copy_to_storage.sh`:**
  - new part `audio_levels`;
  - logs modified < 2 min ago are skipped. The hook's own job log had failed V1 / V2 on the first run; the data files
    were fine.
- **`ephys/server/run_audio_levels.sh`:** MIC01, MIC02, CH01, CH02 for 08-30 → 09-12, plus 09-16 / 17 (the
  empty-arena baseline), on 48 workers, through the hook.
- **`ephys/mic_wake_pilot.py`** — description only:
  - per-day mic vs per-house head-IMU movement (house assignment);
  - sound, housemate and outdoor cues before wakes vs a 2-min-earlier chance reference.

## Results

**Storage:** `Q:\…\3rd_rat\analysis\audio_levels\` holds 1,385 hour-files and passed verification (commit `7fbd966`).

**Local test before the server run:**
- 231 normally timed mic files from the local run are identical to the server output (0.0 dB, same timestamps).
- The first run's camera files were redone after the timestamp fix. Some camera hours have holes of up to ~13 min,
  which had shifted everything after them.

**Placement:**
- MIC01 / MIC02 sit on the ceiling inside the houses (the user).
- MIC01 = house_2 is confirmed: daily ρ 0.52–0.74 with house_2 movement.
- MIC02 = house_1 is plausible (ρ −0.20 to 0.46); MIC02 is flat above 4 kHz.

**Pilot:** cues are somewhat more frequent before wakes than 2 min earlier, but the 10-dB rule is not specific (44–57 %
by chance). Validation needs the user's listening check.
[Report](../results/2026c/ephys_spikes/reports/ephys_spikes_mic_wake_pilot_2026c.md).

## Fixes along the way

- A Hann-window calibration error (+1.76 dB) was caught by the self-test.
- A job tuple unpacking bug after `--redo`: the hook correctly refused to copy.
- A stale SSH socket.
