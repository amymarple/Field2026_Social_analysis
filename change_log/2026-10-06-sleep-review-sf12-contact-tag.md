# Sleep-score review by the user + SF12 contact tag (2026-10-06)

Follows [2026-10-05-sleep-scores-all-sessions.md](2026-10-05-sleep-scores-all-sessions.md).

## The user's review

The user reviewed every `imu_remclean` SSResults figure under a deliberately **strict** standard: anything that looks off
is marked, which does not mean the score is wrong. The export is
`ephys/configs/sleep_review_2026c/sleep_review_2026c_imu_remclean_2026-10-06.csv` (the later of two exports two minutes
apart).

**196 sessions marked: 186 ok, 7 noise, 3 bad.**

- **noise (logger noise):**
  - six on SF12:
    - `4_20260901_054714` (1.8-min stub);
    - `1_20260907_090326` (1-min stub);
    - `2_20260907_180003` (09-07 night, 12.5 h);
    - `15_20260910_210518` (09-10 night);
    - `2_20260911_094554` (stub);
    - `17_20260911_192428` (final night);
  - one on SF11: `6_20260906_132454` (6-min piece).
- **bad (suspect), all on SF07 and all about REM** ("Is REM right?" / "EMG/REM looks weird"):
  - `5_20260901_075052`;
  - `6_20260901_125442`;
  - `8_20260904_080936`.
- **Not marked:** SF08 `3_20260901_054222` (2-min stub) and SF11 `7_20260905_151133` (2.9 h).

**An objective correlate (descriptive, not used for any decision).** In every SF12 session marked noise, the scorer's
automatic channel choice left SF12's usual channels:
- usual: SW channel 12 or 43, TH channel 44;
- in the noise sessions: SW 59, 61, 59, 64, 42, 52 and TH 33, 36, 44, 36, 27, 56.

The 09-07 night (`2_20260907_180003`) predates every recorded SF12 contact problem; the session index rates it
`ambiguous` (not `clean`).

## SF12 contact tag

- **What the record says** (the `recording-inquiry` agent, from Notion, field2026-sync and the recording repo, cross-checked
  with this registry). It is a mechanical headstage/probe-connector contact that handling opens and closes:
  - shank 4 was normal until the end of `8_20260910_083507` (09-10 14:53:45) and at shank 1's half amplitude by 21:05;
  - in the 09-10 night, shanks 1 and 4 open intermittently;
  - in the 09-11 day, all 64 channels are open until ~17:50;
  - usable signal ends 09-11 23:30.
- **Notion has no separate date.** Its observation-log 09-11 row records the shanks-1/4 loosening, and its 09-17 row calls
  it the likely precursor of the implant loss (≈ 03:16 on 09-17).
- **New registry key `ephys.quality_flags`** (`cohorts/2026c.yaml`): record-quality periods
  $\{\text{animal}, \text{from}, [\text{until}], \text{tag}, \text{note}, \text{source}\}$.
  - A session gets the tag when $[t_\text{start}, t_\text{end}] \cap [\text{from}, \text{until}) \neq \emptyset$ on the
    logger clock (no `until` = to the end of the record).
  - A tag describes the record and never excludes a session by itself, unlike `field_flags` (out of coverage) and
    `valid_until` (clips the session).
  - First entry: `SF12_contact_failing` from **2026-09-10 14:53:45**. It tags 4 scored sessions: `15_20260910_210518`,
    `0_20260911_093859`, `2_20260911_094554` and `17_20260911_192428`. The 09-11 day session and the 09-12 home-cage
    sessions were not scored and are already field-flagged.
- **`ephys/sleep_review.py --merge <export>`** writes `results/2026c/ephys_spikes/reports/ephys_spikes_sleep_review_2026c.csv`.
  It has one row per session: the `imu_remclean` scores, the user's verdict and note, and `tags` from `quality_flags`,
  `valid_until`, `field_flags` and `not_scored`.

## Registry repair

The lab's copy of the registry (`field2026-sync/from-lab/2026-09-21_pc-time-algorithm-backup/2026c.yaml`) held two
`probe_notes` this repo never had (`git log -S` finds no trace). Both are the 09-09 18:10 depth-landmark notes:
- **SF08:** probe retracted ≥ 100–150 µm.
- **SF12:** probe retracted 250–400 µm, plus four new dead columns 48 58 60 63 on shank 1 in the 09-08 night.

They are restored verbatim with their source. No other fact in the backup is missing here.

**Sources disagree on the onset of the shank-1 channel loss; listed, not resolved:**
- 09-08 night (the restored note);
- "since the 09-09 day" (connector answer);
- "first time" in the 09-10 day sessions (09-10 lab request).

The 09-03 offload QC shows no SF12 dead channels.
