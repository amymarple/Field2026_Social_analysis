# 2026-07-12 — Phase 3 / Module 7: in-bout approach/avoid (coarse, heading-free, NIGHT-BLOCK, gate-first)

**Status:** ⚠️ candidate. Roadmap Phase 3 — approach/avoid WITHIN validated active bouts. Plan:
[`implementation_plan/2026-07-12-approach-avoid.md`](../implementation_plan/2026-07-12-approach-avoid.md).
Governed by [`change_log/2026-07-11-dbv-crosscheck-locomotor.md`](2026-07-11-dbv-crosscheck-locomotor.md)
(heading is NOT resolvable at WISER resolution). Prerequisites [1, 4] built (module-3 `bouts.csv`).

## What this measures (and why heading-free)

The literal module-7 outcome is "per-step relative bearing toward/away". DBV falsified reliable heading
at WISER resolution; the spec allows only "**coarse approach/avoid at ≥ 1 m**". So this module measures
approach/avoid as a **net distance change over a validated active bout**, never an instantaneous bearing.

For each validated active bout of a focal (excluding `spans_dropout`/`has_gap`) and each conspecific at
≥ 1 m at bout start: **`toward`** = (d0 − ‖focal_end − partner_start‖) / ‖displacement‖ ∈ [−1, 1] — how
much of the bout went toward the partner's start position. Included only for bouts with displacement ≥
14 in (jitter-safe) and a partner at d0 ≥ 1 m (both above the ~7 in floor).

## Files

- **`src/approach_avoid.py`** — `bout_approach_context`, `direction_null_z` (pooled descriptive),
  `night_block_gate`, `measurement_gate`, `build_model_table` (gated).
- **`scripts/build_approach_avoid.py`** — module-3 `bouts.csv` + shared `load_clean_stream` fixes →
  context → **night-block gate** → (gated) model table + report + manifest.
- **`scripts/selftest_approach_avoid.py`** — 8 planted checks (approach / avoid / random-direction /
  sub-floor / sub-1 m / night-block SOCIAL-vs-LAYOUT). **PASS (8/8).**
- Outputs → `outputs/approach_avoid_2026-06-28_to_2026-07-05/` (git-ignored).

## The critical correction (adversarial review → whole gate redone)

The first gate used a **per-pair z** (observed mean vs a null-of-the-mean over the 3,936 (bout, partner)
pairs). The adversarial review (5-dim × 3-verifier workflow) confirmed **3 findings**, the top one
**HIGH and decisive**: those pairs are **heavily pseudoreplicated** (each bout emits ~4 partner rows
sharing ONE displacement; bouts within a night share layout; consecutive bouts are serially correlated),
so the per-pair z scales with √n_pairs, **not effect size** — z ≈ 27 was pseudoreplication, not evidence,
and it never blocked at the night level despite the manifest claiming "whole nights are the outer
blocks". Also fixed: the day-shuffle averaged obs over all pairs but the null dropped no-other-night
pairs (subpopulation mismatch); and `net_sign` used sign(raw mean) not sign(obs − geometry-null).

**Fix:** the gate was **rebuilt at the NIGHT-BLOCK level** — per night compute the geometry-adjusted
effect and the real-time-social increment, then a **night-level binomial sign test** across the ~8
nights (the real N). The result **SURVIVED** the correction (a pseudoreplication artifact would have
collapsed to non-significance; instead the night-level sign test is p = 0.008).

## Definitions (formula + plain text)

- **Per-night geometry-adjusted effect** $e_{\text{dir}}(n)=\overline{\text{toward}}(n)-\mu_{\text{dir}}(n)$;
  $\mu_{\text{dir}}(n)$ = the night's **direction-randomized** mean (rotate each displacement by a random
  angle about its start) = the GEOMETRY expectation (generally < 0 — a step from a point usually
  increases distance). $e_{\text{dir}}>0$ ⇒ moves toward partners MORE than chance geometry.
- **Per-night social increment** $e_{\text{day}}(n)=\overline{\text{toward}}_{\text{valid}}(n)-\mu_{\text{day}}(n)$;
  $\mu_{\text{day}}(n)$ replaces each partner with the SAME partner at the same clock-hour on a DIFFERENT
  night (LAYOUT, not real-time). ``valid`` restricts obs and null to the SAME pairs (those with another
  night available). $e_{\text{day}}>0$ ⇒ real-time approach beyond shared layout; $<0$ ⇒ real-time avoid.
- **Night-level sign test:** two-sided binomial over the $N\approx8$ per-night effects (null p = 0.5) —
  THE significance (the per-pair z is invalid here).
- **Gate:** RESOLVABLE = support ∧ $e_{\text{dir}}$ sign-test p ≤ 0.1 (pooled or any d0 bin); SOCIAL =
  RESOLVABLE ∧ $e_{\text{day}}$ sign-test p ≤ 0.1. Model fit only if SOCIAL.

## Result (8 nights 06-28→07-05; 3,936 bout-partner pairs; night-block)

| d0 bin | n pairs | e_dir (vs geometry) | dir sign-p (+/N) | e_day (real-time social) | day sign-p (+/N) |
|---|---|---|---|---|---|
| ALL | 3,936 | +0.291 | 0.008 (8/8) | +0.036 | 0.07 (7/8) |
| 1–2m | 259 | +0.268 | 0.016 (7/7) | **−0.235** | 0.016 (0/7) |
| 2–3.8m | 947 | +0.178 | 0.008 (8/8) | **−0.110** | 0.008 (0/8) |
| >3.8m | 2,730 | +0.333 | 0.008 (8/8) | **+0.117** | 0.008 (8/8) |

**Two separate controls, two separate readings:**
1. **vs geometry (e_dir):** the focal moves toward conspecifics **more than chance geometry at every
   distance**, night-consistently (sign-test p 0.008–0.016, 7–8/8 nights). The *raw* toward-ness is
   negative at close range **purely by geometry** (a step from a close partner tends to increase
   distance); above geometry it is a toward bias everywhere.
2. **vs layout (e_day = real-time social):** the sign is **DISTANCE-DEPENDENT and night-consistent** —
   real-time **APPROACH to far conspecifics** (>3.8m: +0.117, 8/8 nights) and real-time **AVOIDANCE of
   near ones** (1–3.8m: −0.11 to −0.24, 0/8 nights positive), beyond shared layout.

**Headline:** the animals **actively maintain a preferred inter-individual spacing** — in-bout, they
close distance on distant group-mates and open distance from close ones, and this holds **night by
night** (not a pooled/pseudoreplicated artifact). This is the first robustly night-validated *social*
signal in the policy effort (module-3 social was negligible; module-5 crowding suppressed *leaving*).
The pooled "net approach" (mean toward +0.079) is far-bin-dominated and **misleading** — the structure
is spacing, not uniform approach. Gate: SOCIAL (resolvable, distance-dependent) → model table written.

## Verification

- `selftest_approach_avoid.py` → **PASS (8/8)**: toward-ness metric (approach/avoid/random via the
  direction null on independent bouts), jitter-safe filters, and the **night-block** SOCIAL-vs-LAYOUT
  discrimination (planted social → e_day p 0.004; planted layout → e_day p 0.18, not social).
- Adversarial review (5-dim workflow) → 3 confirmed findings, all fixed (pseudoreplication → night-block
  redesign; day-shuffle subpopulation mask; net_sign vs geometry). Result survives the correction.

## Scope & language

Coarse net proximity change, ≥ 1 m, **heading-free** (no fine steering — DBV). **Association, NOT
motivation:** "in-bout approach/avoid tendency" / "maintains a preferred inter-individual spacing",
never "the rat chooses to approach" or "attraction/aversion". **Group-level** (nearest/any present
partner); pair-resolved (dyadic) only if module 13 passes. Frame UNVERIFIED (topology + coarse distance
only); ~8-night pilot; approach to the partner's START position (the partner also moves) — coarse net
proximity change, not fine steering.
