# Scientific summary — What structures rats' movement decisions, and does the group matter?

> ⛔ **SUPERSEDED (8-night version).** Replaced 2026-07-12 by the **11-night** current-state summary at
> [`wiser_policy_social_extension_SCIENTIFIC_SUMMARY_2026a.md`](wiser_policy_social_extension_SCIENTIFIC_SUMMARY_2026a.md).
> Key change: the crowding-suppresses-leaving magnitude here (≈0.012 bits) **attenuates to ≈0.003** on the
> fuller data (still rest-independent, but small). Kept for provenance only — do not cite these numbers.

*Standalone, current-state summary (regenerated 2026-07-12) of the behavioral-policy program: the
locomotor decision hierarchy built on WISER UWB tracking. ~5 min read; the quantitative appendix is
read on demand. **Nothing here is Established as a biological result** — all findings are Candidate,
gated by the pilot's frame/hardware limits. Links down to the technical ledger for detail.*

## Biological picture

Over eight nights (2026-06-28→07-05; five UWB-tagged rats; active window 21:00–05:00) we asked which
low-level movement decisions of an outdoor rat group are structured, and by what. Working only with what
the sensor can resolve — coarse locomotion above a ~7 in position-jitter floor, in an **unverified**
coordinate frame that supports topology and coarse distance but no direction or route — one picture
holds: the animals' resolvable movement decisions follow a **single shared rule** set by the physical
layout and by how long a rat has already stayed somewhere, carrying a **specific social overlay**, with
**no detectable individual signature**. The dominant caveat is that every quantity is a coarse proxy
(low-speed "rest" is not validated sleep; a bout "onset" is a lower bound that misses in-nest stirring),
so all findings are candidate and stated as associations, not causes.

## Finding 1 — Social state shapes movement, but only certain decisions, and as spacing, not attraction

Two independent, robust social effects appear, and a third social question comes back negative — the
**contrast** is the finding. (i) Real-time crowding is associated with a resident **staying put**: adding
the pre-decision group configuration improves held-out prediction of *leaving a site* by **≈0.012 bits
(~4% skill), positive on all 8 nights**, surviving both a within-night time-shift and a day-shuffle null
(z ≫ 2) using only jitter-safe (≥1 m) features. (ii) Within active movement bouts, animals maintain a
**preferred inter-individual spacing**: against a mismatched-night (layout) control they close distance on
**far** group-mates (>3.8 m: +0.117, significant on **8/8 nights**) and open distance from **near** ones
(1–3.8 m: positive on **0/8 nights**), a distance-dependent pattern that holds night by night
(night-level sign-test **p ≤ 0.016**). (iii) Yet the *same* group-social state does **not** predict when a
resting animal **starts** a bout (Δbits ≈ 0.0002, far below the 0.003-bit threshold). So social context
governs *when a resident leaves* and *how animals hold distance while moving*, but not *when they initiate
movement*. All of this is **group-level** (herd, not pairs) and **associative** — not attraction, not a
decision to approach.

## Finding 2 — One shared, time-invariant environment-and-dwell rule; no individual policy, no recoverable reward

When a rat leaves a named site is predictable from an explicit-layout + elapsed-dwell baseline (held-out
**skill 0.13–0.26** across a preregistered parameter grid), and that rule is **constant**: letting it vary
by hour-of-night or by night yields no held-out gain (hour-varying **Δbits −0.0004**; night-slope variance
**z 0.51**) — apparent hour/night differences are shifts in *where the animals are*, not in the rule.
Knowing *which* individual adds essentially nothing (personalization **≈0.001 bits**). We therefore stop
at an interpretable shared choice model; a reward function is **not identifiable** here (a multi-agent,
non-stationary, partially observed, measurement-degraded system yields observationally equivalent
rewards), so no reward or utility is claimed.

## Finding 3 — Departures mostly end in the open; destinations are the minority outcome

Rebuilding the destination analysis so a "destination" counts **only after the animal reaches sustained
stable residence** overturns the site-to-site picture the older method implied. Of departures from a
settled shelter, **≈60% end with the animal simply stopping in the open** (open-field termination), only
**≈19% relocate to another named site**, and ≈13% return to the same site — robust across the
settlement-threshold grid (n = 295 departures). Where a rat *does* relocate, the origin predicts the
destination (origin-conditioned held-out **Δbits 0.63** over a global-hub baseline), with house-to-house
switching dominant — but on only **55 relocation events**, so this is exploratory. No stable individual
house preference was detectable (0/2 animals testable).

## Candidate interpretation to watch: distance-dependent social spacing

Finding 1(ii) is the freshest and, if it holds, the most biologically interesting: it is consistent with
**active maintenance of a characteristic inter-individual distance** rather than simple aggregation. It is
Candidate for concrete reasons — it is coarse (net proximity change over a bout, ≥1 m, no orientation),
group-level, and we **cannot yet separate active steering from passive co-location dynamics** in shared
space. It did survive the key statistical hazard for this design: the thousands of bout–partner pairs are
pseudoreplicated, so its significance rests on a **night-level sign test over the 8 nights**, not on the
inflated per-pair count.

## No longer supported

- **"Group crowding does not affect leaving."** That earlier verdict came from a jitter-contaminated
  decision unit; on the corrected (hysteresis-based) unit it reverses to the crowding-suppresses-leaving
  result in Finding 1.
- **"Rats travel purposefully between named sites."** Most departures end in the open; site-to-site
  relocation is the minority outcome.
- **Fine-movement structure** (heading, turn angles, sub-second pauses, "decision legs"): at this
  resolution these are not separable from position jitter, so no route or reorientation-decision claim is
  made.

## Unresolved (ranked by impact on the conclusion)

1. Is the spacing **active steering or passive co-location**? Needs orientation/contact from video.
2. Do these effects **survive beyond 8 nights** and with more animals? Everything here is one short pilot.
3. All spatial claims remain gated by the **unverified coordinate frame**.

## Next decision (ordered by expected value)

1. **Georeference survey** — it gates every spatial claim (route, direction, metric distance).
2. **Extend the same pipelines to the 11–13 nights already recorded** — the destination-choice and
   initiation-social results are underpowered, not absent.
3. **Bring the shelter/interior cameras** to the spacing, contact, and true-sleep questions WISER cannot
   resolve.

## Technical references

Change logs: [module 3 initiation](../../../../change_log/2026-07-11-locomotor-bout-initiation.md) ·
[module 5 leaving](../../../../change_log/2026-07-10-decision-unit-hysteretic-social.md) +
[temporal](../../../../change_log/2026-07-11-temporal-policy.md) ·
[module 6 destination/settlement](../../../../change_log/2026-07-11-destination-settlement-rebuild.md) ·
[module 7 approach/avoid](../../../../change_log/2026-07-12-approach-avoid.md) ·
[DBV resolution limit](../../../../change_log/2026-07-11-dbv-crosscheck-locomotor.md). Index:
[`ANALYSIS_STATUS.md`](../../../../wiser/ANALYSIS_STATUS.md). Full tables/reports live beside this file and in
`outputs/locomotor_initiation_*`, `outputs/destination_settlement_*`, `outputs/approach_avoid_*`.

---

## Quantitative appendix — how each finding was quantified

Primary loss throughout: **held-out cross-entropy in bits/decision**, leave-one-night-out (whole nights
= the ~8 outer blocks). `Δbits = H_baseline − H_model` (>0 = better); `skill = 1 − H_model/H_baseline`.

**F1(i) — crowding suppresses leaving.** *Quantity:* social increment on the per-epoch leaving hazard
(bits/decision; range ~[−0.05, 0.05]). *Formula:* $\Delta\text{bits}=H(\text{layout+dwell+weather})-
H(\text{+jitter-safe group-social})$, social = {n within 1 m, mean-others-distance}. *Value:* ≈**+0.012**
(~4% skill), +on 8/8 nights, across 8 grid configs. *Null/rule:* within-night circular time-shift **z
11–32** and day-shuffle **z ~30** (both ≫ 2), jitter-safe features only ⇒ real-time group effect, not
shared arousal or sub-floor artifact. *Sensitivity:* robust across buffer×exit×epoch grid; `--fast` perms
(rerun full for publication z). *Inference:* Δbits > 0 + survives both nulls ⇒ crowding is associated with
staying (group, not dyad).

**F1(ii) — distance-dependent social spacing.** *Quantity:* per-night geometry-adjusted effect
`e_dir` and real-time social increment `e_day` of toward-ness (dimensionless, [−1,1]). *Formula:*
$\text{toward}=(d_0-\lVert p_{\text{end}}-p_{\text{partner,0}}\rVert)/\lVert\Delta\rVert$;
$e_{\text{dir}}(n)=\overline{\text{toward}}(n)-\mu_{\text{dir}}(n)$ (direction-randomized geometry null);
$e_{\text{day}}(n)=\overline{\text{toward}}_{\text{valid}}(n)-\mu_{\text{day}}(n)$ (same partner, same
hour, different night = layout). *Value (n=3,936 pairs, 8 nights):* e_day far (>3.8 m) **+0.117, 8/8
nights**; near (1–3.8 m) **−0.11 to −0.24, 0/8 nights positive**; e_dir +0.18 to +0.33 in every bin.
*Null/rule:* **night-level two-sided binomial sign test p ≤ 0.016** (NOT the pseudoreplicated per-pair z).
*Sensitivity:* consistent across all three distance bins and per night. *Inference:* e_day sign flips with
distance and is night-consistent ⇒ preferred-spacing tendency (approach far / avoid near), beyond layout.

**F1(iii) — social does not drive initiation.** *Quantity:* social increment on the bout-**initiation**
hazard. *Value:* Δbits ≈ **+0.0002** (survives nulls at z~4 but magnitude ≪ threshold). *Rule:* GO
requires Δbits > 0.003 ⇒ **NO-GO on magnitude** (detectable but negligible). *Inference:* social predicts
leaving, not initiation — a process-specific asymmetry.

**F2 — shared, time-invariant leaving rule; individual negligible.** *Values:* environment+dwell skill
**0.13–0.26**; hour-varying held-out **Δbits −0.0004** (hour-label null z 0.73); night-slope variance **z
0.51**; personalization **≈0.001 bits** (cond-perm z 2–9, magnitude negligible). *Rules:* held-out gain
≤0 or ≪0.003 bits ⇒ no added structure; ~8 blocks under-power a <0.003-bit effect ⇒ NO-GO = upper bound,
not exact zero. *Inference:* one shared rule, constant in time, no individual policy; reward not
identifiable (preconditions ≠ identification).

**F3 — destinations are the minority; origin conditions destination.** *Quantity:* transition-type mix
over departures from sustained settlements; origin-conditioned choice bits. *Values (n=295 departures):*
open-field termination **173 (0.59)**, relocation **55 (0.19)**, same-site return 37 (0.13), censored 17,
pass-through 13; robust 0.59–0.63 across the settlement-threshold grid. Origin-conditioned held-out
**Δbits 0.63** over the global-hub base rate (n=55 relocations; baseline-independent). *Rule:* relocation
counts only after sustained stable residence (representation validated: relocation-fraction range across
the duration threshold 0.065 ≤ 0.10). *Sensitivity:* the transition mix is stable across the grid; the
choice fit is thin (n=55) and the uniform-chance comparison is baseline-sensitive. *Inference:* most
departures terminate in the open; where relocation occurs, origin predicts destination, exploratory.

*All values are code-verified (offline selftests PASS) — code verification is not biological validation.
Frame UNVERIFIED; rest/onset are coarse proxies; single 8-night pilot.*
