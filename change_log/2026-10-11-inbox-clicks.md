# 2026-10-11 — In-box CH07 (house_2): the user's first identity clicks — composition, colour → IR stability, camera ↔ WISER fit, the pre-registered order test, WISER as an identity aid (PRELIMINARY)

Plan: [`implementation_plan/2026-10-10-inbox-ch0708-wiser-identity-p0.md`](../implementation_plan/2026-10-10-inbox-ch0708-wiser-identity-p0.md),
section "Pre-registered use of the user's clicks" + **amendment 11** (how the step is run; written before any fit, order or
assignment result — only the click table had been listed) + the status paragraph at the end (after results). Report:
[`results/2026c/cv_field/reports/cv_field_inbox_clicks_2026c.md`](../results/2026c/cv_field/reports/cv_field_inbox_clicks_2026c.md)
(every derived quantity defined as a formula and in words). The agent never looked at a frame.

**PRELIMINARY.** Data = browser snapshot 2026-10-10 20:17 of the identity page's localStorage
(`cv/configs/inbox_identity_2026c/browser_snapshot_20261010T2017.json`, sha256 `b37a94cb…`), 11 of 22 segments clicked, **not a
formal export** (the user has not exported yet). Re-run on the export: `python cv/cv_field/inbox_click_analysis.py --clicks <export.json>`.

## What changed

- **New driver** `cv/cv_field/inbox_click_analysis.py` (base Python; `--selftest` 31 checks on synthetic data: similarity recovery
  of rotation / scale, handedness choice by LOFO in a proper and a mirrored world, the page-orientation conversion (180° / no
  mirror ↔ θ_house 88°; 90° + mirror), fixed-rotation fit, Kendall τ, exact and tie order rules, ACCEPTED on well-separated piles and
  NOT ACCEPTED with swapped identities, INSUFFICIENT with < 5 flashes, the alternative reading, Hungarian vs greedy, per-flash-offset
  assignment, click statuses blind / after-reveal / unsaved / legacy / deleted, blind record from `verdict_first`, B correction,
  displacement px / inches, IMU classes, DST-aware field-PC seconds).
- **Run** `D:/Field2026_analysis_out/2026c/cv_field_inbox_clicks_20261010_2042/` (tables per variant, `run.json`, three figures);
  pointer `results/2026c/cv_field/reports/run_manifest_inbox_clicks_2026c.json`.
- The snapshot is committed unchanged as the analysis input. Plan amendment 11 + status; `CLAUDE.md` cv_field map (one sentence).
  `change_log/README.md` is **not** updated here (another session holds uncommitted edits there) — its index row is still to add.

## Results (house_2 / CH07 only; CH08 has no clicks)

- **Clicks**: 141 = 135 blind (saved at the reveal; read from `verdict_first`), 5 after the reveal (all IR +15 s of 09-10 14:32),
  1 unsaved (09-10 15:23, segment not revealed), 0 legacy; the blind record equals the live values (no edit, no deletion). The
  SF09 / SF10 one-time swap touched 6 clicks (09-09 19:10).
- **1. Composition** (colour frame, blind): the clicked set equals the WISER house roster in **8 of 10** revealed segments; 09-10 08:37
  (18-min colour segment in the AM round) misses SF08, SF09 on the colour frame (+1 unknown click), 09-11 09:28 misses SF10 (SF12
  untracked by WISER); in both every roster animal is clicked on some frame of the segment. No clicked animal outside a roster;
  **SF11 never clicked**; 3 unknown clicks.
- **2. Colour → IR** (IR frame < 30 s after the colour frame; 7 segments, 60 animal × frame pairs): head displacement median
  **27 px** (≈ 0.3 in), p75 46, max 387 px. Head IMU still on every second between: n 36, median 21, **max 44 px**; IMU registered
  movement: n 24, median 52, max 387 px. Long segments (IR 37–554 s after the colour frame) are no test of the premise. 10 of 92
  colour × IR-frame slots not clicked on IR (the blind IR +15 s of 09-10 14:16 and 14:32 were left empty).
- **3. Fit** (40 blind colour clicks with a WISER mean, 8 flashes): **proper** handedness (LOFO RMS 5.96 vs 9.65 in improper);
  79.3 px/in; θ_house +89.8°, θ_paddock −178.2° → page-equivalent **178°, no mirror vs the user's 180° (Δ −1.8°)**; fold rotations
  86.4…92.0°; LOFO RMS **5.96 in / 470 px** (median 4.29 in / 343 px); rotation fixed at 180°: 5.90 in. Residual along the ridge 5.06,
  across 3.15 in; removing a per-flash offset → 5.34 in (in-sample), a per-tag offset (LOO) → 6.35 in: not a calibratable bias.
  The page's WISER means were reproduced exactly with the page's code (45 pairs, max |Δ| 0.0000 in).
- **4. Pre-registered order test: NOT ACCEPTED** — exact order in **0 of the first 5** flashes (0 of 8); Kendall τ median +0.40
  (first 5), +0.50 (all). Tie version (pairs < 8 in by WISER not tested): 4 of 5 (accepted), 25 of 28 pairs ≥ 8 in concordant (89 %).
  Every variant (other handedness, rotation fixed at 180°, raw-fix means, without the lid-flagged flash, the alternative reading, a
  window centred on the colour frame) is NOT ACCEPTED; the tie version fails with raw-fix means and the alternative reading (3 of 5).
- **5. WISER as an identity aid**: Hungarian assignment of the LOFO-mapped heads to the WISER means **65 %** correct (26 / 40;
  chance 20 %; greedy 55 %; free per-flash offset 72 %; centred window 76 %). By the clicked animal's separation from the nearest other
  roster mean: < 4 in 70 % (n 10), 4–8 in 60 % (n 20), 8–15 in 50 % (n 6), ≥ 15 in 100 % (n 4). Pile neighbours are a median 5.7 in apart
  (2.0 in along the ridge); a mapped head lies a median 4.3 in from its own WISER mean.
- **Reading**: WISER gives the house roster (a lower bound — SF11 is untagged) and clearly separated animals (≥ 8–15 in), not the
  order inside a pile; the plan's rule (trust > 15 in per fix, > 8 in for 1-min means) stands. The head IMU is a candidate gate for
  carrying colour identities into IR.

## Headline definitions (full set in the report)

- **Click correction / display coordinates**: $(u', v') = B\,(u, v, 1)^\top$, $(p, q) = (u', -v')$ — reference px of the lid
  segment, image right / up.
- **Similarity fit**: $\hat\alpha = \sum \overline{(z - \bar z)}(w - \bar w) / \sum |z - \bar z|^2$, $\hat w(z) = \hat\alpha z + \bar w - \hat\alpha \bar z$,
  $z = p + i\sigma q$ ($\sigma = \pm 1$ = proper / mirrored), $w$ = WISER minute mean (along + i across, in): scale $1/|\hat\alpha|$ px/in,
  rotation $\arg\hat\alpha$ (display → house frame); page orientation rot $= -(\arg\hat\alpha + \varphi)$ (proper), $\varphi = 92°$.
- **LOFO residual**: $e = |\hat w_{-f}(z_{f,a}) - w_{f,a}|$ (in), the fit leaving flash $f$ out; px = WISER mapped into the image vs the click.
- **Order test**: WISER order by along; click order by $\mathrm{Re}\,\hat w_{-f}(z)$; exact = identical permutations; ACCEPTED if ≥ 4 of
  the first 5 eligible flashes (≥ 3 animals with a blind named colour click and a WISER mean). Tie version: only pairs with
  $|A_a - A_b| \ge 8$ in tested, a flash matches if all tested pairs are concordant. Kendall
  $\tau_a = \sum_{a<b}\mathrm{sgn}(\Delta A)\,\mathrm{sgn}(\Delta\hat A) / \binom{n}{2}$.
- **Assignment accuracy**: share of heads whose Hungarian match (min $\sum |\hat w_{-f}(z_h) - w_{\pi(h)}|$) is the user's ID; chance $= 1/n_{cand}$;
  separation $= \min_{b \ne a} |w_a - w_b|$ (in).
- **Colour → IR displacement**: $d = |(u', v')_{IR} - (u', v')_{col}|$ (ref px); IMU class over the field-PC seconds between the frames
  (all still / moved / still partial / no IMU) from `imu_seconds_cache`.

## Not verified

Snapshot, not export; one labeller; one house; a 2-D similarity ignores perspective and head height (camera ≈ 1 ft above piled heads);
WISER means come from the minute before ON; lid-flagged frames (09-10 07:14, 09-11 09:28) use the lid segment's median correction;
the user's 180° orientation was chosen by eye after 5 reveals (independent of the fit's numbers, not blind to WISER); click
repeatability on one head is unmeasured.
