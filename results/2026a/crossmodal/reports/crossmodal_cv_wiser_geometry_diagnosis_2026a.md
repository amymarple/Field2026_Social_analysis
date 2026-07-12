# WISER geometry diagnosis — 07-02 CV×WISER cross-val (crashed run)

Crashed run: `D:\Field2026_analysis_out\sleep_site_cv_crossval_20260706_2033\` (crashed at
`analyze_sleep_site_cv_crossval.py:309`, `KeyError: 'stratum'`, because `picks` was empty:
`WISER daytime bins/shelter: 1; episodes: 0`).

## Verdict
**NOT a coordinate-frame / ROI mismatch. Root cause = a pandas 3.0.3 `datetime64[ms]` binning bug in
`wiser_analysis_utils.py`.** WISER shelter occupancy for 07-02 is **NOT auditable via this pipeline in the
current env** — but because the binning is broken, **not** because the tags are absent or the frame is wrong.
**`state=0` is a code artifact, not rat absence.**

## Evidence (all verified read-only on the 2026-07-03 snapshot)
1. **WISER 07-02 coverage is full** — 1,700,757 raw fixes, all 24 hours; **1,132,208** valid daytime
   (05:00–21:00) fixes. Not a WISER dropout.
2. **Frame / units / ROIs consistent across dates** (medians, WISER offset inch frame):
   | date | x range | y range | median | pct in house_1 | pct in house_2 |
   |---|---|---|---|---|---|
   | 2026-06-30 | 221–822 | 534–964 | (419,728) | **35.7%** | 9.1% |
   | 2026-07-01 | 238–795 | 513–1028 | (420,729) | — | — |
   | 2026-07-02 | 225–793 | 443–983 | (428,725) | **32.3%** | 11.5% |
   ROIs: `house_1` rect center **(411.5, 718.6)** 36.4×26.6 in, orient 90°; `house_2` (613.6, 717.3).
   The point-cloud median sits essentially **on** `house_1`'s center. **Direct point-in-rect membership
   (independent of the pipeline) puts ~32% of 07-02 fixes inside `house_1`** → tags ARE in the shelter.
3. **No transform applied** — `configs/wiser_to_field_transform.json` does not exist (`load/apply_field_transform`
   are no-ops), so positions are raw inches, same frame as the ROIs. `_rect_membership` works correctly when
   called directly (house_1 center → `in_core=True`). So neither the frame, units, ROI geometry, nor the
   membership helper is at fault.
4. **The bug** — `datetime` dtype is **`datetime64[ms]`** under **pandas 3.0.3**. Three binning sites compute
   `datetime.astype("int64") // (bin_s * 1_000_000_000)` assuming **nanoseconds**:
   - `wiser_analysis_utils.py:3407` — `wiser_shelter_state` (shelter STATE)
   - `wiser_analysis_utils.py:3502` — `wiser_shelter_presence` (raw point-wise)
   - `wiser_analysis_utils.py:3620` — `_cv_bins` (CV↔WISER alignment; via `t_utc`)
   On `[ms]` data `astype("int64")` returns **milliseconds**, so `// 60e9` buckets a ~**16-hour** span into
   **one** bin. Confirmed: 07-02 daytime **1,132,208 fixes → 1 bin** (forcing `[ns]` → **960** bins). That one
   16-h bin has `frac_near ≈ 0.35 < near_frac 0.5` → `state=0` for every rat/shelter → false "no occupancy" →
   0 episodes → empty `picks` → crash.
5. **Blast radius** — the same bug breaks **06-29/06-30** too (the pair that originally produced joint
   κ=0.66, on an older pandas where `datetime` was `[ns]`). `scripts/selftest_cv_crossval.py` builds synthetic
   timestamps in **ns**, so it passes and never caught this. Any WISER analysis binning `datetime.astype("int64")`
   is suspect under pandas 3.0.

## Classification (regime-aware-wiser-tracking)
- 07-02 WISER shelter occupancy via `analyze_sleep_site_cv_crossval.py` → **invalid / not-auditable (code
  artifact)**, NOT "likely behavioral" and NOT "rat absent." Do not interpret `state=0` as absence.
- Provenance note: the WISER pipeline has **no `measurement_context` sidecar / `mc_run_id`** (weaker provenance
  than CV), and its only integration selftest uses `[ns]` synthetic data — so this env-driven regression was
  invisible to QC.

## Recommended fix (before any rerun; NOT applied here)
Normalize the timestamp resolution at the 3 binning sites — e.g. `d["datetime"].values.astype("datetime64[ns]").astype("int64")`
(and likewise `t_utc`) — or floor resolution-agnostically via `pd.Series.dt` flooring. Then add a `datetime64[ms]`
(and `[us]`) regression case to `selftest_cv_crossval.py`, and only then rerun the 07-02 cross-val.

*(Overlay plot skipped: matplotlib's Agg import/savefig aborts natively in this foreground env; the coordinate
ranges + direct membership above establish the frame is correct without it.)*

---

## Resolution — patched & rerun 2026-07-06

**Fix applied** (see `change_log/2026-07-06-wiser-binning-resolution-fix.md`). `wiser_analysis_utils.py`
now floors bins through a resolution-agnostic helper `_bin_utc_ns` (`pd.to_datetime(dt).dt.floor("{bin_s}s")`
→ int64-ns) at all three sites (`wiser_shelter_state`, `wiser_shelter_presence`, `_cv_bins`); the CV lag is
applied as a `timedelta` before flooring. `selftest_cv_crossval.py` gained a `[ns]`/`[us]`/`[ms]`
resolution-invariance regression (**`SELFTEST: PASS`**). For `[ns]` inputs the output is byte-identical to
before, so this is a pure correctness fix — no threshold/ROI/hysteresis/view-quality change.

**Rerun** (`--dates 2026-07-02 --no-plots`, on `…_2026-07-03.sqlite`; `KMP_DUPLICATE_LIB_OK=TRUE`):
- **`WISER daytime bins/shelter: 960`** (was **1**); **`episodes: 42 (19 high-confidence)`** (was **0**).
  The collapse is gone and the run completes instead of crashing on empty `picks`.

**What this confirms about the original claim:**
- The previous 07-02 "WISER assigns ~no tag to the shelter ROI / one empty bin" result was **not
  interpretable** — a pandas `[ms]` binning code artifact, **not** rat absence and **not** a coordinate-frame
  / ROI mismatch.
- **Raw WISER coverage and the coordinate frame were valid all along** (full 24 h coverage; frame/units/ROIs
  consistent across dates; ~32 % of 07-02 fixes directly inside `house_1`).
- **CV-vs-WISER occupancy is still NOT interpreted here.** The rerun's alignment is unverified (joint
  κ = 0.20, best-fit lag 0 s) and the CH05 recall gap sits on *clear* glass, so recall/precision remain
  measurement diagnostics. Resolve the clock alignment before any behavior interpretation (details +
  metrics table in the change-log).

**Provenance note (unchanged):** the WISER pipeline still has no `measurement_context` sidecar / `mc_run_id`
(weaker provenance than the CV side), and its integration selftest was `[ns]`-only — which is exactly why
this env-driven regression was invisible to QC until now (the regression test closes that gap).
