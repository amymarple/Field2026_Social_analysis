# In-bout approach/avoid — coarse, heading-free, NIGHT-BLOCK (Module 7, Phase 3)

**Status:** ⚠️ candidate (measurement-gate). WITHIN validated active bouts only; a **coarse, heading-free** net-distance-change approach/avoid (decision_boundary_validation falsified reliable heading at WISER resolution). Significance is tested at the **NIGHT-BLOCK level** (the ~8 nights are the outer units) — a per-night effect + a sign test — NOT a pseudoreplicated per-pair z. Gate runs BEFORE any model. Generated 2026-07-12T07:00:34.558127; min_disp=14.0 in.

## Definitions (formula + plain text)

- **toward** $= (d_0 - |p_{\text{end}} - p_{\text{partner,0}}|)/\lVert\Delta\rVert \in[-1,1]$, where
  $d_0=|p_{\text{start}}-p_{\text{partner,0}}|$ and $\Delta=p_{\text{end}}-p_{\text{start}}$ is the bout
  displacement. Plain: how much of the bout went toward the partner's start position ($+1$ straight at,
  $-1$ straight away). Heading-free. Included only for bouts with $\lVert\Delta\rVert\ge$ min_disp and a
  partner at $d_0\ge 1$ m (both above the ~7 in floor).
- **Per-night geometry-adjusted effect** $e_{\text{dir}}(n)=\overline{\text{toward}}(n)-\mu_{\text{dir}}(n)$,
  where $\mu_{\text{dir}}(n)$ is the night's direction-randomized (rotate each $\Delta$ about its start)
  mean — the GEOMETRY expectation (generally $<0$; a step from a point usually increases distance).
- **Per-night social increment** $e_{\text{day}}(n)=\overline{\text{toward}}_{\text{valid}}(n)-\mu_{\text{day}}(n)$,
  where $\mu_{\text{day}}(n)$ replaces each partner with the SAME partner at the same clock-hour on a
  DIFFERENT night (layout, not real-time). ``valid`` = pairs whose (partner,hour) cell has another
  night, so obs and null are the SAME subpopulation.
- **Night-level sign test:** two-sided binomial over the $N\approx8$ per-night effects (null $p=0.5$).
  This is the significance — **NOT** the per-pair z, which is invalid here (thousands of pseudoreplicated
  pairs; each bout emits several partner rows and bouts within a night share layout).
- **Gate:** RESOLVABLE = support AND $e_{\text{dir}}$ sign-test $p\le0.1$ (pooled or any $d_0$ bin);
  SOCIAL = RESOLVABLE AND $e_{\text{day}}$ sign-test $p\le0.1$. Model fit only if SOCIAL.

## Result (night-block; the RAW toward sign is distance-dependent by geometry, so read the ADJUSTED effects)

**Support:** 5717 (bout, partner) pairs over 11 night-blocks.

| d0 bin | n pairs | n nights | e_dir (vs geometry) | dir +/N | dir sign-p | e_day (real-time social) | day +/N | day sign-p | net |
|---|---|---|---|---|---|---|---|---|---|
| ALL | 5717 | 11 | 0.3007 | 11/11 | 0.001 | 0.0377 | 10/11 | 0.012 | approach |
| 1-2m | 396 | 11 | 0.2582 | 11/11 | 0.001 | -0.2626 | 0/11 | 0.001 | approach |
| 2-3.8m | 1398 | 11 | 0.1888 | 11/11 | 0.001 | -0.1098 | 0/11 | 0.001 | approach |
| >3.8m | 3923 | 11 | 0.3486 | 11/11 | 0.001 | 0.1233 | 11/11 | 0.001 | approach |

- **RESOLVABLE (a toward/away bias above geometry, night-consistent): True**.
- **SOCIAL (real-time, above shared layout, night-consistent): True**;
  **distance-dependent: True** (per-bin social signs: {'1-2m': 'avoid', '2-3.8m': 'avoid', '>3.8m': 'approach'}).

**Read:** `e_dir` > 0 means the focal moves toward partners MORE than chance geometry (positive across
bins ⇒ a real toward bias at all distances; the raw negative toward at close range is geometry). `e_day`
is the REAL-TIME social increment beyond shared layout — its **sign is distance-dependent**: the animals
tend to **close distance to FAR conspecifics and open distance to NEAR ones**, i.e. maintain a preferred
inter-individual spacing, only where the night-level sign test is significant ($p\le0.1$).

### Verdict: SOCIAL approach/avoid resolvable at the night level — DISTANCE-DEPENDENT (approach far / avoid near): social spacing

The approach/avoid MODEL table is gated on SOCIAL and was written (approach_model_table.csv).

## Scope & language

Coarse net proximity change, ≥ 1 m, heading-free (no fine steering — DBV). **Association, not
motivation:** "in-bout approach/avoid tendency relative to the group", never "the rat chooses to
approach" or "attraction/aversion". Group-level; pair-resolved (dyadic) only if module 13 passes.
Frame UNVERIFIED (topology + coarse distance only).
