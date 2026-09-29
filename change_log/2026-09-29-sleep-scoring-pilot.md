# Sleep-state scoring pilot: the IMU as the EMG, 4 local sessions × 3 variants (2026-09-29)

Plan: [implementation_plan/2026-09-28-sleep-scoring-imu.md](../implementation_plan/2026-09-28-sleep-scoring-imu.md).

## What changed

- **New driver `ephys/score_sleep.py`.** It runs PreprocessPipeline's SleepScoreMaster port
  (`src/preprocess/state_scoring.py`, commit `eb3dad4`, unmodified) on our LFP (`<ar>/lfp/`).
  - **Where the IMU enters.** It is written as `<session>.EMGFromLFP.LFP.mat` before the call, and the scorer reuses
    an existing EMG file.
  - **Folder per variant** `<ar>/sleep/<variant>/<SFxx>/<session>/`: the `.lfp` hard-linked (no copy), a
    `session.mat` from the animal's XML, the scorer outputs, and `score_sleep.json`.
  - **`complex_system/`** holds a copy for the user's manual review in `Sleep_dynamics/state_editor.py`. It is seeded
    once and never overwritten.
  - **Refusals.** It refuses sessions with frozen or invalid IMU; excluded time is not supported yet.
  - **Reports.** Both CSVs are rebuilt from every `score_sleep.json` on each run. With no `--sessions`, it only
    rebuilds them.
- **IMU rerun with the frozen-chip / implant-loss fix** (`make_imu.py`, commit 6451d6c). It covered all 203 sessions
  with no errors. Sessions with blanked IMU time:

  | Session | Frozen | Invalid (after implant loss) |
  |---|---|---|
  | SF12 `14_20260902_191103.245` | 16,962 s (4.7 h) | |
  | SF11 `13_20260906_195234.827` | | 7,361 s (2.0 h) |
  | SF07 `9_20260906_194035.495` | 570 s | |
  | SF07 `11_20260904_140054.476` | 6.2 s | |
  | SF07 `12_20260910_204411.854` | 1.5 s | |

  None of the sessions named in session -ae's bug report failed.

## Definitions

Per session, 1-s epochs $t$; $s(t) \in \{\text{WAKE}, \text{NREM}, \text{REM}, 0\}$ is the scorer's state (0 =
unscored).

- **IMU EMG** (the `imu*` variants' EMG slot):
  $$E(t) = \log_{10}\bigl(\overline{\text{VeDBA}}_{[t-1,\,t+1]} + 0.01\bigr), \quad t = 0.5, 1.0, \dots\ \text{s}\ (2\ \text{Hz})$$
  **Text:** log head-movement intensity from `make_imu.py` (m/s²). The scorer smooths it (15 s), min-max normalises it
  and thresholds it at its histogram dip.
- **Variants.**
  - `imu`: IMU EMG; movement gates REM only (the MATLAB rule).
  - `imu_nremgate`: IMU EMG with `useEMG_NREM=True`, so NREM also needs low movement.
  - `lfpemg`: the scorer's own LFP-EMG (300–600 Hz correlation on the 1250-Hz `.lfp`).
- **Moving second** $m(t) = [\text{VeDBA}_{1s}(t) \ge \theta_a]$, where $\theta_a$ is the per-animal still/active
  valley (SF07 0.387, SF08 0.307, SF10 0.325 m/s²). **Run length** $r(t)$ = the length of the unbroken moving run
  containing $t$ (s).
- **Consistency with the IMU:**
  - $\text{sustained\_moving\_scored\_wake} = \text{mean}_{t:\,m,\ r \ge 30}\,[s = \text{WAKE}]$
    (acceptance ≥ 0.95);
  - $\text{brief\_moving\_scored\_sleep} = \text{mean}_{t:\,m,\ r < 5}\,[s \in \{\text{NREM},\text{REM}\}]$;
  - $\text{still\_scored\_sleep} = \text{mean}_{t:\,\neg m}\,[s \in \{\text{NREM},\text{REM}\}]$.

  All are fractions in [0, 1].
- **Agreement between variants $a$ and $b$**, over epochs both score:
  $\text{agree} = \text{mean}_t[s_a = s_b]$, and $\kappa = (\text{agree} - p_e)/(1 - p_e)$ with
  $p_e = \sum_k p_a(k)\,p_b(k)$.
- **REM share of sleep** = REM / (REM + NREM).

## Results

| Session | Variant | WAKE / NREM / REM | REM share of sleep | Sustained moving → WAKE | Brief moving → sleep | Still → sleep |
|---|---|---|---|---|---|---|
| SF10 `9_20260902` (day, 8.5 h) | imu | 0.18 / 0.64 / 0.19 | 0.23 | 0.98 | 0.75 | 0.96 |
| | imu_nremgate | 0.18 / 0.63 / 0.19 | 0.23 | 1.00 | 0.74 | 0.96 |
| | lfpemg | 0.18 / 0.64 / 0.18 | 0.22 | 0.96 | 0.71 | 0.95 |
| SF08 `6_20260910` (day, 6.3 h) | imu = imu_nremgate | 0.13 / 0.67 / 0.19 | 0.22 | 0.99 | 0.64 | 0.95 |
| | lfpemg | 0.13 / 0.67 / 0.19 | 0.22 | 0.97 | 0.61 | 0.95 |
| SF07 `15_20260902` (day, 8.5 h) | imu | 0.26 / 0.60 / 0.14 | 0.19 | 0.99 | 0.46 | 0.90 |
| | imu_nremgate | 0.27 / 0.59 / 0.14 | 0.19 | 1.00 | 0.46 | 0.90 |
| | lfpemg | 0.27 / 0.60 / 0.13 | 0.18 | 0.99 | 0.44 | 0.89 |
| SF07 `9_20260901` (night, 4.2 h) | all | 1.00 / 0.00 / 0.00 | — | 1.00 | 0.00–0.04 | 0.04–0.13 |

- **Agreement between variants** (day sessions):
  - imu vs imu_nremgate: κ 0.99–1.00;
  - imu vs lfpemg: κ 0.96–0.99;
  - on the day sessions, 93–98 % of the IMU variant's REM epochs are REM in lfpemg.
- **SF07 night.** All WAKE is consistent with the IMU: SF07 is still 2 % of the time, and its longest still run is
  18 s. But the automatic SW threshold (0.70 vs 0.375–0.54) and the SW channel (5 vs 11 on SF07's day session) show
  that per-session thresholds break on sleep-poor sessions.
- **SF08 REM anchor** (`from-field/behaviour_observations_cohort3.csv`: 14:37, rec 22230 s, "asleep with the legs
  twitching repeatedly", video; minute precision):
  - ± 60 s scores WAKE 65 / NREM 41 / REM 15 in every variant.
  - The head IMU shows movement there (VeDBA 0.3–5 m/s² at 22215–22295 s); both EMGs rise, so the scorer says WAKE.
  - The nearest clean REM bout is 22045–22135 s (theta high, slow wave low, IMU still), about 95 s before.
  - Twitches vs arousal is the user's call. Context: a five-rat pile, and logger work from 14:40.
- **REM share of sleep** is 18–23 %, at or above the 5–20 % expected.

## Verification

- The three variants share the channel selection (SW/TH channels identical per session).
- Thresholds are read from `SleepScoreMetrics.histsandthreshs`; the SF10 rows were backfilled from their state files.
- Run length is taken from the per-second IMU table and the state is sampled at $t + 0.5$ s.
- Not judged by the agent: spectrograms and hypnograms. The user reviews them in `state_editor.py`.

## Not done yet

- The user's manual review. The κ against their labels is the acceptance number.
- Fixed per-animal thresholds and channels from day sessions (plan item 5). This needs an un-normalised metric,
  because the scorer min-max normalises each session.
- Gap-aware excluded time (frozen IMU, rounds, probe moves, ADC lane), so that those sessions can be scored.
- Server run on the BioHPC LFP.
