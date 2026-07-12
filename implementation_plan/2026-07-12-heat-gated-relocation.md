# Implementation plan — Direction 3: heat-gated house-leaving (temperature as a gate)

**Date:** 2026-07-12 · **Type:** analysis (new stats primitives + driver + self-test). Candidate / descriptive.
**Env:** `C:\Users\Cornell\anaconda3\python.exe` (3.13, np 2.1.3, pd 2.2.3), `KMP_DUPLICATE_LIB_OK=TRUE`.
**Data (read-only):** WISER snapshot `1stcohort_2026_2026-07-09.sqlite` (static; 06-28→07-08, 5 rats),
baseline `tag_reports_2026-06-30.sqlite`, weather `AWN-…20260628-20260709.csv`, ROIs `wiser_rois.json`.

## Question
Does **instantaneous daytime temperature gate leaving the enclosed house** — i.e. below some threshold rats
stay inside a house, above it they come out toward cooling/margin sites — and does this hold **within a
single day** (the day as its own control), so it is not just "hot days were early / still exploring"?

**Prior (field + exploration).** A dose-response gate is already visible: P(out of house) is flat ~5% up to
~30 °C, then jumps to 27–40% above ~32 °C; out-of-house peaks at 14:00–15:00 (hot hours); on the days that
cross 32 °C, within-day above-gate vs below-gate P(out) rises ~6× (0.05→0.30) and exits become more
cooling-directed (44%→66%). This pass formalizes and inference-tests that.

## Identifiability / scope (enforced in wording)
- **Candidate / descriptive.** Tests an **association** between ambient temperature and an occupancy state;
  does **not** prove thermoregulatory causation.
- **Sensor path vs animal path** (per `/regime-aware-wiser-tracking`): "out of house" = position classified
  in a non-house ROI band, **low-movement proxy**, **unverified inch frame**; `refuge_4` (burrow) + `tunnel`
  are interpretation-limited and **excluded**; `unknown` (dropout) bins excluded. Temperature = **ambient**
  AWN air temp (no in-shelter microclimate), merged to bins by wall-clock (±15 min, unverified).
- **Confound handling.** Above-gate temperatures occurred on only ~5 (early) days, so absolute temperature is
  confounded with day-in-sequence. The **within-day above/below-gate contrast** removes day/rat/sequence/
  exploration (each rat-day is its own control); it is the **headline**. The across-day gate curve is
  **supporting** and explicitly carries the "few hot days" caveat.
- Inference is **day-clustered** (rats within a day share the same weather → days, not rat-days, are the
  independent units).

## Definitions (formula + plain text) — every derived quantity
Trunk = local `[05:00, locomotor_emergence(day))`, rest = smoothed UWB speed `< c` (p99 stationary,
~12.5 in/s); **release day 06-28 dropped** (truncated evening release). Bins = 5-min median position →
`classify_site_state`.
- **enclosed** = state ∈ {house_1, house_2} (food→house). **out** = state ∈ {doorway, exposed, water_1,
  water_2, refuge_1, refuge_2, refuge_3}. Interpretable bin = enclosed ∨ out (drop refuge_4/tunnel/unknown).
- **P(out)** over a set of bins = (# out) / (# interpretable). Plain: share of resting time positioned
  outside the enclosed house.
- **instantaneous temp** `T(bin)` = AWN `temp_c` at the nearest weather sample to the bin's local time (≤15 min).
- **Gate** `G` (°C): a candidate threshold. **above/below** = `T ≥ G` / `T < G`.
- **Within-day contrast** (headline): for each rat-day with `≥ m` interpretable bins **both** below and above
  `G` (`m=3`), `ΔP_out = P(out | T≥G) − P(out | T<G)`. Also `Δreloc`. Plain: on a day that crosses the gate,
  does the same animal come out more during its above-gate (midday) window than its below-gate window?
- **leave-house hazard** = among enclosed bins, `P(next consecutive 5-min bin ∈ out)` (only across bins 4–6
  min apart; gaps break the pair). Below vs above `G`. Plain: per-5-min chance of stepping out of the house.
- **cooling-directed exit fraction** = of house-exits (enclosed→out transitions), the fraction whose
  destination ∈ out, below vs above `G` (composition of where exits go).
- **Threshold estimate** = fit 1-D **logistic** `P(out) = σ(b0 + b1·T)` over all interpretable bins;
  `T_50 = (logit(level) − b0)/b1` at `level` where P(out) crosses (report at level=0.15, mid-way up the
  ramp, and the slope `b1`). Plain: the temperature at which coming-out becomes non-trivial.
- **Inference — day-clustered bootstrap:** resample the set of **days** with replacement `B=2000×`; recompute
  the statistic (mean `ΔP_out`, or `T_50`); report the 95% percentile CI and the fraction of replicates `>0`
  (for Δ) as the evidence measure. Plain: is the effect stable when we resample which days we happened to get?

## Analyses / outputs
- **A. Gate curve + threshold.** P(out) per 2 °C temp bin; logistic fit → `T_50`, slope, bootstrap CI (cluster
  by day). Figure `HG1`.
- **B. Within-day above/below-gate contrast (HEADLINE).** `ΔP_out`, `Δreloc` at `G ∈ {31,32,33}`; day-clustered
  bootstrap CI + fraction>0; per-rat breakdown (is it all animals or a subset?). Figure `HG2` (per-rat-day
  dumbbell below→above).
- **C. Timing.** P(out) and mean temp by clock hour (does out-of-house track the afternoon heat peak?). Figure `HG3`.
- **D. Cooling-directedness.** Exit-destination composition below vs above gate.
- CSVs: `gate_curve.csv`, `within_day_contrast.csv`, `per_rat_contrast.csv`, `timing_by_hour.csv`,
  `heat_gate_verdict.csv`. Report + `run_manifest.json` + `LATEST_RUN.txt` pointer.

## New code
- **`src/wiser_analysis_utils.py`** — pure, testable primitives:
  `logistic_fit_1d(x, y, iters, l2)` (IRLS → b0,b1), `logistic_threshold(b0, b1, level)` (T at p=level),
  `cluster_bootstrap(groups, n_boot, seed, agg)` (resample groups=days → mean/CI/frac>0).
- **`scripts/analyze_heat_gated_relocation.py`** — driver (load → per-bin state+temp → A–D → figures/CSVs/report),
  using `output_paths.run_dir`/`report_dir`/`write_latest_pointer`.
- **`scripts/selftest_heat_gated_relocation.py`** — offline planted: logistic threshold recovery (step at
  a known T), `logistic_threshold` algebra, `cluster_bootstrap` (positive-mean groups → CI excludes 0 & frac>0
  high; zero-mean → CI includes 0), and a synthetic bin-set whose above-gate P(out) is high → within-day Δ recovered.

## Reuse
`load_wiser_session`, `time_utils.convert_timestamps/trim_last_n_minutes`, `add_speed`, `speed_noise_floor`,
`add_validity_flags`, `apply_tag_cutoffs`, `select_route_window`, `rest_mask`, `classify_site_state`,
`_bin_utc_ns`, `LOCAL_TZ_OFFSET_HOURS`, `nightly_activity_profile`+`locomotor_emergence` (trunk end),
`load_weather_multi`, `output_paths.*`.

## Verification
- **Offline:** `python scripts/selftest_heat_gated_relocation.py` → threshold + bootstrap + within-day Δ
  recovered → **PASS**.
- **Real run** on the snapshot: prints `T_50` (CI), within-day `ΔP_out` at G∈{31,32,33} with day-clustered CI +
  per-rat, timing, cooling-directed fractions; spot-check `HG1–3`. Read-only DB/weather; outputs to
  git-ignored `D:\Field2026_analysis_out` via `output_paths`.
- **Reconcile** against the exploration (gate ~32–33 °C; within-day P(out) 0.05→0.30 at G=32; exits 44%→66%).

## Non-goals
No causal/thermoregulation claim; no in-shelter microclimate (ambient only); no georeference/directional claim;
no reward/IRL; no change to the biological-day or hierarchy reports. The finding enters the Direction-3
summary as a **candidate** only, after the promotion gate.
