# WISER common-mode error across tags and pairwise-distance precision (cohort 2026c)

**Status:** PLANNED 2026-10-03, written before any number of this step was computed.
**Approval:** step C of the A → B → C sequence the user approved on 2026-10-03 ("干吧") after the Fable SOTA audit
(points 5 and Q6.10: common-mode error is unmodelled; it can only be removed across tags; it cancels in pairwise
distances, so the ≥ 14-in distance rule may be conservative). Operational details are marked **[op]**.
**Direction:** `wiser_baseline`. **Driver:** new `wiser/scripts/analyze_wiser_common_mode.py` (imports, never edits, the
failure-audit and smoothing-pilot modules). **Config:** new `wiser/configs/wiser_common_mode_2026c.json`.

## Why

The failure audit found a common-mode cluster: four tags (SF07, SF08, SF09, SF12) made ≥ 12-in excursions within 5 min of
2026-09-10 09:48:41 while every head was certified still. A shared (anchor-side) error cannot be removed by any per-tag
smoother, but (i) it can be estimated from *other* tags that are known to be still — the still rats act as reference
stations, as in differential GPS — and (ii) it cancels in inter-animal distances, the quantity the social analyses use.

## Established facts (not re-derived)

Audit periods/animals/exclusions and certified ≥ 30-s still segments (truth = the segment's coordinate-wise median raw
fix; drift is a lower bound) are the failure audit's (`D:\Field2026_analysis_out\2026c\wiser_failure_audit_20261002_1511`:
`tables/segments.csv` with `truth_x/y`, `zone`, `anchors_med`; `tracks/<SFxx>_<period>.npz` with `t_al_ms`, `anchors`,
`raw`, `B1`, `B2`, `B2p`, …). 98 % of certified still time is inside the two houses, so this step measures common mode
mostly between tags in the same house. Raw still per-fix RMS 5.6 | 7.7 in (calm | rain); B2 1.60 | 2.65 in; the
behavioural-policy rule uses jitter 7 in → minimum resolvable distance 14 in.

## Questions and metrics

**Joint stillness.** For every pair of tags (i, j), the intersection of their primary certified segments (both heads
still), kept when ≥ 30 s **[op]**. Residual vectors $\mathbf e_i(t)=\tilde{\mathbf p}_i(t)-\mathbf c_{\sigma_i}$ on a
common 1-s grid, $\tilde{\mathbf p}$ = the median of the method's fixes within ± 0.5 s (≥ 2 fixes) — for raw, B1, B2, B2′
**[op]**; also 10-s medians.

- **C1 — is the error shared?** Per pair-overlap and pooled: correlation of residuals at lag 0 (and ± 1, ± 2 s) per axis and
  as a vector (trace of the cross-covariance over the root product of the traces), at the 1-s and 10-s scales; stratified
  by zone pairing (same house / different houses / house–outside / both outside), calm | rain, day | night. Common-mode
  share of variance = the vector correlation. 95 % CIs: 1000 resamples of 10-min blocks of the pair-overlap time.
  **Anchor sets:** the fix caches carry `anchors_list` (which anchors were used). Reported: whether the 1-s residual
  correlation is higher in seconds when both tags lost the same anchor(s) than when neither or only one did, and which
  anchors' loss coincides with the largest shared excursions (incl. the 09-10 09:48 cluster) — a pointer to the
  anchor-side cause, not a correction.
- **C2 — pairwise-distance precision.** $d_{ij}(t)=\lVert\tilde{\mathbf p}_i(t)-\tilde{\mathbf p}_j(t)\rVert$ vs the
  truth $\lVert\mathbf c_{\sigma_i}-\mathbf c_{\sigma_j}\rVert$: SD, p95 and p99 of the error $d_{ij}-d^{\text{truth}}_{ij}$
  per method (raw, B1, B2, B2′), and the ratio $R=\mathrm{SD}_{\text{obs}}/\mathrm{SD}_{\text{indep}}$ with
  $\mathrm{SD}^2_{\text{indep}}=\mathrm{Var}(\mathbf e_i\cdot\mathbf u)+\mathrm{Var}(\mathbf e_j\cdot\mathbf u)$,
  $\mathbf u$ = unit vector between the truths (R < 1 → shared error cancels). Stratified as C1 and by truth distance
  (< 14 in / 14–48 in / > 48 in).
- **C3 — differential correction, leave-one-tag-out (non-circular for the target).** For a target tag i in a certified
  segment at time t, the common-mode estimate is built **only from the other tags** that are certified still at t:
  $\hat{\mathbf m}_{-i}(t)$ = mean of their 1-s residuals $\mathbf e_j(t)$ — variant (z) same zone only, variant (a) any
  zone **[op]**; it exists when ≥ 1 reference tag is available. Corrected track $\tilde{\mathbf p}_i(t)-\hat{\mathbf m}_{-i}(t)$,
  scored on i's segment against its truth: per-fix (1-s) RMS, 10-s drift (median, p90), ≥ 12-in events, for raw-1-s and
  B2-1-s inputs; paired block-bootstrap CI of the relative change. Also the coverage (share of certified still time with a
  reference). The 09-10 09:48 cluster is shown as a case.

## Pre-registered verdict

- **Common mode "material"** if (1) the pooled same-zone vector correlation of 10-s residuals (B2) is ≥ 0.3 with the CI
  above 0, **and** (2) the leave-one-out correction (variant z, B2 input) reduces the target's 10-s drift p90 **or** its
  1-s RMS by ≥ 10 % with the CI excluding 0. Otherwise "not material" (or "material for raw only" when (1)–(2) hold for raw
  but not B2).
- **Distance precision:** the report states the B2 pairwise-distance error p95 during joint stillness (by zone pairing and
  truth-distance band) and the distance difference it can resolve; **no change to the 14-in rule is made in this step** —
  a tighter value becomes a proposal to the user. Moving-animal distances are not measured here (no truth).

## Data

Read-only: the audit run (tracks, segments), the WISER fix caches `D:\Field2026_analysis_out\2026c\wiser_fix_cache\`
(`anchors_list`, and any column missing from the tracks). No new Kalman
runs are needed **[op: B2 on corrected fixes is not run in this step]**; no SQLite, no IMU access.

## Verification

- `--selftest` (synthetic): three still tags with independent noise + a shared OU common-mode term of known variance
  share (e.g. 50 %) + one tag without common mode → C1 recovers the share (± 0.05), C2's R matches the analytic value,
  C3 reduces the shared-term tags' error by the expected amount and does not improve the independent tag; zone stratifier
  and the ≥ 30-s overlap rule on planted cases.
- Reproduction: the per-tag still RMS of raw/B2 recomputed on the 1-s grid is reported next to the audit's per-fix values
  (they differ by construction; the 1-s values must be ≤ the per-fix ones).

## Outputs

- Bulk `D:\Field2026_analysis_out\2026c\wiser_common_mode_<ts>\`: `tables/` (pair overlaps, C1 correlations, C2 distance
  errors, C3 corrected metrics, bootstrap), `summary.json`, `input_provenance.json`, `log.txt`.
- Report `results/2026c/wiser_baseline/reports/wiser_baseline_common_mode_2026c.md` (+ figures
  `wiser_baseline_common_mode_*_2026c.png`), pointer `run_manifest_common_mode_2026c.json`.
- `change_log/2026-10-03-wiser-common-mode.md`. The main session updates CLAUDE.md and both index READMEs. No commit.

## Caveats known in advance

Joint stillness is almost all inside the houses (often huddles): common mode between distant tags and in the open field is
barely sampled. The truth is each segment's own median, so a common-mode offset constant over a segment is absorbed and
invisible. Rain is three weather episodes. Distances are in the unverified WISER inch frame (frame-invariant).

## Amendment 1 (2026-10-03, made BEFORE any pooled number of this step was computed)

Written after the driver and its synthetic selftest were complete and before the first run on field data. None of the
metrics, thresholds or the verdict rule changes; these fix details the plan left open or that turned out to be ambiguous.

1. **`anchors_list` is the listed set, not the used set.** In every fix of the caches `anchors_used ≤ n_list` (e.g. SF07,
   09-10: 24 % of fixes list more anchors than they used), and the cache does not say which listed anchors were used. Closest
   faithful option: an anchor is **lost** when it is not listed (certainly not used). Per segment, the reference set =
   anchors listed in ≥ 50 % of its fixes; an anchor of that set is lost in a second when it is listed in < 50 % of that
   second's fixes. Pair-second categories: neither lost / one lost / both lost but different anchors / the same anchor lost.
   Because the list is a superset, a secondary stratification on `anchors_used` (both tags' 1-s mean < 8 / one / neither) is
   reported next to it (descriptive only).
2. **Correlation centring.** The cross-covariance of C1 is centred within each pair overlap (each tag's mean residual over the
   overlap's pair-seconds is subtracted) — this is the version the verdict uses. The truth-centred version (second moments
   about the truth, which keeps offsets shared over a whole overlap) is reported as a sensitivity only.
3. **Joint stillness.** The overlap is the intersection of the two segments' *trimmed* spans and must be ≥ 30 s; the 1-s grid
   is the integer seconds of the IMU-aligned clock (`t_al_ms`, as the audit scores), and every 1-s / 10-s window lies wholly
   inside the segment's trimmed span (10-s windows as the audit's 10-s drift, ≥ 10 fixes).
4. **"Same zone"** (verdict criterion 1 and C3 variant z) = identical zone label (`house_1`, `house_2` or `outside`), i.e. same
   house plus both-outside.
5. **C2 quantiles.** p95 / p99 are taken of |d − d_truth|; the mean signed error (bias) is reported alongside.
6. **C3 details.** Corrected and uncorrected metrics are compared on the covered seconds only (same seconds, paired); the
   reference tags are the other tags with a valid 1-s residual of the same method inside one of their primary ≥ 30-s certified
   segments at that second (no ≥ 30-s pair-overlap requirement — the plan's "certified still at t"). The 10-s drift on the 1-s
   series = the maximum over 1-s centres of the coordinate-wise median of the covered 1-s values in [c − 5 s, c + 5 s) (≥ 5
   values); ≥ 12-in events = the audit's crazy-drift rule (≥ 12 in for ≥ 10 consecutive centres) on that series. Criterion 2
   passes when the relative change is ≤ −10 % **and** the 95 % CI's upper bound is < 0. A whole-segment version (zero
   correction where no reference) is reported as secondary.
7. **Bootstrap blocks** = 10-min blocks of clock time within a period, shared by all pairs / tags in that window (simultaneous
   pairs share tags and the common mode itself), resampled within each stratum among the blocks holding its data; C3
   segments are assigned by midpoint. Drift medians / p90 under resampling use block-weighted lower quantiles; |ε| quantiles
   use 0.05-in histograms.
8. **Shared excursions** (the "largest shared excursions" of C1): pair-seconds where both tags' raw 10-s residuals are ≥ 12 in
   (the audit's crazy-drift size); runs within an overlap = events; events of all pairs overlapping in time (gap ≤ 1 s) =
   clusters; anchor enrichment = share of the top-20 clusters' event seconds with the anchor lost by both ÷ the same share over
   all joint pair-seconds.

## Amendment 2 (2026-10-03, made AFTER the pooled numbers were seen — reporting only)

Nothing here changes a metric, threshold, stratum or the verdict (which stays as computed by the pre-registered rule:
**not material**). Added to the report after the first run, then re-rendered from the same saved seconds with the same
bootstrap seeds (identical numbers):

1. **Reproduction:** the plan expected the 1-s still RMS to be ≤ the audit's per-fix RMS. It holds for raw; for B2 the 1-s
   value is 0.0–1.7 % higher, because B2 is already smooth at 1 s and the 1-s grid weights every second equally while the
   per-fix RMS weights seconds by their fix count (seconds with few fixes have larger errors). A fix-count-weighted 1-s RMS is
   added next to it; it is ≤ the per-fix value for every tag and set.
2. **Analytic check of C3** (not a criterion): predicted RMS ratio $\sqrt{(1-\rho)(1+1/\bar n)}$ from the measured truth-centred
   1-s ρ and the mean number of references, next to the observed ratio.
3. A plain-language **Findings** list, a note on strata resting on < 10 ten-minute blocks, the 09-10 case table showing the
   window RMS (with the maxima in brackets) instead of maxima only, and a per-tag small-multiples version of the 09-10 figure.
