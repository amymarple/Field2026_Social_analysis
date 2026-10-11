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
- **Reading**: WISER gives the house roster (complete here — SF11 had left the paddock at the 09-07 AM round; corrected 2026-10-11) and clearly separated animals (≥ 8–15 in), not the
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

## Addendum (2026-10-11) — correction of a fact: SF11 kept its tag (plan amendment 12; text only)

The report's composition section had said SF11 was untagged after 09-07 06:10:45 and called every roster a lower bound.
That was wrong (the user: "SF11 has tag"; field incident log 09-07). SF11 kept its tag and left the paddock at the 09-07 AM
round (last fix 08:20), so on the clicked days (09-09 → 09-11) all five animals in the paddock were tagged and the rosters
are complete.

**No number in the report depended on the "lower bound" reading.** The rosters and untracked lists are read from the
phase-0 page data, which comes from the cleaned per-second states. Those states are unchanged, and all 22 segments were
re-checked. Under either reading, SF11 is in no roster or untracked list after 09-07.

The report text was corrected by hand: the summary, section 1 and the composition note, plus a correction note at the top.
The generator `inbox_click_analysis.py` now carries the corrected wording, and its self-test passes 31 / 31. The
clicks run was not re-run, because nothing in it changes.

## Addendum (2026-10-11) — re-run on the user's formal export; the snapshot run is superseded

**Input.** The user's CSV export `cv/configs/inbox_identity_2026c/inbox_identity_2026c_20261010_220725.csv` (sha256 `3233d7b4…`). It is
the newest of three exports (21:51, 22:05, 22:07; all three kept in that folder). It holds 294 clicks in 20 of 22 segments:
284 blind, 10 after the reveal, 0 unsaved, 0 legacy. The input also includes the user's composition statement
`composition_statement_user_2026-10-11.json`: every clicked frame is complete, fewer clicks = animals outside the house, and
09-10 19:50 is unusable (black). The CSV carries everything the analysis uses (`first_*` = the blind record, `b11…b23`, reveal
flags). Only `orientation_by_house` is JSON-only; the prior comes from `cv/configs/inbox_camera_orientation_2026c.json` anyway.
Run `D:/Field2026_analysis_out/2026c/cv_field_inbox_clicks_20261010_2227/`. The snapshot was re-analysed into its
`superseded_snapshot/` and reproduces the 10-10 run exactly on all 8 variants. The report now leads with the export and keeps the
snapshot results in a "Superseded preliminary run" section. Same pre-registered rules (amendment 11); nothing re-tuned.

**Blind record, snapshot → export.** The 140 saved snapshot clicks are identical in the export (animal, position, frame, status,
B). One click changed: the snapshot's single unsaved click (09-10 15:23, colour, unknown) is now a blind SF10 click. 153 clicks
are new, all in segments the snapshot did not hold (except 5 after-reveal clicks on 09-10 14:16 IR +15 s). **No blind click of
the order test's first 5 flashes differs**, and their WISER means are identical too.

| | snapshot (superseded) | export (primary) |
|---|---|---|
| 1. colour set = WISER roster | 8 of 10 | 17 of 20 |
| 2. colour → IR < 30 s: pairs, median / max px | 60, 27 / 387 | 140, 27 / 643 |
| 2. head IMU still between the frames: n, max px | 36, 44 | 64, 54 |
| 3. fit points / flashes | 40 / 8 | 89 / 18 |
| 3. handedness; px/in | proper; 79.3 | proper; 74.8 |
| 3. page rotation (Δ vs the user's 180°) | 178.2° (−1.8°) | 174.3° (−5.7°) |
| 3. LOFO RMS in / px | 5.96 / 470 | 5.45 / 406 |
| 4. exact order, first 5 → verdict | 0 of 5 → **NOT ACCEPTED** | 0 of 5 → **NOT ACCEPTED** |
| 4. tie version (pairs < 8 in untested), first 5 | 4 of 5 (accepted) | 3 of 5 (not accepted) |
| 4. Kendall τ median first 5 / all | +0.40 / +0.50 | +0.20 / +0.20 |
| 4. exact order, all flashes; pairs ≥ 8 in concordant | 0 of 8; 25 of 28 | 1 of 18; 46 of 52 |
| 5. Hungarian accuracy (chance) | 65 % of 40 (20 %) | 64 % of 89 (20 %) |
| 5. heads ≥ 15 in from every other animal | 4 of 4 | 6 of 6 |

- **The pre-registered order test is NOT ACCEPTED in both runs.** It uses the same five flashes and the same inputs. The tie
  version moved from 4/5 to 3/5 only because each flash is now mapped by a fit on 17 other flashes instead of 7. At 09-10 07:14
  the clicks now map to the order SF07 < SF10 < SF09 < SF08 < SF12, and its only pair ≥ 8 in apart (SF08–SF12) is now discordant. Across the
  secondary variants the tie version is accepted in 2 of 5 (rotation fixed at 180°: 4/5; without lid-flagged flashes: 4/5).
  It is borderline and turns on one flash. The exact-order verdict is NOT ACCEPTED in every variant.
- **Composition with the user's statement.** The roster is the cleaned house state **at the colour frame** (page code: dilated
  rectangle + 15 in, 6-s smoothing, 20-s dwell). Only the WISER positions use the minute before ON, so "the roster window is
  the minute before" is not the mechanism. No clicked animal was ever missing from a roster.
- **The roster animals not clicked.** There are 4: 09-10 08:37 SF08 and SF09, 09-11 09:28 SF10, 09-11 09:54 SF12. By WISER
  ±5 s around the colour frame, 3 lay 5.1–8.8 in outside the house body, inside the 15-in dilated zone. One (08:37 SF08) lay
  inside the body by WISER, and that colour frame also carries one unknown click.
- **Reading the composition.** Under the statement, these 4 animals are WISER over-inclusions by the dilation / dwell rule.
  Two are in AM-round lid windows; the 09-11 09:54 segment (413 s) comes after the round. A stricter roster (inside the body
  footprint) matches only 2 of 20, so the dilation is needed.
- **Colour → IR** (140 pairs < 30 s). The head moved ≤ 54 px when the head IMU was still on every second between the frames
  (n 64), and up to 387 px when it moved (n 30). The 643-px maximum is SF10 at 09-10 15:23, with no IMU-ok second.
- **New definitions** (in the report): the composition sets, $\mathcal R_f$ (roster at the colour frame) and $\mathcal K_f$
  (clicked set); "WISER at the colour frame" (mean of all primary fixes in $[t_{col} - 5\,\mathrm s, t_{col} + 5\,\mathrm s)$);
  inside the body $\Leftrightarrow |A| \le 12.3$ and $|C| \le 9.0$ in, outside distance
  $\sqrt{\max(|A|-12.3,0)^2 + \max(|C|-9.0,0)^2}$; the blind-record comparison by `click_id`.
- **Code.** `inbox_click_analysis.py` gains a CSV-export loader, the snapshot ↔ export blind comparison, the composition
  statement, WISER at the colour frame, the superseded re-analysis, and three new self-test checks (34 / 34 PASS). The defaults
  are now the export, the snapshot as superseded, and the statement.
- **Docs.** `cv/configs/inbox_identity_2026c/README.md` marks the snapshot superseded (file kept). The plan status and the
  `CLAUDE.md` cv_field line were updated. `change_log/README.md` is still not touched; its index row is still to be added.
