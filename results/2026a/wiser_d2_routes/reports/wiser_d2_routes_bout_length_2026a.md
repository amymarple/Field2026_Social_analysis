# Bout-length analysis — do rats run long corridors, or fixed-length bouts (a capacity limit)?

**Date:** 2026-07-11 · **Status:** ⚠️ candidate / exploratory. Post-hoc analysis of the Phase-B route
bouts (`route_bouts.csv`, 1692 bouts, 13 nights 06-28→07-10, 21:00→04:00, 4–5 rats). Inch frame
UNVERIFIED — no absolute-distance claim vs the physical paddock beyond internal ratios.

## Question

Do the rats **love long runs** (sustained corridor travel — a heavy-tailed length distribution) or do
they run **fixed-length bouts** capped by some **capacity** (a characteristic length with a sharp
upper bound)?

## Answer (candidate): FIXED-LENGTH, capacity-like — and the capacity looks like a short RUN DURATION, not a distance.

1. **Bout length is tightly concentrated, not heavy-tailed.** Net displacement median **100 in (~8.3 ft)**,
   mean 104 in, **CV 0.32**, **mean/median 1.05** (≈1.0 = symmetric/capped, not 1.44 of an exponential
   tail). 50 % of bouts are ≥100 in but only **9 % ≥150 in, 1 % ≥200 in, 0 % ≥300 in**; the single
   longest bout is **261 in ≈ half the paddock diagonal**. They essentially **never run the full length
   of the paddock in one bout** — the opposite of long sustained corridor travel.
2. **The "capacity" is TIME/persistence, not distance.** Speed is near-constant (**median 25 in/s,
   CV 0.22**) and longer bouts are longer in **time** (corr(disp, duration) = **0.71**), while duration
   itself is short and bounded (**median 3.8 s, p99 7.8 s, max 10.9 s**). So they run at a stereotyped
   speed for a stereotyped **short burst (~4 s)**, which yields the characteristic ~8 ft length.
3. **The longer bouts ARE the straight corridor runs.** Straightness (path/displacement) → **1.0–1.1**
   for all bouts ≥ 50 in but **1.46** for the shortest (15–50 in): long bouts are near-perfectly
   straight (corridor-like), short bouts are wiggly local moves. The **most-reused** routes are the
   **mid-length ~80–150 in straight** segments (lowest nearest-route distance); the few longest bouts
   (150–260 in) are straight but slightly less reused (more one-off).
4. **It is a SHARED trait, not an individual one.** All 4–5 rats have the same distribution (median
   95–105 in, p90 144–153 in, straightness 1.1). No individual "long-runner" — consistent with the
   shared-road / herd findings.

**Net:** they do **not** run long corridors; they make **repeated, straight, short-duration hops of a
characteristic ~8 ft length**, at roughly constant speed. The pattern is capacity-like, and the
capacity is a **short continuous-run duration**.

## ⚠️ Load-bearing caveat (measurement, not animal)

The "fixed length" is **partly definitional**. A bout ends at any gap **> `max_gap_s` = 2 s** (and must
be ≥ `min_bout_s` = 3 s), so **any longer journey that includes a brief pause is split into ~4 s
chunks**. Part of the tight duration cap therefore reflects the **segmentation parameters**, not a hard
biological limit. To separate "they genuinely run short" from "long journeys are chopped at pauses":
re-extract with a larger `max_gap_s` (merge across brief stops), or measure **rest-site→rest-site
journeys** (start_roi→end_roi) instead of contiguous moving runs. Until then this is a statement about
**contiguous moving runs**, not whole trips. (Also: `disp≥15 in` left-censors tiny shuffles; the
top-40/animal-night cap dropped 85 short bouts — both mildly bias toward longer, so the true short end
is if anything even shorter.) Path length is jitter-inflated; net displacement + duration are robust.

## Definitions

Per bout $i$ (an arc-length-resampled contiguous moving run):

- **Net displacement** $d_i = \lVert \mathbf{x}^{\text{end}}_i - \mathbf{x}^{\text{start}}_i \rVert$
  (in). Straight-line start→end distance; jitter-robust. *"How far the run went."*
- **Path length** $\ell_i = \sum_k \lVert \mathbf{p}_{i,k+1}-\mathbf{p}_{i,k}\rVert$ over the resampled
  points (in). *Total traveled distance; **jitter-inflated**, use only in ratios.*
- **Straightness** $s_i = \ell_i / d_i \ge 1$. $s_i=1$ perfectly straight (corridor); $s_i \gg 1$
  meandering. Unitless.
- **Duration** $\Delta_i = (t^{\text{end}}_i - t^{\text{start}}_i)$ (s), from UTC timestamps.
- **Net speed** $v_i = d_i / \Delta_i$ (in/s).
- **Nearest-route distance** $\text{nn}_i = \min_{j\ne i}\text{dist}(\text{path}_i,\text{path}_j)$ (in,
  mean-pointwise metric) — **route reuse**; small = a near-identical partner route exists (recurrent).
- **CV** $= \sigma/\mu$ of a quantity (unitless): low CV + mean≈median ⇒ **characteristic scale /
  capped**; high CV + mean≫median ⇒ **heavy-tailed**.
- **mean/median ratio:** ≈1.0 symmetric/capped; ≈1.44 exponential; >1.44 heavier tail.
- **Length bins** (net disp, in): 15–50 · 50–100 · 100–150 · 150–250 · 250+ — used to test whether
  straightness/reuse change with length.

## Follow-ups

- **Re-segment with larger `max_gap_s`** (or rest-site→rest-site trips) to test whether the duration cap
  is biological or definitional — the one thing that could overturn "fixed-length."
- Roadway-camera audit (still UNDONE) would confirm the straight long bouts are the visible trampled road.

## Outputs
`bout_length_by_bout.csv` (per-bout with straightness/speed) · `plots/bout_length.png` (length + duration
histograms, corridor-by-length-bin, disp-vs-duration constant-speed).
