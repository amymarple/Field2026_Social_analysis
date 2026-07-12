# Implementation plan — Direction 3: sleep-site landmark hierarchy (state role in the decision process)

**Date:** 2026-07-11 · **Type:** analysis (new util primitives + driver + self-test). Candidate / descriptive.
**Env:** `C:\Users\Cornell\anaconda3\python.exe` (3.13, np 2.1.3, pd 2.2.3), `KMP_DUPLICATE_LIB_OK=TRUE`.
**Data (read-only):** WISER snapshot `1stcohort_2026_2026-07-09.sqlite` (static; 06-28→07-08, 5 rats),
baseline `tag_reports_2026-06-30.sqlite`, weather `AWN-…20260628-20260709.csv`, ROIs `wiser_rois.json`.

## Question
Are the daytime rest-site landmarks (`house_1`, `house_2`, `doorway`, `exposed`, secondary refuges) the
**same status** in the animals' sleep-site decision process, or are they **ranked** — with `house_1` a
top-ranked morning/return anchor and the others midday/secondary destinations?

**Revised hypothesis (after a read-only exploration of the existing state-sequence CSVs).** The original
proposal was an ordered chain `house_1 → doorway → house_2 → fully out`, temperature-driven. The
exploration (55 rat-days) supports a **ranked anchor** but revises the chain:
- **Supported:** `house_1` is the day's first (anchor) state on 28/55 rat-days (**68%** of interpretable
  anchors), *even for the two `house_2`-dwelling rats*; it is a net **sink** (peripheral→house_1 flux is
  one-sided); and there is a **diurnal excursion** (house_1 morning → house_2/doorway at the ~13:00 heat
  window → house_1 returns latest ~14.6 h).
- **Revised:** house↔house moves are mostly **direct** (56 vs 8 via a doorway), so doorway is **not** a
  systematic intermediate; house_1↔house_2 is **reversible** (28 vs 26), an excursion-and-**return**, not a
  one-way descent; the trunk **ends in a house**, not exposed ("fully out" = the *emergence*, a separate
  boundary already characterized). Ranking is **partly shared** (house_1 anchor) but **partly rat-specific**
  (2/5 rats dwell mostly in house_2).

We therefore test **state-role structure**, not a linear chain.

## Identifiability boundary (stated up front, enforced in wording)
- We test the **decision structure over *labelled* states** — this does **not** need the physical frame and
  is identifiable. We do **NOT** claim the physical **cause** (temperature / a spatial "toward-out"
  gradient): the WISER frame is **unverified**, temperature is **ambient-only**, "sleep" is a **low-movement
  proxy**. Temperature enters only as a **coarse within-rat covariate on an excursion metric**, reported as
  *candidate, no confirmed association*.
- Level = **semi-Markov descriptive choice structure**. Per the prior agent-policy identifiability finding
  ([[agent-policy-identifiability-nogo]]), a fitted **reward / IRL** model is **out of scope (NO-GO)**.
- `refuge_4` (burrow, 07-03→07-07) and `tunnel` are **interpretation-limited** → excluded from the
  role/ranking headline (reported separately, flagged). `doorway`/`exposed` are classifier-dependent →
  buffer-sensitivity check.
- n = 5 rats × 11 days; within-rat tests; **uncorrected** multiple comparisons; permutation nulls are the
  inference, not asymptotic p-values.

## Definitions (formula + plain text) — every derived quantity
Let a **rat-day state sequence** be the ordered list of confident state-segments
`s_1..s_K` (each ≥ `min_dwell_bins`=3 bins = 15 min) from `trunk_state_dwell_transitions` (reused), with
per-segment start time `t_k`, duration `d_k` (bins), and state `σ_k ∈ S` (the ROI state space). `A` = the
set of the 55 rat-days.

1. **Dwell share** `w(s) = (Σ_{a,k: σ=s} d_k) / (Σ_{a,k} d_k)` — unconditional occupancy fraction of state
   `s` over all trunk bins (already validated; sums to 1). Plain: how much of daytime rest is spent in `s`.
2. **Anchor share** `α(s) = |{a ∈ A : σ_1(a)=s}| / |A|` — fraction of rat-days whose **first** confident
   state is `s`. Plain: how often the day *starts* in `s`.
3. **Terminal share** `ω(s) = |{a : σ_K(a)=s}| / |A|` — fraction of rat-days whose **last** confident
   state (before emergence) is `s`. Plain: how often the day *ends* in `s`.
4. **Transition counts** `N(s→s')` = number of relocations from `s` to `s'` over all rat-days (reused
   matrix). **Arrivals** `In(s)=Σ_{s'} N(s'→s)`, **departures** `Out(s)=Σ_{s'} N(s→s')`.
5. **Net-flux (sink) score** `φ(s) = (In(s) − Out(s)) / (In(s) + Out(s))` ∈ [−1,1]; `φ>0` = net **sink**
   (entered more than left → an attractor/return state), `φ<0` = net **source**. Plain: does traffic flow
   into or out of `s`?
6. **Home-base index** `H(s) = mean(α(s), ω(s))` — combined start+end prominence ∈ [0,1]. Plain: how much
   `s` acts as the day's home base (start and return). Report the **ranking** of `H` (and of `φ`).
7. **Anchor-vs-occupancy concentration** (the *non-exchangeability* statistic): compare the observed anchor
   distribution `α(·)` to the **dwell-weighted expectation** `w(·)` via
   `D = Σ_s α(s)·log(α(s)/w(s))` (KL divergence, states with α=0 skipped). Plain: are day-starts
   concentrated in particular states **beyond** what their overall occupancy predicts? `D≈0` → exchangeable
   given occupancy; `D≫0` → a special anchor role.
   - **Null / p-value:** for each of `n_perm` (=2000) permutations, redraw each rat-day's anchor state from
     the categorical `w(·)` (occupancy-weighted), recompute `D*`; `p = P(D* ≥ D_obs)`. A separate null for
     `ω` (terminal). Plain: could the observed start/end concentration arise if states were entered in
     proportion to occupancy?
8. **Diurnal occupancy profile** `O(s, h)` = fraction of state-`s` bins that fall in local clock-hour bin
   `h` (segments expanded to their bins at `t_k + i·bin_s`). **Peak hour** `argmax_h O(s,h)`;
   **bimodality flag** = two separated modes (morning + evening) for the anchor. Plain: when in the day is
   each state used?
   - **Null:** circular-shift each rat-day's per-bin state series by a random offset within its trunk,
     recompute the across-state **hour-separation** statistic (variance of peak hours across states);
     `p = P(shift ≥ observed)`. Plain: is the time-of-day ordering of states reproducible or an artifact of
     when trunks happen to be sampled?
9. **Path structure:**
   - **Round-trip rate** `R` = among rat-days that leave the anchor `house_1` at least once, the fraction
     that **return** to it later the same day (vs terminate elsewhere). Plain: are excursions there-and-back?
   - **Direct-vs-intermediate** = of all adjacent `house_1↔house_2` segment pairs vs
     `house→doorway→other-house` triples, the counts (already 56 vs 8). Plain: is doorway a waystation?
   - **Markov-null** for `R`: shuffle each rat-day's segment order (keeping the multiset of states),
     recompute `R*`; `p=P(R* ≥ R)`. Plain: is return higher than a memoryless re-ordering?
10. **Shared-vs-idiosyncratic ranking:** per rat `r`, rank states by `H_r` (its own anchor+terminal) →
    rank vector. **Concordance** = **Kendall's W** across the 5 rats (over the shared state set) ∈ [0,1];
    W=1 identical rankings, W=0 no agreement. Plain: do all rats rank the landmarks the same? Also report,
    specifically, `house_1`'s anchor share among the **house_2-dwelling** rats (shared-anchor test).
    - **Null:** permute state labels within each rat, recompute `W*`; `p=P(W* ≥ W)`.
11. **Excursion metric + temperature (candidate):** per rat-day, `E_a` = fraction of trunk bins spent
    **away from that rat's own primary (modal-dwell) state**. Within-rat Spearman `ρ(E, midday_peak_temp)`
    (rat-centered), n=55. Plain: do rats spend more of the day away from their home base on hotter days?
    **Candidate only** (ambient temp, unverified frame, uncorrected).

All permutation p-values use `np.random.default_rng(seed=…)` (reported) for reproducibility.

## Reuse (don't reinvent)
`load_wiser_session`, `time_utils.convert_timestamps`, `add_speed`, `speed_noise_floor`,
`add_validity_flags`, `apply_tag_cutoffs`, `select_route_window(5,21)`, `rest_mask`, `assign_roi`,
`load_rois`, `trunk_state_dwell_transitions` (→ segments/relocations/dwell), `classify_site_state`,
`SHELTER_STATES`, `LOCAL_TZ_OFFSET_HOURS`, `load_weather_multi`, `make_output_dir`,
`write_run_manifest`. Trunk window + emergence bound identical to `analyze_biological_day_sleep.py`.

## New code
- **`src/wiser_analysis_utils.py`** — small **pure, testable primitives** (analysis-layer):
  `net_flux_scores(trans_df)`, `anchor_concentration_kl(anchor_counts, dwell_weights)` +
  `permutation_pvalue(observed, null_samples, tail='right')`, `kendall_w(rank_matrix)`. (Aggregation +
  the permutation loops live in the driver; these primitives are what the self-test plants and checks.)
- **`scripts/analyze_sleep_site_hierarchy.py`** — driver: load snapshot (read-only) → trunk per rat-day →
  segments → metrics 1–11 → CSVs + figures + report. Emits `crossval_verdict`-style headline
  (ranked vs exchangeable) with the permutation p-values.
- **`scripts/selftest_sleep_site_hierarchy.py`** — offline, planted: a synthetic cohort with a KNOWN
  anchor/sink (state X always first + a net sink) and a KNOWN shared ranking → assert `φ`, `H`, `D`, the
  exchangeability p-value (small), `kendall_w` (high), round-trip recovery, and an exchangeable control
  (X assigned by occupancy → large p). PASS/FAIL exit code.

## Figures
- `H1_state_role_ranking.png` — per-state dwell vs anchor vs terminal vs net-flux (ranked); house_1 as home base.
- `H2_diurnal_occupancy_profile.png` — occupancy fraction vs clock-hour per state (the excursion).
- `H3_transition_flux.png` — transition/flux diagram (arrivals−departures; house↔house symmetry; direct-vs-intermediate).
- `H4_shared_vs_idiosyncratic.png` — per-rat state rankings + Kendall's W + house_1 anchor among house_2-dwellers.

Outputs → `D:\Field2026_analysis_out\sleep_site_hierarchy_<ts>\` (CSVs, figures, `run_manifest.json`,
`hierarchy_verdict.txt`) + report copy to `outputs/direction3_sleep_site_hierarchy/`.

## Verification
- **Offline:** `python scripts/selftest_sleep_site_hierarchy.py` → planted anchor/sink/ranking recovered +
  exchangeable control rejected → **PASS**.
- **Real run** on the snapshot: prints the state-role ranking, exchangeability p-values (anchor + terminal),
  diurnal peak hours, round-trip rate + Markov-null p, Kendall's W + p, and the temperature-excursion ρ;
  spot-check figures. Read-only DB/weather; outputs to git-ignored `D:\Field2026_analysis_out`.
- **Reconcile** the anchor/sink/timing numbers against the exploration (house_1 anchor ~68% interpretable;
  house_1↔house_2 ≈ symmetric; house_2/doorway midday, house_1 return latest; 56 direct vs 8 via-doorway).

## Non-goals
- No reward / IRL / policy learning (identifiability NO-GO). No physical-cause claim (frame unverified,
  ambient temp). No cross-night personalization or social/dyadic structure. No change to the biological-day
  report or its numbers. No new DB writes.
